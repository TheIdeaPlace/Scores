"""Soccer's Standings, Statistics and Teams on Windows, on ESPN's real answers: a league with one
table, MLS's conferences, a cup's league phase or groups, and a cup with no table at all."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import threading
import time

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
    assert espn_api.CORE_LEADER_LEAGUES == soccer.SOCCER_LEAGUES
    assert not espn_api.CORE_LEADER_LEAGUES & espn_api.LEADER_LEAGUES


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


NAMES = {"253989": "Erling Haaland"}


def athlete(url):
    """Only one real athlete's page is saved. The rest are that page with their own name, so a
    row can be told from another."""
    number = re.search(r"/athletes/(\d+)", url).group(1)
    page = copy.deepcopy(load("core_athlete_EPL_253989.json"))
    page["displayName"] = NAMES.get(number, f"Player {number}")
    return page


@pytest.fixture
def leaders(espn, monkeypatch):
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)
    espn.on("/season$", load("season_EPL.json"))
    espn.on(r"/seasons/\d+/types/1/leaders", load("leaders_core_EPL.json"))
    espn.on(r"/athletes/\d+", athlete)
    espn.on(r"/seasons/\d+/teams/\d+", load("core_team_EPL_382.json"))
    return espn


class TestLeaders:
    def test_they_come_from_the_core_api_under_type_1_for_espns_season(self, leaders):
        espn_api.get_player_statistics("EPL")
        first = leaders.urls("/leaders")[0]
        assert "/soccer/leagues/eng.1/seasons/2026/types/1/leaders" in first
        assert "limit=20" in first
        assert not leaders.urls("site.web.api"), "/leaders is a 404 for most of soccer"

    def test_the_lists_are_the_iphones_without_the_repeats(self, leaders):
        result = espn_api.get_player_statistics("EPL")
        titles = [category["category"] for category in result["player_stats"]]
        assert titles == ["Goals", "Assists", "Shots On Target", "Yellow Cards", "Red Cards",
                          "Fouls Committed", "Fouls Suffered", "Total Shots", "Accurate Passes", "Saves"]
        assert result["team_stats"] == []

    def test_a_row_has_a_looked_up_name_and_team_and_reads_as_a_number(self, leaders):
        goals = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"][0]
        assert goals == {"player_name": "Erling Haaland", "team": "MNC", "value": "9", "stat_name": "Goals"}

    def test_it_says_which_season(self, leaders):
        assert espn_api.get_player_statistics("EPL")["season"] == "2026-27 English Premier League"

    def test_rows_rank_on_the_list_as_the_other_leagues_do(self, leaders):
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert ranking_rows("player", stats)[0] == [1, "Erling Haaland", "MNC", "9"]

    def test_each_reference_is_asked_for_once_over_https(self, leaders):
        espn_api.get_player_statistics("EPL")
        references = leaders.urls("/athletes/") + leaders.urls(r"/seasons/\d+/teams/")
        assert len(references) == len(set(references))
        assert all(url.startswith("https://") for url in references)

    def test_the_names_share_connections_kept_open(self, leaders):
        """A new connection for each took a minute for the Premier League."""
        espn_api.get_player_statistics("EPL")
        sessions = {id(kwargs.get("session")) for url, kwargs in zip(leaders.calls, leaders.kwargs)
                    if "/athletes/" in url}
        assert len(sessions) == 1
        session = next(kwargs["session"] for url, kwargs in zip(leaders.calls, leaders.kwargs) if "/athletes/" in url)
        assert session.get_adapter("https://espn.example")._pool_maxsize == espn_api.CORE_REF_WORKERS

    def test_a_second_opening_only_asks_for_the_list(self, leaders):
        espn_api.get_player_statistics("EPL")
        before = len(leaders.urls("/athletes/"))
        espn_api.get_player_statistics("EPL")
        assert len(leaders.urls("/athletes/")) == before

    def test_a_league_in_its_playoffs_still_reads_its_season_from_type_1(self, leaders):
        leaders.on("/season$", load("season_NWSL.json"))
        espn_api.get_player_statistics("NWSL")
        assert "/usa.nwsl/seasons/2026/types/1/leaders" in leaders.urls("/leaders")[0]

    def test_a_list_where_everyone_is_on_nothing_is_left_out(self):
        lists = soccer.core_leader_lists(load("leaders_core_UEL_2024.json"))
        assert [category["title"] for category in lists] == ["Goals"]

    def test_lists_that_differ_both_stay(self):
        data = load("leaders_core_EPL.json")
        data["categories"][2]["leaders"][1]["value"] += 1
        data["categories"][2]["leaders"][1]["displayValue"] = "99"
        titles = [category["title"] for category in soccer.core_leader_lists(data)]
        assert titles.count("Goals") == 2

    def test_a_season_with_no_list_yet_means_the_one_before_and_says_so(self, leaders):
        leaders.on(r"/seasons/2026/types/1/leaders", HTTP_404)
        leaders.on(r"/seasons/2025$", load("season_EPL_2025.json"))
        result = espn_api.get_player_statistics("EPL")
        assert result["player_stats"]
        assert result["season"] == "2025-26 English Premier League"

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT, NOT_JSON, EMPTY_JSON], ids=["500", "timeout", "not_json", "empty"])
    def test_an_earlier_seasons_name_not_coming_still_says_its_year(self, leaders, reply):
        leaders.on(r"/seasons/2026/types/1/leaders", HTTP_404)
        leaders.on(r"/seasons/2025$", reply)
        assert espn_api.get_player_statistics("EPL")["season"] == "2025"

    def test_three_seasons_of_nothing_is_an_honest_nothing(self, leaders):
        leaders.on(r"/types/1/leaders", HTTP_404)
        result = espn_api.get_player_statistics("EPL")
        assert result == {"player_stats": [], "team_stats": []}
        asked = [re.search(r"/seasons/(\d+)/", url).group(1) for url in leaders.urls("/leaders")]
        assert asked == ["2026", "2025", "2024"]

    def test_the_season_comes_from_espn_not_the_calendar(self, leaders):
        season = load("season_EPL.json")
        season["year"] = 2031
        leaders.on("/season$", season)
        espn_api.get_player_statistics("EPL")
        assert "/seasons/2031/" in leaders.urls("/leaders")[0]

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT, NOT_JSON, FakeResponse({"code": 403}, status=403)],
                             ids=["500", "timeout", "not_json", "403"])
    def test_a_failed_list_says_so_rather_than_showing_last_season(self, leaders, reply):
        leaders.on(r"/types/1/leaders", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            ApiService.get_player_statistics("EPL")
        assert not leaders.urls("/seasons/2025/")

    def test_a_500_gets_a_second_try(self, leaders):
        answers = [HTTP_500, load("leaders_core_EPL.json")]
        leaders.on(r"/types/1/leaders", lambda url: answers.pop(0))
        assert espn_api.get_player_statistics("EPL")["player_stats"]

    def test_the_season_failing_says_so(self, espn):
        espn.on(".*", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            ApiService.get_player_statistics("UCL")

    def test_one_name_failing_keeps_the_row_and_says_so(self, leaders):
        leaders.on(r"/athletes/253989", HTTP_404)
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert stats[0]["player_name"] == soccer.NAME_UNAVAILABLE
        assert stats[0]["team"] == "MNC"
        assert stats[0]["value"] == "9"
        assert stats[1]["player_name"].startswith("Player ")

    def test_a_team_failing_keeps_the_row_and_reads_not_available(self, leaders):
        leaders.on(r"/seasons/\d+/teams/382\b", HTTP_404)
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert stats[0]["player_name"] == "Erling Haaland"
        assert ranking_rows("player", stats)[0][2] == "N/A"

    def test_every_team_failing_is_a_failure_not_a_column_of_blanks(self, leaders):
        leaders.on(r"/seasons/\d+/teams/\d+", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("EPL")

    def test_one_page_that_is_always_a_404_doesnt_fail_later_openings(self, leaders):
        """It's never cached, so a later opening has it as the only name still to find."""
        leaders.on(r"/athletes/253989", HTTP_404)
        for _ in range(3):
            stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
            assert stats[0]["player_name"] == soccer.NAME_UNAVAILABLE
            assert stats[1]["player_name"].startswith("Player ")

    def test_one_team_that_is_always_a_404_doesnt_fail_later_openings(self, leaders):
        leaders.on(r"/seasons/\d+/teams/382\b", HTTP_404)
        for _ in range(2):
            assert espn_api.get_player_statistics("EPL")["player_stats"]

    def test_a_closing_app_asks_for_no_more_names(self, leaders, monkeypatch):
        closing = threading.Event()
        closing.set()
        monkeypatch.setattr(espn_api, "_APP_CLOSING", closing)
        with pytest.raises(ApiError):
            espn_api.get_player_statistics("EPL")
        assert not leaders.urls("/athletes/")

    def test_a_closing_app_really_does_exit_with_lookups_still_queued(self, tmp_path):
        """Python joins a pool's workers at exit, and they work through the queue first, with the
        main thread still counted as alive. 400 lookups of half a second on 8 workers is 25 seconds."""
        script = tmp_path / "exits.py"
        script.write_text(textwrap.dedent(f"""
            import sys, threading, time
            sys.path.insert(0, {str(Path(__file__).parents[3])!r})
            import espn_api

            class Answer:
                status_code = 200
                def json(self):
                    return {{"displayName": "A"}}

            def slow(url, **kwargs):
                time.sleep(0.5)
                return Answer()

            espn_api._http_get = slow
            references = {{f"https://espn.example/{{i}}" for i in range(400)}}
            reader = espn_api._CoreRefReader()
            threading.Thread(target=reader.read, args=(references, espn_api._athlete_name), daemon=True).start()
            time.sleep(1)
            espn_api.stop_core_lookups()
        """), encoding="utf-8")
        started = time.monotonic()
        subprocess.run([sys.executable, str(script)], check=True, timeout=20)
        assert time.monotonic() - started < 10

    def test_quitting_stops_the_lookups(self):
        source = (Path(__file__).parents[3] / "scores.py").read_text(encoding="utf-8")
        assert "aboutToQuit.connect(stop_core_lookups)" in source

    def test_every_name_failing_is_a_failure_not_a_screen_of_blanks(self, leaders):
        leaders.on(r"/athletes/\d+", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("EPL")

    def test_a_server_error_on_a_name_is_asked_again(self, leaders):
        answers = [HTTP_500]
        leaders.on(r"/athletes/253989", lambda url: answers.pop() if answers else athlete(url))
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert stats[0]["player_name"] == "Erling Haaland"

    def test_a_not_found_name_is_not_asked_again(self, leaders):
        leaders.on(r"/athletes/253989", HTTP_404)
        espn_api.get_player_statistics("EPL")
        assert len(leaders.urls("/athletes/253989")) == 1

    def test_a_timeout_on_a_name_is_not_asked_again(self, leaders):
        leaders.on(r"/athletes/253989", TIMEOUT)
        espn_api.get_player_statistics("EPL")
        assert len(leaders.urls("/athletes/253989")) == 1

    def test_a_lost_connection_on_a_name_is_asked_again(self, leaders):
        leaders.on(r"/athletes/253989", requests.ConnectionError("reset"))
        espn_api.get_player_statistics("EPL")
        assert len(leaders.urls("/athletes/253989")) == 2

    def test_a_name_that_is_not_json_is_left_out(self, leaders):
        leaders.on(r"/athletes/253989", NOT_JSON)
        stats = espn_api.get_player_statistics("EPL")["player_stats"][0]["stats"]
        assert stats[0]["player_name"] == soccer.NAME_UNAVAILABLE

    def test_a_stalled_network_stops_asking_for_the_rest(self, leaders):
        references = {leader["athlete"]["$ref"] for category in load("leaders_core_EPL.json")["categories"]
                      for leader in category["leaders"]}
        teams = {leader["team"]["$ref"] for category in load("leaders_core_EPL.json")["categories"]
                 for leader in category["leaders"]}
        leaders.on(r"/athletes/\d+", TIMEOUT)
        leaders.on(r"/seasons/\d+/teams/\d+", TIMEOUT)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("EPL")
        stopped_at = espn_api.CORE_REF_FAILURES_BEFORE_GIVING_UP + espn_api.CORE_REF_WORKERS
        asked = leaders.urls("/athletes/") + leaders.urls(r"/seasons/\d+/teams/")
        assert len(references) + len(teams) > stopped_at, "the fixture should have enough references to show it"
        assert len(asked) <= stopped_at

    def test_a_network_that_stalls_after_some_names_fails_rather_than_a_screen_of_blanks(self, leaders):
        answered = []

        def first_then_nothing(url):
            if not answered:
                answered.append(url)
                return athlete(url)
            return requests.ConnectionError("reset")

        leaders.on(r"/athletes/\d+", first_then_nothing)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("EPL")

    def test_most_names_not_coming_fails_even_with_some_known_already(self, leaders):
        known = next(iter(soccer.core_leader_lists(load("leaders_core_EPL.json"))))["leaders"][0]["athlete"]
        espn_api._CORE_REF_CACHE[known] = "Erling Haaland"
        leaders.on(r"/athletes/\d+", HTTP_500)
        with pytest.raises(ApiError, match="ESPN isn't providing these right now"):
            espn_api.get_player_statistics("EPL")

    def test_every_name_known_already_needs_no_new_one(self, leaders):
        espn_api.get_player_statistics("EPL")
        leaders.on(r"/athletes/\d+", HTTP_500)
        assert espn_api.get_player_statistics("EPL")["player_stats"]

    def test_a_name_comes_from_whatever_the_page_has(self):
        assert espn_api._athlete_name({"fullName": "A B"}) == "A B"
        assert espn_api._athlete_name({"shortName": "A. B"}) == "A. B"
        assert espn_api._athlete_name({}) is None
        assert espn_api._team_abbreviation({"displayName": "Arsenal"}) == "Arsenal"


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

    @pytest.mark.parametrize("case", GRID["tables"], ids=lambda case: case["fixture"])
    def test_every_table_reads_as_the_grid_says(self, case):
        divisions = StandingsData(soccer.parse_soccer_standings(load(case["fixture"]))).divisions
        groups = [{"name": name, "rows": [soccer.soccer_table_cells(i + 1, team) for i, team in enumerate(teams)]}
                  for name, teams in divisions.items()]
        assert groups == case["groups"]

    @pytest.mark.parametrize("case", GRID["leaders"], ids=lambda case: case["fixture"])
    def test_every_list_of_leaders_reads_as_the_grid_says(self, espn, case):
        espn.on("/season$", load("season_EPL.json"))
        espn.on("/types/1/leaders", load(case["fixture"]))
        espn.on(r"/athletes/\d+", lambda url: {"displayName": "Athlete " + re.search(r"/athletes/(\d+)", url).group(1)})
        espn.on(r"/seasons/\d+/teams/\d+", lambda url: {"abbreviation": re.search(r"/teams/(\d+)", url).group(1)})
        answer = espn_api.get_player_statistics("EPL")
        assert answer["season"] == case["season"]
        lists = [{"title": category["category"],
                  "rows": [dict(zip(("rank", "player", "team", "value"), row))
                           for row in ranking_rows("player", category["stats"])]}
                 for category in answer["player_stats"]]
        assert lists == case["lists"]


def test_a_reference_that_is_not_text_is_no_reference():
    assert soccer._secure(None) == ""
    assert soccer._secure("https://espn.example/a") == "https://espn.example/a"


def test_a_team_list_with_no_leagues_is_no_teams():
    assert soccer.parse_team_list({}) == []
    assert soccer.parse_team_list({"sports": [{"leagues": []}]}) == []
