"""cfl.py on the CFL's real feed, and tests/fixtures/cfl_grid.json, which holds the iPhone
(CFLGridTests.swift) to the same reading of the weeks, the games, the standings and the teams."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import cfl

FIXTURES = Path(__file__).parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "cfl_grid.json").read_text(encoding="utf-8"))
ROUNDS = json.loads((FIXTURES / "espn" / GRID["rounds"]).read_text(encoding="utf-8"))
SQUADS = json.loads((FIXTURES / "espn" / GRID["squads"]).read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 8, 0, 53, tzinfo=timezone.utc)  # when the fixture was captured


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def game_row(g):
    return {"id": g["id"], "date": g["date"], "name": g["name"],
            "away": [g["away"]["id"], g["away"]["abbreviation"], g["away"]["score"], g["away"]["record"]],
            "home": [g["home"]["id"], g["home"]["abbreviation"], g["home"]["score"], g["home"]["record"]],
            "state": g["state"], "detail": g["detail"], "season_type": g["season_type"]}


def group_rows(groups):
    return [{"name": g["name"], "entries": [[e["rank"], e["id"], e["abbreviation"], e["record"]]
                                            for e in g["entries"]]} for g in groups]


# ------------------------------------------------------------------ the shared grid

@pytest.mark.parametrize("case", GRID["statuses"], ids=lambda c: c["case"])
def test_each_status_reads_as_the_grid_says(case):
    game = cfl.make_game(case["game"], cfl.REGULAR_SEASON, {})
    assert (game["state"], game["detail"]) == (case["state"], case["detail"])
    assert (game["away"]["score"], game["home"]["score"]) == (case["away_score"], case["home_score"])


@pytest.mark.parametrize("case", GRID["weeks"], ids=lambda c: c["case"])
def test_each_week_reads_as_the_grid_says(case):
    rounds = json.loads((FIXTURES / "espn" / case["rounds"]).read_text(encoding="utf-8"))
    week = cfl.parse_round(rounds, SQUADS, case["index"], at(case["now"]))
    assert week["index"] == case["expect_index"]
    assert (week["label"], week["count"], week["is_current"]) == (case["label"], case["count"], case["is_current"])
    assert [game_row(g) for g in week["games"]] == case["games"]


def test_the_standings_read_as_the_grid_says():
    assert group_rows(cfl.standings(SQUADS)) == GRID["standings"]


def test_draws_and_level_teams_read_as_the_grid_says():
    case = GRID["standings_with_draws"]
    assert group_rows(cfl.standings(case["squads"])) == case["groups"]


def test_the_teams_read_as_the_grid_says():
    assert [[t["id"], t["name"], t["abbreviation"]] for t in cfl.teams(SQUADS)] == GRID["teams"]


@pytest.mark.parametrize("case", GRID["schedules"], ids=lambda c: c["team_id"])
def test_each_schedule_reads_as_the_grid_says(case):
    games = cfl.team_schedule(ROUNDS, case["team_id"], SQUADS)
    assert [[g["id"], g["state"], g["detail"], g["away"]["score"], g["home"]["score"]] for g in games] == case["games"]


@pytest.mark.parametrize("case", GRID["team_info"], ids=lambda c: f"{c['team_id']} {c['now']}")
def test_each_team_reads_as_the_grid_says(case):
    info = cfl.team_info(ROUNDS, SQUADS, case["team_id"], at(case["now"]))
    next_id = info["next_game"]["id"] if info["next_game"] else None
    assert [info["name"], info["record"], info["standing"], next_id] == [
        case["name"], case["record"], case["standing"], case["next_game"]]


def test_the_failure_wording_is_the_iphones():
    for what, sentence in GRID["failed"].items():
        assert cfl.unavailable(what) == sentence


def test_the_grid_covers_every_status_the_feed_sends_and_a_live_game():
    assert {c["game"]["status"] for c in GRID["statuses"]} >= cfl.KNOWN_STATUSES
    assert any(g["state"] == "in" for w in GRID["weeks"] for g in w["games"])
    assert any(g["detail"] == "Q3 15:00" for w in GRID["weeks"] for g in w["games"])
    assert any(g["home"][0] == "0" for w in GRID["weeks"] for g in w["games"])


# ------------------------------------------------------------------ the feed itself

class TestTheFeed:
    def test_the_captured_week_has_a_game_at_halftime_after_its_end(self):
        # The capture: the West final at halftime, at 00:53Z, past the round's end of 23:59Z.
        week = ROUNDS[25]
        assert week["name"] == "Conference Finals" and week["endDate"] == "2026-11-07T23:59:00+00:00"
        assert [g["status"] for g in week["tournaments"]] == ["complete", "half_time"]
        assert cfl.current_round_index(ROUNDS, NOW) == 25

    def test_going_by_the_end_alone_would_have_shown_the_grey_cup(self):
        finished = json.loads(json.dumps(ROUNDS))
        finished[25]["tournaments"][1]["status"] = "complete"
        assert cfl.current_round_index(finished, NOW) == 26

    def test_a_week_whose_end_cant_be_read_isnt_over(self):
        rounds = [{"name": "A", "endDate": "2020-01-01T00:00:00+00:00", "tournaments": []},
                  {"name": "B", "endDate": None, "tournaments": []}]
        assert cfl.current_round_index(rounds, NOW) == 1

    def test_after_the_season_its_the_last_week(self):
        rounds = [{"name": "A", "endDate": "2020-01-01T00:00:00+00:00", "tournaments": []},
                  {"name": "B", "endDate": "2020-01-02T00:00:00+00:00", "tournaments": []}]
        assert cfl.current_round_index(rounds, NOW) == 1

    def test_no_weeks_at_all(self):
        assert cfl.parse_round([], SQUADS) == {"games": [], "index": 0, "label": "", "count": 0, "is_current": True}
        assert cfl.parse_round(None, None)["count"] == 0
        assert cfl.standings(None) == [] and cfl.teams("nonsense") == []

    def test_a_hidden_game_isnt_listed(self):
        rounds = json.loads(json.dumps(ROUNDS))
        rounds[3]["tournaments"][0]["isHidden"] = True
        assert len(cfl.parse_round(rounds, SQUADS, 3)["games"]) == 2

    def test_tbd_is_not_a_team(self):
        assert SQUADS[0]["id"] == 0
        assert "0" not in [t["id"] for t in cfl.teams(SQUADS)]
        assert sum(len(g["entries"]) for g in cfl.standings(SQUADS)) == 9

    def test_every_team_in_the_feed_has_a_known_division(self):
        assert {t["abbreviation"] for t in cfl.teams(SQUADS)} == cfl.EAST_TEAMS | cfl.WEST_TEAMS

    def test_a_status_that_isnt_text_is_scheduled(self):
        assert cfl.game_status({"status": {"odd": 1}})["detail"] == "Scheduled"
        assert cfl.game_status({"status": ["x"]})["state"] == "pre"

    def test_a_week_with_no_name_is_week_n_everywhere(self):
        rounds = json.loads(json.dumps(ROUNDS))
        rounds[3]["name"] = None
        assert cfl.parse_round(rounds, SQUADS, 3)["label"] == "Week 4"
        assert {g["week"] for g in cfl.all_games(rounds, SQUADS) if g["id"] == "13419674"} == {"Week 4"}

    def test_a_team_not_listed_has_no_page(self):
        assert cfl.team_info(ROUNDS, SQUADS, "999") is None


# ------------------------------------------------------------------ what Windows shows

class TestRows:
    def week(self, index=None):
        return cfl.parse_round(ROUNDS, SQUADS, index, NOW)

    def test_score_rows(self, monkeypatch):
        rows = cfl.score_rows(self.week()["games"])
        assert [r[:3] for r in rows] == [
            ["Winnipeg Blue Bombers at Montreal Alouettes", "WPG 23, MTL 33", "Final"],
            ["BC Lions at Edmonton Elks", "BC 9, EDM 6", "Halftime"]]
        assert all(r[3] for r in rows)

    def test_a_game_to_come_has_no_score(self):
        assert cfl.score_rows(self.week(26)["games"])[0][:3] == ["Montreal Alouettes at TBD", "Not started", "Scheduled"]

    def test_week_summary(self):
        assert cfl.week_summary(self.week()) == "Conference Finals, this week, 2 games"
        assert cfl.week_summary(self.week(26)) == "113th Grey Cup, 1 game"
        assert cfl.week_summary({"label": "Week 9", "games": [], "is_current": False}) == "Week 9, no games"

    def test_the_game_page(self):
        game = self.week()["games"][1]
        assert cfl.game_rows(game) == [["BC Lions", "9", "10-8", "Away"], ["Edmonton Elks", "6", "13-5", "Home"]]
        assert cfl.game_summary(game).startswith("Halftime. Conference Finals. Saturday, November 7, ")
        grey_cup = self.week(26)["games"][0]
        assert cfl.game_rows(grey_cup)[1] == ["TBD", "Not started", "No record", "Home"]

    def test_standings_rows(self):
        groups = cfl.standings(SQUADS)
        assert cfl.standings_headers(groups) == ["Rank", "Team", "Division", "W", "L", "Pct"]
        rows = cfl.standings_rows(groups)
        assert rows[0] == ["1", "Montreal Alouettes", "East Division", "14", "4", ".778"]
        assert rows[4] == ["1", "Edmonton Elks", "West Division", "13", "5", ".722"]
        assert cfl.standings_team_ids(groups)[4] == "114347"

    def test_a_draw_adds_a_ties_column(self):
        groups = cfl.standings(GRID["standings_with_draws"]["squads"])
        assert cfl.standings_headers(groups) == ["Rank", "Team", "Division", "W", "L", "T", "Pct"]
        assert cfl.standings_rows(groups)[0] == ["1", "Hamilton Tiger-Cats", "East Division", "5", "4", "1", ".550"]
        assert cfl.standings_rows(groups)[-1][-1] == ".000"

    def test_an_unbeaten_team_is_1000(self):
        assert cfl._percent_text(1.0) == "1.000"

    def test_team_rows(self):
        rows = cfl.team_rows(cfl.teams(SQUADS))
        assert rows[0] == ["BC Lions", "BC", "West Division", "10-8"]
        assert len(rows) == 9

    def test_schedule_rows_say_it_from_the_teams_side(self):
        games = cfl.team_schedule(ROUNDS, "114347", SQUADS)
        rows = cfl.schedule_rows(games, "114347")
        assert [r[0:2] for r in rows[-2:]] == [["at Saskatchewan Roughriders", "L 9-16"], ["vs BC Lions", "Halftime, 6-9"]]
        assert rows[-1][3] == "Conference Finals"
        assert cfl.schedule_start_row(games) == len(games) - 1

    def test_a_season_over_starts_on_its_last_game(self):
        games = cfl.team_schedule(ROUNDS, "88019", SQUADS)
        assert cfl.schedule_start_row(games) == len(games) - 1
        assert cfl.schedule_start_row([]) == 0

    def test_a_tie(self):
        game = cfl.make_game({"id": 5, "date": "2026-07-03T23:30:00+00:00", "status": "complete",
                              "homeSquad": {"id": 1, "name": "A", "shortName": "A", "score": 20},
                              "awaySquad": {"id": 2, "name": "B", "shortName": "B", "score": 20}}, 2, {})
        assert cfl.schedule_result(game, "1") == "T 20-20"

    def test_team_summary(self):
        mtl = cfl.team_info(ROUNDS, SQUADS, "86680", NOW)
        assert cfl.team_summary(mtl).startswith(
            "14-4, 1st in East Division. Next game: at TBD, Sunday, November 15, ")
        edm = cfl.team_info(ROUNDS, SQUADS, "114347", NOW)
        assert cfl.team_summary(edm) == "13-5, 1st in West Division."

    def test_a_date_that_cant_be_read(self):
        assert cfl.parse_date("soon") is None and cfl.parse_date(None) is None
        assert cfl.iso(None) == ""
        game = cfl.make_game({"id": 5, "date": "soon", "status": "scheduled"}, 2, {})
        assert game["date"] == "" and cfl.kickoff_text(game) == ""
        assert game["away"]["name"] == "TBD"
