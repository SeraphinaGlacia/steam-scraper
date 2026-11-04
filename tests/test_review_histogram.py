from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from steam_scraper.models import ReviewSnapshot
from steam_scraper.scrapers.review_scraper import ReviewScraper, read_app_ids
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager


@pytest.fixture
def scraper(app_config):
    instance = ReviewScraper(
        config=app_config,
        checkpoint=Checkpoint(config=app_config, save_interval=0),
        failure_manager=FailureManager(app_config),
    )
    instance.client = AsyncMock()
    yield instance
    instance.db.close()


def bucket(day, positive=10, negative=2):
    timestamp = int(
        datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()
    )
    return {
        "date": timestamp,
        "recommendations_up": positive,
        "recommendations_down": negative,
    }


@pytest.mark.asyncio
async def test_monthly_rollups_and_recent_daily_counts_remain_distinct(scraper):
    scraper.client.get_json.return_value = {
        "success": 1,
        "results": {
            "rollup_type": "month",
            "rollups": [bucket("2026-10-01", 15742, 7011)],
            "recent": [
                bucket("2026-10-01", 458, 221),
                bucket("2026-11-04", 314, 142),
            ],
        },
    }

    reviews, skipped = await scraper.scrape_reviews(570)

    assert not skipped
    assert reviews == [
        ReviewSnapshot(570, date(2026, 10, 1), 15742, 7011, "month"),
        ReviewSnapshot(570, date(2026, 10, 1), 458, 221, "day"),
        ReviewSnapshot(570, date(2026, 11, 4), 314, 142, "day"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("rollup_type", ["week", "day", None])
async def test_rollup_granularity_is_preserved_or_explicitly_unknown(
    scraper, rollup_type
):
    results = {"rollups": [bucket("2026-10-01")]}
    if rollup_type is not None:
        results["rollup_type"] = rollup_type
    scraper.client.get_json.return_value = {"success": 1, "results": results}

    reviews, _ = await scraper.scrape_reviews(570)

    assert reviews[0].granularity == (rollup_type or "unknown")


@pytest.mark.asyncio
async def test_recent_daily_bucket_wins_when_rollups_have_same_date(scraper):
    scraper.client.get_json.return_value = {
        "success": 1,
        "results": {
            "rollup_type": "day",
            "rollups": [bucket("2026-10-01", 10), bucket("2026-10-01", 20)],
            "recent": [bucket("2026-10-01", 30)],
        },
    }

    reviews, _ = await scraper.scrape_reviews(570)

    assert reviews == [ReviewSnapshot(570, date(2026, 10, 1), 30, 2)]


@pytest.mark.asyncio
async def test_real_empty_history_is_saved_and_completed(scraper, monkeypatch):
    scraper.client.get_json.return_value = {
        "success": 1,
        "results": {
            "start_date": None,
            "end_date": None,
            "weeks": [],
            "rollup_type": "week",
            "recent": [],
        },
        "count_all_reviews": False,
        "expand_graph": False,
    }
    save_reviews = Mock(wraps=scraper.db.save_reviews)
    monkeypatch.setattr(scraper.db, "save_reviews", save_reviews)
    scraper.checkpoint.mark_appid_failed(1422450, "review")
    scraper.failure_manager.log_failure("review", 1422450, "old empty-response error")

    reviews, skipped = await scraper.scrape_reviews(1422450, force=True)

    assert reviews == []
    assert not skipped
    save_reviews.assert_called_once_with(1422450, [], commit=True)
    assert scraper.checkpoint.is_appid_completed(1422450, "review")
    assert not scraper.checkpoint.is_appid_failed(1422450, "review")
    assert scraper.failure_manager.get_failures() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "results",
    [
        {},
        {"weeks": [], "recent": []},
        {"start_date": None, "end_date": None, "weeks": [], "recent": None},
        {"start_date": 123, "end_date": 456, "weeks": [], "recent": []},
        {
            "start_date": None,
            "end_date": None,
            "weeks": [],
            "recent": [],
            "rollup_type": "year",
        },
        {"rollups": None},
        {"rollups": [], "recent": {}},
        {"rollups": [], "rollup_type": "year"},
        {"rollups": [bucket("2026-10-01", -1)]},
        {"rollups": [bucket("2026-10-01", True)]},
        {"rollups": [bucket("2026-10-01", "10")]},
    ],
)
async def test_malformed_history_is_not_silently_accepted(scraper, results):
    scraper.client.get_json.return_value = {"success": 1, "results": results}

    reviews, _ = await scraper.scrape_reviews(570)

    assert reviews is None
    assert scraper.checkpoint.is_appid_failed(570, "review")
    assert not scraper.checkpoint.is_appid_completed(570, "review")
    assert scraper.db.conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_read_app_ids_filters_invalid_values_and_accepts_utf8_bom(tmp_path):
    input_file = tmp_path / "appids.txt"
    input_file.write_text("570\n0\n-1\nbad\n\n730\n570\n", encoding="utf-8-sig")
    ui = Mock()

    assert read_app_ids(input_file, ui) == [570, 730, 570]
    assert ui.print_warning.call_count == 3


@pytest.mark.parametrize("is_directory", [False, True])
def test_read_app_ids_propagates_file_errors(tmp_path, is_directory):
    path = tmp_path if is_directory else tmp_path / "missing.txt"

    with pytest.raises(OSError):
        read_app_ids(path)


@pytest.mark.asyncio
async def test_invalid_ids_in_file_do_not_abort_valid_reviews(scraper, tmp_path):
    input_file = tmp_path / "appids.txt"
    input_file.write_text("-1\n0\ninvalid\n570\n", encoding="utf-8")
    scraper.client.get_json.return_value = {"success": 1, "results": {"rollups": []}}

    await scraper.scrape_from_file(input_file)

    scraper.client.get_json.assert_awaited_once_with(
        "https://store.steampowered.com/appreviewhistogram/570"
        "?l=schinese&review_score_preference=0",
        delay=True,
    )
    assert scraper.checkpoint.is_appid_completed(570, "review")
    assert scraper.failure_manager.get_failures() == []
