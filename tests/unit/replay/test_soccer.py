"""Soccer's Standings, Statistics and Teams on Windows, on ESPN's real answers: a league with one
table, MLS's conferences, a cup's league phase or groups, and a cup with no table at all."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import espn_api
from exceptions import ApiError
from models.standings import StandingsData
from services.api_service import ApiService
import soccer
from team_stats import ranking_rows

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, FakeResponse, load


def team(rows, name):
    return next(row for row in rows if row["team_name"] == name)


def test_every_soccer_league_is_named_and_the_world_cups_are_not():
    paths = {key for key, path in espn_api.LEAGUES.items() if path.startswith("soccer/")}
    assert soccer.SOCCER_LEAGUES == paths - {"WC2026", "WWC2027"}
    assert not soccer.SOCCER_LEAGUES & espn_api.LEADER_LEAGUES, "soccer asks /leaders for its own season types"


class TestStandings:
    def standings(self, espn, league, fixture):
        espn.on(r"/apis/v2/sports/soccer/[\w.]+/standings$", load(fixture))
        return espn_api.get_standings(league)

    def test_a_league_has_one_table_in_order(self, espn):
        rows = self.standings(espn, "EPL", "standings_EPL.json")
        assert {row["division"] for row in rows} == {"2026-27 English Premier League"}
        assert [row["table_rank"] for row in rows] == sorted(row["table_rank"] for row in rows)
        assert len(espn.calls) == 1, "one request, where the team list took one for each team"

    def test_a_row_reads_wins_draws_losses_and_says_where_the_place_leads(self, espn):
        arsenal = team(self.standings(espn, "EPL", "standings_EPL.json"), "Arsenal")
        assert (arsenal["wins"], arsenal["ties"], arsenal["losses"]) == (8, 0, 1)
        assert arsenal["record"] == "8-0-1"
        assert arsenal["games_played"] == 9
        assert (arsenal["goals_for"], arsenal["goals_against"], arsenal["goal_difference"]) == (14, 5, 9)
        assert arsenal["goal_difference_text"] == "+9"
        assert arsenal["points"] == 24
        assert arsenal["note"] == "Champions League"
        assert arsenal["team_id"] == "359"
        assert arsenal["season"] == "2026-27 English Premier League"

    def test_the_foot_of_the_table_is_relegation(self, espn):
        last = self.standings(espn, "EPL", "standings_EPL.json")[-1]
        assert last["table_rank"] == 20
        assert last["note"] == "Relegation"

    def test_mls_has_its_two_conferences_and_says_which_season(self, espn):
        rows = self.standings(espn, "MLS", "standings_MLS.json")
        assert list(StandingsData(rows).divisions) == ["Eastern Conference", "Western Conference"]
        # The root of the same answer says 2027, which hasn't started.
        assert load("standings_MLS.json")["season"]["year"] == 2027
        assert {row["season"] for row in rows} == {"2026 MLS"}

    def test_each_conference_goes_by_espns_rank_not_the_order_of_its_answer(self, espn):
        """On Nov 4, 2026, ESPN's East opened with 4th, then 8th, then 3rd."""
        raw = load("standings_MLS.json")["children"][0]["standings"]["entries"]
        rank = [next(stat["value"] for stat in entry["stats"] if stat["name"] == "rank") for entry in raw]
        assert rank != sorted(rank), "the fixture should show the problem"
        rows = self.standings(espn, "MLS", "standings_MLS.json")
        for teams in (StandingsData(rows).divisions["Eastern Conference"], StandingsData(rows).divisions["Western Conference"]):
            places = [team["table_rank"] for team in teams]
            assert places == sorted(places)
        east = [row["table_rank"] for row in rows if row["division"] == "Eastern Conference"]
        assert east == sorted(east), "and in the rows themselves, for Teams"

    def test_a_cup_has_its_league_phase(self, espn):
        rows = self.standings(espn, "UCL", "standings_UCL.json")
        assert {row["division"] for row in rows} == {"League Phase"}
        assert rows[0]["note"] == "Qualifies for round of 16"
        assert rows[-1]["table_rank"] == 36
        assert rows[-1]["note"] == "Eliminated"

    def test_a_cups_groups_are_kept_apart(self, espn):
        divisions = StandingsData(self.standings(espn, "UCL", "standings_UCL_2023.json")).divisions
        assert list(divisions) == [f"Group {letter}" for letter in "ABCDEFGH"]
        assert all(len(teams) == 2 for teams in divisions.values())

    def test_a_table_can_have_no_notes(self, espn):
        rows = self.standings(espn, "Liga MX", "standings_LigaMX.json")
        assert all(row["note"] == "" for row in rows)
        assert rows[0]["team_name"] == "América", "with its accent"
        assert rows[0]["division"] == "2026 Torneo Apertura"

    def test_a_knockout_competition_has_no_table_and_that_is_not_a_failure(self, espn):
        assert self.standings(espn, "CONCACAF", "standings_CONCACAF.json") == []

    def test_a_world_cup_reads_the_same_way_rather_than_one_request_a_team(self, espn):
        rows = self.standings(espn, "WC2026", "worldcup_standings_WC2026.json")
        assert rows
        assert all(row["division"].startswith("Group") for row in rows)
        assert len(espn.calls) == 1

    @pytest.mark.parametrize("league", sorted(soccer.SOCCER_LEAGUES))
    @pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON],
                             ids=["timeout", "connection", "404", "500", "not_json"])
    def test_a_failed_request_says_so_in_plain_words(self, espn, league, reply):
        espn.on(".*", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing standings right now"):
            ApiService.get_standings(league)

    def test_a_table_keeps_espns_rank_over_points(self, espn):
        """Level on points, goal difference decides, and only ESPN's rank has that."""
        data = load("standings_EPL.json")
        entries = data["children"][0]["standings"]["entries"]
        for entry in entries:
            next(stat for stat in entry["stats"] if stat["name"] == "points")["value"] = 10.0
        espn.on("/standings", data)
        names = [entry["team"]["displayName"] for entry in entries]
        divisions = StandingsData(espn_api.get_standings("EPL")).divisions
        assert [row["team_name"] for row in next(iter(divisions.values()))] == names

    def test_a_rank_missing_at_a_seasons_start_is_its_place_in_the_list(self):
        data = load("standings_EPL.json")
        for entry in data["children"][0]["standings"]["entries"]:
            entry["stats"] = [stat for stat in entry["stats"] if stat["name"] != "rank"]
        rows = soccer.parse_soccer_standings(data)
        assert [row["table_rank"] for row in rows] == [1, 2, 3, 4]

    def test_a_null_number_falls_back_to_its_text_and_then_to_nothing(self):
        data = load("standings_EPL.json")
        entry = data["children"][0]["standings"]["entries"][0]
        stats = {stat["name"]: stat for stat in entry["stats"]}
        stats["wins"]["value"] = None
        stats["points"].update(value=None, displayValue=None)
        stats["losses"].update(value=None, displayValue="not a number")
        del stats["pointDifferential"]["displayValue"]
        row = soccer.parse_soccer_standings(data)[0]
        assert (row["wins"], row["points"], row["losses"]) == (8, 0, 0)
        assert row["goal_difference_text"] == "+9"

    def test_a_goal_difference_with_no_text_reads_with_its_sign(self):
        data = load("standings_EPL.json")
        entries = data["children"][0]["standings"]["entries"]
        for entry, value in zip(entries, (-3, 0)):
            stat = next(stat for stat in entry["stats"] if stat["name"] == "pointDifferential")
            stat.update(value=value, displayValue=None)
        rows = soccer.parse_soccer_standings(data)
        assert [rows[0]["goal_difference_text"], rows[1]["goal_difference_text"]] == ["-3", "0"]


class TestTableCells:
    def test_a_row_lines_up_with_its_headers(self, espn):
        espn.on("/standings", load("standings_EPL.json"))
        row = StandingsData(espn_api.get_standings("EPL")).teams[0]
        cells = soccer.soccer_table_cells(1, row)
        assert dict(zip(soccer.SOCCER_TABLE_HEADERS, cells)) == {
            "Pos": "1", "Team": "Arsenal", "GP": "9", "W": "8", "D": "0", "L": "1",
            "GF": "14", "GA": "5", "GD": "+9", "Pts": "24", "Status": "Champions League"}

    def test_no_cell_is_silent(self, espn):
        espn.on("/standings", load("standings_LigaMX.json"))
        for row in espn_api.get_standings("Liga MX"):
            assert all(soccer.soccer_table_cells(1, row))
            assert soccer.soccer_table_cells(1, row)[-1] == soccer.NOTHING_TO_SHOW

    def test_with_no_rank_it_reads_its_place(self):
        assert soccer.soccer_table_cells(7, {"team_name": "A"})[0] == "7"


class TestTeams:
    def test_a_league_with_a_table_is_one_request_with_its_records(self, espn):
        espn.on("/standings", load("standings_EPL.json"))
        headers, ordered, rows = soccer.soccer_teams_table(ApiService.get_soccer_teams("EPL"))
        assert headers == soccer.SOCCER_TEAM_HEADERS
        assert rows[0] == ["Arsenal", "9", "8", "0", "1", "24"]
        assert ordered[0]["team_id"] == "359"
        assert len(espn.calls) == 1

    def test_a_cup_with_no_table_still_has_its_teams_by_name(self, espn):
        espn.on("/standings", load("standings_CONCACAF.json"))
        espn.on("/concacaf.champions/teams", load("teams_CONCACAF.json"))
        teams = ApiService.get_soccer_teams("CONCACAF")
        assert len(teams) == 3
        assert {team["division"] for team in teams} == {soccer.TEAMS_WITH_NO_GROUP}
        assert all(team["team_id"] for team in teams)
        headers, ordered, rows = soccer.soccer_teams_table(teams)
        assert headers == soccer.TEAM_NAME_ONLY_HEADERS
        assert rows == sorted(rows)
        assert [team["team_name"] for team in ordered] == [row[0] for row in rows]

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON], ids=["timeout", "500", "not_json"])
    def test_the_team_list_failing_says_so(self, espn, reply):
        espn.on("/standings", load("standings_CONCACAF.json"))
        espn.on("/teams", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing teams right now"):
            ApiService.get_soccer_teams("CONCACAF")

    def test_nothing_in_the_team_list_is_nothing(self, espn):
        espn.on("/standings", load("standings_CONCACAF.json"))
        espn.on("/teams", EMPTY_JSON)
        assert ApiService.get_soccer_teams("CONCACAF") == []


def test_a_competition_with_no_table_says_it_plainly():
    assert soccer.no_table_message("CONCACAF") == (
        "ESPN has no league table for CONCACAF right now. A knockout competition doesn't have one.")


def query(url, name):
    return parse_qs(urlparse(url).query).get(name, [None])[0]


def asked(espn):
    """(season, season type, limit) of each /leaders request."""
    return [(query(url, "season"), query(url, "seasontype"), query(url, "limit")) for url in espn.urls("/leaders")]


def named(data, season_name=None, type_id=None, type_name=None):
    """A real answer, as if it were for another season or torneo."""
    data = copy.deepcopy(data)
    requested = data["requestedSeason"]
    if season_name:
        requested["displayName"] = season_name
    if type_id:
        requested["type"].update(id=str(type_id), name=type_name)
    return data


@pytest.fixture
def leaders(espn, monkeypatch):
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)
    espn.on("/season$", load("season_EPL.json"))
    espn.on("/leaders", load("leaders_v3_EPL.json"))
    return espn


class TestLeaders:
    def test_one_request_has_the_names_and_teams(self, leaders):
        """The core API took one for each player and team, about 150 for the Premier League."""
        espn_api.get_player_statistics("EPL")
        assert len(leaders.urls("/leaders")) == 1
        assert leaders.calls == leaders.urls("/season$") + leaders.urls("/leaders")

    def test_it_asks_what_the_iphone_asks(self, leaders):
        """Without season, ESPN answers last season or a 500; without seasontype, a 404 or a playoff
        round's; without region and lang, a 500 far more often."""
        espn_api.get_player_statistics("EPL")
        url = leaders.urls("/leaders")[0]
        assert url.startswith("https://site.web.api.espn.com/apis/site/v3/sports/soccer/eng.1/leaders?")
        assert (query(url, "region"), query(url, "lang")) == ("us", "en")
        assert asked(leaders) == [("2026", "1", "20")]

    def test_the_lists_are_the_iphones_without_the_repeats(self, leaders):
        result = espn_api.get_player_statistics("EPL")
        titles = [category["category"] for category in result["player_stats"]]
        assert titles == ["Goals", "Assists", "Shots On Target", "Yellow Cards", "Red Cards",
                          "Fouls Committed", "Fouls Suffered", "Total Shots", "Accurate Passes", "Saves"]
        assert result["team_stats"] == []

    def test_a_list_keeps_espns_name_for_it_for_its_definition(self, leaders):
        keys = [category["key"] for category in espn_api.get_player_statistics("EPL")["player_stats"]]
        assert keys[:3] == ["goalsLeaders", "assistsLeaders", "shotsOnTarget"]

    def test_a_row_has_a_name_and_team_and_reads_as_a_number(self, leaders):
        goals = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"][0]
        assert goals == {"player_name": "Erling Haaland", "team": "MNC", "value": "9", "stat_name": "Goals"}

    def test_it_says_which_season(self, leaders):
        assert espn_api.get_player_statistics("EPL")["season"] == "2026-27 English Premier League"

    def test_rows_rank_on_the_list_as_the_other_leagues_do(self, leaders):
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert ranking_rows("player", stats)[:3] == [[1, "Erling Haaland", "MNC", "9"], [2, "Thierno Barry", "EVE", "6"],
                                                     [2, "Alexander Isak", "LIV", "6"]]

    def test_a_league_in_its_playoffs_still_reads_its_season_from_type_1(self, leaders):
        leaders.on("/season$", load("season_NWSL.json"))
        espn_api.get_player_statistics("NWSL")
        assert "/soccer/usa.nwsl/leaders" in leaders.urls("/leaders")[0]
        assert asked(leaders) == [("2026", "1", "20")]

    def test_the_season_comes_from_espn_not_the_calendar(self, leaders):
        season = load("season_EPL.json")
        season["year"] = 2031
        leaders.on("/season$", season)
        espn_api.get_player_statistics("EPL")
        assert asked(leaders)[0][0] == "2031"

    def test_a_season_with_no_list_yet_means_the_one_before_and_says_so(self, leaders):
        leaders.on(r"/leaders\?.*season=2026&", HTTP_404)
        leaders.on(r"/leaders\?.*season=2025&", named(load("leaders_v3_EPL.json"), "2025-26 English Premier League"))
        result = espn_api.get_player_statistics("EPL")
        assert result["player_stats"]
        assert result["season"] == "2025-26 English Premier League"
        assert not leaders.urls(r"/seasons/2025"), "only Liga MX needs an earlier season's types"

    def test_an_answer_with_nobody_on_it_also_means_the_one_before(self, leaders):
        leaders.on(r"/leaders\?.*season=2026&", load("leaders_v3_LigaMX_clausura_empty.json"))
        assert espn_api.get_player_statistics("EPL")["player_stats"]
        assert [season for season, _, _ in asked(leaders)] == ["2026", "2025"]

    def test_an_answer_with_no_name_for_its_season_says_its_year(self, leaders):
        data = load("leaders_v3_EPL.json")
        data["requestedSeason"] = None
        leaders.on("/leaders", data)
        assert espn_api.get_player_statistics("EPL")["season"] == "2026"

    def test_three_seasons_of_nothing_is_an_honest_nothing(self, leaders):
        leaders.on("/leaders", HTTP_404)
        assert espn_api.get_player_statistics("EPL") == {"player_stats": [], "team_stats": []}
        assert [season for season, _, _ in asked(leaders)] == ["2026", "2025", "2024"]

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT, NOT_JSON, FakeResponse({"code": 403}, status=403),
                                       FakeResponse([1, 2])],
                             ids=["500", "timeout", "not_json", "403", "not_an_answer"])
    def test_a_failed_list_says_so_rather_than_showing_last_season(self, leaders, reply):
        leaders.on("/leaders", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            ApiService.get_player_statistics("EPL")
        assert not leaders.urls("season=2025")

    def test_a_500_is_tried_again_fresh_then_steps_down_to_10(self, leaders):
        """NWSL's and CONCACAF's have never answered at 20, and 10 is better than nothing."""
        answers = [HTTP_500, HTTP_500, load("leaders_v3_EPL.json")]
        leaders.on("/leaders", lambda url: answers.pop(0))
        assert espn_api.get_player_statistics("EPL")["player_stats"]
        assert [limit for _, _, limit in asked(leaders)] == ["20", "20", "10"]
        urls = leaders.urls("/leaders")
        assert query(urls[0], "_") is None and query(urls[1], "_"), "ESPN can cache a 500"
        assert {(season, season_type) for season, season_type, _ in asked(leaders)} == {("2026", "1")}

    def test_failing_at_every_limit_says_so(self, leaders):
        leaders.on("/leaders", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("CONCACAF")
        assert [limit for _, _, limit in asked(leaders)] == ["20", "20", "10", "5"]

    def test_the_season_failing_says_so(self, espn):
        espn.on(".*", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            ApiService.get_player_statistics("UCL")

    def test_a_name_missing_keeps_the_row_and_says_so(self, leaders):
        data = load("leaders_v3_EPL.json")
        data["leaders"]["categories"][0]["leaders"][0]["athlete"] = None
        leaders.on("/leaders", data)
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert stats[0] == {"player_name": soccer.NAME_UNAVAILABLE, "team": "MNC", "value": "9", "stat_name": "Goals"}
        assert stats[1]["player_name"] == "Thierno Barry"

    def test_a_team_missing_keeps_the_row_and_reads_not_available(self, leaders):
        data = load("leaders_v3_EPL.json")
        data["leaders"]["categories"][0]["leaders"][0]["team"] = None
        leaders.on("/leaders", data)
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert ranking_rows("player", stats)[0] == [1, "Erling Haaland", "N/A", "9"]

    def test_a_value_missing_is_not_a_silent_cell(self):
        data = load("leaders_v3_EPL.json")
        row = data["leaders"]["categories"][1]["leaders"][0]
        row["value"], row["displayValue"] = 5, None
        data["leaders"]["categories"][1]["leaders"][1].update(value=4, displayValue="")
        stats = soccer.soccer_leader_lists(data)[1]["stats"]
        assert stats[0]["value"] == "5"
        assert all(row["value"] for row in stats)

    def test_a_list_where_everyone_is_on_nothing_is_left_out(self):
        lists = soccer.soccer_leader_lists(load("leaders_v3_UEL_2024.json"))
        assert [category["category"] for category in lists] == ["Goals"]

    def test_lists_that_differ_both_stay(self):
        data = load("leaders_v3_EPL.json")
        data["leaders"]["categories"][2]["leaders"][1]["value"] += 1
        data["leaders"]["categories"][2]["leaders"][1]["displayValue"] = "99"
        titles = [category["category"] for category in soccer.soccer_leader_lists(data)]
        assert titles.count("Goals") == 2

    def test_a_list_with_no_name_is_called_by_its_key(self):
        data = {"leaders": {"categories": [{"name": "goals", "leaders": [{"value": 3, "displayValue": "3"}]}]}}
        assert soccer.soccer_leader_lists(data)[0]["category"] == "Goals"


@pytest.fixture
def liga_mx(espn, monkeypatch, freeze_now):
    """Liga MX on Nov 7, 2026, in its Apertura, unless a test moves the clock."""
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)
    espn.on("/season$", load("season_LigaMX.json"))
    espn.on("/leaders", load("leaders_v3_LigaMX.json"))
    espn.freeze = lambda text: freeze_now(datetime.fromisoformat(text.replace("Z", "+00:00")))
    espn.freeze("2026-11-07T12:00:00Z")
    return espn


CLAUSURA_2026 = r"/leaders\?.*season=2026&seasontype=5&"


class TestLigaMXTorneos:
    """#178: a Liga MX season is two torneos, each with its own leaders."""

    def test_the_apertura_is_type_1_and_says_so(self, liga_mx):
        result = espn_api.get_player_statistics("Liga MX")
        assert asked(liga_mx) == [("2026", "1", "20")]
        assert result["season"] == "2026-27 Liga BBVA MX Torneo Apertura"

    def test_its_season_types_come_inside_the_season_already_asked_for(self, liga_mx):
        espn_api.get_player_statistics("Liga MX")
        assert liga_mx.calls == liga_mx.urls("/season$") + liga_mx.urls("/leaders")

    def test_from_january_it_is_the_clausura_found_by_name(self, liga_mx):
        liga_mx.freeze("2027-01-20T12:00:00Z")
        liga_mx.on(CLAUSURA_2026, named(load("leaders_v3_LigaMX.json"), type_id=5, type_name="Torneo Clausura"))
        result = espn_api.get_player_statistics("Liga MX")
        assert asked(liga_mx) == [("2026", "5", "20")]
        assert result["season"] == "2026-27 Liga BBVA MX Torneo Clausura"

    def test_a_clausura_with_nobody_on_it_yet_means_the_apertura_before_it(self, liga_mx):
        liga_mx.freeze("2027-01-02T12:00:00Z")
        liga_mx.on(CLAUSURA_2026, load("leaders_v3_LigaMX_clausura_empty.json"))
        result = espn_api.get_player_statistics("Liga MX")
        assert asked(liga_mx) == [("2026", "5", "20"), ("2026", "1", "20")]
        assert result["season"] == "2026-27 Liga BBVA MX Torneo Apertura"

    def test_the_apertura_playoffs_are_still_the_apertura(self, liga_mx):
        """ESPN dates the 2026 Clausura's playoff rounds in Nov and Dec 2026, and /season's
        current type names a playoff round, so neither can say which torneo is on."""
        liga_mx.freeze("2026-12-15T12:00:00Z")
        espn_api.get_player_statistics("Liga MX")
        assert asked(liga_mx) == [("2026", "1", "20")]

    def test_before_the_apertura_it_is_last_seasons_clausura_whatever_its_number(self, liga_mx):
        liga_mx.freeze("2026-05-31T12:00:00Z")
        liga_mx.on(r"/seasons/2025$", load("season_LigaMX_2025.json"))
        liga_mx.on(r"/leaders\?.*season=2025&seasontype=8&", load("leaders_v3_LigaMX_2025_clausura.json"))
        result = espn_api.get_player_statistics("Liga MX")
        assert asked(liga_mx) == [("2025", "8", "20")]
        assert result["season"] == "2025-26 Liga BBVA MX Torneo Clausura"

    @pytest.mark.parametrize("reply", [HTTP_500, HTTP_404, TIMEOUT, NOT_JSON], ids=["500", "404", "timeout", "not_json"])
    def test_an_earlier_season_not_coming_says_so(self, liga_mx, reply):
        """Not knowing which torneo to show isn't nothing to show."""
        liga_mx.freeze("2026-05-31T12:00:00Z")
        liga_mx.on(r"/seasons/2025$", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("Liga MX")
        assert not asked(liga_mx)

    def test_at_most_three_lists_are_asked_for(self, liga_mx):
        liga_mx.freeze("2027-02-01T12:00:00Z")
        liga_mx.on("/leaders", load("leaders_v3_LigaMX_clausura_empty.json"))
        liga_mx.on(r"/seasons/2025$", load("season_LigaMX_2025.json"))
        assert espn_api.get_player_statistics("Liga MX") == {"player_stats": [], "team_stats": []}
        assert [(season, season_type) for season, season_type, _ in asked(liga_mx)] == [
            ("2026", "5"), ("2026", "1"), ("2025", "8")]


class TestSeasonTypes:
    def test_a_season_with_no_types_listed_asks_for_the_apertura(self):
        now = datetime(2027, 2, 1, tzinfo=timezone.utc)
        assert soccer.leaders_season_types("Liga MX", {}, now) == [1]
        assert soccer.leaders_season_types("Liga MX", {"types": {"items": None}}, now) == [1]

    def test_a_torneo_with_no_date_it_can_read_is_not_counted_as_started(self):
        season = {"types": {"items": [{"id": "1", "name": "Torneo Apertura", "startDate": "2026-06-01T04:00Z"},
                                      {"id": "5", "name": "Torneo Clausura", "startDate": "soon"},
                                      {"id": None, "name": "Torneo Clausura", "startDate": "2027-01-01T05:00Z"}]}}
        assert soccer.leaders_season_types("Liga MX", season, datetime(2027, 2, 1, tzinfo=timezone.utc)) == [1]

    def test_an_apertura_with_no_date_it_can_read_is_taken_as_started(self):
        season = {"types": {"items": [{"id": "1", "name": "Torneo Apertura"},
                                      {"id": "5", "name": "Torneo Clausura", "startDate": "2027-01-01T05:00Z"}]}}
        assert soccer.leaders_season_types("Liga MX", season, datetime(2026, 11, 7, tzinfo=timezone.utc)) == [1]
        assert soccer.leaders_season_types("Liga MX", season, datetime(2027, 2, 1, tzinfo=timezone.utc)) == [5, 1]

    def test_only_liga_mx_has_torneos(self):
        assert soccer.TORNEO_LEAGUES == {"Liga MX"} and soccer.TORNEO_LEAGUES <= soccer.SOCCER_LEAGUES
        assert soccer.leaders_season_types("UCL", load("season_LigaMX.json"), datetime.now(timezone.utc)) == [1]


GRID = json.loads((Path(__file__).parents[2] / "fixtures" / "soccer_grid.json").read_text(encoding="utf-8"))


class TestSharedGrid:
    """SoccerGridTests in LeagueLeadersTests.swift holds the iPhone to the same file."""

    def test_it_has_the_cases_that_matter(self):
        assert {case["fixture"] for case in GRID["tables"]} >= {
            "standings_EPL.json", "standings_MLS.json", "standings_UCL.json", "standings_UCL_2023.json",
            "standings_LigaMX.json", "standings_CONCACAF.json"}
        assert GRID["headers"] == soccer.SOCCER_TABLE_HEADERS
        rows = [row for case in GRID["leaders"] for category in case["lists"] for row in category["rows"]]
        assert any(row["rank"] == 2 and other["rank"] == 2 and row is not other for row in rows for other in rows), \
            "it should show a tie"
        assert {case["season"] for case in GRID["leaders"]} >= {
            "2026-27 Liga BBVA MX Torneo Apertura", "2025-26 Liga BBVA MX Torneo Clausura"}
        liga_mx = [case["types"] for case in GRID["seasonTypes"] if case["league"] == "Liga MX"]
        assert [] in liga_mx and [5, 1] in liga_mx and [8, 1] in liga_mx, "both Clausura numbers, and none started"

    @pytest.mark.parametrize("case", GRID["tables"], ids=lambda case: case["fixture"])
    def test_every_table_reads_as_the_grid_says(self, case):
        divisions = StandingsData(soccer.parse_soccer_standings(load(case["fixture"]))).divisions
        groups = [{"name": name, "rows": [soccer.soccer_table_cells(i + 1, team) for i, team in enumerate(teams)]}
                  for name, teams in divisions.items()]
        assert groups == case["groups"]

    @pytest.mark.parametrize("case", GRID["leaders"], ids=lambda case: case["fixture"])
    def test_every_list_of_leaders_reads_as_the_grid_says(self, case):
        data = load(case["fixture"])
        assert soccer.soccer_leaders_season(data, case["league"], case["year"]) == case["season"]
        lists = [{"title": category["category"],
                  "rows": [dict(zip(("rank", "player", "team", "value"), row))
                           for row in ranking_rows("player", category["stats"])]}
                 for category in soccer.soccer_leader_lists(data)]
        assert lists == case["lists"]

    @pytest.mark.parametrize("case", GRID["seasonTypes"], ids=lambda case: f"{case['league']} {case['now']}")
    def test_every_choice_of_season_type_is_as_the_grid_says(self, case):
        now = datetime.fromisoformat(case["now"].replace("Z", "+00:00"))
        assert soccer.leaders_season_types(case["league"], load(case["season"]), now) == case["types"], case["why"]

    def test_the_app_reads_a_league_as_the_grid_does(self, leaders):
        """The grid's EPL case through the whole request, so the pure parts are the ones used."""
        case = next(case for case in GRID["leaders"] if case["fixture"] == "leaders_v3_EPL.json")
        answer = espn_api.get_player_statistics("EPL")
        assert answer["season"] == case["season"]
        assert [category["category"] for category in answer["player_stats"]] == [item["title"] for item in case["lists"]]


def test_a_team_list_with_no_leagues_is_no_teams():
    assert soccer.parse_team_list({}) == []
    assert soccer.parse_team_list({"sports": [{"leagues": []}]}) == []
