"""Labels and facts read from real ESPN payloads (tests/fixtures/espn)."""
import json
import os
from datetime import datetime, timezone

import pytest

import espn_api
from game_labels import (basketball_period_label, best_odds, broadcast_names,
                         football_period_label, football_period_sort_key, format_height,
                         format_weight, game_standings_tables, injured_player_count,
                         local_schedule_datetime, scoreboard_today)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("league,period,label", [
    ("NCAAM", 1, "1st Half"), ("NCAAM", 2, "2nd Half"), ("NCAAM", 3, "OT"), ("NCAAM", 4, "2OT"), ("NCAAM", 5, "3OT"),
    ("NCAAWB", 1, "1st Quarter"), ("NCAAWB", 4, "4th Quarter"), ("NCAAWB", 5, "OT"), ("NCAAWB", 6, "2OT"),
    ("NBA", 3, "3rd Quarter"), ("NBA", 5, "OT"), ("WNBA", 6, "2OT"),
])
def test_basketball_periods(league, period, label):
    assert basketball_period_label(league, period) == label


def test_football_overtime_follows_the_fourth_quarter():
    labels = [football_period_label(n) for n in (6, 1, 5, 4, 7)]
    assert labels == ["2OT", "Quarter 1", "OT", "Quarter 4", "3OT"]
    assert sorted(labels, key=football_period_sort_key) == ["Quarter 1", "Quarter 4", "OT", "2OT", "3OT"]
    assert football_period_label("?") == "Unknown Quarter"


def test_broadcasts_in_both_forms():
    assert broadcast_names([{"names": ["ESPN", "ABC"]}]) == ["ESPN", "ABC"]
    assert broadcast_names([{"media": {"shortName": "NESN"}}, {"station": "Scripps"},
                            {"media": {"shortName": "NESN"}}]) == ["NESN", "Scripps"]
    assert broadcast_names([], [{"media": {"shortName": "NBCSN"}}]) == ["NBCSN"]
    assert broadcast_names(None, []) == []


def test_injuries_counts_players_not_teams():
    teams = [{"injuries": [{}, {}, {}]}, {"injuries": [{}]}]
    assert injured_player_count(teams) == 4
    assert injured_player_count(None) == 0


def test_odds_come_from_pickcenter_when_odds_is_empty():
    assert best_odds({"odds": [], "pickcenter": [{"details": "CLE -4.5", "overUnder": 229.5}]})["details"] == "CLE -4.5"
    assert best_odds({"odds": [{"details": "A -1"}]})["details"] == "A -1"
    assert best_odds({}) == {}


def test_evening_game_keeps_its_local_date():
    """7 PM Central on Nov 2 is Nov 3 in UTC."""
    utc = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
    result = local_schedule_datetime("2026-11-03T01:00Z")
    assert result == utc.astimezone().replace(tzinfo=None)
    assert result.tzinfo is None


def test_game_without_a_set_time_keeps_espns_date():
    assert local_schedule_datetime("2026-11-07T05:00Z", time_valid=False) == datetime(2026, 11, 7, 5, 0)


@pytest.mark.parametrize("raw,expected", [(77.0, "6'5\""), (77, "6'5\""), ("72", "6'0\""), (None, ""), (0, ""), ("x", "")])
def test_height(raw, expected):
    assert format_height(raw) == expected


@pytest.mark.parametrize("raw,expected", [(325.0, "325 lbs"), (200, "200 lbs"), (None, ""), (0, "")])
def test_weight(raw, expected):
    assert format_weight(raw) == expected


def test_game_summary_standings():
    data = load("game_standings_NFL.json")["standings"]
    tables = game_standings_tables(data)
    assert tables[0]["title"] == data["groups"][0]["header"]
    assert tables[0]["headers"][0] == "Team"
    assert tables[0]["rows"]
    assert all(len(row) == len(tables[0]["headers"]) for row in tables[0]["rows"])
    assert game_standings_tables(None) == []


class TestCollegeStandings:
    def team(self, league, name):
        rows = espn_api.parse_college_standings(load(f"standings_{league}.json"))
        return next(r for r in rows if r["team_name"] == name)

    def test_overall_record_not_the_last_split(self):
        utsa = self.team("NCAAF", "UTSA Roadrunners")
        assert (utsa["wins"], utsa["losses"]) == (7, 1)
        assert utsa["win_percentage"] == "0.875"
        assert utsa["conference_record"] == "4-0"
        assert utsa["streak"] == "W5"

    def test_sun_belt_nesting(self):
        rows = espn_api.parse_college_standings(load("standings_NCAAF.json"))
        assert any("Sun Belt" in r["division"] for r in rows)

    def test_entries_at_the_root_with_ties(self):
        yale = self.team("NCAAWH", "Yale Bulldogs")
        assert (yale["wins"], yale["losses"], yale["ties"]) == (2, 1, 1)

    def test_empty(self):
        assert espn_api.parse_college_standings({}) == []


def test_statistics_never_invented():
    assert espn_api._get_sample_statistics_data("NBA") == {"player_stats": [], "team_stats": []}


@pytest.mark.parametrize("league", ["NFL", "NHL"])
def test_list_shaped_player_statistics_parse(league):
    stats = load(f"statistics_{league}.json")["stats"]["categories"]
    categories = espn_api._parse_generic_player_stats(stats)
    assert len(categories) >= 2  # the fixture is trimmed
    assert categories[0]["stats"]


@pytest.mark.parametrize("now,day", [
    (datetime(2026, 11, 3, 0, 12), "2026-11-02"),
    (datetime(2026, 11, 3, 4, 59), "2026-11-02"),
    (datetime(2026, 11, 3, 5, 0), "2026-11-03"),
    (datetime(2026, 11, 2, 23, 0), "2026-11-02"),
])
def test_scoreboard_day_runs_past_midnight(now, day):
    assert scoreboard_today(now).isoformat() == day


class FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.mark.parametrize("league,parser", [("NFL", "_get_nfl_standings_fast"), ("NBA", "_get_nba_standings_fast")])
def test_games_back_is_computed(monkeypatch, league, parser):
    monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: FakeResponse(load(f"standings_{league}.json")))
    rows = getattr(espn_api, parser)()
    assert rows
    by_division = {}
    for row in rows:
        by_division.setdefault(row["division"], []).append(row)
    leaders = [teams[0]["games_back"] for teams in by_division.values()]
    assert all(gb == "—" for gb in leaders), leaders
    assert any(row["games_back"] not in ("—", "0.0", "") for row in rows)


def test_streak_on_pro_standings(monkeypatch):
    monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: FakeResponse(load("standings_NFL.json")))
    assert any(row["streak"] for row in espn_api._get_nfl_standings_fast())


def test_nhl_utah_is_in_central(monkeypatch):
    data = load("standings_NHL.json")
    # The fixture is trimmed, so one of its teams plays Utah's part.
    entry = data["children"][0]["standings"]["entries"][0]
    entry["team"]["abbreviation"] = "UTAH"
    monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: FakeResponse(data))
    utah = next(r for r in espn_api._get_nhl_standings_fast() if r["abbreviation"] == "UTAH")
    assert utah["division"].endswith("Central")
