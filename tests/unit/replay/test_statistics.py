"""Statistics on real payloads. Sample players used to fill these gaps: never again."""
import copy
from datetime import datetime

import pytest
import requests

import espn_api

from exceptions import ApiError
from services.api_service import ApiService

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, FakeResponse, load

SITE = espn_api.BASE_URL
LEADERS = espn_api.LEADERS_BASE_URL
NOTHING = {"player_stats": [], "team_stats": []}


def with_season_type(fixture, season_type):
    """A real season as ESPN would send it at another point in the year."""
    season = load(fixture)
    season["type"]["type"] = season_type
    return season


def by_category(result):
    return {c["category"]: c["stats"] for c in result["player_stats"]}


@pytest.fixture(autouse=True)
def pauses(monkeypatch):
    seen = []
    monkeypatch.setattr(espn_api.time, "sleep", seen.append)
    return seen


@pytest.fixture
def nba(espn):
    espn.on("/season$", load("season_NBA.json"))
    return espn


class TestWhichSeason:
    def test_the_url(self, nba):
        """Asked with no region or language, ESPN fails far more often, even at 20."""
        nba.on("/leaders", load("leaders_v3_NBA.json"))
        espn_api.get_player_statistics("NBA")
        assert nba.calls == [
            "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/season",
            f"{LEADERS}/basketball/nba/leaders?region=us&lang=en&season=2027&seasontype=2&limit=20",
        ]

    def test_not_the_calendar_year(self, nba, freeze_now):
        freeze_now(datetime(2026, 11, 4))
        nba.on("/leaders", load("leaders_v3_NBA.json"))
        espn_api.get_player_statistics("NBA")
        assert "season=2027" in nba.calls[1]

    def test_the_playoffs_show_that_seasons_regular_season(self, espn):
        """The real WNBA season, in its playoffs. Left to itself ESPN answers with those."""
        espn.on("/season$", load("season_WNBA.json")).on("/leaders", load("leaders_v3_NBA.json"))
        espn_api.get_player_statistics("WNBA")
        assert "season=2026&seasontype=2" in espn.calls[1]

    def test_the_off_season_is_filed_under_the_season_just_played(self, espn):
        espn.on("/season$", with_season_type("season_NFL.json", 4)).on("/leaders", load("leaders_v3_NFL.json"))
        espn_api.get_player_statistics("NFL")
        assert "season=2026&seasontype=2" in espn.calls[1]

    def test_a_preseason_shows_the_last_regular_season(self, espn):
        espn.on("/season$", with_season_type("season_NBA.json", 1)).on("/leaders", load("leaders_v3_NBA.json"))
        espn_api.get_player_statistics("NBA")
        assert "season=2026&seasontype=2" in espn.calls[1]
        assert len(espn.urls("/leaders")) == 1

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_404, HTTP_500, NOT_JSON, EMPTY_JSON, {"year": None}, {"year": "2027"}],
                             ids=["timeout", "404", "500", "not_json", "empty", "null", "text"])
    def test_not_knowing_the_season_is_a_failure_not_a_guess(self, espn, reply):
        espn.on("/season$", reply)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NBA")
        assert not espn.urls("/leaders")

    def test_a_regular_season_with_nobody_on_the_list_yet_shows_the_last_one(self, nba):
        empty = load("leaders_v3_NBA.json")
        empty["leaders"]["categories"] = []
        nba.on("/leaders", lambda url: empty if "season=2027" in url else load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["player_stats"]
        assert len(nba.urls("/leaders")) == 2

    def test_a_season_espn_does_not_have_yet_shows_the_last_one(self, nba):
        """ESPN's real answer for a season not begun, for most leagues."""
        nba.on("/leaders", lambda url: HTTP_404 if "season=2027" in url else load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["player_stats"]

    def test_nobody_on_the_list_in_either_season_is_no_leaders(self, nba):
        nba.on("/leaders", {"leaders": {"categories": []}})
        assert espn_api.get_player_statistics("NBA") == NOTHING
        assert len(nba.urls("/leaders")) == 2

    def test_no_season_on_file_this_year_or_last_is_a_failure(self, nba):
        nba.on("/leaders", HTTP_404)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NBA")


class TestRealLeaders:
    @pytest.mark.parametrize("league,fixture,season,category,first,value,team", [
        # 509 and 4 are what /statistics showed as these leaders, from the preseason.
        ("NFL", "leaders_v3_NFL.json", "season_NFL.json", "Passing Yards", "Jordan Love", "2246", "GB"),
        ("NHL", "leaders_v3_NHL.json", "season_NBA.json", "Goals", "Kirill Kaprizov", "15", "MIN"),
        ("NBA", "leaders_v3_NBA.json", "season_NBA.json", "Points Per Game", "Luka Doncic", "38.3", "LAL"),
        ("NCAAM", "leaders_v3_NCAAM.json", "season_NBA.json", "Points Per Game", "Zander Carter", "21.0", "LIB"),
    ])
    def test_the_rows_the_dialog_reads(self, espn, league, fixture, season, category, first, value, team):
        espn.on("/season$", load(season)).on("/leaders", load(fixture))
        result = espn_api.get_player_statistics(league)
        assert result["team_stats"] == []
        assert by_category(result)[category][0] == {
            "player_name": first, "team": team, "value": value, "stat_name": category}

    def test_they_match_the_core_apis_regular_season_and_not_its_preseason(self, espn):
        espn.on("/season$", load("season_NFL.json")).on("/leaders", load("leaders_v3_NFL.json"))
        rows = by_category(espn_api.get_player_statistics("NFL"))["Passing Yards"]

        def passing(fixture):
            return next(c for c in load(fixture)["categories"] if c["name"] == "passingYards")["leaders"]

        assert [float(r["value"]) for r in rows] == [x["value"] for x in passing("leaders_core_NFL_regular.json")[:2]]
        assert float(rows[0]["value"]) != passing("leaders_core_NFL_preseason.json")[0]["value"]

    def test_espns_order_is_kept_so_low_is_good_reads_best_first(self, espn):
        espn.on("/season$", load("season_NBA.json")).on("/leaders", load("leaders_v3_NHL.json"))
        rows = by_category(espn_api.get_player_statistics("NHL"))["Goals Against Average"]
        assert [r["value"] for r in rows] == ["1.33", "1.49"]

    def test_says_what_season_they_are_from(self, nba):
        nba.on("/leaders", load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["season"] == "2026-27 Regular Season"

    def test_a_past_college_football_season_says_season_since_it_runs_through_the_bowls(self, espn):
        """ESPN answers seasontype=2 for 2025 with type 3: 4379 yards, where core's type 2 says 4129."""
        data = load("leaders_v3_NCAAF_2025.json")
        assert data["requestedSeason"]["type"]["type"] == 3, "the fixture should show the problem"
        espn.on("/season$", load("season_NFL.json")).on("/leaders", data)
        result = espn_api.get_player_statistics("NCAAF")
        assert result["season"] == "2025 Season"
        assert by_category(result)["Passing Yards"][0]["value"] == "4379"

    def test_a_list_stops_where_espn_goes_back_to_the_top(self, espn):
        """A real, whole category: qualified players, then everyone else on 100 percent."""
        data = load("leaders_v3_NCAAM_full.json")
        whole = data["leaders"]["categories"][0]["leaders"]
        assert len(whole) == 20 and whole[6]["value"] > whole[5]["value"], "the fixture should show the problem"
        espn.on("/season$", load("season_NBA.json")).on("/leaders", data)
        rows = by_category(espn_api.get_player_statistics("NCAAM"))
        assert [r["value"] for r in rows["Field Goal Percentage"]] == ["71.4", "64.3", "55.6", "50.0", "46.2", "42.9"]
        assert [r["value"] for r in rows["Average 3-Point Field Goals Made"]] == ["5.0", "3.0", "3.0", "3.0"]

    @pytest.mark.parametrize("fixture,category", [
        ("leaders_v3_NHL.json", "Goals Against Average"),
        ("leaders_v3_MLB.json", "Earned Run Average"),
        ("leaders_v3_MLB.json", "Walks Plus Hits Per Inning Pitched"),
    ])
    def test_a_low_is_good_list_is_not_cut_short(self, espn, fixture, category):
        espn.on("/season$", load("season_NBA.json")).on("/leaders", load(fixture))
        espn.on("statsapi.mlb.com", HTTP_500)
        league = "NHL" if "NHL" in fixture else "MLB"
        assert len(by_category(espn_api.get_player_statistics(league))[category]) == 2

    def test_ties_and_a_row_with_no_value_do_not_end_a_list(self):
        leaders = [{"value": 5}, {"value": 5}, {}, {"value": 4}, {"value": 9}, {"value": 3}]
        assert [x.get("value") for x in espn_api._leaders_in_order("goals", leaders)] == [5, 5, None, 4]

    def test_preseason_numbers_are_never_shown(self, espn):
        """Even if ESPN answers with them: this is the bug that started all this."""
        preseason = load("leaders_v3_NFL.json")
        preseason["requestedSeason"]["type"]["type"] = 1
        espn.on("/season$", load("season_NFL.json")).on("/leaders", preseason)
        assert espn_api.get_player_statistics("NFL") == NOTHING

    def test_a_rating_with_nobody_rated_is_not_a_list_of_leaders(self, espn):
        espn.on("/season$", load("season_NBA.json")).on("/leaders", load("leaders_v3_NCAAM.json"))
        raw = next(c for c in load("leaders_v3_NCAAM.json")["leaders"]["categories"] if c["name"] == "PER")
        assert all(leader["value"] == 0 for leader in raw["leaders"]), "the fixture should show the problem"
        assert raw["displayName"] not in by_category(espn_api.get_player_statistics("NCAAM"))

    def test_a_row_with_no_name_loses_only_that_row(self, nba):
        data = load("leaders_v3_NBA.json")
        data["leaders"]["categories"][0]["leaders"][0]["athlete"] = {}
        nba.on("/leaders", data)
        assert len(by_category(espn_api.get_player_statistics("NBA"))["Points Per Game"]) == 1

    @pytest.mark.parametrize("data", [
        {"leaders": None}, {"leaders": {"categories": None}}, {"leaders": {"categories": ["text", None]}},
        {"leaders": {"categories": [{"name": None, "leaders": [{}]}]}},
        {"leaders": {"categories": [{"name": "x", "leaders": ["text", None]}]}},
        {"leaders": {"categories": [{"name": "x", "leaders": [{"value": 3, "athlete": {}}]}]}},
    ], ids=["no_leaders", "no_categories", "text_categories", "blank_leader", "text_leaders", "nameless"])
    def test_a_bad_payload_is_no_leaders_rather_than_an_exception(self, nba, data):
        nba.on("/leaders", data)
        assert espn_api.get_player_statistics("NBA") == NOTHING

    def test_a_category_with_no_display_name_uses_its_own(self, nba):
        data = {"leaders": {"categories": [{"name": "goals", "leaders": [
            {"value": 3, "displayValue": "3", "athlete": {"shortName": "A. Bee"}, "team": {"displayName": "Bees"}}]}]}}
        nba.on("/leaders", data)
        result = espn_api.get_player_statistics("NBA")
        assert result["player_stats"] == [{"category": "Goals", "stats": [
            {"player_name": "A. Bee", "team": "Bees", "value": "3", "stat_name": "Goals"}]}]
        assert result["season"] == ""

    def test_lower_case(self, nba):
        nba.on("/leaders", load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("nba")["player_stats"]


class TestEspnFailing:
    """/leaders answers 500 often, and more often the more it's asked for (see espn_api)."""

    def replies(self, espn, *answers):
        answers = list(answers)
        espn.on("/leaders", lambda url: answers.pop(0))

    def test_one_500_is_asked_again_past_the_cache(self, nba, pauses):
        self.replies(nba, HTTP_500, load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["player_stats"]
        first, second = nba.urls("/leaders")
        assert "limit=20" in first and "limit=20" in second
        assert second != first, "the same URL can read the cached failure"
        assert pauses == [1]

    def test_two_500s_step_down_to_a_shorter_list(self, nba, pauses):
        self.replies(nba, HTTP_500, HTTP_500, load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["player_stats"]
        assert "limit=10" in nba.urls("/leaders")[2]
        assert pauses == [1], "stepping down has no cached failure to wait out"

    def test_it_steps_down_as_far_as_five(self, nba):
        self.replies(nba, HTTP_500, HTTP_500, HTTP_500, load("leaders_v3_NBA.json"))
        assert espn_api.get_player_statistics("NBA")["player_stats"]
        assert "limit=5" in nba.urls("/leaders")[3]

    def test_failing_at_every_limit_says_so(self, nba):
        nba.on("/leaders", HTTP_500)
        with pytest.raises(ApiError) as caught:
            espn_api.get_player_statistics("NBA")
        assert str(caught.value) == espn_api.STATISTICS_UNAVAILABLE
        assert len(nba.urls("/leaders")) == 4

    def test_the_message_reaches_the_dialog_through_the_service(self, nba):
        nba.on("/leaders", HTTP_500)
        with pytest.raises(ApiError, match="Try again in a minute"):
            ApiService.get_player_statistics("NBA")

    @pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), NOT_JSON],
                             ids=["timeout", "connection", "not_json"])
    def test_a_broken_answer_says_so_without_more_waiting(self, nba, reply):
        nba.on("/leaders", reply)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NBA")
        assert len(nba.urls("/leaders")) == 1

    def test_being_refused_is_not_asked_again(self, nba):
        nba.on("/leaders", FakeResponse({"code": 403}, status=403))
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NBA")
        assert len(nba.urls("/leaders")) == 1


class TestLeaguesWithNoLeaders:
    @pytest.mark.parametrize("league", ["NCAAH", "NCAAWH", "EPL", "MLS", "La Liga", "PGA", "CRICKET"])
    def test_none_without_asking(self, espn, league):
        """/leaders is a 404 here, which would otherwise read as a failure. The dialog says
        no player statistics are available, and for these that's the truth."""
        assert espn_api.get_player_statistics(league) == NOTHING
        assert espn.calls == []


class TestMlbStatistics:
    def by_category(self, url):
        return load("mlb_leaders_homeRuns.json") if "leaderCategories=homeRuns" in url else {"leagueLeaders": []}

    def test_url(self, espn, freeze_now):
        freeze_now(datetime(2026, 8, 1))
        espn.on("statsapi.mlb.com", self.by_category)
        espn_api.get_player_statistics("MLB")
        assert ("https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories=homeRuns"
                "&statGroup=hitting&season=2026&limit=50") in espn.calls
        assert len(espn.urls("statGroup=pitching")) == 14
        assert len(espn.urls("statGroup=fielding")) == 9

    def test_real_leaders(self, espn):
        espn.on("statsapi.mlb.com", self.by_category)
        result = espn_api.get_player_statistics("MLB")
        assert [c["name"] for c in result["player_stats"]] == ["Home Runs"]
        category = result["player_stats"][0]
        assert category["abbreviation"] == "homeRuns"
        assert category["leaders"][0] == {"name": "Pete Crow-Armstrong", "value": "45", "team": "Chicago Cubs", "position": None}
        assert len(category["leaders"]) == 3

    def test_a_failed_category_only_loses_that_category(self, espn):
        espn.on("statsapi.mlb.com", lambda url: TIMEOUT if "leaderCategories=rbi" in url else load("mlb_leaders_homeRuns.json"))
        names = {c["name"] for c in espn_api.get_player_statistics("MLB")["player_stats"]}
        assert "RBIs" not in names and "Home Runs" in names and len(names) == 38

    def test_the_mlb_api_down_falls_back_to_espn_and_reads_numbers_not_stat_lines(self, espn):
        espn.on("statsapi.mlb.com", HTTP_500)
        espn.on("/season$", load("season_NFL.json")).on("/leaders", load("leaders_v3_MLB.json"))
        rows = by_category(espn_api.get_player_statistics("MLB"))
        assert rows["Batting Average"][0]["value"] == ".316"
        assert rows["Earned Run Average"][0]["value"] == "1.80"
        assert rows["Home Runs"][0]["value"] == "45"
        assert rows["On-Base-Plus-Slugging"][0]["value"] == "1.033"

    def test_the_mlb_api_down_and_espn_failing_says_so(self, espn):
        espn.on("statsapi.mlb.com", HTTP_500).on("/season$", load("season_NFL.json")).on("/leaders", HTTP_500)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("MLB")


class TestTeamStatistics:
    @pytest.fixture
    def stubbed(self, espn):
        espn.on("/nba/teams$", load("teams_NBA.json"))
        espn.on("/nba/teams/.*/statistics", load("team_stats_NBA_15.json"))
        return espn

    def test_urls(self, stubbed):
        espn_api.get_team_statistics("NBA")
        assert stubbed.calls[0] == f"{SITE}/basketball/nba/teams"
        assert sorted(stubbed.calls[1:]) == sorted(f"{SITE}/basketball/nba/teams/{i}/statistics" for i in ("1", "2", "17"))

    def test_real_categories_and_stats(self, stubbed):
        result = espn_api.get_team_statistics("NBA")
        assert result["player_stats"] == []
        general = next(c for c in result["team_stats"] if c["category"] == "General")
        hawks = next(t for t in general["stats"] if t["team_name"] == "Atlanta Hawks")
        assert hawks["team_id"] == "1"
        assert hawks["stats"] == {"Rebounds Per Game": "49.6", "Assist To Turnover Ratio": "1.6", "Fouls Per Game": "22.6"}
        assert len(general["stats"]) == 3

    def test_one_team_failing_keeps_the_others(self, stubbed):
        stubbed.on("/teams/2/statistics", HTTP_500).on("/teams/17/statistics", TIMEOUT)
        general = next(c for c in espn_api.get_team_statistics("NBA")["team_stats"] if c["category"] == "General")
        assert [t["team_name"] for t in general["stats"]] == ["Atlanta Hawks"]

    def with_seasons(self, espn, seasons):
        """The real team statistics, with the season block ESPN sends, by team id."""
        espn.on("/nba/teams$", load("teams_NBA.json"))

        def team(url):
            data = load("team_stats_NBA_15.json")
            team_id = url.split("/teams/")[1].split("/")[0]
            data["season"] = seasons[team_id]
            return data

        espn.on("/nba/teams/.*/statistics", team)

    REGULAR = {"year": 2027, "type": 2, "name": "Regular Season", "displayName": "2026-27"}
    POSTSEASON = {"year": 2026, "type": 3, "name": "Postseason", "displayName": "2026"}

    def test_says_the_season_when_every_team_has_the_same(self, espn):
        self.with_seasons(espn, {"1": self.REGULAR, "2": self.REGULAR, "17": self.REGULAR})
        assert espn_api.get_team_statistics("NBA")["season"] == "2026-27 Regular Season"

    def test_says_nothing_when_they_differ_as_in_the_playoffs(self, espn):
        self.with_seasons(espn, {"1": self.POSTSEASON, "2": self.REGULAR, "17": self.REGULAR})
        assert "season" not in espn_api.get_team_statistics("NBA")

    def test_says_nothing_without_a_season_block(self, stubbed):
        assert "season" not in espn_api.get_team_statistics("NBA")

    def test_a_team_without_stats_or_id_is_left_out(self, espn):
        teams = load("teams_NBA.json")
        del teams["sports"][0]["leagues"][0]["teams"][0]["team"]["id"]
        espn.on("/nba/teams$", teams).on("/nba/teams/.*/statistics", {"results": {}})
        assert espn_api.get_team_statistics("NBA") == NOTHING

    @pytest.mark.parametrize("teams", [HTTP_500, TIMEOUT, {}, {"sports": []}, {"sports": [{"leagues": []}]},
                                       {"sports": [{"leagues": [{"teams": []}]}]}])
    def test_no_teams_means_no_stats(self, espn, teams):
        espn.on("/nba/teams$", teams)
        assert espn_api.get_team_statistics("NBA") == NOTHING

    def test_unknown_league(self, espn):
        assert espn_api.get_team_statistics("CRICKET") == NOTHING
        assert espn.calls == []

    def test_an_exception_past_the_inner_handlers_is_still_nothing(self, monkeypatch):
        def boom(league):
            raise RuntimeError("boom")
        monkeypatch.setattr(espn_api, "_get_team_statistics", boom)
        assert espn_api.get_team_statistics("NBA") == NOTHING
