"""
配置管理模块。

提供统一的配置管理，支持从 YAML 文件加载配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class HttpConfig:
    """HTTP 请求配置。

    Attributes:
        timeout: 请求超时时间（秒）。
        max_retries: 最大重试次数。
        min_delay: 请求间隔最小值（秒）。
        max_delay: 请求间隔最大值（秒）。
        user_agent: 用户代理字符串。
    """

    timeout: int = 30
    max_retries: int = 3
    min_delay: float = 1.0
    max_delay: float = 3.0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )


@dataclass
class ScraperConfig:
    """爬虫配置。

    Attributes:
        language: Steam 商店语言。
        currency: Steam 商店货币代码。
        category: Steam 商店分类 ID（998 为游戏）。
    """

    language: str = "english"
    currency: str = "us"
    category: str = "998"
    max_workers: int = 10


@dataclass
class OutputConfig:
    """输出配置。

    Attributes:
        data_dir: 数据输出目录。
        checkpoint_file: 断点文件名。
    """

    data_dir: str = "./data"
    checkpoint_file: str = ".checkpoint.json"
    failure_log_file: str = "failures.json"
    db_path: str = "./data/steam_data.db"


@dataclass
class Config:
    """全局配置。

    Attributes:
        http: HTTP 请求配置。
        scraper: 爬虫配置。
        output: 输出配置。
    """

    http: HttpConfig = field(default_factory=HttpConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """从字典创建配置对象。

        Args:
            data: 配置字典。

        Returns:
            Config: 配置对象。
        """
        http_data = data.get("http", {})
        scraper_data = data.get("scraper", {})
        output_data = data.get("output", {})

        return cls(
            http=HttpConfig(**http_data),
            scraper=ScraperConfig(**scraper_data),
            output=OutputConfig(**output_data),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """从 YAML 文件加载配置。

        Args:
            path: YAML 配置文件路径。

        Returns:
            Config: 配置对象。
        """
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls.from_dict(data)

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> Config:
        """加载配置，优先使用指定路径，否则查找默认配置文件。

        Args:
            config_path: 可选的配置文件路径。

        Returns:
            Config: 配置对象。
        """
        if config_path:
            return cls.from_yaml(config_path)

        # 查找默认配置文件
        default_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path(__file__).parent.parent / "config.yaml",
        ]

        for path in default_paths:
            if path.exists():
                return cls.from_yaml(path)

        return cls()


# 全局默认配置实例
_default_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置实例。

    Returns:
        Config: 全局配置对象。
    """
    global _default_config
    if _default_config is None:
        _default_config = Config.load()
    return _default_config


def set_config(config: Config) -> None:
    """设置全局配置实例。

    Args:
        config: 配置对象。
    """
    global _default_config
    _default_config = config
