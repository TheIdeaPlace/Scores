"""Labels and facts read from real ESPN payloads (tests/fixtures/espn)."""
import json
import os
from datetime import datetime, timezone

import pytest

import espn_api
from game_labels import (basketball_period_label, best_odds, broadcast_names,
                         football_period_label, football_period_sort_key, format_height,
                         format_weight, game_standings_tables, injured_player_count,
                         leader_display_value, local_schedule_datetime, scoreboard_today)

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


def leader_display_cases():
    path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "leader_display_grid.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["cases"]


@pytest.mark.parametrize("case", leader_display_cases(), ids=lambda case: f"{case['category']}-{case['why']}")
def test_a_leaders_number_reads_as_the_shared_grid_says(case):
    """LeaderDisplayValueGridTests in LeagueLeadersTests.swift holds the iPhone to the same grid."""
    assert leader_display_value(case["category"], case["value"], case["display"]) == case["reads"]


def test_a_value_that_is_not_a_number_falls_back_to_espns_text():
    assert leader_display_value("goals", "15", "15") == "15"
    assert leader_display_value("goals", True, "15") == "15"
    assert leader_display_value(None, 15.0, None) == "15"


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
    """The real entry from ESPN's standings, which call Utah UTA."""
    data = load("standings_NHL.json")
    monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: FakeResponse(data))
    utah = next(r for r in espn_api._get_nhl_standings_fast() if r["team_name"].startswith("Utah"))
    assert utah["abbreviation"] == "UTA"
    assert utah["division"].endswith("Central")


def test_nhl_utah_is_in_central_by_its_team_page_abbreviation_too(monkeypatch):
    data = load("standings_NHL.json")
    entry = next(e for node in data["children"] for e in node["standings"]["entries"]
                 if e["team"]["displayName"].startswith("Utah"))
    entry["team"]["abbreviation"] = "UTAH"
    monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: FakeResponse(data))
    utah = next(r for r in espn_api._get_nhl_standings_fast() if r["team_name"].startswith("Utah"))
    assert utah["division"].endswith("Central")


def test_wnba_standings_are_the_regular_season_not_the_playoffs(monkeypatch):
    data = load("standings_WNBA.json")
    urls = []

    def fake_get(url, *a, **k):
        urls.append(url)
        return FakeResponse(data)

    monkeypatch.setattr(espn_api, "_http_get", fake_get)
    rows = espn_api.get_standings("WNBA")
    assert rows
    assert all("basketball/wnba" in url for url in urls)
    assert len({r["division"] for r in rows}) == 2
    entry = next(e for node in data["children"] for e in node["standings"]["entries"])
    total = next(st for st in entry["stats"] if st.get("type") == "total")
    row = next(r for r in rows if r["team_name"] == entry["team"]["displayName"])
    assert f"{row['wins']}-{row['losses']}" == total["summary"]
    behind = next(st for st in entry["stats"] if st.get("type") == "gamesbehind")
    assert row["games_back"] == behind["displayValue"]
