"""The Windows favorite card's loader: the lines it hands Home, from real ESPN payloads, and
what it says when a request fails. Runs the loader's work directly, with no thread."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import espn_api  # noqa: E402
import favorite_card  # noqa: E402
import scores  # noqa: E402
from exceptions import ApiError  # noqa: E402

ESPN = Path(__file__).parent.parent / "fixtures" / "espn"
HEADLINES = [{"headline": "One"}, {"headline": "Two"}, {"headline": "Three"}]
CAPTURED = datetime(2026, 11, 7, 23, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((ESPN / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def fail(message):
    def raise_it(*args, **kwargs):
        raise ApiError(message)
    return raise_it


@pytest.fixture
def espn(monkeypatch):
    """ApiService answering from fixtures; a test swaps in a failure."""
    games = favorite_card.card_games(load("schedule_NCAAF_333_live.json")["events"])
    service = scores.ApiService
    monkeypatch.setattr(service, "get_favorite_card_schedule", staticmethod(lambda league, team: games))
    monkeypatch.setattr(service, "get_game_details",
                        staticmethod(lambda league, game: load("summary_live_NCAAF_401856740.json")))
    monkeypatch.setattr(service, "get_team_news", staticmethod(lambda league, team, limit=25: HEADLINES))
    # The moment the fixtures were captured, so the next game is still to come.
    pick = favorite_card.pick
    monkeypatch.setattr(favorite_card, "pick", lambda games, now: pick(games, CAPTURED))
    return service


def card(app, team_id="333", league="NCAAF"):
    loader = scores.FavoriteCardLoader(team_id, league)
    got = []
    loader.card_ready.connect(lambda *emitted: got.append(emitted))
    loader.run()
    assert len(got) == 1 and got[0][:2] == (team_id, league)
    return got[0][2]


def test_live_game_then_next_game_then_two_headlines(app, espn):
    lines = card(app)
    assert lines[0] == "Live: Alabama Crimson Tide 10 @ LSU Tigers 12, 2:44 - 3rd Quarter"
    assert lines[1].startswith("Next: @ VAN, 11/1")
    assert lines[2:] == ["One", "Two"]


def test_no_game_being_played_shows_the_last_result(app, espn, monkeypatch):
    games = favorite_card.card_games(load("schedule_MLB_10_2026_post.json")["events"])
    monkeypatch.setattr(espn, "get_favorite_card_schedule", staticmethod(lambda league, team: games))
    assert card(app, "10", "MLB") == ["Last: L vs TB 3-4, ALDS - Game 3", "One", "Two"]


def test_a_schedule_that_failed_says_so(app, espn, monkeypatch):
    monkeypatch.setattr(espn, "get_favorite_card_schedule", staticmethod(fail(espn_api.SCHEDULE_UNAVAILABLE)))
    assert card(app) == [espn_api.SCHEDULE_UNAVAILABLE, "One", "Two"]


def test_an_empty_schedule_says_there_are_no_games(app, espn, monkeypatch):
    monkeypatch.setattr(espn, "get_favorite_card_schedule", staticmethod(lambda league, team: []))
    assert card(app)[0] == "No games on the schedule."


def test_a_live_summary_that_failed_keeps_the_game_and_says_so(app, espn, monkeypatch):
    monkeypatch.setattr(espn, "get_game_details", staticmethod(fail(espn_api.GAME_UNAVAILABLE)))
    assert card(app)[0] == f"Live: @ LSU. {espn_api.GAME_UNAVAILABLE}"


def test_news_that_failed_says_so(app, espn, monkeypatch):
    monkeypatch.setattr(espn, "get_team_news", staticmethod(fail(espn_api.NEWS_UNAVAILABLE)))
    assert card(app)[-1] == espn_api.NEWS_UNAVAILABLE


def test_the_card_never_reads_the_scoreboard(app, espn, monkeypatch):
    monkeypatch.setattr(espn_api, "get_scores", fail("the scoreboard was read"))
    monkeypatch.setattr(espn_api, "get_team_info", fail("the team page was read"))
    assert card(app)[0].startswith("Live: ")
