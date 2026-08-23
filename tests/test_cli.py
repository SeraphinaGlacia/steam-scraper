import argparse
import subprocess
import sys
from pathlib import Path

from steam_scraper.cli import build_parser, main, run_clean, run_export
from steam_scraper.config import Config, OutputConfig
from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo
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
