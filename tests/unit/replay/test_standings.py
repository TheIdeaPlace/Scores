"""Standings for every league, from real payloads, and the fallback that replaces them."""
from datetime import datetime

import pytest

import espn_api

from .support import HTTP_500, TIMEOUT, load

V2 = "https://site.api.espn.com/apis/v2/sports"
SITE = espn_api.BASE_URL


def row(rows, name):
    return next(r for r in rows if r["team_name"] == name)


class TestMlb:
    @pytest.fixture
    def rows(self, espn):
        espn.on("/mlb/standings", load("standings_MLB.json"))
        return espn_api.get_standings("MLB")

    def test_url(self, espn, rows):
        assert espn.calls == [f"{V2}/baseball/mlb/standings"]

    def test_a_team(self, rows):
        yankees = row(rows, "New York Yankees")
        assert (yankees["wins"], yankees["losses"], yankees["win_percentage"]) == (93, 68, "0.578")
        assert (yankees["team_id"], yankees["abbreviation"], yankees["division"]) == ("10", "NYY", "AL East")
        assert (yankees["runs_for"], yankees["runs_against"], yankees["run_differential"]) == (739, 601, 138)
        assert (yankees["home_wins"], yankees["home_losses"], yankees["road_wins"], yankees["road_losses"]) == (46, 34, 47, 34)
        assert yankees["magic_number"] == 6
        assert yankees["logo"].endswith("/nyy.png")

    def test_streak_sign(self, rows):
        assert row(rows, "New York Yankees")["streak"] == "W1"
        assert row(rows, "Boston Red Sox")["streak"] == "L1"

    def test_games_back_within_a_division(self, rows):
        assert row(rows, "New York Yankees")["games_back"] == "—"
        assert row(rows, "Boston Red Sox")["games_back"] == "6.5"  # (93-87 + 75-68) / 2

    def test_divisions_cover_the_abbreviations_espn_uses(self, rows):
        assert row(rows, "Chicago White Sox")["division"] == "AL Central"
        athletics = next(r for r in rows if r["abbreviation"] == "ATH")
        assert athletics["division"] == "AL West"
        assert {r["division"] for r in rows} >= {"AL East", "AL Central", "AL West", "NL East", "NL West"}

    def test_sorted_by_division_then_wins(self, rows):
        keys = [(r["division"], -r["wins"]) for r in rows]
        assert keys == sorted(keys)

    def test_an_unknown_team_goes_to_its_league(self):
        assert espn_api._get_team_division("XXX", "American") == "American League"


class TestNfl:
    @pytest.fixture
    def rows(self, espn):
        espn.on("/nfl/standings", load("standings_NFL.json"))
        return espn_api.get_standings("NFL")

    def test_url(self, espn, rows):
        assert espn.calls == [f"{V2}/football/nfl/standings"]

    def test_a_team(self, rows):
        bills = row(rows, "Buffalo Bills")
        assert (bills["wins"], bills["losses"], bills["ties"], bills["record_display"]) == (6, 1, 0, "6-1")
        assert (bills["win_percentage"], bills["streak"], bills["division"]) == ("0.857", "W3", "AFC East")
        assert (bills["points_for"], bills["points_against"], bills["point_differential"]) == (233, 181, 52)
        assert bills["playoff_seed"] == 1

    def test_every_real_team_has_a_division(self, rows):
        assert rows and all(r["division"] != "Unknown Division" for r in rows)

    def test_ties_show_in_the_record(self, espn):
        data = load("standings_NFL.json")
        entry = data["children"][0]["standings"]["entries"][0]
        entry["stats"].append({"name": "ties", "value": 1})
        espn.on("/nfl/standings", data)
        assert any(r["record_display"].count("-") == 2 for r in espn_api.get_standings("NFL"))


class TestNba:
    def test_the_url_names_the_season(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        espn.on("/nba/standings", load("standings_NBA.json"))
        espn_api.get_standings("NBA")
        assert espn.calls == [f"{V2}/basketball/nba/standings?season=2027"]

    def test_a_team(self, espn):
        espn.on("/nba/standings", load("standings_NBA.json"))
        nets = row(espn_api.get_standings("NBA"), "Brooklyn Nets")
        assert (nets["wins"], nets["losses"], nets["win_percentage"]) == (1, 5, "0.167")
        assert (nets["division"], nets["streak"], nets["playoff_seed"]) == ("Eastern Conference Atlantic", "W1", 15)
        assert nets["avg_points_for"] == pytest.approx(108.166664)
        assert nets["clinch_status"] is None

    def test_every_real_team_has_a_division(self, espn):
        espn.on("/nba/standings", load("standings_NBA.json"))
        rows = espn_api.get_standings("NBA")
        assert rows and all(r["division"].split(" Conference ")[-1] != r["division"] for r in rows)

    def test_no_entries_yet_lists_the_teams_at_0_0(self, espn):
        """A new season, before ESPN has standings."""
        espn.on("/nba/standings", {"children": [{"name": "Eastern Conference", "standings": {"entries": []}}]})
        espn.on("/nba/teams$", load("teams_NBA.json"))
        rows = espn_api.get_standings("NBA")
        assert [r["team_name"] for r in rows] == ["Boston Celtics", "Brooklyn Nets", "Atlanta Hawks"]
        hawks = row(rows, "Atlanta Hawks")
        assert (hawks["division"], hawks["wins"], hawks["win_percentage"], hawks["games_back"]) == (
            "Eastern Conference Southeast", 0, "0.000", "—")
        assert hawks["logo"].endswith("atl.png")

    @pytest.mark.parametrize("reply", [HTTP_500, {"sports": []}, TIMEOUT])
    def test_fresh_standings_fail_empty(self, espn, reply):
        espn.on("/nba/standings", {"children": []})
        espn.on("/nba/teams$", reply)
        assert espn_api.get_standings("NBA") == []


class TestNhl:
    @pytest.fixture
    def rows(self, espn):
        espn.on("/nhl/standings", load("standings_NHL.json"))
        return espn_api.get_standings("NHL")

    def test_url(self, espn, rows):
        assert espn.calls == [f"{V2}/hockey/nhl/standings"]

    def test_a_team_ranks_on_points(self, rows):
        bruins = row(rows, "Boston Bruins")
        assert (bruins["wins"], bruins["losses"], bruins["ot_losses"], bruins["points"]) == (10, 4, 1, 21)
        assert bruins["win_percentage"] == "0.700"  # 21 of a possible 30
        assert (bruins["goals_for"], bruins["goals_against"], bruins["goal_differential"]) == (55, 36, 19)
        assert (bruins["division"], bruins["streak"], bruins["playoff_seed"]) == ("Eastern Conference Atlantic", "W1", 2)

    def test_sorted_by_division_then_points(self, rows):
        keys = [(r["division"], -r["points"]) for r in rows]
        assert keys == sorted(keys)


class TestCollege:
    @pytest.mark.parametrize("league,path,fixture", [
        ("NCAAF", "football/college-football", "standings_NCAAF.json"),
        ("NCAAM", "basketball/mens-college-basketball", "standings_NCAAM.json"),
        ("NCAAWB", "basketball/womens-college-basketball", "standings_NCAAWB.json"),
        ("NCAAH", "hockey/mens-college-hockey", "standings_NCAAH.json"),
        ("NCAAWH", "hockey/womens-college-hockey", "standings_NCAAWH.json"),
    ])
    def test_url_and_rows(self, espn, league, path, fixture):
        espn.on("/standings", load(fixture))
        rows = espn_api.get_standings(league)
        assert espn.calls == [f"{V2}/{path}/standings"]
        assert rows and all(r["team_name"] != "Unknown" and r["team_id"] for r in rows)

    def test_no_rows_falls_back_to_team_records(self, espn):
        espn.on("/mens-college-hockey/standings", {"children": []})
        espn.on("/mens-college-hockey/teams$", {"sports": []})
        assert espn_api.get_standings("NCAAH") == []
        assert espn.calls[-1] == f"{SITE}/hockey/mens-college-hockey/teams"

    def test_a_timeout_falls_back_too(self, espn):
        espn.on("/mens-college-hockey/standings", TIMEOUT)
        espn.on("/mens-college-hockey/teams$", {"sports": []})
        assert espn_api.get_standings("NCAAH") == []


class TestFallbackFromTeamRecords:
    """The slow path: a teams list, then one request per team."""

    def test_wnba_reads_real_team_records(self, espn):
        espn.on("/wnba/teams$", load("teams_NBA.json"))
        espn.on(r"/wnba/teams/\d+$", load("team_WNBA_8.json"))
        rows = espn_api.get_standings("WNBA")
        assert espn.urls("/teams/") == [f"{SITE}/basketball/wnba/teams/{i}" for i in ("1", "2", "17")]
        assert all((r["wins"], r["losses"], r["win_percentage"], r["streak"]) == (0, 2, "0.000", "L2") for r in rows)
        assert {r["division"] for r in rows} == {"League"}
        assert rows[0]["games_back"] == "—"
        assert rows[0]["logo"]

    def test_games_back_in_the_division(self, espn):
        teams = {"sports": [{"leagues": [{"teams": [
            {"team": {"id": "1", "abbreviation": "NYY", "displayName": "Yankees"}},
            {"team": {"id": "2", "abbreviation": "BOS", "displayName": "Red Sox"}},
            {"team": {"id": "3", "abbreviation": "TOR", "displayName": "Blue Jays"}},
            {"team": {"id": "4", "abbreviation": "ATH", "displayName": "Athletics"}},
        ]}]}]}
        records = {"1": "90-70", "2": "85-75", "3": "90-71", "4": "70-90"}
        espn.on("/mlb/teams$", teams)
        espn.on(r"/mlb/teams/\d+$", lambda url: {"team": {"record": {"items": [
            {"type": "total", "summary": records[url.rsplit("/", 1)[1]]}]}}})
        rows = espn_api._get_standings_original("MLB")
        assert row(rows, "Yankees")["games_back"] == "—"
        assert row(rows, "Red Sox")["games_back"] == "5.0"
        assert row(rows, "Blue Jays")["games_back"] == "0.5"
        athletics = row(rows, "Athletics")
        assert (athletics["division"], athletics["games_back"]) == ("AL West", "—")

    @pytest.mark.parametrize("data", [{}, {"sports": []}, {"sports": [{"leagues": []}]}])
    def test_no_teams(self, data):
        assert espn_api._parse_standings_from_teams_api(data, "NBA") == []

    def test_an_unknown_league_requests_nothing(self, espn):
        assert espn_api.get_standings("CRICKET") == []
        assert espn.calls == []

    def test_the_fast_path_falling_over_uses_the_teams(self, espn):
        """A bad payload in the fast path, not a failed request: it catches and falls back."""
        espn.on("/nfl/standings", {"children": "not a list of conferences"})
        espn.on("/nfl/teams$", {"sports": []})
        assert espn_api.get_standings("NFL") == []
        assert espn.calls == [f"{V2}/football/nfl/standings", f"{SITE}/football/nfl/teams"]

    @pytest.mark.parametrize("league,path", [("MLB", "baseball/mlb"), ("NBA", "basketball/nba"), ("NHL", "hockey/nhl")])
    def test_each_fast_path_falls_back(self, espn, league, path):
        espn.on(f"/{path}/standings", {"children": "not a list of conferences"})
        espn.on(f"/{path}/teams$", {"sports": []})
        assert espn_api.get_standings(league) == []
        assert espn.calls[-1] == f"{SITE}/{path}/teams"


class TestTeamRecord:
    def record(self, espn, payload):
        espn.on("/teams/1$", payload)
        return espn_api._get_team_record("1", "NBA")

    def items(self, *items):
        return {"team": {"record": {"items": list(items)}}}

    def test_streaks(self, espn):
        win = self.items({"type": "total", "summary": "5-2", "stats": [{"name": "streak", "value": 3}]})
        assert self.record(espn, win) == (5, 2, "0.714", "W3")
        loss = self.items({"type": "total", "summary": "5-2", "stats": [{"name": "streak", "value": -2}]})
        assert self.record(espn, loss) == (5, 2, "0.714", "L2")

    def test_no_games_yet(self, espn):
        assert self.record(espn, self.items({"type": "total", "summary": "0-0"})) == (0, 0, "0.000", "")

    def test_no_total_row(self, espn):
        assert self.record(espn, self.items({"type": "home", "summary": "1-1"})) == (0, 0, "0.000", "")

    def test_nothing_to_ask_about(self, espn):
        assert espn_api._get_team_record("", "NBA") == (0, 0, "0.000", "")
        assert espn_api._get_team_record("1", "CRICKET") == (0, 0, "0.000", "")
        assert espn.calls == []


def test_get_standings_returns_rows_the_standings_model_accepts(espn):
    """The screen wraps these in StandingsData, so the two have to agree."""
    from models.standings import StandingsData
    espn.on("/nfl/standings", load("standings_NFL.json"))
    data = StandingsData(espn_api.get_standings("NFL"))
    east = data.divisions["AFC East"]
    assert east[0]["team_name"] == "Buffalo Bills"
    assert east[0]["record"] == "6-1"
