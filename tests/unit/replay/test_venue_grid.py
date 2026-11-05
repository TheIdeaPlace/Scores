"""What a real scoreboard reads as on the Venues screen, and the months each league asks
for. The iPhone is held to the same file, in VenuesTests.swift, since both apps build their
venues from a scoreboard with the same rule."""
import json
from datetime import datetime
from itertools import islice
from pathlib import Path

import pytest

import espn_api
from services import venue_service
from services.venue_service import VenueService, venue_summary, venues_from_events

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "venues_grid.json").read_text(encoding="utf-8"))


def board_of(case):
    board = json.loads((FIXTURES / "espn" / case["fixture"]).read_text(encoding="utf-8"))
    if "games" not in case:
        return board["events"]
    events = []
    for game in case["games"]:
        event = next(e for e in board["events"] if e["competitions"][0]["venue"]["fullName"] == game["venue"])
        events += [event] * game["times"]
    return events


def test_the_grid_has_the_cases_that_matter():
    assert {league["league"].lower() for league in GRID["leagues"]} == set(venue_service.IN_SEASON_MONTHS)
    assert {case["league"].lower() for case in GRID["cases"]} == set(venue_service.IN_SEASON_MONTHS)
    assert {month["league"].lower() for month in GRID["months"]} == set(venue_service.IN_SEASON_MONTHS)
    shared = [venue for case in GRID["cases"] for venue in case["venues"] if len(venue["home_teams"]) > 1]
    assert shared, "it should show a shared venue"
    assert any(venue["indoor"] is None for case in GRID["cases"] for venue in case["venues"])


@pytest.mark.parametrize("league", GRID["leagues"], ids=lambda league: league["league"])
def test_windows_asks_for_each_league_as_the_grid_says(league, monkeypatch):
    monkeypatch.setattr(espn_api, "_ncaaf_coverage_group", lambda: "90")
    key = league["league"].lower()
    assert espn_api.LEAGUES[league["league"]] == league["path"]
    assert venue_service._scoreboard_query(key) == league["query"]


@pytest.mark.parametrize("month", GRID["months"], ids=lambda m: f"{m['league']}-{m['year']}-{m['month']}")
def test_windows_tries_the_months_the_grid_says(month):
    key = month["league"].lower()
    months = venue_service._months_back(
        datetime(month["year"], month["month"], 15), venue_service.IN_SEASON_MONTHS[key], venue_service.MONTHS_AHEAD.get(key, 0))
    assert list(islice(months, venue_service.MONTHS_TO_TRY)) == month["months"]


@pytest.mark.parametrize("case", GRID["cases"], ids=lambda case: f"{case['fixture']}-{case['league']}-{case.get('games')}")
def test_windows_reads_it_as_the_grid_says(case):
    key = case["league"].lower()
    venues = sorted(venues_from_events(board_of(case), key).values(), key=lambda venue: venue["name"])
    assert [{
        "id": venue["id"],
        "name": venue["name"],
        "city": venue["city"],
        "state": venue["state"],
        "location": venue["location"],
        "indoor": venue.get("indoor"),
        "home_teams": [{"id": team["id"], "name": team["name"], "abbreviation": team["abbreviation"]}
                       for team in venue["home_teams"]],
        "summary": venue_summary(venue),
        "facts": VenueService()._generate_interesting_facts(venue, key),
    } for venue in venues] == case["venues"]
