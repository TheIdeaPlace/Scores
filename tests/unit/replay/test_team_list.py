"""A league's list of teams, for Teams and the Transactions filter, on ESPN's real answers: from
/teams?limit=1000 with the standings' groups and records, or from the standings alone where the
team list can't say which teams are the league's. tests/fixtures/team_list_sources.json holds both
apps to which leagues are which."""
import json
from pathlib import Path

import pytest

import espn_api
import settings
import team_list
from exceptions import ApiError
from services.api_service import ApiService

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, load

GRID = json.loads((Path(__file__).parents[2] / "fixtures" / "team_list_sources.json").read_text(encoding="utf-8"))


class TestTheSharedGrid:
    def test_the_grid_names_every_league_with_teams_once(self):
        named = GRID["standings"] + GRID["teamList"]
        assert len(named) == len(set(named))
        with_teams = {path for key, path in espn_api.LEAGUES.items()
                      if not path.startswith("golf/") and key not in ("WC2026", "WWC2027")}
        assert set(named) == with_teams

    @pytest.mark.parametrize("path", GRID["standings"])
    def test_these_come_from_the_standings(self, path):
        assert team_list.source(path) == team_list.STANDINGS

    @pytest.mark.parametrize("path", GRID["teamList"])
    def test_these_come_from_the_team_list(self, path):
        assert team_list.source(path) == team_list.TEAM_LIST


class TestParse:
    def test_a_team_list_reads_name_id_abbreviation_and_logo(self):
        rows = team_list.parse_team_list(load("teams_MLB.json"))
        assert len(rows) == 10
        yankees = next(row for row in rows if row["team_name"] == "New York Yankees")
        assert yankees["team_id"] == "10"
        assert yankees["abbreviation"] == "NYY"
        assert yankees["logo"].endswith(".png")
        assert yankees["division"] == team_list.TEAMS_WITH_NO_GROUP
        assert "wins" not in yankees

    def test_a_team_with_no_logos_has_an_empty_one(self):
        data = load("teams_NCAAH.json")
        for entry in data["sports"][0]["leagues"][0]["teams"]:
            entry["team"]["logos"] = None
        rows = team_list.parse_team_list(data)
        assert len(rows) == 7 and all(row["logo"] == "" for row in rows)

    @pytest.mark.parametrize("data", [{}, {"sports": None}, {"sports": [{"leagues": []}]},
                                      {"sports": [{"leagues": [{"teams": [None, {"team": None}, {"team": {"id": 1}}]}]}]}],
                             ids=["nothing", "null", "no_leagues", "no_names"])
    def test_a_list_with_nothing_readable_is_no_teams(self, data):
        assert team_list.parse_team_list(data) == []


class TestWithStandings:
    def listed(self, *teams):
        return [{"team_name": name, "team_id": tid, "abbreviation": "", "logo": "",
                 "division": team_list.TEAMS_WITH_NO_GROUP} for name, tid in teams]

    def test_a_team_in_the_standings_is_its_standings_row(self):
        standings = [{"team_name": "A", "team_id": "1", "division": "East", "wins": 3}]
        assert team_list.with_standings(self.listed(("A", "1")), standings) == standings

    def test_a_team_the_standings_leave_out_comes_last_under_other_teams(self):
        standings = [{"team_name": "A", "team_id": "1", "division": "East", "wins": 3}]
        rows = team_list.with_standings(self.listed(("B", "2"), ("A", "1")), standings)
        assert [row["team_name"] for row in rows] == ["A", "B"]
        assert rows[1]["division"] == team_list.OTHER_TEAMS
        assert "wins" not in rows[1]

    def test_with_no_standings_every_team_is_one_group(self):
        rows = team_list.with_standings(self.listed(("B", "2"), ("A", "1")), [])
        assert {row["division"] for row in rows} == {team_list.TEAMS_WITH_NO_GROUP}
        assert len(rows) == 2

    def test_a_standings_team_off_the_list_stays(self):
        standings = [{"team_name": "Delaware Blue Hens", "team_id": "48", "division": "League", "wins": 0}]
        assert team_list.with_standings([], standings) == standings

    def test_the_same_school_under_another_id_is_listed_once(self):
        standings = [{"team_name": "Minnesota State Mavericks", "team_id": "99", "division": "League", "wins": 0}]
        rows = team_list.with_standings(self.listed(("Minnesota State Mavericks", "2364")), standings)
        assert rows == standings

    def test_a_team_twice_on_the_list_is_listed_once(self):
        rows = team_list.with_standings(self.listed(("A", "1"), ("A", "1")), [])
        assert len(rows) == 1

    def test_records_are_rows_with_wins(self):
        assert team_list.has_records([{"team_name": "A"}, {"team_name": "B", "wins": 0}])
        assert not team_list.has_records([{"team_name": "A"}])
        assert not team_list.has_records([])


class TestGetTeams:
    def test_a_pro_league_is_its_team_list_with_the_standings_records(self, espn):
        espn.on("/baseball/mlb/standings", load("standings_MLB.json"))
        espn.on("/baseball/mlb/teams", load("teams_MLB.json"))
        teams = ApiService.get_teams("MLB")
        assert len(teams) == 10
        yankees = next(team for team in teams if team["team_name"] == "New York Yankees")
        assert yankees["division"] == "AL East"
        assert "wins" in yankees
        others = [team for team in teams if team["division"] == team_list.OTHER_TEAMS]
        assert sorted(team["team_name"] for team in others) == ["Colorado Rockies", "Miami Marlins"]
        assert all("wins" not in team for team in others)
        assert espn.urls(r"/teams\?limit=1000$")

    def test_a_league_between_seasons_still_has_its_teams(self, espn):
        espn.on("/standings", HTTP_404)
        espn.on("/teams", load("teams_MLB.json"))
        teams = ApiService.get_teams("MLB")
        assert len(teams) == 10
        assert {team["division"] for team in teams} == {team_list.TEAMS_WITH_NO_GROUP}
        assert not any(team.get("records_unavailable") for team in teams)

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON], ids=["timeout", "500", "not_json"])
    def test_standings_that_fail_cost_the_records_not_the_teams(self, espn, reply):
        espn.on("/standings", reply)
        espn.on("/teams", load("teams_MLB.json"))
        teams = ApiService.get_teams("MLB")
        assert len(teams) == 10
        assert all(team["records_unavailable"] for team in teams)
        assert all("wins" not in team for team in teams)

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, {"sports": None}],
                             ids=["timeout", "500", "not_json", "null"])
    def test_a_team_list_that_fails_says_so(self, espn, reply):
        espn.on("/standings", load("standings_MLB.json"))
        espn.on("/teams", reply)
        with pytest.raises(ApiError) as caught:
            ApiService.get_teams("MLB")
        assert str(caught.value) == espn_api.TEAMS_UNAVAILABLE

    def test_college_hockey_lists_the_teams_its_standings_leave_out(self, espn):
        espn.on("/mens-college-hockey/standings", load("standings_NCAAH.json"))
        espn.on("/mens-college-hockey/teams", load("teams_NCAAH.json"))
        teams = ApiService.get_teams("NCAAH")
        williams = next(team for team in teams if team["team_name"] == "Williams Ephs")
        assert williams["division"] == team_list.OTHER_TEAMS
        assert sum(team["team_name"] == "Michigan State Spartans" for team in teams) == 1

    def test_womens_college_basketball_is_its_division_one_team_list(self, espn):
        espn.on("/womens-college-basketball/standings", load("standings_NCAAWB.json"))
        espn.on("/womens-college-basketball/teams", load("teams_NCAAWB.json"))
        teams = ApiService.get_teams("NCAAWB")
        ids = [team["team_id"] for team in teams]
        listed = [row["team_id"] for row in team_list.parse_team_list(load("teams_NCAAWB.json"))]
        assert len(listed) == 6
        assert all(ids.count(tid) == 1 for tid in listed)
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("coverage,group", [("fbs", "80"), ("all_d1", "90")])
    def test_college_football_is_its_standings_and_follows_the_coverage_setting(self, espn, coverage, group):
        settings.set("ncaaf_coverage", coverage)
        espn.on("/college-football/standings", load("standings_NCAAF_group90.json"))
        teams = ApiService.get_teams("NCAAF")
        assert len(teams) == 26
        assert any(team["team_name"] == "Montana State Bobcats" for team in teams)
        assert espn.calls == [f"https://site.api.espn.com/apis/v2/sports/football/college-football/standings?group={group}"]

    def test_mens_college_basketball_is_its_standings_not_the_cut_off_list(self, espn):
        espn.on("/mens-college-basketball/standings", load("standings_NCAAM.json"))
        espn.on("/mens-college-basketball/teams", load("teams_NCAAM_all.json"))
        teams = ApiService.get_teams("NCAAM")
        assert teams
        assert not espn.urls("/teams")
        assert not any(team["team_name"] == "Williams Ephs" for team in teams)

    @pytest.mark.parametrize("league", ["NCAAF", "NCAAM"])
    def test_standings_that_fail_where_they_are_the_list_say_so(self, espn, league):
        espn.on("/standings", HTTP_500)
        with pytest.raises(ApiError) as caught:
            ApiService.get_teams(league)
        assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE

    def test_no_teams_anywhere_is_no_teams(self, espn):
        espn.on("/standings", HTTP_404)
        espn.on("/teams", EMPTY_JSON)
        assert ApiService.get_teams("NBA") == []
