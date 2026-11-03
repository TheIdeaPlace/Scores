"""Bugs the replay tests found and the fixes made for them. The ones not fixed yet
are in test_known_gaps.py."""
from datetime import datetime

import pytest

import espn_api
import timezone_utils

from .support import load


@pytest.mark.parametrize("offset,is_dst,zone", [
    (-4, True, "US/Eastern"), (-5, False, "US/Eastern"),
    (-5, True, "US/Central"), (-6, False, "US/Central"),
    (-6, True, "US/Mountain"), (-7, False, "US/Mountain"),
    (-7, True, "US/Pacific"), (-8, False, "US/Pacific"),
    (1, False, "US/Central"),  # outside the US: the existing default
])
def test_the_zone_comes_from_the_standard_time_offset(offset, is_dst, zone):
    """Daylight saving added an hour where it should take one off, so Eastern at -4
    became -3, matched nothing and fell through to Central all summer."""
    assert timezone_utils._zone_for_offset(offset, is_dst) == zone


@pytest.mark.parametrize("offset,is_dst,local_time", [
    (-4, True, "7:00 PM"),   # New York in summer stays at the time ESPN gave
    (-5, True, "6:00 PM"),   # Chicago
    (-7, True, "4:00 PM"),   # Los Angeles
])
def test_summer_game_times_end_to_end(monkeypatch, offset, is_dst, local_time):
    monkeypatch.setattr(timezone_utils, "_local_offset_and_dst", lambda: (offset, is_dst))
    assert timezone_utils.convert_espn_time_to_local("7:00 PM EDT").startswith(local_time + " ")


def test_golf_schedule_asks_for_the_year_not_a_range(espn, freeze_now):
    """Same 49 events either way when checked against ESPN; only the year is safe."""
    freeze_now(datetime(2026, 11, 3, 12))
    espn.on("/golf/pga/scoreboard", load("golf_schedule_PGA.json"))
    espn_api.get_golf_schedule("PGA")
    assert espn.calls == [f"{espn_api.BASE_URL}/golf/pga/scoreboard?dates=2026"]


def test_white_sox_are_in_a_division_when_mlb_falls_back_to_team_records(espn):
    """ESPN's abbreviation is CHW (see standings_MLB.json); this map had CWS, so the
    fallback filed the White Sox under "League"."""
    abbreviations = {entry["team"]["abbreviation"]
                     for league in load("standings_MLB.json")["children"]
                     for entry in league["standings"]["entries"]}
    assert "CHW" in abbreviations
    teams = {"sports": [{"leagues": [{"teams": [{"team": {"id": "4", "abbreviation": "CHW",
                                                          "displayName": "Chicago White Sox"}}]}]}]}
    espn.on("/teams/4$", {"team": {"record": {"items": []}}})
    assert espn_api._parse_standings_from_teams_api(teams, "MLB")[0]["division"] == "AL Central"


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
