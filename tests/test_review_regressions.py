import asyncio
import sqlite3
import threading
from unittest.mock import AsyncMock

import pytest

from steam_scraper.scrapers.review_scraper import ReviewScraper
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager


@pytest.fixture
def review_scraper(app_config):
    scraper = ReviewScraper(
        config=app_config,
        checkpoint=Checkpoint(config=app_config, save_interval=0),
        failure_manager=FailureManager(app_config),
    )
    scraper.client = AsyncMock()
    yield scraper
    scraper.db.close()


def review_payload():
    return {
        "success": 1,
        "results": {
            "rollups": [
                {
                    "date": 1724544000,
                    "recommendations_up": 12,
                    "recommendations_down": 3,
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_empty_review_history_completes_and_clears_failure(review_scraper):
    scraper = review_scraper
    scraper.client.get_json.return_value = {"success": 1, "results": {"rollups": []}}
    scraper.checkpoint.mark_appid_failed(10, "review")
    scraper.failure_manager.log_failure("review", 10, "old timeout")

    reviews, skipped = await scraper.scrape_reviews(10, force=True)

    assert reviews == []
    assert not skipped
    assert scraper.checkpoint.is_appid_completed(10, "review")
    assert not scraper.checkpoint.is_appid_failed(10, "review")
    assert scraper.failure_manager.get_failures() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"success": 0}, {}, {"results": {}}])
async def test_invalid_review_response_is_recorded_as_failure(review_scraper, payload):
    scraper = review_scraper
    scraper.client.get_json.return_value = payload

    reviews, skipped = await scraper.scrape_reviews(10)

    assert reviews is None
    assert not skipped
    assert scraper.checkpoint.is_appid_failed(10, "review")
    assert not scraper.checkpoint.is_appid_completed(10, "review")
    assert scraper.failure_manager.get_failures()[0]["id"] == 10


@pytest.mark.asyncio
async def test_review_write_failure_never_becomes_batch_success(
    review_scraper, monkeypatch
):
    scraper = review_scraper
    scraper.client.get_json.return_value = review_payload()

    def fail_write(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(scraper.db, "save_reviews", fail_write)
    await scraper.scrape_from_list([10])

    assert scraper.checkpoint.is_appid_failed(10, "review")
    assert not scraper.checkpoint.is_appid_completed(10, "review")
    assert scraper.db.conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_partially_parsed_reviews_are_not_returned_as_success(review_scraper):
    scraper = review_scraper
    payload = review_payload()
    payload["results"]["rollups"].append({"date": 1724630400})
    scraper.client.get_json.return_value = payload

    reviews, _ = await scraper.scrape_reviews(10)

    assert reviews is None
    assert scraper.checkpoint.is_appid_failed(10, "review")


@pytest.mark.asyncio
async def test_batch_completes_empty_history_and_skips_it_on_resume(review_scraper):
    scraper = review_scraper
    scraper.client.get_json.return_value = {"success": 1, "results": {"rollups": []}}

    await scraper.scrape_from_list([10])
    await scraper.scrape_from_list([10])

    assert scraper.checkpoint.is_appid_completed(10, "review")
    scraper.client.get_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_commit_failure_is_visible_and_not_checkpointed(
    review_scraper, monkeypatch
):
    scraper = review_scraper
    scraper.client.get_json.return_value = review_payload()

    def fail_commit():
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(scraper.db, "commit", fail_commit)
    with pytest.raises(sqlite3.OperationalError, match="disk full"):
        await asyncio.wait_for(scraper.scrape_from_list([10]), timeout=5)

    assert not scraper.checkpoint.is_appid_completed(10, "review")
    scraper.client.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
async def test_review_cancellation_waits_for_database_thread(
    review_scraper, monkeypatch, batch
):
    scraper = review_scraper
    scraper.client.get_json.return_value = review_payload()
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    method = "commit" if batch else "save_reviews"
    original = getattr(scraper.db, method)

    def blocked_write(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        original(*args, **kwargs)
        finished.set()

    monkeypatch.setattr(scraper.db, method, blocked_write)
    operation = scraper.scrape_from_list([10]) if batch else scraper.scrape_reviews(10)
    run_task = asyncio.create_task(operation)
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        run_task.cancel()
        await asyncio.sleep(0)
        assert not run_task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(run_task, timeout=5)
        assert finished.is_set()
        assert (
            scraper.db.conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
        )
    finally:
        release.set()
        await asyncio.gather(run_task, return_exceptions=True)
