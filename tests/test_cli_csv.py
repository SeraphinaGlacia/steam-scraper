import csv

import pytest

from steam_scraper.cli import main
from steam_scraper.config import Config
from steam_scraper.database import DatabaseManager
from steam_scraper.models import GameInfo


@pytest.mark.parametrize("raw", [False, True])
def test_csv_cli_selects_safe_or_raw_text(app_config, tmp_path, monkeypatch, raw):
    database = DatabaseManager(app_config.output.db_path)
    database.save_game(GameInfo(10, "=1+1"))
    database.close()
    monkeypatch.setattr(Config, "load", lambda: app_config)
    output = tmp_path / "exported"
    arguments = ["export", "--format", "csv", "--output", str(output)]
    if raw:
        arguments.append("--raw-csv")

    main(arguments)

    with (output / "steam_games.csv").open(encoding="utf-8-sig") as file:
        exported_name = next(csv.DictReader(file))["name"]
    assert exported_name == ("=1+1" if raw else "'=1+1")


def test_raw_csv_option_requires_csv_format():
    with pytest.raises(SystemExit) as exc:
        main(["export", "--raw-csv"])
    assert exc.value.code == 2
