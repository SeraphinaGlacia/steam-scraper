import json
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.utils.exceptions import IllegalCharacterError

from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo, ReviewSnapshot


def _sample_game() -> GameInfo:
    return GameInfo(
        app_id=10,
        name="逗号, 游戏",
        developers=["A, Studio", "B Studio"],
        publishers=["Publisher"],
        genres=["RPG", "Action"],
    )


def test_database_round_trip(database: DatabaseManager) -> None:
    game = _sample_game()
    database.save_game(game)
    database.save_reviews(
        game.app_id,
        [ReviewSnapshot(game.app_id, date(2026, 8, 23), 10, 2)],
    )

    row = database.conn.execute(
        "SELECT developers FROM games WHERE app_id = ?", (game.app_id,)
    ).fetchone()
    assert row is not None
    assert json.loads(row[0]) == ["A, Studio", "B Studio"]
    assert database.is_game_exists(game.app_id)
    assert database.get_all_app_ids() == [game.app_id]


def test_exports_create_readable_excel_and_csv(
    database: DatabaseManager, tmp_path: Path
) -> None:
    game = _sample_game()
    database.save_game(game)
    database.save_reviews(
        game.app_id,
        [ReviewSnapshot(game.app_id, date(2026, 8, 23), 10, 2)],
    )

    excel_file = tmp_path / "nested" / "steam_data.xlsx"
    csv_dir = tmp_path / "csv"
    database.export_to_excel(excel_file)
    database.export_to_csv(csv_dir)

    workbook = load_workbook(excel_file, read_only=True)
    assert workbook.sheetnames == ["Games", "Reviews"]
    workbook.close()
    games_csv = (csv_dir / "steam_games.csv").read_text(encoding="utf-8-sig")
    assert "A, Studio, B Studio" in games_csv
    assert (csv_dir / "steam_reviews.csv").is_file()


def test_excel_preserves_text_starting_with_equals(
    database: DatabaseManager, tmp_path: Path
) -> None:
    game = GameInfo(
        app_id=10,
        name="=1+1",
        developers=["=Studio"],
        description="=This is a description, not a formula",
    )
    database.save_game(game)
    database.save_reviews(10, [ReviewSnapshot(10, date(2026, 8, 23), 10, 2)])
    output = tmp_path / "steam_data.xlsx"

    database.export_to_excel(output)

    workbook = load_workbook(output, read_only=True, data_only=True)
    try:
        game_rows = list(workbook["Games"].values)
        exported_game = dict(zip(game_rows[0], game_rows[1], strict=True))
        assert exported_game["name"] == game.name
        assert exported_game["description"] == game.description
        assert exported_game["developers"] == "=Studio"
        review_rows = list(workbook["Reviews"].values)
        exported_review = dict(zip(review_rows[0], review_rows[1], strict=True))
        assert exported_review["game_name"] == game.name
        assert exported_review["recommendations_up"] == 10
    finally:
        workbook.close()


def test_failed_excel_export_preserves_previous_workbook(
    database: DatabaseManager, tmp_path: Path
) -> None:
    output = tmp_path / "steam_data.xlsx"
    database.save_game(_sample_game())
    database.export_to_excel(output)
    previous_content = output.read_bytes()
    database.save_game(GameInfo(app_id=20, name="Game", description="bad\x00text"))

    with pytest.raises(IllegalCharacterError):
        database.export_to_excel(output)

    assert output.read_bytes() == previous_content
    assert list(tmp_path.glob(".steam-export-*")) == []
