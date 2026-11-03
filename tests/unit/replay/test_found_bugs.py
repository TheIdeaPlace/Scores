"""Bugs the replay tests found and the fixes made for them. The ones not fixed yet
are in test_known_gaps.py."""
from datetime import datetime

import espn_api

from .support import load


def test_golf_schedule_asks_for_the_year_not_a_range(espn, freeze_now):
    """Same 49 events either way when checked against ESPN; only the year is safe."""
    freeze_now(datetime(2026, 11, 3, 12))
    espn.on("/golf/pga/scoreboard", load("golf_schedule_PGA.json"))
    espn_api.get_golf_schedule("PGA")
    assert espn.calls == [f"{espn_api.BASE_URL}/golf/pga/scoreboard?dates=2026"]


def test_soccer_standings_read_the_record_not_0_0(espn):
    """A three-part summary raised inside _get_team_record, so every soccer team read 0-0."""
    espn.on(r"/soccer/eng\.1/teams$", load("teams_EPL.json"))
    espn.on(r"/soccer/eng\.1/teams/\d+$", load("team_EPL_359.json"))
    arsenal = next(row for row in espn_api.get_standings("EPL") if row["team_name"] == "Arsenal")
    assert (arsenal["wins"], arsenal["losses"], arsenal["win_percentage"]) == (8, 1, "0.889")


def test_team_record_without_stats_falls_back_to_the_summary(espn):
    team = {"team": {"record": {"items": [{"type": "total", "summary": "10-4-1"}]}}}
    espn.on("/teams/1$", team)
    assert espn_api._get_team_record("1", "NFL") == (10, 4, "0.714", "")
