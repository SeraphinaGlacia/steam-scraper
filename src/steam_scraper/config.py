"""配置管理模块。

提供统一的配置管理，支持从 YAML 文件加载配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class HttpConfig:
    """HTTP 请求配置。

    Attributes:
        timeout: 请求超时时间（秒）。
        max_retries: 最大重试次数。
        min_delay: 请求间隔最小值（秒）。
        max_delay: 请求间隔最大值（秒）。
        max_connections: HTTP 连接池允许的最大连接数。
        max_keepalive_connections: HTTP 连接池保留的最大空闲连接数。
        user_agent: 用户代理字符串。
    """

    timeout: int = 30
    max_retries: int = 3
    min_delay: float = 0.5
    max_delay: float = 1.5
    # 连接池配置
    max_connections: int = 100
    max_keepalive_connections: int = 20
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
        max_workers: 同时执行的爬取任务数量。
    """

    language: str = "english"
    currency: str = "us"
    category: str = "998"
    max_workers: int = 20


@dataclass
class OutputConfig:
    """输出配置。

    Attributes:
        data_dir: 数据输出目录。
        database_file: SQLite 数据库文件名。
        checkpoint_file: 断点文件名。
        failure_log_file: 失败记录文件名。
    """

    data_dir: str = "./data"
    database_file: str = "steam_data.db"
    checkpoint_file: str = ".checkpoint.json"
    failure_log_file: str = "failures.json"

    @property
    def data_path(self) -> Path:
        """返回用户配置的数据目录。"""
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        """返回由数据目录和数据库文件名组成的完整路径。"""
        return self.data_path / self.database_file

    @property
    def checkpoint_path(self) -> Path:
        """返回由数据目录和断点文件名组成的完整路径。"""
        return self.data_path / self.checkpoint_file

    @property
    def failure_log_path(self) -> Path:
        """返回由数据目录和失败日志文件名组成的完整路径。"""
        return self.data_path / self.failure_log_file


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

        Raises:
            ValueError: YAML 顶层不是映射时抛出。
        """
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path, encoding="utf-8") as f:
            data: object = yaml.safe_load(f)

        if data is None:
            return cls()
        if not isinstance(data, dict):
            msg = f"配置文件顶层必须是映射: {path}"
            raise ValueError(msg)

        return cls.from_dict(data)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
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
            # 从源码检出目录运行时，配置文件仍位于仓库根目录。
            Path(__file__).resolve().parents[2] / "config.yaml",
        ]

        for path in default_paths:
            if path.exists():
                return cls.from_yaml(path)

        return cls()


# 全局默认配置实例
_default_config: Config | None = None


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
