import asyncio
import threading
from unittest.mock import AsyncMock

import httpx
import pytest

from steam_scraper.models import GameInfo
from steam_scraper.scrapers.game_scraper import GameScraper, SteamSearchError
from steam_scraper.utils.checkpoint import Checkpoint


@pytest.mark.parametrize("method", ["get_total_pages", "scrape_page_games"])
@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.asyncio
async def test_search_failure_is_not_an_empty_success(app_config, method, status):
    app_config.http.max_retries = 0
    scraper = GameScraper(config=app_config)
    scraper.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="Service unavailable")
        )
    )
    try:
        with pytest.raises(SteamSearchError) as error:
            if method == "get_total_pages":
                await scraper.get_total_pages()
            else:
                await scraper.scrape_page_games(1)
        if status == 503:
            assert isinstance(error.value.__cause__, httpx.HTTPStatusError)
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.asyncio
async def test_failed_count_closes_client_before_exiting(app_config):
    app_config.http.max_retries = 0
    checkpoint = Checkpoint(config=app_config)
    scraper = GameScraper(config=app_config, checkpoint=checkpoint)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    scraper.client._client = client
    existing_tasks = asyncio.all_tasks()
    try:
        with pytest.raises(SteamSearchError):
            await scraper.run()
        assert client.is_closed
        assert asyncio.all_tasks() == existing_tasks
        assert not checkpoint.is_page_completed(1)
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.asyncio
async def test_large_result_count_is_not_capped(app_config):
    scraper = GameScraper(config=app_config)
    scraper.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text='<div class="search_pagination_left">'
                "showing 1 - 25 of 179926</div>",
            )
        )
    )
    try:
        assert await scraper.get_total_pages() == 7198
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.parametrize(
    "summary", ["0 results match your search.", "有 0 项结果符合您的搜索。"]
)
@pytest.mark.asyncio
async def test_explicit_empty_search_is_valid(app_config, summary):
    scraper = GameScraper(config=app_config)
    scraper.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=f'<div class="search_results_count">{summary}</div>'
                '<div id="search_result_container"><div class="search_rule"></div></div>',
            )
        )
    )
    try:
        assert await scraper.get_total_pages() == 0
        assert await scraper.scrape_page_games(1) == []
        assert await scraper.run() == []
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.parametrize("invalid_id", ["", "invalid", "0", "-1"])
@pytest.mark.asyncio
async def test_invalid_appid_does_not_return_partial_page(app_config, invalid_id):
    scraper = GameScraper(config=app_config)
    scraper.client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=f'<a data-ds-appid="10"></a><a data-ds-appid="{invalid_id}"></a>',
            )
        )
    )
    try:
        with pytest.raises(SteamSearchError, match="无效 AppID"):
            await scraper.scrape_page_games(1)
    finally:
        await scraper.client.close()
        scraper.db.close()


@pytest.mark.asyncio
async def test_failed_page_preserves_committed_results_for_resume(
    app_config, monkeypatch
):
    app_config.http.max_retries = 0
    checkpoint = Checkpoint(config=app_config, save_interval=0)
    scraper = GameScraper(config=app_config, checkpoint=checkpoint)
    persisted = asyncio.Event()
    loop = asyncio.get_running_loop()
    save_games = scraper.db.save_games_batch

    def save_and_notify(games, commit=True):
        save_games(games, commit=commit)
        loop.call_soon_threadsafe(persisted.set)

    async def respond(request):
        if request.url.params["page"] == "2":
            await asyncio.wait_for(persisted.wait(), timeout=5)
            return httpx.Response(503)
        return httpx.Response(200, text='<a data-ds-appid="10"></a>')

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    scraper.client._client = client
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=2))
    monkeypatch.setattr(
        scraper, "get_game_details", AsyncMock(return_value=GameInfo(10, "Game 10"))
    )
    monkeypatch.setattr(scraper.db, "save_games_batch", save_and_notify)
    existing_tasks = asyncio.all_tasks()
    try:
        with pytest.raises(SteamSearchError, match="第 2 页"):
            await asyncio.wait_for(scraper.run(), timeout=5)
        assert client.is_closed
        assert asyncio.all_tasks() == existing_tasks
        assert scraper.get_app_ids() == [10]
        assert checkpoint.is_page_completed(1)
        assert not checkpoint.is_page_completed(2)
    finally:
        await scraper.client.close()
        scraper.db.close()

    resumed_checkpoint = Checkpoint(config=app_config, save_interval=0)
    resumed = GameScraper(config=app_config, checkpoint=resumed_checkpoint)
    visited_pages = []

    def recover(request):
        visited_pages.append(int(request.url.params["page"]))
        return httpx.Response(200, text='<a data-ds-appid="20"></a>')

    resumed.client._client = httpx.AsyncClient(transport=httpx.MockTransport(recover))
    monkeypatch.setattr(resumed, "get_total_pages", AsyncMock(return_value=2))
    monkeypatch.setattr(
        resumed, "get_game_details", AsyncMock(return_value=GameInfo(20, "Game 20"))
    )
    try:
        await asyncio.wait_for(resumed.run(), timeout=5)
        assert visited_pages == [2]
        assert set(resumed.get_app_ids()) == {10, 20}
        assert resumed_checkpoint.is_page_completed(2)
    finally:
        await resumed.client.close()
        resumed.db.close()


@pytest.mark.parametrize("cancel_during_cleanup", [False, True])
@pytest.mark.asyncio
async def test_page_failure_cleanup_waits_for_active_writer(
    app_config, monkeypatch, cancel_during_cleanup
):
    app_config.http.max_retries = 0
    checkpoint = Checkpoint(config=app_config, save_interval=0)
    scraper = GameScraper(config=app_config, checkpoint=checkpoint)
    writer_entered = threading.Event()
    writer_release = threading.Event()
    writer_finished = threading.Event()
    worker_entered = asyncio.Event()
    worker_cancelled = asyncio.Event()
    page_failed = asyncio.Event()
    save_games = scraper.db.save_games_batch

    def blocked_save(games, commit=True):
        writer_entered.set()
        assert writer_release.wait(timeout=5)
        save_games(games, commit=commit)
        writer_finished.set()

    async def details(app_id):
        if app_id == 11:
            worker_entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                worker_cancelled.set()
        return GameInfo(app_id, f"Game {app_id}")

    async def respond(request):
        if request.url.params["page"] == "2":
            await worker_entered.wait()
            assert await asyncio.to_thread(writer_entered.wait, 5)
            page_failed.set()
            return httpx.Response(503)
        return httpx.Response(
            200, text='<a data-ds-appid="10"></a><a data-ds-appid="11"></a>'
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    scraper.client._client = client
    monkeypatch.setattr(scraper, "get_total_pages", AsyncMock(return_value=2))
    monkeypatch.setattr(scraper, "get_game_details", details)
    monkeypatch.setattr(scraper.db, "save_games_batch", blocked_save)
    existing_tasks = asyncio.all_tasks()
    run_task = asyncio.create_task(scraper.run())
    try:
        await asyncio.wait_for(page_failed.wait(), timeout=5)
        await asyncio.wait_for(worker_cancelled.wait(), timeout=5)
        assert not checkpoint.is_page_completed(1)
        assert not checkpoint.is_page_completed(2)
        if cancel_during_cleanup:
            run_task.cancel()
            done, _ = await asyncio.wait({run_task}, timeout=0.01)
            assert not done
        assert not run_task.done()
        writer_release.set()
        expected_error = (
            asyncio.CancelledError if cancel_during_cleanup else SteamSearchError
        )
        with pytest.raises(expected_error):
            await asyncio.wait_for(run_task, timeout=5)
        assert writer_finished.is_set()
        assert client.is_closed
        assert scraper.get_app_ids() == [10]
        assert checkpoint.is_appid_completed(10)
        assert not checkpoint.is_appid_completed(11)
        assert not checkpoint.is_page_completed(1)
        assert not checkpoint.is_page_completed(2)
        assert asyncio.all_tasks() == existing_tasks
    finally:
        writer_release.set()
        await asyncio.gather(run_task, return_exceptions=True)
        assert await asyncio.to_thread(writer_finished.wait, 5)
        await scraper.client.close()
        scraper.db.close()
