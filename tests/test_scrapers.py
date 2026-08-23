import asyncio
from datetime import date, datetime, timezone

import pytest

from steam_scraper.config import Config
from steam_scraper.models import GameInfo
from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.scrapers.review_scraper import ReviewScraper
from steam_scraper.utils.checkpoint import Checkpoint


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeGameClient:
    def __init__(self, html: str) -> None:
        self.html = html

    async def get(self, url, params=None, delay=True):
        return FakeResponse(self.html)

    async def close(self) -> None:
        return None


class FakeReviewClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def get_json(self, url, params=None, delay=True):
        return self.payload

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_total_pages_does_not_add_extra_page(
    app_config: Config,
) -> None:
    scraper = GameScraper(config=app_config)
    scraper.client = FakeGameClient(
        '<div class="search_pagination_left">Showing 1 - 25 of 50</div>'
    )

    try:
        assert await scraper.get_total_pages() == 2
    finally:
        scraper.db.close()


@pytest.mark.asyncio
async def test_page_parser_uses_first_appid_from_bundle(
    app_config: Config,
) -> None:
    scraper = GameScraper(config=app_config)
    scraper.client = FakeGameClient(
        '<a data-ds-appid="10"></a><a data-ds-appid="20,30"></a>'
    )

    try:
        assert await scraper.scrape_page_games(1) == [10, 20]
    finally:
        scraper.db.close()


@pytest.mark.asyncio
async def test_game_pipeline_commits_unique_games_without_deadlock(
    app_config: Config, monkeypatch
) -> None:
    checkpoint = Checkpoint(path=app_config.output.checkpoint_path, save_interval=0)
    scraper = GameScraper(config=app_config, checkpoint=checkpoint)

    async def fake_total_pages() -> int:
        return 1

    async def fake_page_games(page: int) -> list[int]:
        assert page == 1
        return [10, 20, 20]

    async def fake_game_details(app_id: int) -> GameInfo:
        return GameInfo(app_id=app_id, name=f"Game {app_id}")

    monkeypatch.setattr(scraper, "get_total_pages", fake_total_pages)
    monkeypatch.setattr(scraper, "scrape_page_games", fake_page_games)
    monkeypatch.setattr(scraper, "get_game_details", fake_game_details)

    try:
        processed = await asyncio.wait_for(scraper.run(max_pages=1), timeout=5)
        assert set(processed) == {10, 20}
        assert set(scraper.get_app_ids()) == {10, 20}
        assert checkpoint.is_appid_completed(10)
        assert checkpoint.is_appid_completed(20)
    finally:
        scraper.db.close()


@pytest.mark.asyncio
async def test_review_timestamp_is_converted_to_china_date(
    app_config: Config,
) -> None:
    checkpoint = Checkpoint(path=app_config.output.checkpoint_path, save_interval=0)
    scraper = ReviewScraper(config=app_config, checkpoint=checkpoint)
    timestamp = int(datetime(2026, 8, 23, 18, tzinfo=timezone.utc).timestamp())
    scraper.client = FakeReviewClient(
        {
            "results": {
                "rollups": [
                    {
                        "date": timestamp,
                        "recommendations_up": 12,
                        "recommendations_down": 3,
                    }
                ]
            }
        }
    )

    try:
        reviews, skipped = await scraper.scrape_reviews(10)
    finally:
        scraper.db.close()

    assert skipped is False
    assert reviews[0].date == date(2026, 8, 24)
    assert checkpoint.is_appid_completed(10, "review")
