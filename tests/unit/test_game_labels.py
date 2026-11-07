"""Labels and facts read from real ESPN payloads (tests/fixtures/espn)."""
import json
import os
from datetime import datetime, timezone

import pytest

import espn_api
from game_labels import (basketball_period_label, best_odds, broadcast_names,
                         football_period_label, football_period_sort_key, format_height,
                         format_weight, game_standings_tables, injured_player_count,
                         leader_display_value, local_schedule_datetime, schedule_game_is_over,
                         schedule_game_label, schedule_row_text, schedule_start_row, scoreboard_today,
                         on_todays_scoreboard)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class TestScheduleGameLabel:
    def label(self, fixture, game_id):
        return schedule_game_label(next(e for e in load(fixture)["events"] if e["id"] == game_id))

    def test_the_note_on_a_postseason_game(self):
        event = load("schedule_NFL_26_post.json")["events"][-1]
        assert event["week"]["text"] == "Super Bowl"
        assert schedule_game_label(event) == "Super Bowl LX"

    def test_the_week_where_a_preseason_game_has_no_note(self):
        assert [schedule_game_label(e) for e in load("schedule_NFL_26_pre.json")["events"]] == [
            "Preseason Week 1", "Preseason Week 2", "Preseason Week 3"]

    def test_the_season_type_where_there_is_no_week_either(self):
        assert schedule_game_label(load("schedule_WNBA_8_pre.json")["events"][0]) == "Preseason"

    def test_a_note_on_a_regular_season_game(self):
        """FCS playoffs and conference title games are filed under the regular season."""
        assert schedule_game_label(load("schedule_NCAAF_333_reg.json")["events"][0]) == "SEC Championship"

    def test_an_everyday_week_is_not_read_on_every_row(self):
        for event in load("schedule_NFL_26_reg.json")["events"]:
            assert event["week"]["text"].startswith("Week ")
            assert schedule_game_label(event) == ""

    def test_a_soccer_season_id_is_not_mistaken_for_a_postseason(self):
        for event in load("schedule_EPL_359_results.json")["events"]:
            assert event["seasonType"]["type"] > 3
            assert schedule_game_label(event) == ""

    def test_a_note_with_no_headline_is_passed_over(self):
        events = load("schedule_UCL_359_2025.json")["events"]
        bare = next(e for e in events if not any(n.get("headline") for n in e["competitions"][0]["notes"]))
        assert bare["competitions"][0]["notes"] and schedule_game_label(bare) == ""

    @pytest.mark.parametrize("event", [
        None, [], {}, {"competitions": None}, {"competitions": []}, {"competitions": [None]},
        {"competitions": [{"notes": None}]}, {"competitions": [{"notes": [None, {"headline": None}, {"headline": "  "}]}]},
        {"seasonType": None}, {"seasonType": {"type": 2, "name": "Regular Season"}},
        {"seasonType": {"type": 3}}, {"seasonType": {"type": 1, "name": None}, "week": None},
    ])
    def test_nothing_to_go_on_is_no_label(self, event):
        assert schedule_game_label(event) == ""


class TestScheduleStartRow:
    OVER = {"completed": True, "status": "Final"}
    CALLED_OFF = {"completed": False, "status": "Postponed"}
    TO_COME = {"completed": False, "status": "Scheduled"}
    TODAY = {"completed": False, "status": "Scheduled", "is_today": True}

    @pytest.mark.parametrize("current_season", [True, False])
    def test_the_next_game_to_play(self, current_season):
        rows = [self.OVER, self.CALLED_OFF, self.TO_COME, self.TO_COME]
        assert schedule_start_row(rows, current_season) == 2

    @pytest.mark.parametrize("current_season", [True, False])
    def test_todays_game_comes_first(self, current_season):
        assert schedule_start_row([self.OVER, self.TO_COME, self.TODAY, self.TO_COME], current_season) == 2

    def test_a_finished_game_today_still_counts(self):
        assert schedule_start_row([self.OVER, dict(self.OVER, is_today=True), self.TO_COME]) == 1

    def test_the_later_of_two_games_today(self):
        assert schedule_start_row([self.TODAY, self.TODAY, self.TO_COME]) == 1

    def test_a_current_season_with_nothing_left_opens_on_its_last_game_not_its_preseason(self):
        """The Lynx in December, or the Seahawks in the spring."""
        assert schedule_start_row([self.OVER, self.OVER, self.OVER], current_season=True) == 2

    def test_a_past_season_opens_at_its_start(self):
        assert schedule_start_row([self.OVER, self.OVER, self.OVER], current_season=False) == 0

    @pytest.mark.parametrize("current_season", [True, False])
    def test_no_rows(self, current_season):
        assert schedule_start_row([], current_season) == 0


class TestScheduleRowText:
    def game(self, **changes):
        game = {"date_display": "Sun, Oct 18", "opponent": "Dallas Cowboys", "home_away": "vs", "time": "Final",
                "status": "Final", "venue": "Lambeau Field", "home_score": "23", "away_score": "13", "game_id": "1",
                "is_today": False, "label": "", "completed": True, "neutral_site": False}
        game.update(changes)
        return game

    @pytest.mark.parametrize("home_away,home,away,result", [
        ("vs", "23", "13", "W 23-13"), ("vs", "13", "23", "L 13-23"),
        ("@", "23", "13", "L 13-23"), ("@", "13", "23", "W 23-13"),
        ("vs", "2", "2", "T 2-2"), ("@", "0", "0", "T 0-0"),
    ])
    def test_the_result_has_the_team_asked_for_first(self, home_away, home, away, result):
        text = schedule_row_text(self.game(home_away=home_away, home_score=home, away_score=away))
        assert text == f"Sun, Oct 18: {home_away} Dallas Cowboys - {result}"

    def test_a_finished_soccer_match_reads_as_a_result(self):
        game = self.game(status="Full Time", time="FT", home_score="1", away_score="0")
        assert schedule_row_text(game) == "Sun, Oct 18: vs Dallas Cowboys - W 1-0"

    def test_a_label_follows_the_result(self):
        assert schedule_row_text(self.game(label="Super Bowl LX")) == "Sun, Oct 18: vs Dallas Cowboys - W 23-13, Super Bowl LX"

    def test_a_label_follows_the_time_and_venue(self):
        game = self.game(completed=False, status="Scheduled", time="9/10 - 7:20 PM CDT", label="NFC Championship")
        assert schedule_row_text(game) == "Sun, Oct 18: vs Dallas Cowboys - 9/10 - 7:20 PM CDT (Lambeau Field), NFC Championship"

    def test_a_neutral_site_is_not_read_as_away_and_the_result_is_still_right(self):
        game = self.game(home_away="@", neutral_site=True, home_score="13", away_score="29")
        assert schedule_row_text(game) == "Sun, Oct 18: vs Dallas Cowboys - W 29-13"

    @pytest.mark.parametrize("home,away", [("", ""), ("", "3"), (None, "3"), ("x", "3")])
    def test_a_finished_game_with_no_usable_scores_says_its_status(self, home, away):
        assert schedule_row_text(self.game(home_score=home, away_score=away)) == "Sun, Oct 18: vs Dallas Cowboys - Final"

    @pytest.mark.parametrize("status", ["Canceled", "Cancelled", "Postponed"])
    def test_a_game_called_off_says_so_and_not_0_0(self, status):
        game = self.game(completed=False, status=status, home_score="0", away_score="0", time="9/10")
        assert schedule_row_text(game) == f"Sun, Oct 18: vs Dallas Cowboys - {status}"
        assert schedule_game_is_over(game) is True

    def test_a_game_to_come_with_no_venue_known(self):
        game = self.game(completed=False, status="Scheduled", time="TBD", venue="TBD", home_score="", away_score="")
        assert schedule_row_text(game) == "Sun, Oct 18: vs Dallas Cowboys - TBD"
        assert schedule_game_is_over(game) is False

    def test_a_game_under_way_is_not_over(self):
        assert schedule_game_is_over(self.game(completed=False, status="Halftime", time="Halftime")) is False

    def test_a_row_with_almost_nothing_still_reads(self):
        assert schedule_row_text({}) == ":  Unknown - "


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

    # ESPN's "-" and "2" read as the NBA's do.
    by_name = {r["team_name"]: r for r in rows}
    assert by_name["Atlanta Dream"]["games_back"] == "—"
    assert by_name["Washington Mystics"]["games_back"] == "2.0"
    half = {"type": "gamesbehind", "value": 2.5, "displayValue": "2.5"}
    assert espn_api._games_back(half) == "2.5"
    assert espn_api._games_back({}) == "—"
    assert espn_api._games_back({"value": "-"}) == "—"


class TestOnTodaysScoreboard:
    """Only today's games can be monitored, since Live Scores shows today."""

    @staticmethod
    def espn_date(local):
        return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    def test_a_game_this_evening_is_today(self):
        start = self.espn_date(datetime(2026, 11, 7, 18, 30))
        assert on_todays_scoreboard(start, now=datetime(2026, 11, 7, 12, 0))
        assert on_todays_scoreboard(start, now=datetime(2026, 11, 7, 23, 0))

    def test_until_5_am_last_nights_game_is_still_today(self):
        start = self.espn_date(datetime(2026, 11, 7, 21, 30))
        assert on_todays_scoreboard(start, now=datetime(2026, 11, 8, 4, 59))
        assert not on_todays_scoreboard(start, now=datetime(2026, 11, 8, 5, 0))

    def test_tomorrows_game_is_not(self):
        start = self.espn_date(datetime(2026, 11, 8, 13, 0))
        assert not on_todays_scoreboard(start, now=datetime(2026, 11, 7, 20, 0))

    @pytest.mark.parametrize("date_str", [None, "", "not a date", 5])
    def test_no_date_is_not_today(self, date_str):
        assert not on_todays_scoreboard(date_str, now=datetime(2026, 11, 7, 12, 0))
