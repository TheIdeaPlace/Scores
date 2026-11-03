"""Bugs the replay tests found and the fixes made for them. The ones not fixed yet
are in test_known_gaps.py."""
import io
import sys
from datetime import datetime

import pytest

import espn_api
import timezone_utils
from services.venue_service import VenueService

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


def test_nba_reads_the_list_shape_like_nfl_and_nhl(espn):
    """statistics_NBA.json has no stats today. When ESPN adds them, in the list shape it
    sends every other league, the NBA parser's .items() raised and lost them all."""
    espn.on("/nba/statistics", load("statistics_NCAAM.json"))
    result = espn_api.get_player_statistics("NBA")
    expected = load("statistics_NCAAM.json")["stats"]["categories"][0]
    assert result["player_stats"][0]["category"] == expected["displayName"]
    assert result["player_stats"][0]["stats"][0]["player_name"] == expected["leaders"][0]["athlete"]["displayName"]


@pytest.mark.parametrize("key,value,expected", [
    ("gameInfo", {"attendance": None, "venue": {"fullName": "Lambeau Field"}}, "Venue: Lambeau Field"),
    ("gameInfo", {"attendance": "64,195"}, "Attendance: 64,195"),
    ("gameInfo", {"attendance": 64195}, "Attendance: 64,195"),
    ("odds", [{"provider": None, "details": "GB -3"}], "• Unknown: GB -3"),
    ("boxscore", {"teams": [{"team": None, "statistics": [{"name": "yards", "displayValue": "300"}]}]},
     "• Unknown: yards: 300"),
    ("odds", [{"provider": {"name": "X"}, "details": None}], "• X: No details"),
    ("odds", [{"provider": {"name": None}, "details": "GB -3"}], "• Unknown: GB -3"),
    ("gameInfo", {"venue": {"fullName": None, "displayName": "Dome"}}, "Venue: Dome"),
    ("gameInfo", {"venue": {"fullName": None}, "attendance": 100}, "Attendance: 100"),
    ("gameInfo", {"weather": {"displayValue": None, "temperature": 50}}, "Weather: 50°F"),
])
def test_format_complex_data_with_unexpected_shapes(key, value, expected):
    """A text attendance, a null provider and a null team all raised."""
    assert espn_api.format_complex_data(key, value) == expected


@pytest.mark.parametrize("league,fact", [
    ("mlb", "Major League Baseball venue"), ("nfl", "National Football League venue"),
    ("nba", "National Basketball Association venue"), ("nhl", "National Hockey League venue"),
    ("ncaaf", "College football venue"),
])
def test_venue_facts_match_the_lower_case_key_scores_passes(league, fact):
    """scores.py lowers the league, and these compared it to "MLB", so they never appeared."""
    assert fact in VenueService()._generate_interesting_facts({"name": "Somewhere"}, league)


def test_the_game_details_injury_line_counts_players_not_teams():
    """The list is per team, so a real summary with 10 injured read "(2 players)"."""
    injuries = load("details_NFL_pieces.json")["injuries"]
    assert espn_api.format_complex_data("injuries", injuries) == "Injury reports available (10 players)"
    assert espn_api.format_complex_data("injuries", [{"injuries": [{}]}]) == "Injury reports available (1 player)"
    assert espn_api.format_complex_data("injuries", [{"injuries": []}]) == "No injuries reported"


def test_team_info_with_no_team_in_the_body_is_empty_not_a_blank_team(espn):
    espn.on("/teams/9$", {})
    assert espn_api.get_team_info("NFL", "9") == {}


def test_mlb_statistics_survive_a_console_that_cannot_print_emoji(espn, monkeypatch):
    """With stdout redirected on Windows, print() encodes as cp1252. Emoji in the progress
    lines raised UnicodeEncodeError, and every MLB leader was lost."""
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    espn.on("statsapi.mlb.com", load("mlb_leaders_homeRuns.json"))
    assert len(espn_api.get_player_statistics("MLB")["player_stats"]) == 39


def test_a_null_venue_name_does_not_lose_the_mlb_facts():
    """Making the league facts reachable made this `"Field" in None` reachable too."""
    facts = VenueService()._generate_interesting_facts({"name": None}, "mlb")
    assert "Major League Baseball venue" in facts


@pytest.mark.parametrize("game_info", [
    {"venue": None}, {"venue": {}}, {"venue": {"fullName": None}},
    {"venue": {"fullName": None, "address": {"city": "Landover"}}},
])
def test_no_venue_name_means_no_venue_line(game_info):
    """It read "Venue: Unknown". With a city and a null name, scores.py added the city
    to None and raised, which lost the whole details list."""
    info = espn_api.extract_meaningful_game_info({"gameInfo": game_info})
    assert not {"venue", "venue_city", "venue_state"} & set(info)


@pytest.mark.parametrize("weather", [None, {}, {"displayValue": None}])
def test_no_weather_means_no_weather_line(weather):
    """It read "Weather: N/A"."""
    assert espn_api.extract_meaningful_game_info({"gameInfo": {"weather": weather}}) == {}


def test_a_temperature_alone_is_still_weather():
    info = espn_api.extract_meaningful_game_info({"gameInfo": {"weather": {"temperature": 50}}})
    assert (info["weather"], info["temperature"]) == ("50°F", "50°F")


@pytest.mark.parametrize("weather,expected,line", [
    ({"displayValue": "Snow", "temperature": 0}, "Snow", "Weather: Snow (0°F)"),
    ({"temperature": 0}, "0°F", "Weather: 0°F"),
])
def test_zero_degrees_is_a_temperature(weather, expected, line):
    """0 is falsy, so it read "Weather: Snow", and on its own showed no line at all."""
    info = espn_api.extract_meaningful_game_info({"gameInfo": {"weather": weather}})
    assert (info["weather"], info["temperature"]) == (expected, "0°F")
    assert espn_api.format_complex_data("gameInfo", {"weather": weather}) == line


def test_a_golfer_with_no_score_is_not_even_par(espn):
    """A null score and no rounds read "E", a score nobody shot."""
    data = load("golf_scoreboard_PGA.json")
    golfers = data["events"][0]["competitions"][0]["competitors"]
    assert golfers[1]["score"] == "E"  # ESPN's own, for a tournament not started
    golfers[0]["score"] = None
    espn.on("/scoreboard", data)
    players = espn_api.get_golf_leaderboard("PGA")["players"]
    assert [p["total_score"] for p in players] == ["", "E", "E"]


class TestNullIsNotTheWordNone:
    """.get(key, default) returns None when the key is there with a null. The sweep in
    test_missing_fields.py finds these across every function; these are the ones heard."""

    def details(self, change):
        data = load("details_NFL_pieces.json")
        change(data["header"]["competitions"][0])
        return espn_api.extract_meaningful_game_info(data)

    def test_a_null_team_name_in_the_score_line(self):
        def change(comp):
            comp["competitors"][0]["team"]["name"] = None
        assert self.details(change)["scores"][0] == "WSH: 27"

    def test_a_null_status_description(self):
        def change(comp):
            comp["status"]["type"]["description"] = None
        assert self.details(change)["status"] == "Unknown"

    def test_a_null_status_detail_is_the_value_scores_filters(self):
        def change(comp):
            comp["status"]["type"]["detail"] = None
        assert self.details(change)["detailed_status"] == "N/A"

    def test_a_null_conference_name_in_a_division(self, espn):
        data = load("standings_NHL.json")
        data["children"][0]["name"] = None
        espn.on("/nhl/standings", data)
        assert "Atlantic" in {row["division"] for row in espn_api.get_standings("NHL")}


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


@pytest.mark.parametrize("summary,expected", [
    ("8-5-1", (8, 1, "0.889", "")),   # 5 draws are not 5 losses
    ("8-0-1", (8, 1, "0.889", "")),
    ("0-9-0", (0, 0, "0.000", "")),
])
def test_a_soccer_summary_is_wins_draws_losses(espn, summary, expected):
    team = load("team_EPL_359.json")
    assert team["team"]["record"]["items"][0]["summary"] == "8-0-1"
    team["team"]["record"]["items"][0].update(summary=summary, stats=[])
    espn.on("/teams/359$", team)
    assert espn_api._get_team_record("359", "EPL") == expected
