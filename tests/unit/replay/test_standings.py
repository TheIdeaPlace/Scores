"""Standings for every league, from real payloads, and the fallback that replaces them."""
from datetime import datetime

import pytest
import requests

import espn_api
import settings
from exceptions import ApiError

from .support import HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, load

V2 = "https://site.api.espn.com/apis/v2/sports"
SITE = espn_api.BASE_URL


def row(rows, name):
    return next(r for r in rows if r["team_name"] == name)


class TestMlb:
    """ESPN's real level=3 answer: the 2026 season's final standings, every division."""

    @pytest.fixture
    def rows(self, espn):
        espn.on("/mlb/standings", load("standings_MLB_divisions.json"))
        return espn_api.get_standings("MLB")

    def test_url_asks_by_division(self, espn, rows):
        assert espn.calls == [f"{V2}/baseball/mlb/standings?level=3"]

    def test_a_team(self, rows):
        yankees = row(rows, "New York Yankees")
        assert (yankees["wins"], yankees["losses"], yankees["win_percentage"]) == (93, 68, "0.578")
        assert (yankees["team_id"], yankees["abbreviation"], yankees["division"]) == ("10", "NYY", "AL East")
        assert yankees["conference"] == "American League"
        assert (yankees["runs_for"], yankees["runs_against"], yankees["run_differential"]) == (739, 601, 138)
        assert (yankees["home_wins"], yankees["home_losses"], yankees["road_wins"], yankees["road_losses"]) == (46, 34, 47, 34)
        assert yankees["magic_number"] == 6
        assert yankees["logo"].endswith("/nyy.png")

    def test_streak_sign(self, rows):
        assert row(rows, "New York Yankees")["streak"] == "W1"
        assert row(rows, "Boston Red Sox")["streak"] == "L1"

    def test_games_back_is_espns_within_the_division(self, rows):
        assert row(rows, "Tampa Bay Rays")["games_back"] == "Leader"
        assert row(rows, "New York Yankees")["games_back"] == "4.5"
        assert row(rows, "Boston Red Sox")["games_back"] == "11"

    def test_divisions_come_from_the_answer(self, rows):
        """Not from a table of abbreviations: the Athletics are ATH there, OAK in the old table."""
        assert row(rows, "Chicago White Sox")["division"] == "AL Central"
        athletics = next(r for r in rows if r["abbreviation"] == "ATH")
        assert athletics["division"] == "AL West"
        assert list(dict.fromkeys(r["division"] for r in rows)) == [
            "AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]

    def test_each_division_in_standing_order(self, rows):
        """ESPN lists MLB's divisions in no order: the Yankees came before the Rays."""
        east = [r["abbreviation"] for r in rows if r["division"] == "AL East"]
        assert east == ["TB", "NYY", "BOS", "BAL", "TOR"]
        assert [r["division_rank"] for r in rows if r["division"] == "AL East"] == [1, 2, 3, 4, 5]


class TestNfl:
    """ESPN's real level=3 answer, mid-season, every division."""

    @pytest.fixture
    def rows(self, espn):
        espn.on("/nfl/standings", load("standings_NFL_divisions.json"))
        return espn_api.get_standings("NFL")

    def test_url_asks_by_division(self, espn, rows):
        assert espn.calls == [f"{V2}/football/nfl/standings?level=3"]

    def test_a_team(self, rows):
        bills = row(rows, "Buffalo Bills")
        assert (bills["wins"], bills["losses"], bills["ties"], bills["record_display"]) == (7, 1, 0, "7-1")
        assert (bills["win_percentage"], bills["streak"], bills["division"]) == ("0.875", "W4", "AFC East")
        assert (bills["points_for"], bills["points_against"], bills["point_differential"]) == (256, 187, 69)
        assert bills["playoff_seed"] == 1

    def test_a_division_leader_is_not_games_back(self, rows):
        """The bug: the conference figure had Denver 0.5 back of Buffalo while it led the AFC West."""
        assert row(rows, "Denver Broncos")["games_back"] == "Leader"
        assert row(rows, "Pittsburgh Steelers")["games_back"] == "Leader"
        assert row(rows, "Cleveland Browns")["games_back"] == "1.5"
        assert row(rows, "Kansas City Chiefs")["games_back"] == "0.5"

    def test_teams_tied_on_record_keep_espns_tiebreak(self, rows):
        north = [r["abbreviation"] for r in rows if r["division"] == "AFC North"]
        assert north == ["PIT", "CIN", "CLE", "BAL"]

    def test_the_eight_divisions_in_order(self, rows):
        assert list(dict.fromkeys(r["division"] for r in rows)) == [
            "AFC East", "AFC North", "AFC South", "AFC West", "NFC East", "NFC North", "NFC South", "NFC West"]
        assert all(len([r for r in rows if r["division"] == d]) == 4 for d in {r["division"] for r in rows})

    def test_ties_show_in_the_record(self, espn):
        data = load("standings_NFL_divisions.json")
        entry = data["children"][0]["children"][0]["standings"]["entries"][0]
        entry["stats"].append({"name": "ties", "value": 1})
        espn.on("/nfl/standings", data)
        assert any(r["record_display"].count("-") == 2 for r in espn_api.get_standings("NFL"))


class TestNba:
    def test_the_url_leaves_the_season_to_espn(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        espn.on("/nba/standings", load("standings_NBA_divisions.json"))
        espn_api.get_standings("NBA")
        assert espn.calls == [f"{V2}/basketball/nba/standings?level=3"]

    def test_a_team(self, espn):
        espn.on("/nba/standings", load("standings_NBA_divisions.json"))
        nets = row(espn_api.get_standings("NBA"), "Brooklyn Nets")
        assert (nets["wins"], nets["losses"], nets["win_percentage"]) == (3, 8, "0.273")
        assert (nets["division"], nets["streak"], nets["playoff_seed"]) == ("Atlantic", "W1", 13)
        assert nets["conference"] == "Eastern Conference"
        assert nets["avg_points_for"] == pytest.approx(110.181816)
        assert nets["clinch_status"] is None

    def test_divisions_in_standing_order_with_their_own_games_back(self, espn):
        """ESPN lists the NBA's divisions worst first, and its default answer counts games back
        from the conference leader: Milwaukee read 9 back, not 7.5."""
        espn.on("/nba/standings", load("standings_NBA_divisions.json"))
        rows = espn_api.get_standings("NBA")
        central = [(r["abbreviation"], r["games_back"]) for r in rows if r["division"] == "Central"]
        assert central == [("DET", "Leader"), ("CLE", "2.5"), ("IND", "4.5"), ("CHI", "6.5"), ("MIL", "7.5")]
        assert list(dict.fromkeys(r["division"] for r in rows)) == [
            "Atlantic", "Central", "Southeast", "Northwest", "Pacific", "Southwest"]

    def test_no_entries_yet_lists_the_teams_at_0_0(self, espn):
        """A new season, before ESPN has standings."""
        espn.on("/nba/standings", {"children": [{"name": "Eastern Conference", "standings": {"entries": []}}]})
        espn.on("/nba/teams$", load("teams_NBA.json"))
        rows = espn_api.get_standings("NBA")
        assert [r["team_name"] for r in rows] == ["Boston Celtics", "Brooklyn Nets", "Atlanta Hawks"]
        hawks = row(rows, "Atlanta Hawks")
        assert (hawks["division"], hawks["wins"], hawks["win_percentage"], hawks["games_back"]) == (
            "Southeast", 0, "0.000", "Leader")
        assert hawks["logo"].endswith("atl.png")

    @pytest.mark.parametrize("teams", [{"sports": []}, {"sports": [None]}], ids=["none", "unreadable"])
    def test_fresh_standings_with_no_teams_are_empty(self, espn, teams):
        espn.on("/nba/standings", {"children": []})
        espn.on("/nba/teams$", teams)
        assert espn_api.get_standings("NBA") == []

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_fresh_standings_failing_say_so(self, espn, reply):
        espn.on("/nba/standings", {"children": []})
        espn.on("/nba/teams$", reply)
        with pytest.raises(ApiError, match="standings"):
            espn_api.get_standings("NBA")


class TestNhl:
    @pytest.fixture
    def rows(self, espn):
        espn.on("/nhl/standings", load("standings_NHL_divisions.json"))
        return espn_api.get_standings("NHL")

    def test_url_asks_by_division(self, espn, rows):
        assert espn.calls == [f"{V2}/hockey/nhl/standings?level=3"]

    def test_a_team_ranks_on_points(self, rows):
        bruins = row(rows, "Boston Bruins")
        assert (bruins["wins"], bruins["losses"], bruins["ot_losses"], bruins["points"]) == (13, 5, 1, 27)
        assert bruins["win_percentage"] == "0.711"  # 27 of a possible 38
        assert (bruins["goals_for"], bruins["goals_against"], bruins["goal_differential"]) == (70, 46, 24)
        assert (bruins["division"], bruins["streak"], bruins["playoff_seed"]) == ("Atlantic", "L1", 5)
        assert bruins["games_back"] == ""

    def test_each_division_by_points_with_espns_tiebreak(self, rows):
        """Tampa Bay and Montreal both have 28 points; ESPN's seed puts Tampa Bay first."""
        atlantic = [(r["abbreviation"], r["points"]) for r in rows if r["division"] == "Atlantic"]
        assert atlantic[:3] == [("TB", 28), ("MTL", 28), ("BOS", 27)]
        for division in {r["division"] for r in rows}:
            points = [r["points"] for r in rows if r["division"] == division]
            assert points == sorted(points, reverse=True)
        assert list(dict.fromkeys(r["division"] for r in rows)) == ["Atlantic", "Metropolitan", "Central", "Pacific"]

NO_FALLBACK = [
    ("WNBA", "basketball/wnba"),
    ("NCAAF", "football/college-football"),
    ("NCAAM", "basketball/mens-college-basketball"),
    ("NCAAWB", "basketball/womens-college-basketball"),
    ("NCAAH", "hockey/mens-college-hockey"),
    ("NCAAWH", "hockey/womens-college-hockey"),
]


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

    @pytest.mark.parametrize("league,path", NO_FALLBACK)
    @pytest.mark.parametrize("reply", [{"children": []}, {}], ids=["no_conferences", "nothing"])
    def test_no_standings_says_so_instead_of_asking_for_every_team(self, espn, league, path, reply):
        """The team list has no divisions, so Teams opened with no tabs and said nothing, and
        Standings was one table of playoff records, or the first 50 of a college league's teams.
        An empty answer gets the screens' "No teams data" and "No standings data" messages."""
        espn.on(f"/{path}/standings", reply)
        assert espn_api.get_standings(league) == []
        assert espn.urls("/teams") == []

    @pytest.mark.parametrize("league,path", NO_FALLBACK)
    @pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON, []],
                             ids=["timeout", "connection", "404", "500", "not_json", "a_list"])
    def test_a_failed_request_is_not_no_data(self, espn, league, path, reply):
        """It says so in a sentence, not with the text of a requests exception."""
        espn.on(f"/{path}/standings", reply)
        with pytest.raises(ApiError) as caught:
            espn_api.get_standings(league)
        assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE
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

    @pytest.mark.parametrize("answer", [{"children": []}, {"children": "not a list of conferences"}],
                             ids=["no conferences", "bad payload"])
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
        assert rows[0]["games_back"] == "Leader"
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
        assert row(rows, "Yankees")["games_back"] == "Leader"
        assert row(rows, "Red Sox")["games_back"] == "5"
        assert row(rows, "Blue Jays")["games_back"] == "0.5"
        athletics = row(rows, "Athletics")
        assert (athletics["division"], athletics["games_back"]) == ("AL West", "Leader")

    @pytest.mark.parametrize("data", [{}, {"sports": []}, {"sports": [{"leagues": []}]}])
    def test_no_teams(self, data):
        assert espn_api._parse_standings_from_teams_api(data, "NBA") == []

    def test_an_unknown_league_requests_nothing(self, espn):
        assert espn_api.get_standings("CRICKET") == []
        assert espn.calls == []

    @pytest.mark.parametrize("league,path", [("MLB", "baseball/mlb"), ("NFL", "football/nfl"),
                                             ("NBA", "basketball/nba"), ("NHL", "hockey/nhl")])
    def test_something_else_where_the_conferences_belong_is_not_an_answer(self, espn, league, path):
        """It says the standings couldn't be loaded, rather than one request per team."""
        espn.on(f"/{path}/standings", {"children": "not a list of conferences"})
        with pytest.raises(ApiError) as caught:
            espn_api.get_standings(league)
        assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE
        assert espn.urls("/teams") == []

    @pytest.mark.parametrize("league,path", [("MLB", "baseball/mlb"), ("NFL", "football/nfl"),
                                             ("NBA", "basketball/nba"), ("NHL", "hockey/nhl")])
    def test_each_fast_path_falling_over_uses_the_teams(self, espn, monkeypatch, league, path):
        """A crash while reading the answer, not a failed request: it catches and falls back."""
        def broken(*args, **kwargs):
            raise KeyError("boom")
        monkeypatch.setattr(espn_api, "_division_rows", broken)
        espn.on(f"/{path}/standings", load("standings_NFL_divisions.json"))
        espn.on(f"/{path}/teams$", {"sports": []})
        assert espn_api.get_standings(league) == []
        assert espn.calls[-1] == f"{SITE}/{path}/teams"

    @pytest.mark.parametrize("league,path", [("MLB", "baseball/mlb"), ("NFL", "football/nfl"), ("NHL", "hockey/nhl")])
    def test_conferences_only_still_list_every_team(self, espn, league, path):
        """If ESPN ever ignores level=3, the conferences are the groups, with their own games back."""
        espn.on(f"/{path}/standings", load("standings_NFL.json"))
        rows = espn_api.get_standings(league)
        assert {r["division"] for r in rows} == {"American Football Conference", "National Football Conference"}
        assert len(rows) == 6


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
    espn.on("/nfl/standings", load("standings_NFL_divisions.json"))
    data = StandingsData(espn_api.get_standings("NFL"))
    east = data.divisions["AFC East"]
    assert east[0]["team_name"] == "Buffalo Bills"
    assert east[0]["record"] == "7-1"
    # The model keeps ESPN's order rather than sorting on record.
    assert [t["abbreviation"] for t in data.divisions["AFC North"]] == ["PIT", "CIN", "CLE", "BAL"]


def test_the_model_keeps_espns_order_over_the_record():
    """Two teams tied on record stay as ESPN ranks them; a sort on percentage would swap them."""
    from models.standings import StandingsData
    rows = [{"team_name": "Second", "wins": 6, "losses": 2, "win_percentage": "0.750", "division": "D", "division_rank": 1},
            {"team_name": "First", "wins": 7, "losses": 1, "win_percentage": "0.875", "division": "D", "division_rank": 2}]
    assert [t["team_name"] for t in StandingsData(rows).divisions["D"]] == ["Second", "First"]
