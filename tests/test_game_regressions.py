import asyncio
import threading
from unittest.mock import AsyncMock

import httpx
import pytest

from steam_scraper.models import GameInfo
from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager


@pytest.mark.asyncio
async def test_search_preserves_region_and_language(app_config):
    app_config.scraper.language = "schinese"
    app_config.scraper.currency = "cn"
    scraper = GameScraper(config=app_config)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            text='<div class="search_pagination_left">'
            'Showing 1 - 25 of 69,792</div><a data-ds-appid="10"></a>',
        )

    scraper.client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await scraper.get_total_pages() == 2792
        assert await scraper.scrape_page_games(1) == [10]
        assert requests[0].url.params["cc"] == "cn"
        assert requests[0].url.params["l"] == "english"
        assert requests[1].url.params["cc"] == "cn"
        assert requests[1].url.params["l"] == "schinese"
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.asyncio
async def test_interrupted_game_page_is_rescanned_on_resume(app_config, monkeypatch):
    stop_event = threading.Event()
    checkpoint = Checkpoint(config=app_config, save_interval=0)
    scraper = GameScraper(
        config=app_config, checkpoint=checkpoint, stop_event=stop_event
    )
    app_ids = list(range(10, 20))

    async def stop_during_details(app_id):
        stop_event.set()
        return GameInfo(app_id=app_id, name=f"Game {app_id}")

    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(scraper, "scrape_page_games", AsyncMock(return_value=app_ids))
    monkeypatch.setattr(scraper, "get_game_details", stop_during_details)
    try:
        await asyncio.wait_for(scraper.run(), timeout=5)
        assert len(scraper.get_app_ids()) < len(app_ids)
        assert not checkpoint.is_page_completed(1)
    finally:
        scraper.db.close()

    resumed_checkpoint = Checkpoint(config=app_config)
    resumed = GameScraper(config=app_config, checkpoint=resumed_checkpoint)

    async def details(app_id):
        return GameInfo(app_id=app_id, name=f"Game {app_id}")

    monkeypatch.setattr(resumed, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(resumed, "scrape_page_games", AsyncMock(return_value=app_ids))
    monkeypatch.setattr(resumed, "get_game_details", details)
    try:
        await asyncio.wait_for(resumed.run(), timeout=5)
        assert set(resumed.get_app_ids()) == set(app_ids)
        assert resumed_checkpoint.is_page_completed(1)
    finally:
        resumed.db.close()


@pytest.mark.asyncio
async def test_producer_error_closes_client_and_workers(app_config, monkeypatch):
    scraper = GameScraper(config=app_config)
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(
        scraper, "scrape_page_games", AsyncMock(side_effect=RuntimeError("page error"))
    )
    close_client = AsyncMock()
    monkeypatch.setattr(scraper.client, "close", close_client)
    existing_tasks = asyncio.all_tasks()
    try:
        with pytest.raises(RuntimeError, match="page error"):
            await asyncio.wait_for(scraper.run(), timeout=5)
        close_client.assert_awaited_once()
        assert asyncio.all_tasks() == existing_tasks
    finally:
        scraper.db.close()


@pytest.mark.asyncio
async def test_write_failure_does_not_complete_game_page(app_config, monkeypatch):
    checkpoint = Checkpoint(config=app_config, save_interval=0)
    scraper = GameScraper(config=app_config, checkpoint=checkpoint)
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(scraper, "scrape_page_games", AsyncMock(return_value=[10]))
    monkeypatch.setattr(
        scraper,
        "get_game_details",
        AsyncMock(return_value=GameInfo(app_id=10, name="Game 10")),
    )

    def fail_to_write(games, commit=True):
        raise OSError("disk full")

    monkeypatch.setattr(scraper.db, "save_games_batch", fail_to_write)
    try:
        with pytest.raises(OSError, match="disk full"):
            await asyncio.wait_for(scraper.run(), timeout=5)
        assert not checkpoint.is_page_completed(1)
        assert not checkpoint.is_appid_completed(10)
        assert scraper.get_app_ids() == []
    finally:
        scraper.db.close()


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.asyncio
async def test_committed_game_clears_old_failure(app_config, monkeypatch, batch):
    failure_manager = FailureManager(config=app_config)
    failure_manager.log_failure("game", 10, "previous request failed")
    scraper = GameScraper(config=app_config, failure_manager=failure_manager)
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(scraper, "scrape_page_games", AsyncMock(return_value=[10]))
    monkeypatch.setattr(
        scraper,
        "get_game_details",
        AsyncMock(return_value=GameInfo(app_id=10, name="Game 10")),
    )
    try:
        if batch:
            await scraper.run()
        else:
            await scraper.process_game(10)
        assert scraper.get_app_ids() == [10]
        assert failure_manager.get_failures() == []
    finally:
        scraper.db.close()


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.asyncio
async def test_cancellation_waits_for_database_writer(app_config, monkeypatch, batch):
    scraper = GameScraper(config=app_config)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    save_method = "save_games_batch" if batch else "save_game"
    save_games = getattr(scraper.db, save_method)

    def blocked_save(games, commit=True):
        entered.set()
        assert release.wait(timeout=5)
        save_games(games, commit=commit)
        finished.set()

    monkeypatch.setattr(scraper.db, save_method, blocked_save)
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=1))
    monkeypatch.setattr(scraper, "scrape_page_games", AsyncMock(return_value=[10]))
    monkeypatch.setattr(
        scraper,
        "get_game_details",
        AsyncMock(return_value=GameInfo(app_id=10, name="Game 10")),
    )
    run_task = asyncio.create_task(scraper.run() if batch else scraper.process_game(10))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        run_task.cancel()
        await asyncio.sleep(0)
        assert not run_task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(run_task, timeout=5)
        assert finished.is_set()
        assert scraper.get_app_ids() == [10]
    finally:
        release.set()
        await asyncio.gather(run_task, return_exceptions=True)
        scraper.db.close()
