"""数据模型模块。

定义游戏信息和评价数据的数据结构。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date


def _string_value(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


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

    @classmethod
    def from_api_response(cls, app_id: int, data: Mapping[str, object]) -> GameInfo:
        """从 Steam API 响应创建游戏信息对象。

        Args:
            app_id: Steam 游戏 ID。
            data: Steam API 返回的游戏数据。

        Returns:
            经过字段验证的游戏信息对象。
        """
        release_data = data.get("release_date")
        release_date = (
            _string_value(release_data.get("date"))
            if isinstance(release_data, Mapping)
            else ""
        )

        price_data = data.get("price_overview")
        price = (
            _string_value(price_data.get("final_formatted"), "Free")
            if isinstance(price_data, Mapping)
            else "Free"
        )

        genres: list[str] = []
        raw_genres = data.get("genres")
        if isinstance(raw_genres, list):
            for genre in raw_genres:
                if isinstance(genre, Mapping):
                    description = genre.get("description")
                    if isinstance(description, str):
                        genres.append(description)

        return cls(
            app_id=app_id,
            name=_string_value(data.get("name")),
            release_date=release_date,
            price=price,
            developers=_string_list(data.get("developers")),
            publishers=_string_list(data.get("publishers")),
            genres=genres,
            description=_string_value(data.get("short_description")),
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
