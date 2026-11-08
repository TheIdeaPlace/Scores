"""Team Hub's Stats tab against stubbed ESPN: what is asked for, which season, and that a failed
request says so rather than reading as nothing to show."""
import pytest
import requests

import espn_api
from exceptions import ApiError

from .support import HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, load

LEADERS = "/leaders"
BYTEAM = "/statistics/byteam"
CORE_TEAM = r"/types/\d/teams/\d+/statistics"


@pytest.fixture(autouse=True)
def pauses(monkeypatch):
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)


# ------------------------------------------------------------------------------- the players

class TestPlayers:
    def test_it_asks_for_the_team_in_the_leagues_season(self, espn):
        espn.on("/season$", load("season_NBA.json")).on(LEADERS, load("leaders_v3_team_NBA_14.json"))
        result = espn_api.get_team_player_leaders("NBA", "14")
        assert espn.urls(LEADERS) == [f"{espn_api.LEADERS_BASE_URL}/basketball/nba/leaders"
                                      "?region=us&lang=en&season=2027&seasontype=2&limit=20&team=14"]
        assert result["season"].endswith(", ranked within this team, qualified players first")
        assert [c["category"] for c in result["player_stats"]] == ["Points Per Game", "Field Goal Percentage"]

    def test_nobody_yet_this_season_is_last_seasons(self, espn):
        espn.on("/season$", load("season_NBA.json"))
        espn.on(LEADERS, lambda url: HTTP_404 if "season=2027" in url else load("leaders_v3_team_NBA_14.json"))
        assert espn_api.get_team_player_leaders("NBA", "14")["player_stats"]
        assert ["team=14" in url for url in espn.urls(LEADERS)] == [True, True]

    def test_no_season_either_year_is_a_failure(self, espn):
        espn.on("/season$", load("season_NBA.json")).on(LEADERS, HTTP_404)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_team_player_leaders("NBA", "14")

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON], ids=["timeout", "500", "not_json"])
    def test_espn_failing_says_so(self, espn, reply):
        espn.on("/season$", load("season_NBA.json")).on(LEADERS, reply)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_team_player_leaders("NBA", "14")

    @pytest.mark.parametrize("league", ["NCAAH", "EPL", "PGA", "CRICKET"])
    def test_a_league_without_leaders_asks_nothing(self, espn, league):
        assert espn_api.get_team_player_leaders(league, "1")["player_stats"] == []
        assert espn.calls == []


# --------------------------------------------------------------------------------- the ranks

def nba(espn, core=None, byteam=None):
    espn.on("/season$", load("season_NBA.json"))
    espn.on(BYTEAM, byteam if byteam is not None else load("byteam_NBA.json"))
    espn.on(CORE_TEAM, core if core is not None else load("core_team_stats_NBA_29.json"))
    return espn


def ranks(result):
    return {row["category"]: row["rank_display"] for row in result["rankings"]}


class TestRanks:
    def test_what_it_asks_for(self, espn):
        nba(espn)
        result = espn_api.get_team_stat_rankings("NBA", "29")
        assert espn.urls(CORE_TEAM) == [f"{espn_api.CORE_BASE_URL}/basketball/leagues/nba/seasons/2027"
                                        "/types/2/teams/29/statistics"]
        assert len(espn.urls(BYTEAM)) == 1
        assert result["season"] == "2026-27 Regular Season"

    def test_the_rank_is_the_league_lists(self, espn):
        nba(espn)
        assert ranks(espn_api.get_team_stat_rankings("NBA", "29"))["Assists"] == "Tied-11th"

    @pytest.mark.parametrize("reply", [HTTP_500, NOT_JSON, HTTP_404], ids=["500", "not_json", "404"])
    def test_no_league_list_only_costs_its_ranks(self, espn, reply):
        nba(espn, byteam=reply)
        shown = ranks(espn_api.get_team_stat_rankings("NBA", "29"))
        assert shown["Assists"] == "Tied-5th", "ESPN's own"
        assert "Points Per Game" not in shown, "ESPN has no rank for it"

    @pytest.mark.parametrize("error", [TIMEOUT, requests.exceptions.ConnectionError("down")], ids=["timeout", "connection"])
    def test_a_network_that_does_not_get_through_fails_it(self, espn, error):
        nba(espn, byteam=error)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_team_stat_rankings("NBA", "29")
        assert not espn.urls(CORE_TEAM), "one timeout before it says so, not two"

    def test_last_seasons_list_is_not_ranked_against(self, espn):
        last = load("byteam_NBA.json")
        last["requestedSeason"]["year"] = 2026
        nba(espn, byteam=lambda url: last if "season=2026" in url else {})
        assert "Points Per Game" not in ranks(espn_api.get_team_stat_rankings("NBA", "29"))

    def test_nothing_this_season_is_last_seasons(self, espn):
        nba(espn, core=lambda url: load("core_team_stats_NBA_29.json") if "/seasons/2026/" in url else HTTP_404)
        espn.on("/seasons/2026$", {"displayName": "2025-26"})
        result = espn_api.get_team_stat_rankings("NBA", "29")
        assert result["rankings"] and result["season"] == "2025-26 Regular Season"
        assert [url.split("/seasons/")[1][:4] for url in espn.urls(CORE_TEAM)] == ["2027", "2026"]

    def test_neither_season_is_nothing_to_show(self, espn):
        nba(espn, core=HTTP_404)
        assert espn_api.get_team_stat_rankings("NBA", "29") == {"rankings": [], "season": ""}

    def test_never_a_preseason(self, espn):
        nba(espn, core=HTTP_404)
        espn_api.get_team_stat_rankings("NBA", "29")
        assert all("/types/2/" in url for url in espn.urls(CORE_TEAM))

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT, NOT_JSON, [1, 2]], ids=["500", "timeout", "not_json", "a_list"])
    def test_a_failed_core_request_says_so(self, espn, reply):
        nba(espn, core=reply)
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_team_stat_rankings("NBA", "29")

    def test_a_new_seasons_first_days_can_be_a_500(self, espn, monkeypatch):
        monkeypatch.setattr(espn_api, "regular_season_just_began", lambda season: True)
        nba(espn, core=lambda url: HTTP_500 if "/seasons/2027/" in url else load("core_team_stats_NBA_29.json"))
        espn.on("/seasons/2026$", {"displayName": "2025-26"})
        assert espn_api.get_team_stat_rankings("NBA", "29")["rankings"]

    def test_soccer_is_filed_under_type_one_with_no_league_list(self, espn):
        espn.on("/season$", load("season_EPL.json"))
        espn.on(CORE_TEAM, {"splits": {"categories": [{"name": "general", "displayName": "General", "stats": [
            {"name": "totalGoals", "displayName": "Goals", "displayValue": "19", "rank": 2, "rankDisplayValue": "2nd"}]}]}})
        result = espn_api.get_team_stat_rankings("EPL", "382")
        assert "/types/1/teams/382/" in espn.urls(CORE_TEAM)[0]
        assert not espn.urls(BYTEAM), "ESPN has none, and answers with a 500"
        assert ranks(result) == {"Goals": "2nd"}
        assert "Regular Season" not in result["season"]

    def test_college_hockey_has_espns_ranks_and_no_list(self, espn):
        espn.on("/season$", load("season_NBA.json"))
        espn.on(CORE_TEAM, {"splits": {"categories": [{"name": "offensive", "displayName": "Offensive", "stats": [
            {"name": "goals", "displayName": "Goals", "displayValue": "40", "rank": 50, "rankDisplayValue": "50th"}]}]}})
        assert ranks(espn_api.get_team_stat_rankings("NCAAH", "2")) == {"Goals": "50th"}
        assert not espn.urls(BYTEAM)

    def test_not_knowing_the_season_is_a_failure(self, espn):
        espn.on("/season$", HTTP_500).on(BYTEAM, load("byteam_NBA.json"))
        with pytest.raises(ApiError, match="Try again"):
            espn_api.get_team_stat_rankings("NBA", "29")

    @pytest.mark.parametrize("league", ["PGA", "CRICKET"])
    def test_a_league_with_no_teams_asks_nothing(self, espn, league):
        assert espn_api.get_team_stat_rankings(league, "1") == {"rankings": [], "season": ""}
        assert espn.calls == []
