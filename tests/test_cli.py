import argparse
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from steam_scraper.cli import (
    build_parser,
    main,
    run_all_async,
    run_clean,
    run_export,
    run_retry_async,
)
from steam_scraper.config import Config, OutputConfig
from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo
from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.scrapers.review_scraper import ReviewScraper
from steam_scraper.utils.checkpoint import Checkpoint
from steam_scraper.utils.failure_manager import FailureManager
from steam_scraper.utils.ui import UIManager


def test_build_parser_parses_resume_and_page_limit() -> None:
    args = build_parser().parse_args(["games", "--pages", "3", "--resume"])

    assert args.command == "games"
    assert args.pages == 3
    assert args.resume is True


def test_main_without_command_prints_help(capsys) -> None:
    main([])

    assert "Steam 游戏数据爬虫" in capsys.readouterr().out


def test_help_has_clean_start_entry_and_unique_examples() -> None:
    help_text = build_parser().format_help()

    assert "==SUPPRESS==" not in help_text
    assert "显示启动页并验证运行环境" in help_text
    assert help_text.count("uv run steam-scraper export --format csv") == 1


def test_module_entrypoint_displays_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "steam_scraper", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Steam 游戏数据爬虫" in result.stdout


def test_run_export_executes_csv_export(app_config: Config, tmp_path: Path) -> None:
    database = DatabaseManager(app_config.output.db_path)
    database.save_game(GameInfo(app_id=10, name="测试游戏"))
    database.close()

    output_dir = tmp_path / "csv"
    args = argparse.Namespace(format="csv", output=str(output_dir))
    run_export(app_config, args, UIManager())

    assert (output_dir / "steam_games.csv").is_file()
    assert (output_dir / "steam_reviews.csv").is_file()


def test_run_clean_uses_configured_state_paths(tmp_path: Path, monkeypatch) -> None:
    configured_data = tmp_path / "configured-data"
    config = Config(
        output=OutputConfig(
            data_dir=str(configured_data),
            checkpoint_file="progress.json",
            failure_log_file="failed.json",
        )
    )
    config.output.checkpoint_path.parent.mkdir(parents=True)
    config.output.checkpoint_path.write_text("{}", encoding="utf-8")
    config.output.failure_log_path.write_text("[]", encoding="utf-8")

    unrelated_checkpoint = tmp_path / "data" / ".checkpoint.json"
    unrelated_checkpoint.parent.mkdir()
    unrelated_checkpoint.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    run_clean(config, FailureManager(config), UIManager())

    assert not config.output.checkpoint_path.exists()
    assert not config.output.failure_log_path.exists()
    assert unrelated_checkpoint.exists()


@pytest.mark.parametrize("command", ["games", "all"])
@pytest.mark.parametrize("pages", ["0", "-1"])
def test_nonpositive_page_limit_is_rejected(command, pages):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([command, "--pages", pages])
    assert exc.value.code == 2


def test_export_missing_database_has_nonzero_exit(app_config, monkeypatch):
    monkeypatch.setattr(Config, "load", lambda: app_config)
    with pytest.raises(SystemExit) as exc:
        main(["export"])
    assert exc.value.code == 1


def test_export_failure_is_reported(app_config, tmp_path, monkeypatch):
    DatabaseManager(app_config.output.db_path).close()

    def fail_export(*args):
        raise OSError("disk full")

    monkeypatch.setattr(DatabaseManager, "export_to_excel", fail_export)
    args = argparse.Namespace(format="excel", output=str(tmp_path / "failed.xlsx"))
    assert run_export(app_config, args, UIManager()) is False


@pytest.mark.asyncio
async def test_retry_clears_stale_failure_for_completed_game(app_config, monkeypatch):
    checkpoint = Checkpoint(config=app_config)
    checkpoint.mark_appid_completed(10)
    checkpoint.save()
    failures = FailureManager(app_config)
    failures.log_failure("game", 10, "stale failure")
    ui = UIManager()
    monkeypatch.setattr(ui, "confirm", lambda *args, **kwargs: True)
    fetch = AsyncMock()
    monkeypatch.setattr(GameScraper, "get_game_details", fetch)

    await run_retry_async(app_config, argparse.Namespace(type="game"), failures, ui)

    assert failures.get_failures() == []
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_stops_before_next_request(app_config, monkeypatch):
    failures = FailureManager(app_config)
    failures.log_failure("review", 10, "timeout")
    failures.log_failure("review", 20, "timeout")
    stop_event = threading.Event()
    calls = []

    async def finish_then_stop(self, app_id, force):
        calls.append(app_id)
        stop_event.set()
        return [], False

    ui = UIManager()
    monkeypatch.setattr(ui, "confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(ReviewScraper, "scrape_reviews", finish_then_stop)

    await run_retry_async(
        app_config, argparse.Namespace(type="review"), failures, ui, stop_event
    )

    assert calls == [10]
    assert [failure["id"] for failure in failures.get_failures()] == [20]


@pytest.mark.asyncio
async def test_all_does_not_report_success_after_export_failure(
    app_config, monkeypatch, capsys
):
    monkeypatch.setattr(GameScraper, "run", AsyncMock(return_value=[]))
    monkeypatch.setattr(ReviewScraper, "scrape_from_list", AsyncMock())
    monkeypatch.setattr("steam_scraper.cli.run_export", lambda *args: False)

    with pytest.raises(SystemExit) as exc:
        await run_all_async(
            app_config,
            argparse.Namespace(resume=True, pages=1),
            FailureManager(app_config),
            UIManager(),
            threading.Event(),
        )

    assert exc.value.code == 1
    assert "全部完成" not in capsys.readouterr().out
