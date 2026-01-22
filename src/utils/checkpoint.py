"""
断点续爬模块。

提供爬取进度的持久化和恢复功能。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.config import Config, get_config


class Checkpoint:
    """断点续爬管理器。

    用于记录爬取进度，支持程序中断后从断点恢复。

    Attributes:
        path: 断点文件路径。
        state: 当前状态数据。
    """

    def __init__(
        self,
        path: Optional[str | Path] = None,
        config: Optional[Config] = None,
    ):
        """初始化断点管理器。

        Args:
            path: 可选的断点文件路径。
            config: 可选的配置对象。
        """
        self.config = config or get_config()

        if path:
            self.path = Path(path)
        else:
            self.path = (
                Path(self.config.output.data_dir) / self.config.output.checkpoint_file
            )

        self.state = self._load()

    def _load(self) -> dict:
        """从文件加载断点状态。

        Returns:
            dict: 断点状态数据。
        """
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "completed_pages": [],
            "completed_appids": [],
            "failed_appids": [],
        }

    def save(self) -> None:
        """保存断点状态到文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def is_page_completed(self, page: int) -> bool:
        """检查页面是否已完成爬取。

        Args:
            page: 页码。

        Returns:
            bool: 如果页面已完成则返回 True。
        """
        return page in self.state["completed_pages"]

    def mark_page_completed(self, page: int) -> None:
        """标记页面为已完成。

        Args:
            page: 页码。
        """
        if page not in self.state["completed_pages"]:
            self.state["completed_pages"].append(page)
            self.save()

    def is_appid_completed(self, app_id: int) -> bool:
        """检查 app_id 是否已完成爬取。

        Args:
            app_id: Steam 游戏 ID。

        Returns:
            bool: 如果已完成则返回 True。
        """
        return app_id in self.state["completed_appids"]

    def mark_appid_completed(self, app_id: int) -> None:
        """标记 app_id 为已完成。

        Args:
            app_id: Steam 游戏 ID。
        """
        if app_id not in self.state["completed_appids"]:
            self.state["completed_appids"].append(app_id)
            self.save()

    def mark_appid_failed(self, app_id: int) -> None:
        """标记 app_id 为失败。

        Args:
            app_id: Steam 游戏 ID。
        """
        if app_id not in self.state["failed_appids"]:
            self.state["failed_appids"].append(app_id)
            self.save()

    def get_failed_appids(self) -> list[int]:
        """获取所有失败的 app_id 列表。

        Returns:
            list[int]: 失败的 app_id 列表。
        """
        return self.state["failed_appids"].copy()

    def clear(self) -> None:
        """清除所有断点状态。"""
        self.state = {
            "completed_pages": [],
            "completed_appids": [],
            "failed_appids": [],
        }
        if self.path.exists():
            self.path.unlink()
