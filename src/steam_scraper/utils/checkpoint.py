"""断点续爬模块。

提供爬取进度的持久化和恢复功能，支持多线程并发安全。

本模块实现了一个线程安全的断点管理器，核心特性：
- 使用 threading.Lock 保护所有状态读写操作
- 使用原子写入（先写临时文件再重命名）避免文件损坏
- 分别记录 games 和 reviews 的完成/失败状态，互不干扰
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal, TypedDict

from steam_scraper.config import Config, get_config

# 类型别名：任务类型
TaskType = Literal["game", "review"]
CompletedKey = Literal["completed_appids", "completed_review_appids"]
FailedKey = Literal["failed_appids", "failed_review_appids"]
_PAGE_CHECKPOINT_VERSION = 2
_REVIEW_CHECKPOINT_VERSION = 1


class CheckpointState(TypedDict):
    """内存中的断点状态；集合用于保证查询和去重效率。"""

    completed_pages: set[int]
    completed_appids: set[int]
    failed_appids: set[int]
    completed_review_appids: set[int]
    failed_review_appids: set[int]


def _load_int_set(data: dict[object, object], key: str) -> set[int]:
    value = data.get(key)
    if not isinstance(value, list):
        return set()
    return {
        item for item in value if isinstance(item, int) and not isinstance(item, bool)
    }


class Checkpoint:
    """线程安全的断点续爬管理器。

    用于记录爬取进度，支持程序中断后从断点恢复。所有公开方法均为线程安全。
    games 和 reviews 分别维护独立的状态，互不干扰。

    Attributes:
        path: 断点文件路径。
        state: 当前状态数据。
        _lock: 线程锁，用于保护状态数据的并发访问。

    Example:
        >>> checkpoint = Checkpoint()
        >>> checkpoint.mark_appid_completed(12345, "game")
        >>> checkpoint.is_appid_completed(12345, "game")
        True
        >>> checkpoint.is_appid_completed(12345, "review")  # 独立状态
        False
    """

    def __init__(
        self,
        path: str | Path | None = None,
        config: Config | None = None,
        save_interval: float = 5.0,
    ) -> None:
        """初始化断点管理器。

        Args:
            path: 可选的断点文件路径。如果未指定，将从配置中读取默认路径。
            config: 可选的配置对象。如果未指定，将使用全局配置。
            save_interval: 自动保存的时间间隔（秒）。默认 5 秒。
        """
        self.config = config or get_config()
        self._lock = threading.Lock()
        self.save_interval = save_interval
        self._last_save_time = 0.0

        if path:
            self.path = Path(path)
        else:
            self.path = self.config.output.checkpoint_path

        self.state = self._load()

    def _get_default_state(self) -> CheckpointState:
        """获取默认的空状态结构。

        Returns:
            games 与 reviews 相互独立的空状态。
        """
        return {
            # Games 状态
            "completed_pages": set(),
            "completed_appids": set(),
            "failed_appids": set(),
            # Reviews 状态（独立）
            "completed_review_appids": set(),
            "failed_review_appids": set(),
        }

    def _load(self) -> CheckpointState:
        """从文件加载断点状态。

        如果文件不存在或解析失败，返回空的初始状态。
        缺失或无效字段按空集合处理，避免局部损坏使整个断点失效。
        旧版在入队时就保存页面完成状态，迁移时重新扫描页面并保留 AppID 状态。
        旧评价断点没有记录统计粒度，迁移时重新采集评价，保留游戏状态。
        加载时将列表转换为集合以支持 O(1) 查找。

        Returns:
            已校验并补齐全部字段的断点状态。
        """
        default = self._get_default_state()

        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    loaded: object = json.load(f)
                if not isinstance(loaded, dict):
                    return default
                return CheckpointState(
                    completed_pages=(
                        _load_int_set(loaded, "completed_pages")
                        if loaded.get("page_checkpoint_version")
                        == _PAGE_CHECKPOINT_VERSION
                        else set()
                    ),
                    completed_appids=_load_int_set(loaded, "completed_appids"),
                    failed_appids=_load_int_set(loaded, "failed_appids"),
                    completed_review_appids=(
                        _load_int_set(loaded, "completed_review_appids")
                        if loaded.get("review_checkpoint_version")
                        == _REVIEW_CHECKPOINT_VERSION
                        else set()
                    ),
                    failed_review_appids=(
                        _load_int_set(loaded, "failed_review_appids")
                        if loaded.get("review_checkpoint_version")
                        == _REVIEW_CHECKPOINT_VERSION
                        else set()
                    ),
                )
            except (OSError, json.JSONDecodeError):
                pass

        return default

    def _save_to_disk(self) -> None:
        """原子保存断点状态到文件。

        独占创建同目录临时文件，避免跟随预先放置的软链接。
        写入完成后再替换原文件，失败时保留原断点并清理本次临时文件。
        保存时将集合转换为列表以支持 JSON 序列化。
        此方法应在持有 _lock 的情况下调用。

        Raises:
            OSError: 文件系统操作失败时抛出。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 转换为列表进行序列化（仅转换集合类型）
        serializable_state = {
            "page_checkpoint_version": _PAGE_CHECKPOINT_VERSION,
            "review_checkpoint_version": _REVIEW_CHECKPOINT_VERSION,
            "completed_pages": sorted(self.state["completed_pages"]),
            "completed_appids": sorted(self.state["completed_appids"]),
            "failed_appids": sorted(self.state["failed_appids"]),
            "completed_review_appids": sorted(self.state["completed_review_appids"]),
            "failed_review_appids": sorted(self.state["failed_review_appids"]),
        }

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(serializable_state, file, indent=2, ensure_ascii=False)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        self._last_save_time = time.time()

    def _request_save(self) -> None:
        """请求保存断点状态。

        如果距离上次保存的时间超过 save_interval，则执行保存。
        此方法应在持有 _lock 的情况下调用。
        """
        if time.time() - self._last_save_time >= self.save_interval:
            self._save_to_disk()

    def save(self) -> None:
        """保存断点状态到文件（线程安全）。

        强制立即保存，忽略 save_interval。
        """
        with self._lock:
            self._save_to_disk()

    # ========== 状态键映射 ==========

    def _get_keys(self, task_type: TaskType) -> tuple[CompletedKey, FailedKey]:
        """根据任务类型获取对应的状态键名。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            对应的完成状态键和失败状态键。
        """
        if task_type == "game":
            return "completed_appids", "failed_appids"
        else:
            return "completed_review_appids", "failed_review_appids"

    # ========== Pages（仅用于 games）==========

    def is_page_completed(self, page: int) -> bool:
        """检查页面是否已完成爬取（线程安全）。

        Args:
            page: 页码（从 1 开始）。

        Returns:
            bool: 如果页面已完成则返回 True。
        """
        with self._lock:
            return page in self.state["completed_pages"]

    def mark_page_completed(self, page: int) -> None:
        """标记页面为已完成并尝试保存（线程安全）。

        Args:
            page: 页码（从 1 开始）。
        """
        with self._lock:
            if page not in self.state["completed_pages"]:
                self.state["completed_pages"].add(page)
                self._request_save()

    # ========== AppID 状态（支持 game/review）==========

    def is_appid_completed(self, app_id: int, task_type: TaskType = "game") -> bool:
        """检查 app_id 是否已完成爬取（线程安全）。

        Args:
            app_id: Steam 游戏 ID。
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            bool: 如果已完成则返回 True。
        """
        completed_key, _ = self._get_keys(task_type)
        with self._lock:
            return app_id in self.state[completed_key]

    def mark_appid_completed(self, app_id: int, task_type: TaskType = "game") -> None:
        """标记 app_id 为已完成并尝试保存（线程安全）。

        成功时会自动从对应的失败列表中移除（如果存在）。

        Args:
            app_id: Steam 游戏 ID。
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            if app_id not in self.state[completed_key]:
                self.state[completed_key].add(app_id)
                self.state[failed_key].discard(app_id)
                self._request_save()

    def mark_appids_completed(
        self, app_ids: list[int], task_type: TaskType = "game"
    ) -> None:
        """批量标记多个 app_id 为已完成并立即保存（线程安全）。

        比循环调用 mark_appid_completed 更高效，因为只进行一次文件写入。

        Args:
            app_ids: Steam 游戏 ID 列表。
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            changed = False
            for app_id in app_ids:
                if app_id not in self.state[completed_key]:
                    self.state[completed_key].add(app_id)
                    changed = True
                if app_id in self.state[failed_key]:
                    self.state[failed_key].discard(app_id)
                    changed = True

            if changed:
                self._save_to_disk()

    def is_appid_failed(self, app_id: int, task_type: TaskType = "game") -> bool:
        """检查 app_id 是否已标记为失败（线程安全）。

        Args:
            app_id: Steam 游戏 ID。
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            bool: 如果已标记为失败则返回 True。
        """
        _, failed_key = self._get_keys(task_type)
        with self._lock:
            return app_id in self.state[failed_key]

    def mark_appid_failed(self, app_id: int, task_type: TaskType = "game") -> None:
        """标记 app_id 为失败并尝试保存（线程安全）。

        已完成的 AppID 不会被标记为失败。

        Args:
            app_id: Steam 游戏 ID。
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            if app_id in self.state[completed_key]:
                return
            if app_id not in self.state[failed_key]:
                self.state[failed_key].add(app_id)
                self._request_save()

    def get_failed_appids(self, task_type: TaskType = "game") -> list[int]:
        """获取所有失败的 app_id 列表（线程安全）。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            list[int]: 失败的 app_id 列表副本。
        """
        _, failed_key = self._get_keys(task_type)
        with self._lock:
            return list(self.state[failed_key])

    def get_completed_appids(self, task_type: TaskType = "game") -> list[int]:
        """获取所有已完成的 app_id 列表（线程安全）。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            list[int]: 已完成的 app_id 列表副本。
        """
        completed_key, _ = self._get_keys(task_type)
        with self._lock:
            return list(self.state[completed_key])

    def clear(self) -> None:
        """清除所有断点状态（线程安全）。

        此操作会重置所有状态（包括 games 和 reviews）并删除断点文件。
        """
        with self._lock:
            self.state = self._get_default_state()
            if self.path.exists():
                self.path.unlink()

    def clear_task(self, task_type: TaskType) -> None:
        """清除指定任务类型的断点状态（线程安全）。

        只清除 game 或 review 的状态，不影响其他类型。
        立即保存更改。

        Args:
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            self.state[completed_key] = set()
            self.state[failed_key] = set()
            if task_type == "game":
                self.state["completed_pages"] = set()
            self._save_to_disk()
