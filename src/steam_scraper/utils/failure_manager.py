"""失败记录管理模块。

提供爬取失败记录的持久化、读取和清理功能。
与 Checkpoint 中的 failed_appids 不同，此模块存储更详细的失败信息，
包括失败原因、时间戳和上下文，便于问题诊断和分析。
"""

from __future__ import annotations

import json
import time
from typing import TypeGuard

from typing_extensions import NotRequired, TypedDict

from steam_scraper.config import Config, get_config


class FailureRecord(TypedDict):
    """可持久化的单条失败任务记录。"""

    type: str
    id: int | str
    reason: str
    timestamp: NotRequired[int]
    context: NotRequired[dict[str, object]]


def _is_failure_record(value: object) -> TypeGuard[FailureRecord]:
    if not isinstance(value, dict):
        return False

    item_type = value.get("type")
    item_id = value.get("id")
    reason = value.get("reason")
    timestamp = value.get("timestamp")
    context = value.get("context")
    return (
        isinstance(item_type, str)
        and isinstance(item_id, (int, str))
        and isinstance(reason, str)
        and (timestamp is None or isinstance(timestamp, int))
        and (context is None or isinstance(context, dict))
    )


class FailureManager:
    """失败记录管理器。

    用于记录爬取过程中失败的项目，并支持重试机制。
    数据以 JSON 格式存储。

    Attributes:
        config: 配置对象。
        path: 失败日志文件路径。
    """

    def __init__(self, config: Config | None = None) -> None:
        """初始化失败管理器。

        Args:
            config: 可选的配置对象。
        """
        self.config = config or get_config()
        self.path = self.config.output.failure_log_path

    def _load_failures(self) -> list[FailureRecord]:
        """从文件加载失败记录。

        Returns:
            结构有效的失败记录列表；损坏记录会被忽略。
        """
        if not self.path.exists():
            return []

        try:
            with open(self.path, encoding="utf-8") as f:
                loaded: object = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(loaded, list):
            return []
        return [item for item in loaded if _is_failure_record(item)]

    def _save_failures(self, failures: list[FailureRecord]) -> None:
        """保存失败记录到文件。

        Args:
            failures: 失败记录列表。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=2, ensure_ascii=False)

    def log_failure(
        self,
        item_type: str,
        item_id: int | str,
        reason: str,
        context: dict[str, object] | None = None,
    ) -> None:
        """记录一条失败信息。

        Args:
            item_type: 项目类型 ('game' 或 'review')。
            item_id: 项目 ID (如 app_id)。
            reason: 失败原因描述。
            context: 可选的上下文信息。
        """
        failures = self._load_failures()

        # 检查是否已存在相同的失败记录（避免重复）
        # 如果同一个项目多次失败，只保留最新的一条，避免日志膨胀
        for failure in failures:
            if failure["type"] == item_type and failure["id"] == item_id:
                # 更新已存在记录的原因和时间，保留最新的失败信息
                failure["reason"] = reason
                failure["timestamp"] = int(time.time())
                if context:
                    failure["context"] = context
                self._save_failures(failures)
                return

        # 添加新记录
        new_failure: FailureRecord = {
            "type": item_type,
            "id": item_id,
            "reason": reason,
            "timestamp": int(time.time()),
            "context": context or {},
        }
        failures.append(new_failure)
        self._save_failures(failures)
        print(f"已记录失败: [{item_type}] ID={item_id} - {reason}")

    def get_failures(self, item_type: str | None = None) -> list[FailureRecord]:
        """获取失败记录。

        Args:
            item_type: 可选的类型过滤 ('game' 或 'review')。

        Returns:
            全部失败记录，或指定类型的失败记录。
        """
        failures = self._load_failures()
        if item_type:
            return [f for f in failures if f["type"] == item_type]
        return failures

    def remove_failure(self, item_type: str, item_id: int | str) -> None:
        """移除一条失败记录。

        通常在重试成功后调用。

        Args:
            item_type: 项目类型。
            item_id: 项目 ID。
        """
        failures = self._load_failures()
        initial_len = len(failures)

        failures = [
            f for f in failures if not (f["type"] == item_type and f["id"] == item_id)
        ]

        if len(failures) < initial_len:
            self._save_failures(failures)

    def clear(self) -> None:
        """清除所有失败记录。"""
        if self.path.exists():
            self.path.unlink()
            print("失败记录已清空。")
