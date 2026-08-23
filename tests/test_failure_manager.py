import json
from pathlib import Path

from steam_scraper.config import Config, OutputConfig
from steam_scraper.utils.failure_manager import FailureManager


def _manager(tmp_path: Path) -> FailureManager:
    config = Config(output=OutputConfig(data_dir=str(tmp_path)))
    return FailureManager(config)


def test_log_failure_updates_existing_record(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.log_failure("game", 10, "first")
    manager.log_failure("game", 10, "latest", {"attempt": 2})

    failures = manager.get_failures("game")

    assert len(failures) == 1
    assert failures[0]["reason"] == "latest"
    assert failures[0]["context"] == {"attempt": 2}


def test_invalid_failure_records_are_ignored(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.path.write_text(
        json.dumps(
            [
                {"type": "review", "id": 20, "reason": "timeout"},
                {"type": "game", "reason": "missing id"},
                "invalid",
            ]
        ),
        encoding="utf-8",
    )

    assert manager.get_failures() == [{"type": "review", "id": 20, "reason": "timeout"}]


def test_remove_and_clear_failure_records(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.log_failure("game", 10, "failed")
    manager.remove_failure("game", 10)
    assert manager.get_failures() == []

    manager.log_failure("review", 20, "failed")
    manager.clear()
    assert not manager.path.exists()
