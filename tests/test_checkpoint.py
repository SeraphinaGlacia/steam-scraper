import json
from pathlib import Path

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
