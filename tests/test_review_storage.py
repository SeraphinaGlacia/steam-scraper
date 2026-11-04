import sqlite3
from datetime import date

import pytest

from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo, ReviewSnapshot


def test_legacy_reviews_migrate_without_inventing_daily_granularity(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER, date TEXT, recommendations_up INTEGER,
                recommendations_down INTEGER, UNIQUE(app_id, date))"""
        )
        connection.executemany(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?)",
            [(7, 10, "2026-10-01", 100, 20), (8, 20, "2026-09-01", 200, 30)],
        )
    manager = DatabaseManager(path)
    try:
        assert manager.conn.execute(
            "SELECT id, app_id, recommendations_up, granularity FROM reviews ORDER BY id"
        ).fetchall() == [(7, 10, 100, "unknown"), (8, 20, 200, "unknown")]
        manager.save_reviews(
            10,
            [
                ReviewSnapshot(10, date(2026, 10, 1), 120, 25, "month"),
                ReviewSnapshot(10, date(2026, 10, 1), 4, 1, "day"),
            ],
        )
        assert manager.conn.execute(
            "SELECT granularity, recommendations_up FROM reviews "
            "WHERE app_id = 10 ORDER BY granularity"
        ).fetchall() == [("day", 4), ("month", 120)]
        assert manager.conn.execute(
            "SELECT granularity FROM reviews WHERE app_id = 20"
        ).fetchone() == ("unknown",)
    finally:
        manager.close()
    reopened = DatabaseManager(path)
    try:
        assert reopened.conn.execute("SELECT COUNT(*) FROM reviews").fetchone() == (3,)
    finally:
        reopened.close()


def test_snapshot_refresh_removes_stale_buckets_and_empty_history(database):
    database.save_reviews(
        10,
        [
            ReviewSnapshot(10, date(2026, 10, 1), 10, 1, "week"),
            ReviewSnapshot(10, date(2026, 10, 8), 20, 2, "week"),
        ],
    )
    database.save_reviews(20, [ReviewSnapshot(20, date(2026, 10, 1), 1, 0)])
    database.save_reviews(10, [ReviewSnapshot(10, date(2026, 10, 1), 30, 3, "month")])
    assert database.conn.execute(
        "SELECT date, recommendations_up, granularity FROM reviews WHERE app_id = 10"
    ).fetchall() == [("2026-10-01", 30, "month")]
    database.save_reviews(10, [])
    assert database.conn.execute("SELECT app_id FROM reviews").fetchall() == [(20,)]


def test_failed_replacement_restores_old_snapshot(database):
    database.save_reviews(10, [ReviewSnapshot(10, date(2026, 10, 1), 10, 1)])
    database.conn.execute(
        """CREATE TRIGGER reject_review BEFORE INSERT ON reviews
        WHEN NEW.recommendations_up = 999
        BEGIN SELECT RAISE(FAIL, 'simulated write failure'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="simulated write failure"):
        database.save_reviews(
            10,
            [
                ReviewSnapshot(10, date(2026, 10, 2), 20, 2),
                ReviewSnapshot(10, date(2026, 10, 3), 999, 3),
            ],
        )
    assert database.conn.execute(
        "SELECT date, recommendations_up FROM reviews"
    ).fetchall() == [("2026-10-01", 10)]


def test_deferred_replacement_is_not_visible_until_batch_commit(database):
    database.save_reviews(10, [ReviewSnapshot(10, date(2026, 10, 1), 10, 1)])
    with sqlite3.connect(database.db_path) as observer:
        database.save_reviews(
            10, [ReviewSnapshot(10, date(2026, 10, 1), 20, 2)], commit=False
        )
        assert observer.execute(
            "SELECT recommendations_up FROM reviews"
        ).fetchone() == (10,)
        database.commit()
        assert observer.execute(
            "SELECT recommendations_up FROM reviews"
        ).fetchone() == (20,)


def test_failed_commit_cannot_leak_into_a_later_successful_save(database):
    database.save_reviews(10, [ReviewSnapshot(10, date(2026, 10, 1), 10, 1)])
    rejected = False

    def reject_commit(action, argument, *_):
        nonlocal rejected
        if (
            action == sqlite3.SQLITE_TRANSACTION
            and argument == "COMMIT"
            and not rejected
        ):
            rejected = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    database.conn.set_authorizer(reject_commit)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        database.save_reviews(10, [ReviewSnapshot(10, date(2026, 10, 1), 99, 1)])
    database.save_reviews(20, [ReviewSnapshot(20, date(2026, 10, 1), 2, 0)])
    with sqlite3.connect(database.db_path) as observer:
        assert observer.execute(
            "SELECT app_id, recommendations_up FROM reviews ORDER BY app_id"
        ).fetchall() == [(10, 10), (20, 2)]


def test_review_export_preserves_granularity(database, tmp_path):
    import csv

    from openpyxl import load_workbook

    database.save_game(GameInfo(10, "Example"))
    database.save_reviews(
        10,
        [
            ReviewSnapshot(10, date(2026, 10, 1), 100, 20, "month"),
            ReviewSnapshot(10, date(2026, 10, 1), 5, 1, "day"),
        ],
    )
    database.export_to_csv(tmp_path)
    with (tmp_path / "steam_reviews.csv").open(encoding="utf-8-sig") as file:
        assert {row["granularity"] for row in csv.DictReader(file)} == {"day", "month"}
    workbook_path = tmp_path / "reviews.xlsx"
    database.export_to_excel(workbook_path)
    workbook = load_workbook(workbook_path, read_only=True)
    try:
        rows = list(workbook["Reviews"].values)
        column = rows[0].index("granularity")
        assert {row[column] for row in rows[1:]} == {"day", "month"}
    finally:
        workbook.close()
