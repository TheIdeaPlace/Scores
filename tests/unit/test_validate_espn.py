"""The live validator's checks, on real saved payloads and damaged copies of them.

A validator that can't fail is worse than none, so each check is shown catching the break
it exists for. Nothing here touches the network.
"""
import copy
import glob
import json
import os
import sys
from datetime import date

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import validate_espn as v  # noqa: E402
from box_score import build_box_tables  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "espn")


def load(pattern):
    with open(glob.glob(os.path.join(FIXTURES, pattern))[0], encoding="utf-8") as f:
        return json.load(f)


def box(league):
    return load(f"box_{league}_*.json")["boxscore"]


def league(key):
    return v.LEAGUE_KEYS[key]


def event(state="post", name="STATUS_FINAL", completed=True, competitors=2):
    return {
        "id": "1", "date": "2026-11-02T01:00Z",
        "status": {"type": {"state": state, "name": name, "completed": completed}},
        "competitions": [{"competitors": [
            {"homeAway": "home" if i == 0 else "away", "team": {"displayName": f"T{i}", "abbreviation": f"T{i}"}}
            for i in range(competitors)]}],
    }


class TestBoxScores:
    @pytest.mark.parametrize("key", ["NFL", "NCAAF", "NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "MLB"])
    def test_real_payloads_pass(self, key):
        assert v.box_score_problems(box(key), league(key)) == []

    @pytest.mark.parametrize("key", ["NCAAH", "NCAAWH"])
    def test_college_hockey_has_none_and_that_is_fine(self, key):
        assert v.box_score_problems(box(key), league(key)) == []

    def test_no_boxscore(self):
        assert v.box_score_problems(None, league("NBA")) == ["no boxscore"]

    def test_athlete_with_no_name_at_all(self):
        data = copy.deepcopy(box("NCAAM"))
        data["players"][0]["statistics"][0]["athletes"][0]["athlete"] = {"links": []}
        assert any("neither displayName nor shortName" in p for p in v.box_score_problems(data, league("NCAAM")))

    def test_athlete_with_only_a_short_name_is_fine(self):
        data = copy.deepcopy(box("NCAAM"))
        data["players"][0]["statistics"][0]["athletes"][0]["athlete"] = {"shortName": "J. Loubens"}
        assert v.box_score_problems(data, league("NCAAM")) == []

    def test_stats_out_of_line_with_columns(self):
        data = copy.deepcopy(box("NBA"))
        group = data["players"][0]["statistics"][0]
        athlete = next(a for a in group["athletes"] if a.get("stats"))
        athlete["stats"] = athlete["stats"][:-1]
        assert any("columns" in p for p in v.box_score_problems(data, league("NBA")))

    def test_columns_gone(self):
        data = copy.deepcopy(box("NFL"))
        for team in data["players"]:
            for group in team["statistics"]:
                group.pop("labels", None)
                group.pop("names", None)
        assert any("no names or labels" in p for p in v.box_score_problems(data, league("NFL")))

    def test_football_group_renamed(self):
        data = copy.deepcopy(box("NFL"))
        for team in data["players"]:
            for group in team["statistics"]:
                if group.get("name") == "passing":
                    group["name"] = "throwing"
        assert any("passing" in p for p in v.box_score_problems(data, league("NFL")))

    def test_team_stats_lose_their_values(self):
        data = copy.deepcopy(box("NCAAM"))
        for stat in data["teams"][0]["statistics"]:
            stat.pop("displayValue")
        assert any("displayValue" in p for p in v.box_score_problems(data, league("NCAAM")))

    def test_baseball_categories_flattened(self):
        data = copy.deepcopy(box("MLB"))
        for stat in data["teams"][0]["statistics"]:
            stat.pop("stats", None)
        assert any("nested" in p for p in v.box_score_problems(data, league("MLB")))

    def test_every_player_check_sees_a_dropped_player(self):
        data = box("NBA")
        tables = build_box_tables(data)
        assert v.played_athletes_missing_from_tables(data, tables) == []
        tables[0].rows = tables[0].rows[1:]
        assert v.played_athletes_missing_from_tables(data, tables)


class TestScoreboard:
    def test_real_events_pass(self):
        events = load("scoreboard_events_by_status.json")
        events = events.get("events", events) if isinstance(events, dict) else events
        if isinstance(events, dict):
            events = [e for group in events.values() for e in (group if isinstance(group, list) else [group])]
        assert v.scoreboard_problems({"events": events}) == []

    def test_no_events_key_is_a_break(self):
        assert v.scoreboard_problems({"leagues": []}) == ["no events list"]

    def test_empty_slate_is_fine(self):
        assert v.scoreboard_problems({"events": []}) == []

    def test_a_team_loses_its_name(self):
        broken = event()
        del broken["competitions"][0]["competitors"][0]["team"]["displayName"]
        assert any("displayName" in p for p in v.scoreboard_problems({"events": [broken]}))

    def test_status_shape_changes(self):
        broken = event()
        broken["status"] = {"typeId": "3"}
        assert any("status" in p for p in v.scoreboard_problems({"events": [broken]}))

    def test_three_competitors(self):
        assert any("3 competitors" in p for p in v.scoreboard_problems({"events": [event(competitors=3)]}))


class TestStandings:
    @pytest.mark.parametrize("key", ["NFL", "NBA", "NHL", "NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"])
    def test_real_payloads_pass(self, key):
        assert v.standings_problems(load(f"standings_{key}.json"), league(key)) == []

    def test_entries_at_the_root_are_found(self):
        assert v.standings_entries(load("standings_NCAAWH.json"))

    def test_nested_conferences_are_found(self):
        data = load("standings_NCAAF.json")
        names = {e["team"]["displayName"] for e in v.standings_entries(data)}
        assert "App State Mountaineers" in names or len(names) > 1

    def test_empty(self):
        assert v.standings_problems({"children": []}, league("NFL")) == ["no entries anywhere in the response"]

    def test_overall_record_stat_gone(self):
        data = copy.deepcopy(load("standings_NFL.json"))
        for entry in v.standings_entries(data):
            for stat in entry["stats"]:
                if stat.get("type") == "total":
                    stat["type"] = "overall"
        assert any("total" in p for p in v.standings_problems(data, league("NFL")))


class TestPlays:
    def test_real_basketball_plays_pass(self):
        data = load("plays_NBA_*.json")
        assert v.play_problems({"plays": data.get("plays", data)}, league("NBA")) == []

    def test_real_hockey_plays_pass(self):
        data = load("plays_NHL_*.json")
        assert v.play_problems({"plays": data.get("plays", data)}, league("NHL")) == []

    def test_empty_plays(self):
        assert v.play_problems({"plays": []}, league("NBA")) == ["plays is empty"]

    def test_college_hockey_has_none_and_that_is_fine(self):
        assert v.play_problems({"plays": []}, league("NCAAH")) == []

    def test_coordinates_vanish(self):
        plays = [{"id": "1", "type": {"text": "Shot"}, "period": {"number": 1}}]
        assert any("coordinate" in p for p in v.play_problems({"plays": plays}, league("NBA")))

    def test_coordinate_system_changes(self):
        plays = [{"id": "1", "type": {"text": "Shot"}, "period": {"number": 1}, "coordinate": {"x": 900, "y": 3}}]
        assert any("outside" in p for p in v.play_problems({"plays": plays}, league("NBA")))

    def test_espn_no_location_value_is_not_a_wild_coordinate(self):
        plays = [{"id": "1", "type": {"text": "Sub"}, "period": {"number": 1},
                  "coordinate": {"x": -214748340, "y": -214748365}}]
        assert v.play_problems({"plays": plays}, league("NBA")) == []

    def test_football_drives_gone(self):
        assert v.play_problems({"drives": {}}, league("NFL")) == ["drives.previous is empty"]

    def test_real_football_drives_pass(self):
        data = load("drives_NCAAF_2OT.json")
        drives = data.get("drives", data)
        assert v.play_problems({"drives": drives}, league("NCAAF")) == []


class TestFinals:
    def test_basketball_final(self):
        assert v.is_played_final(event())

    def test_soccer_says_full_time(self):
        assert v.is_played_final(event(name="STATUS_FULL_TIME"))

    def test_final_in_overtime(self):
        assert v.is_played_final(event(name="STATUS_FINAL_OT"))

    def test_postponed_is_post_but_not_played(self):
        assert not v.is_played_final(event(name="STATUS_POSTPONED"))

    def test_canceled(self):
        assert not v.is_played_final(event(name="STATUS_CANCELED", completed=True))

    def test_live_game(self):
        assert not v.is_played_final(event(state="in", name="STATUS_IN_PROGRESS", completed=False))

    def test_a_golf_style_field_is_not_a_game(self):
        assert not v.is_played_final(event(competitors=70))

    def test_espn_files_an_evening_game_under_its_eastern_date(self):
        assert v.espn_date("2026-11-03T01:00Z") == date(2026, 11, 2)
        assert v.espn_date("2026-11-03T18:00Z") == date(2026, 11, 3)


class TestInvented:
    def test_finds_sample_players_anywhere(self):
        data = {"player_stats": [{"stats": [{"player_name": "Sample Player 1", "team": "X"}]}]}
        assert v.invented_names(data) == ["Sample Player 1"]

    def test_real_names_are_fine(self):
        assert v.invented_names({"player_stats": [{"player_name": "Jordan Love"}]}) == []


class TestReport:
    def test_fail_decides_the_outcome(self):
        report = v.Report()
        report.ok("NFL", "a")
        report.warn("NFL", "b", "why")
        assert not report.failed
        report.fail("NFL", "c", "why")
        assert report.failed

    def test_failures_come_first_and_pipes_are_escaped(self):
        from datetime import datetime
        report = v.Report()
        report.ok("NFL", "Fine")
        report.fail("NBA", "Broken", "a|b", "https://x")
        text = v.render(report, datetime(2026, 11, 3), 5)
        assert "is broken" in text
        assert text.index("## Failed") < text.index("## Passed")
        assert "a\\|b" in text

    def test_clean_run_says_so(self):
        from datetime import datetime
        report = v.Report()
        report.ok("NFL", "Fine")
        assert "Nothing the apps rely on is broken" in v.render(report, datetime(2026, 11, 3), 5)

    def test_every_league_the_app_has_with_a_standard_path_is_known(self):
        import espn_api
        for key, spec in v.LEAGUE_KEYS.items():
            assert espn_api.LEAGUES[key] == spec.path, key


class TestHttp:
    class FakeSession:
        def __init__(self, responses):
            self.responses = list(responses)
            self.headers = {}
            self.calls = 0

        def get(self, url, timeout):
            self.calls += 1
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    class FakeResponse:
        def __init__(self, status, data=None):
            self.status_code, self.data = status, data

        def json(self):
            if self.data is None:
                raise ValueError
            return self.data

    def http(self, responses):
        http = v.Http(pause=0)
        http.session = self.FakeSession(responses)
        return http

    def test_a_503_is_retried(self):
        http = self.http([self.FakeResponse(503), self.FakeResponse(200, {"ok": 1})])
        assert http.get("u") == (200, {"ok": 1})
        assert http.session.calls == 2

    def test_a_timeout_is_retried_then_reported(self):
        http = self.http([v.requests.Timeout()] * 3)
        assert http.get("u") == ("Timeout", None)
        assert http.session.calls == 3

    def test_a_400_is_an_answer_not_a_blip(self):
        http = self.http([self.FakeResponse(400, {"code": 400})])
        assert http.get("u") == (400, {"code": 400})
        assert http.session.calls == 1

    def test_a_page_that_is_not_json(self):
        http = self.http([self.FakeResponse(200)])
        assert http.get("u") == (200, None)
