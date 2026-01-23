"""
失败记录管理模块。

提供爬取失败记录的持久化、读取和清理功能。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from src.config import Config, get_config


class FailureManager:
    """失败记录管理器。

    用于记录爬取过程中失败的项目，并支持重试机制。
    数据以 JSON 格式存储。

    Attributes:
        config: 配置对象。
        path: 失败日志文件路径。
    """

    def __init__(self, config: Optional[Config] = None):
        """初始化失败管理器。

        Args:
            config: 可选的配置对象。
        """
        self.config = config or get_config()
        self.path = (
            Path(self.config.output.data_dir) / self.config.output.failure_log_file
        )

    def _load_failures(self) -> list[dict[str, Any]]:
        """从文件加载失败记录。

        Returns:
            list[dict]: 失败记录列表。
        """
        if not self.path.exists():
            return []

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_failures(self, failures: list[dict[str, Any]]) -> None:
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
        context: Optional[dict] = None,
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
        for failure in failures:
            if failure["type"] == item_type and failure["id"] == item_id:
                # 更新原因和时间
                failure["reason"] = reason
                failure["timestamp"] = int(time.time())
                if context:
                    failure["context"] = context
                self._save_failures(failures)
                return

        # 添加新记录
        new_failure = {
            "type": item_type,
            "id": item_id,
            "reason": reason,
            "timestamp": int(time.time()),
            "context": context or {},
        }
        failures.append(new_failure)
        self._save_failures(failures)
        print(f"已记录失败: [{item_type}] ID={item_id} - {reason}")

    def get_failures(self, item_type: Optional[str] = None) -> list[dict[str, Any]]:
        """获取失败记录。

        Args:
            item_type: 可选的类型过滤 ('game' 或 'review')。

        Returns:
            list[dict]: 失败记录列表。
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
