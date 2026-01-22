"""
数据模型模块。

定义游戏信息和评价数据的数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class GameInfo:
    """游戏基础信息。

    Attributes:
        app_id: Steam 游戏 ID。
        name: 游戏名称。
        release_date: 发行日期字符串。
        price: 价格（已格式化的字符串）。
        developers: 开发商列表。
        publishers: 发行商列表。
        genres: 游戏类型列表。
        description: 游戏简介。
    """

    app_id: int
    name: str
    release_date: str = ""
    price: str = "Free"
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        """转换为字典格式（兼容原有代码）。

        Returns:
            dict: 游戏信息字典。
        """
        return {
            "id": self.app_id,
            "name": self.name,
            "release_date": self.release_date,
            "price": self.price,
            "developers": ", ".join(self.developers),
            "publishers": ", ".join(self.publishers),
            "genres": ", ".join(self.genres),
            "description": self.description,
        }

    @classmethod
    def from_api_response(cls, app_id: int, data: dict) -> GameInfo:
        """从 Steam API 响应创建游戏信息对象。

        Args:
            app_id: Steam 游戏 ID。
            data: Steam API 返回的游戏数据。

        Returns:
            GameInfo: 游戏信息对象。
        """
        return cls(
            app_id=app_id,
            name=data.get("name", ""),
            release_date=data.get("release_date", {}).get("date", ""),
            price=data.get("price_overview", {}).get("final_formatted", "Free"),
            developers=data.get("developers", []),
            publishers=data.get("publishers", []),
            genres=[genre["description"] for genre in data.get("genres", [])],
            description=data.get("short_description", ""),
        )


@dataclass
class ReviewSnapshot:
    """评价快照数据。

    Attributes:
        app_id: Steam 游戏 ID。
        date: 评价日期。
        recommendations_up: 好评数量。
        recommendations_down: 差评数量。
    """

    app_id: int
    date: date
    recommendations_up: int
    recommendations_down: int

    def to_dict(self) -> dict:
        """转换为字典格式。

        Returns:
            dict: 评价快照字典。
        """
        return {
            "id": self.app_id,
            "date": self.date.strftime("%Y-%m-%d"),
            "recommendations_up": self.recommendations_up,
            "recommendations_down": self.recommendations_down,
        }
