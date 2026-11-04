import argparse
import io
import json
from unittest.mock import AsyncMock, Mock

import pytest
from rich.console import Console

from steam_scraper.cli import run_retry_async
from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.scrapers.review_scraper import ReviewScraper, read_app_ids
from steam_scraper.utils.failure_manager import FailureManager
from steam_scraper.utils.ui import UIManager, terminal_text

PAYLOADS = [
    ("\x1b[2J\x1b[Hhidden", r"\x1b[2J\x1b[Hhidden"),
    ("\x9b2Jhidden", r"\x9b2Jhidden"),
    ("\x1b]8;;https://invalid.test\x07link", r"\x1b]8;;https://invalid.test\x07link"),
    ("[/red]", "[/red]"),
    ("[bold]伪造[/bold]", "[bold]伪造[/bold]"),
    ("普通中文 [方括号] 😀", "普通中文 [方括号] 😀"),
]


@pytest.fixture
def captured_ui():
    output = io.StringIO()
    ui = UIManager()
    ui.console = Console(
        file=output, width=240, color_system=None, highlight=False, theme=ui.theme
    )
    return ui, output


@pytest.mark.parametrize(("payload", "expected"), PAYLOADS)
def test_appid_warning_is_literal_and_does_not_interrupt_valid_ids(
    tmp_path, captured_ui, payload, expected
):
    ui, output = captured_ui
    input_file = tmp_path / "ids.txt"
    input_file.write_text(f"570\n{payload}\n730\n570\n", encoding="utf-8-sig")

    assert read_app_ids(input_file, ui) == [570, 730, 570]
    assert expected in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "expected"), PAYLOADS)
async def test_retry_reason_is_literal_before_confirmation(
    app_config, monkeypatch, captured_ui, payload, expected
):
    ui, output = captured_ui
    failures = FailureManager(app_config)
    failures.path.write_text(
        json.dumps([{"type": "game", "id": 570, "reason": payload}]),
        encoding="utf-8",
    )
    original = failures.path.read_bytes()
    confirm = Mock(return_value=False)
    monkeypatch.setattr(ui, "confirm", confirm)

    await run_retry_async(app_config, argparse.Namespace(type="all"), failures, ui)

    confirm.assert_called_once()
    assert expected in output.getvalue()
    assert "操作已取消" in output.getvalue()
    assert failures.path.read_bytes() == original
    assert not app_config.output.db_path.exists()


@pytest.mark.parametrize(("payload", "expected"), PAYLOADS)
def test_failure_logging_sanitizes_display_but_preserves_reason(
    app_config, capsys, payload, expected
):
    failures = FailureManager(app_config)

    failures.log_failure("review", 570, payload)

    assert expected in capsys.readouterr().out
    assert failures.get_failures()[0]["reason"] == payload


def test_trusted_warning_markup_and_line_breaks_are_preserved(captured_ui):
    ui, output = captured_ui

    ui.print_warning("第一行\n建议运行 [cyan]retry[/cyan]。")

    rendered = output.getvalue()
    assert "第一行\n" in rendered
    assert "建议运行 retry。" in rendered
    assert "[cyan]" not in rendered


def test_terminal_text_neutralizes_all_c0_del_and_c1_controls(captured_ui):
    ui, output = captured_ui
    controls = "".join(chr(code) for code in [*range(32), *range(127, 160)])
    message = terminal_text(f"中文[/red]{controls}😀")

    ui.print_error(message)

    assert all(char not in message.plain for char in controls)
    assert not message.spans
    assert message.plain.startswith("中文[/red]\\x00")
    assert message.plain.endswith("\\x9f😀")
    assert "中文[/red]" in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("scraper_kind", ["game", "review"])
async def test_scraper_exception_is_safe_in_both_error_and_failure_log(
    app_config, captured_ui, monkeypatch, capsys, scraper_kind
):
    ui, output = captured_ui
    payload = "[/red]\x1b[2J\x9b2J"
    expected = r"[/red]\x1b[2J\x9b2J"
    failures = FailureManager(app_config)
    scraper_type = GameScraper if scraper_kind == "game" else ReviewScraper
    scraper = scraper_type(config=app_config, failure_manager=failures, ui_manager=ui)
    get_json = AsyncMock(side_effect=ValueError(payload))
    monkeypatch.setattr(scraper.client, "get_json", get_json)
    try:
        if isinstance(scraper, GameScraper):
            assert await scraper.get_game_details(570) is None
        else:
            assert await scraper.scrape_reviews(570) == (None, False)
    finally:
        await scraper.client.close()
        scraper.db.close()

    get_json.assert_awaited_once()
    assert expected in output.getvalue()
    assert expected in capsys.readouterr().out
    assert failures.get_failures()[0]["reason"] == payload
