"""Statistics on real payloads. Sample players used to fill these gaps: never again."""
from datetime import datetime

import pytest

import espn_api

from exceptions import ApiError
from services.api_service import ApiService

from .support import HTTP_404, HTTP_500, TIMEOUT, FakeResponse, load

SITE = espn_api.BASE_URL
NOTHING = {"player_stats": [], "team_stats": []}


def categories(fixture):
    return load(fixture)["stats"]["categories"]


class TestEspnsBlip:
    """ESPN's /statistics fails like this on a good share of requests (#133)."""

    BLIP = FakeResponse({"code": 404, "message": espn_api.STATISTICS_BLIP}, status=404)

    @pytest.fixture(autouse=True)
    def no_waiting(self, monkeypatch):
        self.pauses = []
        monkeypatch.setattr(espn_api.time, "sleep", self.pauses.append)

    def replies(self, espn, *answers):
        answers = list(answers)
        espn.on("/statistics", lambda url: answers.pop(0))

    def test_a_blip_is_asked_again_past_the_cache(self, espn):
        self.replies(espn, self.BLIP, load("statistics_NFL.json"))
        result = espn_api.get_player_statistics("NFL")
        assert result["player_stats"]
        assert len(espn.calls) == 2
        assert self.pauses == [1], "asking again at once would hit the same failure"
        assert espn.calls[0] == f"{SITE}/football/nfl/statistics"
        assert espn.calls[1] != espn.calls[0], "the same URL can read the cached failure"

    def test_it_can_take_every_try(self, espn):
        self.replies(espn, self.BLIP, self.BLIP, load("statistics_NFL.json"))
        assert espn_api.get_player_statistics("NFL")["player_stats"]

    def test_a_blip_that_lasts_says_so_rather_than_showing_nothing(self, espn):
        self.replies(espn, self.BLIP, self.BLIP, self.BLIP)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NFL")
        assert len(espn.calls) == espn_api.STATISTICS_TRIES

    @pytest.mark.parametrize("later", [TIMEOUT, HTTP_500, HTTP_404], ids=["timeout", "500", "other 404"])
    def test_a_blip_then_a_different_failure_still_says_so(self, espn, later):
        self.replies(espn, self.BLIP, later, later)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("NCAAM")

    def test_a_404_that_is_not_json_is_not_a_blip(self, espn):
        espn.on("/statistics", FakeResponse(status=404, bad_json=True))
        assert espn_api.get_player_statistics("NFL") == NOTHING
        assert len(espn.calls) == 1

    def test_a_404_whose_body_is_a_list_is_not_a_blip(self, espn):
        espn.on("/statistics", FakeResponse([], status=404))
        assert espn_api.get_player_statistics("NFL") == NOTHING
        assert len(espn.calls) == 1

    def test_mlb_falling_back_to_espn_during_a_blip_says_so_too(self, espn):
        espn.on("statsapi.mlb.com", HTTP_500)
        self.replies(espn, self.BLIP, self.BLIP, self.BLIP)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_player_statistics("MLB")

    def test_the_message_reaches_the_dialog_through_the_service(self, espn):
        self.replies(espn, self.BLIP, self.BLIP, self.BLIP)
        with pytest.raises(ApiError) as caught:
            ApiService.get_player_statistics("NFL")
        assert str(caught.value) == espn_api.STATISTICS_UNAVAILABLE

    def test_any_other_404_is_not_retried(self, espn):
        espn.on("/statistics", HTTP_404)
        assert espn_api.get_player_statistics("NFL") == NOTHING
        assert len(espn.calls) == 1

    def test_the_full_statistics_call_also_gets_past_it(self, espn):
        self.replies(espn, self.BLIP, load("statistics_NFL.json"))
        espn.on("/teams", {"sports": []})
        assert espn_api.get_statistics("NFL")["player_stats"]

    def test_the_full_statistics_call_does_not_raise_when_it_lasts(self, espn):
        """Its team statistics may still be fine."""
        self.replies(espn, self.BLIP, self.BLIP, self.BLIP)
        espn.on("/teams", {"sports": []})
        assert espn_api.get_statistics("NFL")["player_stats"] == []


class TestPlayerStatistics:
    def test_asks_only_for_statistics(self, espn):
        """/leaders and /athletes are 404 in every league, up to 10 seconds each when stalled."""
        espn.on("/nfl/statistics", load("statistics_NFL.json"))
        espn_api.get_player_statistics("NFL")
        assert espn.calls == [f"{SITE}/football/nfl/statistics"]

    @pytest.mark.parametrize("league,path,fixture", [
        ("NFL", "nfl", "statistics_NFL.json"),
        ("NHL", "nhl", "statistics_NHL.json"),
        ("NCAAM", "mens-college-basketball", "statistics_NCAAM.json"),
    ])
    def test_real_leaders(self, espn, league, path, fixture):
        espn.on(f"/{path}/statistics", load(fixture))
        result = espn_api.get_player_statistics(league)
        assert result["team_stats"] == []
        raw = categories(fixture)
        assert [c["category"] for c in result["player_stats"]] == [c["displayName"] for c in raw if c.get("leaders")]
        first = result["player_stats"][0]["stats"][0]
        leader = raw[0]["leaders"][0]
        assert first["player_name"] == leader["athlete"]["displayName"]
        assert first["value"] == str(leader["value"])
        assert first["stat_name"] == raw[0]["displayName"]

    @pytest.mark.parametrize("league,fixture", [("NBA", "statistics_NBA.json"), ("NCAAH", "statistics_NCAAH.json")])
    def test_no_stats_in_the_payload_means_no_players(self, espn, league, fixture):
        espn.on(".*", load(fixture))
        assert espn_api.get_player_statistics(league) == NOTHING

    def test_every_endpoint_failing_means_no_players(self, espn):
        espn.on(".*", TIMEOUT)
        assert espn_api.get_player_statistics("NFL") == NOTHING

    def test_unknown_league_and_lower_case(self, espn):
        assert espn_api.get_player_statistics("CRICKET") == NOTHING
        assert espn.calls == []
        espn.on(".*", HTTP_500)
        assert espn_api.get_player_statistics("nfl") == NOTHING
        assert espn.calls[0] == f"{SITE}/football/nfl/statistics"

    def test_a_bad_payload_is_nothing_rather_than_an_exception(self, espn):
        espn.on(".*", {"stats": {"categories": [{"name": None, "leaders": [{}]}]}})
        assert espn_api.get_player_statistics("NCAAM") == NOTHING


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

    def test_the_mlb_api_down_falls_back_to_espn(self, espn):
        espn.on("statsapi.mlb.com", HTTP_500)
        espn.on("/mlb/statistics", load("statistics_NFL.json"))
        result = espn_api.get_player_statistics("MLB")
        assert result["player_stats"][0]["stats"][0]["player_name"] == categories("statistics_NFL.json")[0]["leaders"][0]["athlete"]["displayName"]

    def test_get_statistics_adds_team_stats(self, espn):
        espn.on("statsapi.mlb.com", self.by_category)
        espn.on("/mlb/teams$", load("teams_NBA.json")).on("/mlb/teams/.*/statistics", load("team_stats_NBA_15.json"))
        result = espn_api.get_statistics("MLB")
        assert [c["name"] for c in result["player_stats"]] == ["Home Runs"]
        assert {c["category"] for c in result["team_stats"]} == {"General", "Offensive"}


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


class TestGetStatistics:
    def test_players_and_teams_together(self, espn):
        espn.on("/nfl/statistics", load("statistics_NFL.json"))
        espn.on("/nfl/teams$", load("teams_NFL.json")).on("/nfl/teams/.*/statistics", load("team_stats_NBA_15.json"))
        result = espn_api.get_statistics("NFL")
        assert result["player_stats"][0]["category"] == categories("statistics_NFL.json")[0]["displayName"]
        assert {c["category"] for c in result["team_stats"]} == {"General", "Offensive"}

    def test_statistics_then_team_stats_when_it_fails(self, espn):
        espn.on(".*", HTTP_404)
        assert espn_api.get_statistics("NFL") == NOTHING
        assert espn.calls == [
            f"{SITE}/football/nfl/statistics",
            f"{SITE}/football/nfl/teams",
        ]

    def test_timeouts_are_nothing(self, espn):
        espn.on(".*", TIMEOUT)
        assert espn_api.get_statistics("NFL") == NOTHING

    def test_team_stats_without_player_stats(self, espn):
        espn.on(".*", HTTP_404)
        espn.on("/nba/teams$", load("teams_NBA.json")).on("/nba/teams/.*/statistics", load("team_stats_NBA_15.json"))
        result = espn_api.get_statistics("NBA")
        assert result["player_stats"] == []
        assert {c["category"] for c in result["team_stats"]} == {"General", "Offensive"}

    def test_a_payload_with_no_stats_moves_on(self, espn):
        """statistics_NBA.json is what ESPN sends the NBA today: no stats key."""
        espn.on(".*", HTTP_404).on("/nba/statistics", load("statistics_NBA.json"))
        assert espn_api.get_statistics("NBA") == NOTHING
        assert espn.calls == [f"{SITE}/basketball/nba/statistics", f"{SITE}/basketball/nba/teams"]

    def test_unknown_league_and_lower_case(self, espn):
        assert espn_api.get_statistics("CRICKET") == NOTHING
        espn.on(".*", HTTP_404)
        assert espn_api.get_statistics("nfl") == NOTHING

    def test_the_mlb_api_down_falls_through_to_espn(self, espn):
        espn.on(".*", HTTP_404)
        assert espn_api.get_statistics("MLB") == NOTHING
        assert f"{SITE}/baseball/mlb/statistics" in espn.calls


class TestParsing:
    LEADERS = [{"athlete": {"displayName": "A", "team": {"abbreviation": "TM"}}, "value": 0.3125, "displayValue": ".313"}]

    def test_ratio_stats_get_three_places(self):
        data = {"stats": {"categories": [{"name": "avg", "displayName": "Batting Average", "leaders": self.LEADERS}]}}
        assert espn_api._parse_statistics_data(data)["player_stats"] == [{"category": "Batting Average", "stats": [
            {"player_name": "A", "team": "TM", "value": "0.312", "stat_name": "Batting Average"}]}]

    def test_edge_cases(self):
        parser = espn_api._parse_generic_player_stats
        assert parser([{"name": "x", "leaders": []}]) == []
        result = parser([{"name": "era", "leaders": [{"athlete": {}}, {"athlete": {"name": "B"}, "value": "n/a"}]}])
        assert result == [{"category": "Era", "stats": [{"player_name": "B", "team": "", "value": "n/a", "stat_name": "Era"}]}]

    def test_soccers_list_of_leaders_is_not_read_yet(self):
        """Real shape, from /soccer/eng.1/statistics. Not built: it comes out as no players."""
        data = {"stats": [{"name": "goalsLeaders", "displayName": "Goals",
                           "leaders": [{"athlete": {"displayName": "A"}, "value": 9.0}]}]}
        assert espn_api._parse_statistics_data(data) == NOTHING

    @pytest.mark.parametrize("data", [{}, "text", [], {"stats": None}, {"stats": {"categories": None}}, load("statistics_NBA.json")])
    def test_no_stats_key_is_nothing(self, data):
        assert espn_api._parse_statistics_data(data) == NOTHING

    def test_text_in_the_lists_is_dropped(self):
        data = {"stats": {"categories": ["text", {"name": "pts", "leaders": ["text", {"athlete": {"name": "B"}, "value": 3}]}]}}
        assert espn_api._parse_statistics_data(data)["player_stats"][0]["stats"][0]["player_name"] == "B"
