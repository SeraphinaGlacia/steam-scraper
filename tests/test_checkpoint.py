import json
from pathlib import Path

import pytest

from steam_scraper.utils.checkpoint import Checkpoint


def test_checkpoint_persists_independent_game_and_review_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = Checkpoint(path=path, save_interval=0)
    checkpoint.mark_page_completed(2)
    checkpoint.mark_appid_failed(20, "game")
    checkpoint.mark_appid_completed(30, "review")
    checkpoint.save()

    restored = Checkpoint(path=path)

    assert restored.is_page_completed(2)
    assert restored.is_appid_failed(20, "game")
    assert restored.is_appid_completed(30, "review")
    assert not restored.is_appid_completed(30, "game")


def test_checkpoint_filters_invalid_values_and_sorts_output(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "page_checkpoint_version": 2,
                "completed_pages": [3, True, "bad", 1],
                "completed_appids": [9, 2],
            }
        ),
        encoding="utf-8",
    )

    checkpoint = Checkpoint(path=path)
    checkpoint.save()
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert set(checkpoint.get_completed_appids()) == {2, 9}
    assert saved["completed_pages"] == [1, 3]
    assert saved["completed_appids"] == [2, 9]


def test_clear_task_preserves_other_task_state(tmp_path: Path) -> None:
    checkpoint = Checkpoint(path=tmp_path / "checkpoint.json", save_interval=0)
    checkpoint.mark_appid_completed(1, "game")
    checkpoint.mark_appid_completed(2, "review")

    checkpoint.clear_task("game")

    assert not checkpoint.is_appid_completed(1, "game")
    assert checkpoint.is_appid_completed(2, "review")


def test_legacy_pages_and_reviews_are_rescanned_without_losing_game_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "completed_pages": [1, 2],
                "completed_appids": [10],
                "failed_appids": [20],
                "completed_review_appids": [10],
                "failed_review_appids": [30],
            }
        ),
        encoding="utf-8",
    )

    checkpoint = Checkpoint(path=path)
    assert not checkpoint.is_page_completed(1)
    assert not checkpoint.is_page_completed(2)
    assert checkpoint.is_appid_completed(10)
    assert checkpoint.is_appid_failed(20)
    assert not checkpoint.is_appid_completed(10, "review")
    assert not checkpoint.is_appid_failed(30, "review")

    checkpoint.mark_page_completed(1)
    checkpoint.save()
    restored = Checkpoint(path=path)
    assert restored.is_page_completed(1)
    assert not restored.is_page_completed(2)


def test_legacy_review_schema_preserves_current_game_pages(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "page_checkpoint_version": 2,
                "completed_pages": [1],
                "completed_appids": [10],
                "failed_appids": [20],
                "completed_review_appids": [10],
                "failed_review_appids": [30],
            }
        ),
        encoding="utf-8",
    )

    checkpoint = Checkpoint(path=path)

    assert checkpoint.is_page_completed(1)
    assert checkpoint.is_appid_completed(10, "game")
    assert checkpoint.is_appid_failed(20, "game")
    assert checkpoint.get_completed_appids("review") == []
    assert checkpoint.get_failed_appids("review") == []
    checkpoint.mark_appid_completed(10, "review")
    checkpoint.mark_appid_failed(30, "review")
    checkpoint.save()

    restored = Checkpoint(path=path)
    assert restored.is_appid_completed(10, "review")
    assert restored.is_appid_failed(30, "review")
    assert json.loads(path.read_text())["review_checkpoint_version"] == 1


@pytest.mark.parametrize(
    "operation", ["save", "automatic", "clear_game", "clear_review"]
)
@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_checkpoint_does_not_follow_preexisting_temporary_link(
    tmp_path, operation, link_kind
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    path = state_dir / "checkpoint.json"
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("must remain unchanged", encoding="utf-8")
    planted_link = path.with_suffix(".tmp")
    if link_kind == "symlink":
        planted_link.symlink_to(sentinel)
    else:
        planted_link.hardlink_to(sentinel)
    checkpoint = Checkpoint(path=path, save_interval=0)

    if operation == "save":
        checkpoint.save()
    elif operation == "automatic":
        checkpoint.mark_appid_completed(570, "game")
    else:
        checkpoint.clear_task("game" if operation == "clear_game" else "review")

    assert sentinel.read_text(encoding="utf-8") == "must remain unchanged"
    assert planted_link.samefile(sentinel)
    assert not path.is_symlink()
    assert json.loads(path.read_text(encoding="utf-8"))["page_checkpoint_version"] == 2
    assert set(state_dir.iterdir()) == {path, planted_link}
    if operation == "automatic":
        assert Checkpoint(path=path).is_appid_completed(570, "game")


@pytest.mark.parametrize("failure_stage", ["write", "replace"])
def test_checkpoint_failed_save_preserves_previous_state_and_cleans_own_temp(
    tmp_path, monkeypatch, failure_stage
):
    path = tmp_path / "checkpoint.json"
    checkpoint = Checkpoint(path=path, save_interval=float("inf"))
    checkpoint.mark_appid_completed(570, "game")
    checkpoint.save()
    original = path.read_bytes()
    last_save = checkpoint._last_save_time
    unrelated = path.with_suffix(".tmp")
    unrelated.write_text("not ours", encoding="utf-8")
    checkpoint.mark_appid_completed(730, "review")

    def interrupted_dump(value, file, **kwargs):
        file.write("{\n")
        raise OSError("disk full")

    def failed_replace(*args):
        raise OSError("replace failed")

    if failure_stage == "write":
        monkeypatch.setattr(
            "steam_scraper.utils.checkpoint.json.dump", interrupted_dump
        )
    else:
        monkeypatch.setattr("steam_scraper.utils.checkpoint.os.replace", failed_replace)

    with pytest.raises(OSError, match="disk full|replace failed"):
        checkpoint.save()

    assert path.read_bytes() == original
    assert unrelated.read_text(encoding="utf-8") == "not ours"
    assert set(tmp_path.iterdir()) == {path, unrelated}
    assert checkpoint._last_save_time == last_save
    assert not Checkpoint(path=path).is_appid_completed(730, "review")
