import json
from pathlib import Path

import pytest

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


def test_failed_log_write_preserves_previous_failures(
    tmp_path: Path, monkeypatch
) -> None:
    manager = _manager(tmp_path)
    manager.log_failure("game", 10, "original failure")
    previous_content = manager.path.read_bytes()

    def interrupted_dump(value, file, **kwargs):
        file.write("[\n")
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", interrupted_dump)

    with pytest.raises(OSError, match="disk full"):
        manager.log_failure("review", 20, "new failure")

    assert manager.path.read_bytes() == previous_content
    assert len(manager.get_failures()) == 1
    assert list(tmp_path.glob("*.tmp")) == []


def test_legacy_string_ids_are_normalized_and_removed(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.path.write_text(
        json.dumps(
            [
                {"type": "game", "id": "10", "reason": "original failure"},
                {"type": "game", "id": 10, "reason": "latest failure"},
            ]
        ),
        encoding="utf-8",
    )

    assert manager.get_failures() == [
        {"type": "game", "id": 10, "reason": "latest failure"}
    ]
    manager.remove_failure("game", 10)
    assert manager.get_failures() == []


@pytest.mark.parametrize("invalid_id", [True, False, "invalid", "", 0, -10, 1.5])
def test_unretryable_failure_ids_are_ignored(tmp_path: Path, invalid_id) -> None:
    manager = _manager(tmp_path)
    manager.path.write_text(
        json.dumps([{"type": "game", "id": invalid_id, "reason": "failed"}]),
        encoding="utf-8",
    )

    assert manager.get_failures() == []


def test_numeric_string_failure_ids_are_deduplicated(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.log_failure("game", "10", "original")
    manager.log_failure("game", 10, "latest")

    assert len(manager.get_failures()) == 1
    assert manager.get_failures()[0]["reason"] == "latest"
    manager.remove_failure("game", "10")
    assert manager.get_failures() == []
