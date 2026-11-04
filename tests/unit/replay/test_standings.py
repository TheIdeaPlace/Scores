"""Standings for every league, from real payloads, and the fallback that replaces them."""
from datetime import datetime

import pytest

import espn_api
import settings

from .support import HTTP_500, NOT_JSON, TIMEOUT, load

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
        ("NCAAF", "football/college-football/standings?group=90", "standings_NCAAF.json"),
        ("NCAAM", "basketball/mens-college-basketball/standings", "standings_NCAAM.json"),
        ("NCAAWB", "basketball/womens-college-basketball/standings", "standings_NCAAWB.json"),
        ("NCAAH", "hockey/mens-college-hockey/standings", "standings_NCAAH.json"),
        ("NCAAWH", "hockey/womens-college-hockey/standings", "standings_NCAAWH.json"),
    ])
    def test_url_and_rows(self, espn, league, path, fixture):
        espn.on("/standings", load(fixture))
        rows = espn_api.get_standings(league)
        assert espn.calls == [f"{V2}/{path}"]
        assert rows and all(r["team_name"] != "Unknown" and r["team_id"] for r in rows)

    @pytest.mark.parametrize("league,path", [
        ("WNBA", "basketball/wnba"),
        ("NCAAF", "football/college-football"),
        ("NCAAM", "basketball/mens-college-basketball"),
        ("NCAAWB", "basketball/womens-college-basketball"),
        ("NCAAH", "hockey/mens-college-hockey"),
        ("NCAAWH", "hockey/womens-college-hockey"),
    ])
    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, {"children": []}, {}],
                             ids=["timeout", "500", "not_json", "no_conferences", "nothing"])
    def test_no_standings_says_so_instead_of_asking_for_every_team(self, espn, league, path, reply):
        """The team list has no divisions, so Teams opened with no tabs and said nothing, and
        Standings was one table of playoff records, or the first 50 of a college league's teams.
        An empty answer gets the screens' "No teams data" and "No standings data" messages."""
        espn.on(f"/{path}/standings", reply)
        assert espn_api.get_standings(league) == []
        assert espn.urls("/teams") == []

    def test_the_wnba_has_its_conferences(self, espn):
        espn.on("/wnba/standings", load("standings_WNBA.json"))
        rows = espn_api.get_standings("WNBA")
        assert {r["division"] for r in rows} == {"Eastern Conference", "Western Conference"}
        assert espn.calls == [f"{V2}/basketball/wnba/standings"]

    def test_a_college_league_with_no_conferences_keeps_its_teams(self, espn):
        espn.on("/womens-college-hockey/standings", load("standings_NCAAWH.json"))
        rows = espn_api.get_standings("NCAAWH")
        assert rows and {r["division"] for r in rows} == {"NCAA Women's Hockey"}


FCS_CONFERENCES = {
    "Big Sky Conference", "Coastal Athletic Association", "FCS Independents", "Ivy League",
    "Mid-Eastern Athletic Conference", "Missouri Valley Football Conference", "Northeast Conference",
    "Ohio Valley Conference", "Patriot League", "Pioneer Football League", "Southern Conference",
    "Southland Conference", "Southwestern Athletic Conference", "United Athletic Conference",
}
FBS_CONFERENCES = {
    "American Conference", "Atlantic Coast Conference", "Big 12 Conference", "Big Ten Conference",
    "Conference USA", "FBS Independents", "Mid-American Conference", "Mountain West Conference",
    "Pac-12 Conference", "Southeastern Conference", "Sun Belt Conference",
}


class TestCollegeFootballCoverage:
    """ESPN's real group=90 answer, trimmed to a team or two in each of its conferences."""

    @pytest.fixture
    def rows(self, espn):
        espn.on("/college-football/standings", load("standings_NCAAF_group90.json"))
        return espn_api.get_standings("NCAAF")

    def test_every_conference_is_there_under_its_own_name(self, rows):
        assert {r["division"] for r in rows} == FCS_CONFERENCES | FBS_CONFERENCES

    def test_the_groupings_above_the_conferences_name_nothing(self, rows):
        assert not {r["division"] for r in rows} & {"FBS", "FCS", "NCAA Division I", "League"}

    def test_an_fcs_team_reads_its_overall_record(self, rows):
        team = row(rows, "Montana State Bobcats")
        assert (team["wins"], team["losses"], team["win_percentage"]) == (8, 1, "0.889")
        assert team["conference_record"] == "5-1"
        assert team["division"] == "Big Sky Conference"
        assert team["team_id"] == "147"

    def test_a_conference_sorts_by_record(self, rows):
        big_sky = [r["team_name"] for r in rows if r["division"] == "Big Sky Conference"]
        assert big_sky == ["Montana State Bobcats", "Montana Grizzlies"]

    def test_the_model_groups_them_for_the_tabs(self, rows):
        from models.standings import StandingsData
        divisions = StandingsData(rows).divisions
        assert FCS_CONFERENCES <= set(divisions)
        assert divisions["Big Sky Conference"][0]["record"] == "8-1"

    @pytest.mark.parametrize("coverage,group", [("all_d1", "90"), ("fbs", "80")])
    def test_the_setting_picks_the_request(self, espn, coverage, group):
        settings.set("ncaaf_coverage", coverage)
        espn.on("/college-football/standings", load("standings_NCAAF.json"))
        espn_api.get_standings("NCAAF")
        assert espn.calls == [f"{V2}/football/college-football/standings?group={group}"]

    def test_an_unknown_setting_means_all_of_division_one(self, espn):
        settings.set("ncaaf_coverage", "something else")
        espn.on("/college-football/standings", load("standings_NCAAF.json"))
        espn_api.get_standings("NCAAF")
        assert espn.calls == [f"{V2}/football/college-football/standings?group=90"]

    def test_only_college_football_sends_a_group(self, espn):
        espn.on("/mens-college-basketball/standings", load("standings_NCAAM.json"))
        espn_api.get_standings("NCAAM")
        assert "group" not in espn.calls[0]

    def test_the_sun_belts_nesting_still_gives_its_teams(self, espn):
        """FBS alone splits the Sun Belt into East and West, a level below the conferences."""
        settings.set("ncaaf_coverage", "fbs")
        espn.on("/college-football/standings", load("standings_NCAAF.json"))
        rows = espn_api.get_standings("NCAAF")
        assert row(rows, "App State Mountaineers")["division"] == "Sun Belt - East"
        assert "Sun Belt Conference" not in {r["division"] for r in rows}

    @pytest.mark.parametrize("answer", [
        TIMEOUT, HTTP_500, {"children": []}, {"children": "not a list of conferences"},
    ], ids=["timeout", "500", "no conferences", "bad payload"])
    def test_no_standings_means_no_rows_not_the_team_list(self, espn, answer):
        """/teams would be the first 50 of 762 teams, Division III included. It isn't stubbed,
        so asking for it fails the test, and the screens get to say there's no data."""
        espn.on("/college-football/standings", answer)
        assert espn_api.get_standings("NCAAF") == []
        assert espn.calls == [f"{V2}/football/college-football/standings?group=90"]

    def test_the_order_covers_fbs_and_leaves_fcs_to_follow(self):
        assert FBS_CONFERENCES <= set(espn_api.NCAAF_CONFERENCE_ORDER)
        assert not FCS_CONFERENCES & set(espn_api.NCAAF_CONFERENCE_ORDER)


class TestStandingsCacheKey:
    def test_changing_the_setting_changes_college_footballs_key(self):
        settings.set("ncaaf_coverage", "all_d1")
        everything = espn_api.standings_cache_key("NCAAF")
        settings.set("ncaaf_coverage", "fbs")
        assert espn_api.standings_cache_key("NCAAF") != everything

    def test_other_leagues_ignore_the_setting(self):
        settings.set("ncaaf_coverage", "all_d1")
        everything = espn_api.standings_cache_key("NCAAM")
        settings.set("ncaaf_coverage", "fbs")
        assert espn_api.standings_cache_key("NCAAM") == everything == "standings_NCAAM"


class TestFallbackFromTeamRecords:
    """The slow path: a teams list, then one request per team."""

    def test_wnba_reads_real_team_records(self, espn):
        espn.on("/wnba/teams$", load("teams_NBA.json"))
        espn.on(r"/wnba/teams/\d+$", load("team_WNBA_8.json"))
        rows = espn_api._get_standings_original("WNBA")
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
