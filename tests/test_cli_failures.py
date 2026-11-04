import argparse
import threading
from unittest.mock import AsyncMock

import pytest

from steam_scraper.cli import main, run_all_async, run_reviews_scraper_async
from steam_scraper.config import Config
from steam_scraper.scrapers.game_scraper import GameScraper, SteamSearchError
from steam_scraper.scrapers.review_scraper import ReviewScraper
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager
from steam_scraper.utils.ui import UIManager


@pytest.mark.parametrize("input_kind", ["missing", "directory", "empty", "invalid"])
def test_bad_input_exits_nonzero_without_erasing_checkpoint(
    app_config, tmp_path, monkeypatch, capsys, input_kind
):
    checkpoint = Checkpoint(config=app_config)
    checkpoint.mark_appid_completed(570, "review")
    checkpoint.save()
    original_checkpoint = app_config.output.checkpoint_path.read_bytes()
    input_path = tmp_path / "ids.txt"
    if input_kind == "directory":
        input_path.mkdir()
    elif input_kind in {"empty", "invalid"}:
        input_path.write_text("" if input_kind == "empty" else "0\n-1\ninvalid\n")
    monkeypatch.setattr(Config, "load", lambda: app_config)

    with pytest.raises(SystemExit) as exc:
        main(["reviews", "--input", str(input_path)])

    assert exc.value.code == 1
    assert app_config.output.checkpoint_path.read_bytes() == original_checkpoint
    assert not app_config.output.db_path.exists()
    assert "爬取完成" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cli_validates_once_and_scrapes_only_valid_appids(
    app_config, tmp_path, monkeypatch
):
    input_path = tmp_path / "ids.txt"
    input_path.write_text("\ufeff-1\n570\n0\n730\nbad\n", encoding="utf-8")
    scrape = AsyncMock()
    monkeypatch.setattr(ReviewScraper, "scrape_from_list", scrape)

    await run_reviews_scraper_async(
        app_config,
        argparse.Namespace(resume=False, input=str(input_path)),
        FailureManager(app_config),
        UIManager(),
        threading.Event(),
    )

    scrape.assert_awaited_once_with([570, 730])


@pytest.mark.parametrize("command", ["games", "all"])
def test_search_failure_has_nonzero_cli_exit(app_config, monkeypatch, capsys, command):
    monkeypatch.setattr(Config, "load", lambda: app_config)
    monkeypatch.setattr(
        GameScraper,
        "run",
        AsyncMock(side_effect=SteamSearchError("search unavailable")),
    )
    with pytest.raises(SystemExit) as exc:
        main([command, "--pages", "1"])
    assert exc.value.code == 1
    assert "爬取完成" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_all_does_not_scrape_reviews_or_export_after_search_failure(
    app_config, monkeypatch
):
    monkeypatch.setattr(
        GameScraper,
        "run",
        AsyncMock(side_effect=SteamSearchError("search unavailable")),
    )
    reviews = AsyncMock()
    monkeypatch.setattr(ReviewScraper, "scrape_from_list", reviews)

    def unexpected_export(*args):
        pytest.fail("export must not run after an incomplete search")

    monkeypatch.setattr("steam_scraper.cli.run_export", unexpected_export)
    with pytest.raises(SteamSearchError):
        await run_all_async(
            app_config,
            argparse.Namespace(resume=True, pages=1),
            FailureManager(app_config),
            UIManager(),
            threading.Event(),
        )
    reviews.assert_not_awaited()
