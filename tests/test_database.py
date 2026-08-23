import json
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

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
