import csv
import os
from pathlib import Path

import pandas as pd
import pytest

from steam_scraper.utils.csv_export import write_csv_pair


def _read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize(
    "text",
    [
        "=1+1",
        "+SUM(1,2)",
        "-1+2",
        "@SUM(1,2)",
        " =1+1",
        "\t=1+1",
        "\r=1+1",
        "\n=1+1",
        " \t\r\n=1+1",
        "\tordinary text",
        "＝1+1",
    ],
)
def test_csv_neutralizes_formula_text_in_both_tables(tmp_path, text):
    games = pd.DataFrame({"name": [text], "app_id": [10]})
    reviews = pd.DataFrame({"game_name": [text], "recommendations_up": [3]})

    write_csv_pair(games, reviews, tmp_path)

    assert _read_rows(tmp_path / "steam_games.csv")[0]["name"] == "'" + text
    assert _read_rows(tmp_path / "steam_reviews.csv")[0]["game_name"] == "'" + text
    assert games.iloc[0]["name"] == text
    assert reviews.iloc[0]["game_name"] == text


def test_csv_preserves_numbers_and_ordinary_text(tmp_path):
    games = pd.DataFrame({"name": ["Game, 中文"], "app_id": [10]})
    reviews = pd.DataFrame({"recommendations_up": [-3], "ratio": [-1.5]})

    write_csv_pair(games, reviews, tmp_path)

    assert _read_rows(tmp_path / "steam_games.csv") == [
        {"name": "Game, 中文", "app_id": "10"}
    ]
    assert _read_rows(tmp_path / "steam_reviews.csv") == [
        {"recommendations_up": "-3", "ratio": "-1.5"}
    ]


def test_raw_csv_preserves_original_formula_text(tmp_path):
    games = pd.DataFrame({"name": [" =1+1"]})
    reviews = pd.DataFrame({"game_name": ["\t=1+1"]})

    write_csv_pair(games, reviews, tmp_path, spreadsheet_safe=False)

    assert _read_rows(tmp_path / "steam_games.csv")[0]["name"] == " =1+1"
    assert _read_rows(tmp_path / "steam_reviews.csv")[0]["game_name"] == "\t=1+1"


@pytest.mark.parametrize("spreadsheet_safe", [False, True])
def test_csv_quotes_carriage_returns_inside_text(tmp_path, spreadsheet_safe):
    text = 'Game\r=1+1, "quoted"'
    games = pd.DataFrame({"name": [text]})
    reviews = pd.DataFrame({"game_name": [text]})

    write_csv_pair(games, reviews, tmp_path, spreadsheet_safe=spreadsheet_safe)

    assert _read_rows(tmp_path / "steam_games.csv") == [{"name": text}]
    assert _read_rows(tmp_path / "steam_reviews.csv") == [{"game_name": text}]


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure_stage", ["generate", "publish"])
def test_csv_failure_preserves_both_files(
    tmp_path, monkeypatch, existing, failure_stage
):
    targets = [tmp_path / "steam_games.csv", tmp_path / "steam_reviews.csv"]
    previous = [b"previous games\r\n", b"previous reviews\r\n"]
    if existing:
        for target, content in zip(targets, previous, strict=True):
            target.write_bytes(content)

    if failure_stage == "generate":
        original_to_csv = pd.DataFrame.to_csv

        def fail_second_generation(frame, path, **kwargs):
            if Path(path).name == "steam_reviews.csv":
                Path(path).write_bytes(b"partial output")
                raise OSError("simulated write failure")
            return original_to_csv(frame, path, **kwargs)

        monkeypatch.setattr(pd.DataFrame, "to_csv", fail_second_generation)
    else:
        original_replace = os.replace

        def fail_second_publish(source, destination):
            if Path(source).name == "steam_reviews.csv":
                raise OSError("simulated publish failure")
            return original_replace(source, destination)

        monkeypatch.setattr(os, "replace", fail_second_publish)

    with pytest.raises(OSError, match="simulated"):
        write_csv_pair(pd.DataFrame({"name": ["new"]}), pd.DataFrame(), tmp_path)

    for target, content in zip(targets, previous, strict=True):
        if existing:
            assert target.read_bytes() == content
        else:
            assert not target.exists()
    assert list(tmp_path.glob(".steam-csv-*")) == []


def test_read_only_second_target_preserves_both_files(tmp_path):
    games_file = tmp_path / "steam_games.csv"
    reviews_file = tmp_path / "steam_reviews.csv"
    games_file.write_bytes(b"previous games")
    reviews_file.write_bytes(b"previous reviews")
    reviews_file.chmod(0o444)
    try:
        with pytest.raises(PermissionError):
            write_csv_pair(pd.DataFrame(), pd.DataFrame(), tmp_path)

        assert games_file.read_bytes() == b"previous games"
        assert reviews_file.read_bytes() == b"previous reviews"
        assert list(tmp_path.glob(".steam-csv-*")) == []
    finally:
        reviews_file.chmod(0o644)


def test_read_only_directory_does_not_publish_files(tmp_path):
    output = tmp_path / "readonly"
    output.mkdir()
    output.chmod(0o555)
    try:
        with pytest.raises(PermissionError):
            write_csv_pair(pd.DataFrame(), pd.DataFrame(), output)
        assert list(output.iterdir()) == []
    finally:
        output.chmod(0o755)


def test_failed_rollback_preserves_backup_for_recovery(tmp_path, monkeypatch):
    games_file = tmp_path / "steam_games.csv"
    reviews_file = tmp_path / "steam_reviews.csv"
    games_file.write_bytes(b"previous games")
    reviews_file.write_bytes(b"previous reviews")
    original_replace = os.replace

    def fail_publish_and_rollback(source, destination):
        if Path(source).name in ("steam_reviews.csv", "steam_games.csv.bak"):
            raise OSError("simulated filesystem failure")
        return original_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_publish_and_rollback)

    with pytest.raises(RuntimeError, match="恢复备份保留在"):
        write_csv_pair(pd.DataFrame({"name": ["new"]}), pd.DataFrame(), tmp_path)

    [backup_dir] = tmp_path.glob(".steam-csv-*")
    assert (backup_dir / "steam_games.csv.bak").read_bytes() == b"previous games"
    assert reviews_file.read_bytes() == b"previous reviews"
