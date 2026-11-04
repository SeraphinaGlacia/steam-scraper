from pathlib import Path

import pytest

from steam_scraper.config import Config


def test_from_yaml_applies_every_user_config_section(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
scraper:
  language: schinese
  currency: cn
  category: "998"
  max_workers: 8
http:
  timeout: 60
  max_retries: 5
  min_delay: 1.0
  max_delay: 2.0
  max_connections: 40
  max_keepalive_connections: 10
  user_agent: Config Test Agent
output:
  data_dir: custom-data
  database_file: custom.sqlite3
  checkpoint_file: progress.json
  failure_log_file: failed.json
""".strip(),
        encoding="utf-8",
    )

    config = Config.from_yaml(config_file)

    assert config.scraper.language == "schinese"
    assert config.scraper.currency == "cn"
    assert config.scraper.max_workers == 8
    assert config.http.timeout == 60
    assert config.http.max_retries == 5
    assert config.http.min_delay == 1.0
    assert config.http.max_delay == 2.0
    assert config.http.max_connections == 40
    assert config.http.max_keepalive_connections == 10
    assert config.http.user_agent == "Config Test Agent"
    assert config.output.data_path == Path("custom-data")
    assert config.output.db_path == Path("custom-data/custom.sqlite3")
    assert config.output.checkpoint_path == Path("custom-data/progress.json")
    assert config.output.failure_log_path == Path("custom-data/failed.json")


def test_load_automatically_reads_config_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.yaml").write_text(
        "scraper:\n  max_workers: 7\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = Config.load()

    assert config.scraper.max_workers == 7


def test_from_yaml_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("- invalid\n- root\n", encoding="utf-8")

    with pytest.raises(ValueError, match="顶层必须是映射"):
        Config.from_yaml(config_file)


def test_missing_yaml_uses_defaults(tmp_path: Path) -> None:
    config = Config.from_yaml(tmp_path / "missing.yaml")

    assert config.scraper.max_workers == 20
    assert config.http.timeout == 30


@pytest.mark.parametrize("workers", [0, -1, 1.5, True, "2"])
def test_invalid_worker_count_is_rejected_before_scraping(workers):
    with pytest.raises(ValueError, match="scraper.max_workers 必须是正整数"):
        Config.from_dict({"scraper": {"max_workers": workers}})
