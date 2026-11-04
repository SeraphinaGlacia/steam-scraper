import pytest

from steam_scraper.models import GameInfo


def test_game_info_validates_dynamic_api_fields() -> None:
    game = GameInfo.from_api_response(
        42,
        {
            "name": "Portal",
            "release_date": {"date": "10 Oct, 2007"},
            "price_overview": {"final_formatted": "$9.99"},
            "developers": ["Valve", 123],
            "publishers": ["Valve"],
            "genres": [{"description": "Puzzle"}, {"bad": "value"}],
            "short_description": "A spatial puzzle game.",
        },
    )

    assert game.developers == ["Valve"]
    assert game.genres == ["Puzzle"]
    assert game.app_id == 42


@pytest.mark.parametrize(
    ("pricing", "expected"),
    [
        ({"is_free": True}, "Free"),
        ({"is_free": False}, ""),
        ({}, ""),
        ({"is_free": False, "price_overview": {}}, ""),
        ({"is_free": True, "price_overview": {"final_formatted": ""}}, "Free"),
        ({"is_free": False, "price_overview": {"final_formatted": "$9.99"}}, "$9.99"),
    ],
)
def test_game_price_distinguishes_free_from_unavailable(pricing, expected) -> None:
    game = GameInfo.from_api_response(42, {"name": "Game", **pricing})

    assert game.price == expected
