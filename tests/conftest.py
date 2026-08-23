from collections.abc import Iterator
from pathlib import Path

import pytest

from steam_scraper.config import Config, HttpConfig, OutputConfig, ScraperConfig
from steam_scraper.database import DatabaseManager


@pytest.fixture
def app_config(tmp_path: Path) -> Config:
    return Config(
        http=HttpConfig(min_delay=0, max_delay=0),
        scraper=ScraperConfig(max_workers=2),
        output=OutputConfig(
            data_dir=str(tmp_path),
            database_file="steam_data.db",
            checkpoint_file="checkpoint.json",
            failure_log_file="failures.json",
        ),
    )


@pytest.fixture
def database(tmp_path: Path) -> Iterator[DatabaseManager]:
    manager = DatabaseManager(tmp_path / "steam_data.db")
    try:
        yield manager
    finally:
        manager.close()
