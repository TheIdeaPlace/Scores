"""favorite_card.py against tests/fixtures/favorite_card_grid.json, the grid the iPhone's
FavoriteCardGames.swift is held to (FavoriteCardGridTests.swift)."""
import json
from datetime import datetime
from pathlib import Path

import pytest

import favorite_card

FIXTURES = Path(__file__).parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "favorite_card_grid.json").read_text(encoding="utf-8"))


def espn_event(game):
    """A grid game in short form as a minimal ESPN schedule event. FavoriteCardGridTests.swift
    builds the same one."""
    status_type = {"name": game["status"], "description": game["status"]}
    for key in ("state", "completed"):
        if key in game:
            status_type[key] = game[key]

    def competitor(side):
        team_id, abbreviation, score = game[side]
        entry = {"homeAway": side, "team": {"id": team_id, "abbreviation": abbreviation, "displayName": abbreviation}}
        if score is not None:
            entry["score"] = {"value": float(score), "displayValue": str(score)}
        return entry

    competition = {
        "competitors": [competitor("home"), competitor("away")],
        "status": {"type": status_type},
        "neutralSite": game.get("neutral", False),
    }
    if game.get("label"):
        competition["notes"] = [{"headline": game["label"]}]
    return {
        "id": game["id"],
        "date": game["date"],
        "name": f"{game['away'][1]} at {game['home'][1]}",
        "timeValid": game.get("time_valid", True),
        "seasonType": {"type": 2},
        "competitions": [competition],
    }


def events_of(case):
    if "fixture" in case:
        return json.loads((FIXTURES / "espn" / case["fixture"]).read_text(encoding="utf-8"))["events"]
    return [espn_event(game) for game in case["games"]]


def game_id(game):
    return game["id"] if game else None


@pytest.mark.parametrize("case", GRID["cases"], ids=[case["name"] for case in GRID["cases"]])
def test_grid(case):
    games = favorite_card.card_games(events_of(case))
    now = datetime.fromisoformat(case["now"].replace("Z", "+00:00"))
    picked = favorite_card.pick(games, now)
    expected = case["expected"]
    assert (game_id(picked.live), game_id(picked.last), game_id(picked.next)) == (
        expected["live"], expected["last"], expected["next"])
    line = favorite_card.result_line(picked.last, case["team_id"]) if picked.last else None
    assert line == expected["last_line"]


def test_the_grid_covers_a_doubleheader_a_postponement_the_off_season_and_a_live_game():
    names = " ".join(case["name"] for case in GRID["cases"])
    for word in ("doubleheader", "postponed", "off-season", "being played"):
        assert word in names
    assert {case.get("fixture") for case in GRID["cases"]} >= {
        "schedule_MLB_10_2026_dh.json", "schedule_MLB_10_2026_post.json", "schedule_NCAAF_333_live.json"}
