"""
断点续爬模块。

提供爬取进度的持久化和恢复功能，支持多线程并发安全。

本模块实现了一个线程安全的断点管理器，核心特性：
- 使用 threading.Lock 保护所有状态读写操作
- 使用原子写入（先写临时文件再重命名）避免文件损坏
- 分别记录 games 和 reviews 的完成/失败状态，互不干扰
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal, Optional

from src.config import Config, get_config

# 类型别名：任务类型
TaskType = Literal["game", "review"]


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
        path: Optional[str | Path] = None,
        config: Optional[Config] = None,
    ):
        """初始化断点管理器。

        Args:
            path: 可选的断点文件路径。如果未指定，将从配置中读取默认路径。
            config: 可选的配置对象。如果未指定，将使用全局配置。
        """
        self.config = config or get_config()
        self._lock = threading.Lock()

        if path:
            self.path = Path(path)
        else:
            self.path = (
                Path(self.config.output.data_dir) / self.config.output.checkpoint_file
            )

        self.state = self._load()

    def _get_default_state(self) -> dict:
        """获取默认的空状态结构。

        Returns:
            dict: 包含 games 和 reviews 分离状态的字典。
        """
        return {
            # Games 状态
            "completed_pages": [],
            "completed_appids": [],
            "failed_appids": [],
            # Reviews 状态（独立）
            "completed_review_appids": [],
            "failed_review_appids": [],
        }

    def _load(self) -> dict:
        """从文件加载断点状态。

        如果文件不存在或解析失败，返回空的初始状态。
        自动迁移旧版本的状态结构（添加 reviews 相关键）。

        Returns:
            dict: 断点状态数据。
        """
        default = self._get_default_state()

        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # 合并：保留已有数据，补充缺失的键
                    for key in default:
                        if key not in loaded:
                            loaded[key] = default[key]
                    return loaded
            except (json.JSONDecodeError, IOError):
                pass

        return default

    def _save_atomic(self) -> None:
        """原子保存断点状态到文件。

        使用先写临时文件再重命名的方式，确保写入过程中断电或崩溃不会损坏原文件。
        此方法应在持有 _lock 的情况下调用。

        Raises:
            OSError: 文件系统操作失败时抛出。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

        os.replace(tmp_path, self.path)

    def save(self) -> None:
        """保存断点状态到文件（线程安全）。"""
        with self._lock:
            self._save_atomic()

    # ========== 状态键映射 ==========

    def _get_keys(self, task_type: TaskType) -> tuple[str, str]:
        """根据任务类型获取对应的状态键名。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            tuple[str, str]: (completed_key, failed_key) 元组。
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
        """标记页面为已完成并立即保存（线程安全）。

        Args:
            page: 页码（从 1 开始）。
        """
        with self._lock:
            if page not in self.state["completed_pages"]:
                self.state["completed_pages"].append(page)
                self._save_atomic()

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
        """标记 app_id 为已完成并立即保存（线程安全）。

        成功时会自动从对应的失败列表中移除（如果存在）。

        Args:
            app_id: Steam 游戏 ID。
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            if app_id not in self.state[completed_key]:
                self.state[completed_key].append(app_id)
                if app_id in self.state[failed_key]:
                    self.state[failed_key].remove(app_id)
                self._save_atomic()

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
                    self.state[completed_key].append(app_id)
                    changed = True
                if app_id in self.state[failed_key]:
                    self.state[failed_key].remove(app_id)
                    changed = True

            if changed:
                self._save_atomic()

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
        """标记 app_id 为失败并立即保存（线程安全）。

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
                self.state[failed_key].append(app_id)
                self._save_atomic()

    def get_failed_appids(self, task_type: TaskType = "game") -> list[int]:
        """获取所有失败的 app_id 列表（线程安全）。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            list[int]: 失败的 app_id 列表副本。
        """
        _, failed_key = self._get_keys(task_type)
        with self._lock:
            return self.state[failed_key].copy()

    def get_completed_appids(self, task_type: TaskType = "game") -> list[int]:
        """获取所有已完成的 app_id 列表（线程安全）。

        Args:
            task_type: 任务类型，"game" 或 "review"。

        Returns:
            list[int]: 已完成的 app_id 列表副本。
        """
        completed_key, _ = self._get_keys(task_type)
        with self._lock:
            return self.state[completed_key].copy()

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

        Args:
            task_type: 任务类型，"game" 或 "review"。
        """
        completed_key, failed_key = self._get_keys(task_type)
        with self._lock:
            self.state[completed_key] = []
            self.state[failed_key] = []
            if task_type == "game":
                self.state["completed_pages"] = []
            self._save_atomic()

