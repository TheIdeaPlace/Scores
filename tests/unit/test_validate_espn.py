"""The live validator's checks, on real saved payloads and damaged copies of them.

A validator that can't fail is worse than none, so each check is shown catching the break
it exists for. Nothing here touches the network.
"""
import copy
import dataclasses
import glob
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

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
        "id": "1", "date": "2026-11-02T01:00Z", "shortName": "T1 @ T0", "season": {"year": 2026, "type": 2},
        "week": {"number": 9},
        "status": {"type": {"state": state, "name": name, "completed": completed}},
        "competitions": [{"status": {"type": {"name": name}}, "competitors": [
            {"homeAway": "home" if i == 0 else "away", "score": "1",
             "team": {"id": f"T{i}", "displayName": f"T{i}", "abbreviation": f"T{i}"}}
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

    def test_a_blank_event_is_not_a_broken_feed_but_is_mentioned(self):
        """ESPN's own list for week 8 of college football in 2025 has a literal {} in it."""
        assert v.scoreboard_problems({"events": [event(), {}]}) == []
        report = v.Report()
        v.check_scoreboard(FakeHttp(default=(200, {"events": [event(), {}]})), report, league("NBA"))
        assert statuses(report, "Scoreboard") == [v.PASS, v.WARN]

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

    def test_competition_status_gone(self):
        broken = event()
        del broken["competitions"][0]["status"]
        assert any("competition status" in p for p in v.scoreboard_problems({"events": [broken]}))

    def test_a_finished_game_with_no_score(self):
        broken = event()
        del broken["competitions"][0]["competitors"][0]["score"]
        assert any("no score" in p for p in v.scoreboard_problems({"events": [broken]}))

    def test_a_postponed_game_needs_no_score(self):
        postponed = event(name="STATUS_POSTPONED")
        for competitor in postponed["competitions"][0]["competitors"]:
            del competitor["score"]
        assert v.scoreboard_problems({"events": [postponed]}) == []

    def test_football_calendar(self):
        assert v.calendar_problems({"leagues": [{"calendar": [{"entries": [{"value": "1"}]}]}]}) == []
        assert v.calendar_problems({"leagues": [{"calendar": []}]})
        assert v.calendar_problems({"leagues": [{"calendar": [{"entries": []}]}]})
        assert v.calendar_problems({})


class TestStandings:
    @pytest.mark.parametrize("key", ["NFL", "NBA", "NHL", "NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"])
    def test_real_payloads_pass(self, key):
        assert v.standings_problems(load(f"standings_{key}.json"), league(key)) == []

    def test_entries_at_the_root_are_found(self):
        assert v.standings_entries(load("standings_NCAAWH.json"))

    def test_nested_conferences_are_found(self):
        data = load("standings_NCAAF.json")
        names = {e["team"]["displayName"] for e in v.standings_entries(data)}
        assert "App State Mountaineers" in names

    def test_empty_is_for_the_season_to_judge(self):
        assert v.standings_problems({"children": []}, league("NFL")) == []

    def test_group_90_passes_the_shape_checks(self):
        assert v.standings_problems(load("standings_NCAAF_group90.json"), league("NCAAF")) == []

    def test_coverage_needs_the_teams_and_both_divisions(self):
        data = load("standings_NCAAF_group90.json")
        trimmed = league("NCAAF")
        assert v.standings_coverage_problems(data, trimmed) == [
            f"{len(v.standings_entries(data))} teams, expected at least 200"]
        assert v.standings_coverage_problems(data, dataclasses.replace(trimmed, standings_min_teams=20)) == []

    def test_coverage_finds_a_division_with_no_conferences(self):
        data = copy.deepcopy(load("standings_NCAAF_group90.json"))
        fcs = next(n for n in v._standing_nodes(data) if n.get("name") == "FCS")
        fcs["children"] = []
        problems = v.standings_coverage_problems(data, dataclasses.replace(league("NCAAF"), standings_min_teams=0))
        assert problems == ["no FCS conference has teams"]

    def test_coverage_of_an_empty_answer(self):
        problems = v.standings_coverage_problems({}, league("NCAAF"))
        assert problems == ["0 teams, expected at least 200", "no FBS conference has teams", "no FCS conference has teams"]

    def test_leagues_with_no_coverage_rule_have_no_coverage_problems(self):
        assert v.standings_coverage_problems(load("standings_NFL.json"), league("NFL")) == []
        assert "NCAAF" not in v.EXPECTED_DIVISIONS

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
                  "coordinate": {"x": -214748340, "y": -214748365}},
                 {"id": "2", "type": {"text": "Shot"}, "period": {"number": 1}, "coordinate": {"x": 10, "y": 20}}]
        assert v.play_problems({"plays": plays}, league("NBA")) == []

    def test_every_play_having_no_location_means_play_audio_has_nothing(self):
        plays = [{"id": "1", "type": {"text": "Sub"}, "period": {"number": 1},
                  "coordinate": {"x": -214748340, "y": -214748365}}]
        assert any("usable coordinate" in p for p in v.play_problems({"plays": plays}, league("NBA")))

    def test_y_is_checked_as_well_as_x(self):
        plays = [{"id": "1", "type": {"text": "Shot"}, "period": {"number": 1}, "coordinate": {"x": 10, "y": 900}}]
        assert any("outside" in p for p in v.play_problems({"plays": plays}, league("NBA")))

    def test_a_coordinate_as_text_is_not_usable(self):
        plays = [{"id": "1", "type": {"text": "Shot"}, "period": {"number": 1}, "coordinate": {"x": "10", "y": "20"}}]
        assert any("usable coordinate" in p for p in v.play_problems({"plays": plays}, league("NBA")))

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

    def test_a_pro_bowl_is_not_a_league_game(self):
        assert v.is_played_final(event(), {"T0", "T1"})
        assert not v.is_played_final(event(), {"T0", "T7"})

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


class FakeHttp(v.Http):
    """Answers by the first route whose text is in the URL. Anything else is a 404."""

    def __init__(self, routes=(), default=(404, None)):
        super().__init__(pause=0)
        self.routes, self.default, self.urls = list(routes), default, []

    def get(self, url, attempts=None, timeout=None):
        self.urls.append(url)
        for text, answer in self.routes:
            if text in url:
                return answer
        return self.default


def statuses(report, name):
    return [c.status for c in report.checks if c.name == name]


def detail(report, name):
    return " ".join(c.detail for c in report.checks if c.name == name)


class TestFindingFinals:
    def test_a_refused_date_is_counted(self):
        finals = v.find_recent_finals(FakeHttp(default=(400, {"code": 400})), league("NBA"))
        assert finals.events == []
        assert finals.bad_statuses == {"400": v.MONTHS_TO_SEARCH + 4}

    def test_a_september_style_break_fails_the_league(self):
        """ESPN refusing every dated query has to fail, not read as a quiet off-season."""
        report, _ = v.check_league(FakeHttp(default=(400, {"code": 400})), league("WNBA"))
        assert FAIL_IN(report, "Recent final")
        assert "400" in detail(report, "Recent final")

    def test_nothing_in_14_months_fails_even_with_clean_answers(self):
        report, in_season = v.check_league(FakeHttp(default=(200, {"events": []})), league("WNBA"))
        assert FAIL_IN(report, "Recent final")
        assert not in_season

    def test_a_refused_date_fails_even_if_an_earlier_day_answered(self, monkeypatch):
        finished = event()
        finished["date"] = datetime.now(timezone.utc).isoformat()
        http = FakeHttp([("teams?", (200, {"sports": [{"leagues": [{"teams": [{"team": {"id": "T0"}}, {"team": {"id": "T1"}}]}]}]}))])
        finals = v.Finals([finished], "u", {"400": 1})
        monkeypatch.setattr(v, "find_recent_finals", lambda *a, **k: finals)
        monkeypatch.setattr(v, "check_app_scores", lambda *a: None)
        monkeypatch.setattr(v, "check_games", lambda *a: None)
        monkeypatch.setattr(v, "check_standings", lambda *a: None)
        monkeypatch.setattr(v, "check_team_hub", lambda *a: None)
        monkeypatch.setattr(v, "check_news", lambda *a: None)
        monkeypatch.setattr(v, "check_statistics", lambda *a: None)
        report, in_season = v.check_league(http, league("NHL"))
        assert FAIL_IN(report, "Dated scoreboard")
        assert in_season

    def test_being_rate_limited_is_not_being_refused(self, monkeypatch):
        finished = event()
        finished["date"] = datetime.now(timezone.utc).isoformat()
        finals = v.Finals([finished], "u", {"429": 2})
        monkeypatch.setattr(v, "find_recent_finals", lambda *a, **k: finals)
        for name in ("check_app_scores", "check_games", "check_standings", "check_team_hub", "check_news",
                     "check_statistics", "check_transactions"):
            monkeypatch.setattr(v, name, lambda *a: None)
        report, _ = v.check_league(FakeHttp(), league("NHL"))
        assert statuses(report, "Dated scoreboard") == [v.WARN]

    def test_a_blip_on_a_date_is_only_a_warning(self, monkeypatch):
        finished = event()
        finished["date"] = datetime.now(timezone.utc).isoformat()
        finals = v.Finals([finished], "u", {"503": 1, "Timeout": 1})
        monkeypatch.setattr(v, "find_recent_finals", lambda *a, **k: finals)
        for name in ("check_app_scores", "check_games", "check_standings", "check_team_hub", "check_news",
                     "check_statistics", "check_transactions"):
            monkeypatch.setattr(v, name, lambda *a: None)
        report, _ = v.check_league(FakeHttp(), league("NHL"))
        assert statuses(report, "Dated scoreboard") == [v.WARN]

    def test_the_newest_final_comes_first(self):
        older, newer = event(), event()
        older["id"], newer["id"] = "old", "new"
        older["date"], newer["date"] = "2026-10-01T01:00Z", "2026-10-02T01:00Z"
        http = FakeHttp(default=(200, {"events": [older, newer]}))
        assert [e["id"] for e in v.find_recent_finals(http, league("NBA")).events] == ["new", "old"]


def FAIL_IN(report, name):
    return v.FAIL in statuses(report, name)


class TestOddGames:
    def finals(self, count):
        events = [event() for _ in range(count)]
        for i, item in enumerate(events):
            item["id"] = str(i)
        return v.Finals(events, "u", {})

    def summary(self, good):
        summary = dict(load("box_NBA_*.json"))
        plays = load("plays_NBA_*.json")
        summary["plays"] = plays.get("plays", plays) if isinstance(plays, dict) else plays
        summary["header"] = {"competitions": [{"status": {"type": {"state": "post"}}, "competitors": [{}, {}]}]}
        if not good:
            summary["boxscore"] = {"teams": []}
        return summary

    def run(self, answers):
        routes = [(f"event={i}", (200, self.summary(good))) for i, good in enumerate(answers)]
        report = v.Report()
        chosen = v.check_games(FakeHttp(routes), report, league("NBA"), self.finals(len(answers)), True)
        return report, chosen

    def test_a_good_game_reads_clean(self):
        report, chosen = self.run([True])
        assert chosen and not report.failed

    def test_one_odd_game_among_good_is_a_warning(self):
        report, chosen = self.run([False, True])
        assert statuses(report, "Box score shape") == [v.WARN]
        assert chosen[0]["id"] == "1"
        assert not report.failed

    def test_most_games_wrong_is_a_failure(self):
        report, chosen = self.run([False, False, True])
        assert FAIL_IN(report, "Box score shape")
        assert chosen[0]["id"] == "2"

    def test_all_games_wrong_is_a_failure(self):
        report, chosen = self.run([False, False, False])
        assert FAIL_IN(report, "Box score shape")
        assert chosen is None

    def test_a_league_with_only_one_final_to_go_on(self):
        report, _ = self.run([False])
        assert FAIL_IN(report, "Box score shape")

    def test_players_dropped_from_every_box_score_fails(self):
        def without_players():
            summary = self.summary(True)
            summary["boxscore"] = {**summary["boxscore"], "players": []}
            return summary

        routes = [(f"event={i}", (200, without_players())) for i in range(3)]
        report = v.Report()
        v.check_games(FakeHttp(routes), report, league("NBA"), self.finals(3), True)
        assert FAIL_IN(report, "Box score shape")
        assert "players" in detail(report, "Box score shape")

    def test_a_summary_that_will_not_load(self):
        report = v.Report()
        v.check_games(FakeHttp(default=(404, None)), report, league("NBA"), self.finals(3), True)
        assert FAIL_IN(report, "Game summary")


class TestInSeason:
    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_empty_standings(self, in_season, expected):
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, {"children": []})), report, league("NBA"), in_season)
        assert statuses(report, "Standings") == [expected]

    @pytest.mark.parametrize("in_season", [True, False])
    def test_an_error_status_fails_whatever_the_season(self, in_season):
        report = v.Report()
        v.check_standings(FakeHttp(default=(500, None)), report, league("NBA"), in_season)
        assert statuses(report, "Standings") == [v.FAIL]

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_empty_rankings(self, in_season, expected):
        report = v.Report()
        v.check_rankings(FakeHttp(default=(200, {"rankings": []})), report, league("NCAAM"), in_season)
        assert statuses(report, "Rankings") == [expected]

    def test_news_can_fail_any_month(self):
        report = v.Report()
        v.check_news(FakeHttp(default=(200, {"articles": []})), report, league("NBA"))
        assert statuses(report, "News") == [v.FAIL]


class StubbedApp:
    """The app's team hub calls, each answering well unless a test says otherwise."""

    def __init__(self, monkeypatch):
        import espn_api
        self.espn_api = espn_api
        self.monkeypatch = monkeypatch
        self.set("get_team_info", {"name": "T0", "record_overall": "1-0"})
        self.set("get_team_roster", [{"name": "A Player", "height": "6' 2\""}])
        self.set("get_team_schedule", [{"id": "1"}])
        self.set("get_team_news", [{"headline": "x"}])
        self.set("core_season", {"year": 2026, "type": {"type": 2}})
        self.set("get_standings", [])

    def set(self, name, answer):
        self.monkeypatch.setattr(self.espn_api, name, lambda *a, **k: answer)


class TestPastPostseasons:
    SEATTLE = "football/nfl/teams/26/schedule?season=2025&seasontype=3"
    ALABAMA = "college-football/teams/333/schedule?season=2025&seasontype=3"
    LYNX = "wnba/teams/8/schedule?season=2025&seasontype=3"

    def http(self, **changes):
        answers = {self.SEATTLE: (200, load("schedule_NFL_26_post.json")),
                   self.ALABAMA: (200, load("schedule_NCAAF_333_post.json")),
                   self.LYNX: (200, load("schedule_WNBA_8_post.json"))}
        answers.update(changes)
        return FakeHttp(list(answers.items()))

    def rows(self, monkeypatch, rows):
        import espn_api
        monkeypatch.setattr(espn_api, "get_team_schedule", lambda *a, **k: rows)

    def good_rows(self):
        return [{"date": "2026-02-08", "label": "Super Bowl LX College Football Playoff Semifinals"}]

    def test_real_payloads_pass(self, monkeypatch):
        self.rows(monkeypatch, self.good_rows())
        report = v.Report()
        v.check_past_postseasons(self.http(), report)
        assert not report.failed
        assert statuses(report, "Past postseason") == [v.PASS, v.PASS, v.PASS]

    def test_a_bad_status_fails(self, monkeypatch):
        self.rows(monkeypatch, self.good_rows())
        report = v.Report()
        v.check_past_postseasons(self.http(**{self.SEATTLE: (500, None)}), report)
        assert FAIL_IN(report, "Past postseason")

    def test_the_super_bowl_losing_its_label_fails(self, monkeypatch):
        self.rows(monkeypatch, self.good_rows())
        data = load("schedule_NFL_26_post.json")
        for item in data["events"]:
            item["competitions"][0]["notes"] = []
            item.pop("week", None)
        report = v.Report()
        v.check_past_postseasons(self.http(**{self.SEATTLE: (200, data)}), report)
        assert "none labelled" in detail(report, "Past postseason")

    def test_the_app_raising_fails(self, monkeypatch):
        import espn_api

        def broken(*a, **k):
            raise ValueError("no")

        monkeypatch.setattr(espn_api, "get_team_schedule", broken)
        report = v.Report()
        v.check_past_postseasons(self.http(), report)
        assert "raised ValueError" in detail(report, "App: past season")

    def test_the_app_showing_another_season_fails(self, monkeypatch):
        self.rows(monkeypatch, [{"date": "2020-11-01", "label": "Super Bowl"}])
        report = v.Report()
        v.check_past_postseasons(self.http(), report)
        assert "another season" in detail(report, "App: past season")

    def test_the_app_losing_the_label_fails(self, monkeypatch):
        self.rows(monkeypatch, [{"date": "2026-02-08", "label": ""}])
        report = v.Report()
        v.check_past_postseasons(self.http(), report)
        assert "none labelled" in detail(report, "App: past season")


class TestSoccerSchedules:
    """Arsenal's real answers. A past season is 38 games, so the fixture's three are repeated."""

    def results(self, count=30, year=None):
        data = load("schedule_EPL_359_2025.json")
        data["events"] = (data["events"] * count)[:count]
        data["requestedSeason"]["year"] = date.today().year - 2 if year is None else year
        return data

    def http(self, results=None, typed=None, fixtures=None):
        fixtures = load("schedule_EPL_359_fixture.json") if fixtures is None else fixtures
        return FakeHttp([("seasontype=2", typed or (200, {"events": []})),
                         ("fixture=true", fixtures if isinstance(fixtures, tuple) else (200, fixtures)),
                         ("season=", results or (200, self.results()))])

    def app(self, monkeypatch, past=None, current=None):
        import espn_api
        past = [{"date": "2025-01-01", "completed": True}] * 30 if past is None else past
        current = [{"date": "2026-11-01", "completed": False}] if current is None else current
        two_back = date.today().year - 2
        monkeypatch.setattr(espn_api, "get_team_schedule",
                            lambda league, team, season=None: past if season == two_back else current)

    def run(self, monkeypatch, http=None, past=None, current=None):
        self.app(monkeypatch, past, current)
        report = v.Report()
        v.check_soccer_schedules(http or self.http(), report)
        return report

    def test_all_well_for_both_leagues(self, monkeypatch):
        report = self.run(monkeypatch)
        assert not report.failed and not [c for c in report.checks if c.status == v.WARN]
        for name in ("Soccer results", "Soccer season type", "Soccer fixtures", "App: soccer schedule"):
            assert statuses(report, name) == [v.PASS, v.PASS]

    def test_never_asks_for_a_season_type_except_to_see_it_is_empty(self, monkeypatch):
        http = self.http()
        self.run(monkeypatch, http)
        typed = [u for u in http.urls if "seasontype" in u]
        assert typed and all("seasontype=2" in u for u in typed)

    def test_results_refused(self, monkeypatch):
        assert FAIL_IN(self.run(monkeypatch, self.http(results=(500, None))), "Soccer results")

    def test_too_few_results(self, monkeypatch):
        report = self.run(monkeypatch, self.http(results=(200, self.results(count=3))))
        assert "has 3 games" in detail(report, "Soccer results")

    def test_another_season_answers(self, monkeypatch):
        report = self.run(monkeypatch, self.http(results=(200, self.results(year=1999))))
        assert "asked for" in detail(report, "Soccer results")

    def test_season_year_gone(self, monkeypatch):
        data = self.results()
        del data["season"]
        report = self.run(monkeypatch, self.http(results=(200, data)))
        assert "season.year" in detail(report, "Soccer results")

    def test_a_season_type_starting_to_answer_is_worth_a_look(self, monkeypatch):
        report = self.run(monkeypatch, self.http(typed=(200, self.results())))
        assert statuses(report, "Soccer season type") == [v.WARN, v.WARN]
        assert not report.failed

    def test_fixtures_refused(self, monkeypatch):
        assert FAIL_IN(self.run(monkeypatch, self.http(fixtures=(500, None))), "Soccer fixtures")

    def test_no_fixtures_can_be_between_seasons(self, monkeypatch):
        report = self.run(monkeypatch, self.http(fixtures={"events": []}))
        assert statuses(report, "Soccer fixtures") == [v.WARN, v.WARN]
        assert not report.failed

    def test_the_app_raising_fails(self, monkeypatch):
        import espn_api

        def broken(*a, **k):
            raise ValueError("no")

        monkeypatch.setattr(espn_api, "get_team_schedule", broken)
        report = v.Report()
        v.check_soccer_schedules(self.http(), report)
        assert "raised ValueError" in detail(report, "App: soccer schedule")

    def test_the_app_with_too_few_rows(self, monkeypatch):
        report = self.run(monkeypatch, past=[{"date": "2025-01-01", "completed": True}])
        assert FAIL_IN(report, "App: soccer schedule")

    def test_the_app_stamping_current_games_on_a_past_season(self, monkeypatch):
        """What EPL season=2020 used to do: eight of this season's games."""
        rows = [{"date": "2026-11-07", "completed": False}] * 30
        report = self.run(monkeypatch, past=rows)
        assert "games to come" in detail(report, "App: soccer schedule")

    def test_the_app_with_nothing_for_the_current_season(self, monkeypatch):
        report = self.run(monkeypatch, current=[])
        assert FAIL_IN(report, "App: soccer schedule")


class TestTeamHub:
    def run(self, key, monkeypatch, days_ago=1, in_season=True, **answers):
        app = StubbedApp(monkeypatch)
        for name, answer in answers.items():
            app.set(name, answer)
        played = event()
        played["date"] = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        report = v.Report()
        v.check_team_hub(FakeHttp(default=(200, {})), report, league(key), played, in_season)
        return report

    def test_all_well(self, monkeypatch):
        assert not self.run("NBA", monkeypatch).failed

    def test_the_schedule_is_asked_for_as_team_hub_asks(self, monkeypatch):
        """With the top of the season list. Team Hub never leaves the season out."""
        import espn_api
        app = StubbedApp(monkeypatch)
        asked = []
        monkeypatch.setattr(espn_api, "get_team_schedule", lambda *a, **k: asked.append(a) or [{"id": "1"}])
        played = event()
        played["date"] = datetime.now(timezone.utc).isoformat()
        v.check_team_hub(FakeHttp(default=(200, {})), v.Report(), league("WNBA"), played, True)
        assert app and asked[0][4] == espn_api.get_available_seasons("WNBA")[0][0]

    def test_schedule_empty_after_a_recent_game_is_a_failure(self, monkeypatch):
        assert FAIL_IN(self.run("NBA", monkeypatch, get_team_schedule=[]), "App: schedule")

    @pytest.mark.parametrize("key", ["EPL", "WNBA"])
    def test_no_league_excuses_an_empty_schedule_any_more(self, monkeypatch, key):
        """WNBA and soccer used to read 30 days of scoreboard, which an old game fell outside."""
        report = self.run(key, monkeypatch, days_ago=60, in_season=False, get_team_schedule=[])
        assert FAIL_IN(report, "App: schedule")

    def test_a_decimal_height_is_caught(self, monkeypatch):
        report = self.run("NBA", monkeypatch, get_team_roster=[{"name": "A", "height": "74.0"}])
        assert FAIL_IN(report, "App: roster")

    def test_college_hockey_having_no_record_or_roster_is_known(self, monkeypatch):
        report = self.run("NCAAH", monkeypatch, get_team_info={"name": "T0"}, get_team_roster=[])
        assert statuses(report, "App: team info") == [v.PASS]
        assert statuses(report, "App: roster") == [v.PASS]

    def test_a_roster_espn_has_and_the_app_lost_fails_any_season(self, monkeypatch):
        app = StubbedApp(monkeypatch)
        app.set("get_team_roster", [])
        played = event()
        played["date"] = datetime.now(timezone.utc).isoformat()
        http = FakeHttp([("/roster", (200, {"athletes": [{"id": 1}]}))], default=(200, {}))
        report = v.Report()
        v.check_team_hub(http, report, league("NCAAH"), played, False)
        assert FAIL_IN(report, "App: roster")

    def test_news_espn_has_and_the_app_lost_fails(self, monkeypatch):
        app = StubbedApp(monkeypatch)
        app.set("get_team_news", [])
        played = event()
        played["date"] = datetime.now(timezone.utc).isoformat()
        http = FakeHttp([("/news", (200, {"articles": [{"headline": "x"}]}))], default=(200, {}))
        report = v.Report()
        v.check_team_hub(http, report, league("NBA"), played, False)
        assert FAIL_IN(report, "App: team news")

    def test_a_quiet_team_only_warns(self, monkeypatch):
        report = self.run("NBA", monkeypatch, get_team_news=[])
        assert statuses(report, "App: team news") == [v.WARN]

    def test_an_empty_roster_in_season_is_a_failure(self, monkeypatch):
        assert FAIL_IN(self.run("NHL", monkeypatch, get_team_roster=[]), "App: roster")

    def test_an_app_call_raising_is_a_failure_not_a_crash(self, monkeypatch):
        import espn_api
        StubbedApp(monkeypatch)

        def boom(*a, **k):
            raise ValueError("bad")

        monkeypatch.setattr(espn_api, "get_team_info", boom)
        played = event()
        played["date"] = datetime.now(timezone.utc).isoformat()
        report = v.Report()
        v.check_team_hub(FakeHttp(default=(200, {})), report, league("NBA"), played, True)
        assert FAIL_IN(report, "App: team info")


class TestTeamRecordAgreesWithStandings:
    LYNX = {"team_id": "8", "wins": 33, "losses": 11}

    def run(self, monkeypatch, key="WNBA", record="33-11", season=(2026, 3), standings=None):
        year, season_type = season
        import espn_api
        monkeypatch.setattr(espn_api, "core_season", lambda path: {"year": year, "type": {"type": season_type}})
        monkeypatch.setattr(espn_api, "get_standings", lambda league: [self.LYNX] if standings is None else standings)
        report = v.Report()
        v.check_team_record(report, league(key), "8", "Lynx", record)
        return report

    def test_the_regular_season_record_in_the_playoffs_passes(self, monkeypatch):
        assert statuses(self.run(monkeypatch), "App: team record") == [v.PASS]

    @pytest.mark.parametrize("record", ["0-2", "0-0"])
    def test_a_playoff_record_fails(self, monkeypatch, record):
        """The Lynx in the 2026 playoffs, and a team that missed them."""
        assert FAIL_IN(self.run(monkeypatch, record=record), "App: team record")

    def test_a_wrong_record_in_the_regular_season_fails(self, monkeypatch):
        assert FAIL_IN(self.run(monkeypatch, record="0-2", season=(2026, 2)), "App: team record")

    def test_a_game_one_feed_has_first_is_not_a_break(self, monkeypatch):
        assert statuses(self.run(monkeypatch, record="34-11", season=(2026, 2)), "App: team record") == [v.PASS]
        assert statuses(self.run(monkeypatch, record="34-12", season=(2026, 2)), "App: team record") == [v.PASS]

    def test_an_nhl_record_with_overtime_losses(self, monkeypatch):
        report = self.run(monkeypatch, "NHL", "33-11-4", season=(2027, 2))
        assert statuses(report, "App: team record") == [v.PASS]

    @pytest.mark.parametrize("season_type", [1, 4], ids=["preseason", "off_season"])
    def test_no_false_alarm_between_seasons(self, monkeypatch, season_type):
        """Team Info has the last season, and Standings can be on the new one at 0-0."""
        standings = [{"team_id": "8", "wins": 0, "losses": 0}]
        report = self.run(monkeypatch, season=(2026, season_type), standings=standings)
        assert statuses(report, "App: team record") == [v.PASS]

    def test_no_false_alarm_as_a_regular_season_begins(self, monkeypatch):
        """ESPN's type turns over before the first game, and standings can be last season's."""
        import espn_api
        began = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        monkeypatch.setattr(espn_api, "core_season", lambda path: {"year": 2027, "type": {"type": 2, "startDate": began}})
        monkeypatch.setattr(espn_api, "get_standings", lambda league: [{"team_id": "8", "wins": 40, "losses": 42}])
        report = v.Report()
        v.check_team_record(report, league("NBA"), "8", "Lynx", "0-0")
        assert statuses(report, "App: team record") == [v.PASS]

    def test_no_false_alarm_in_a_college_postseason(self, monkeypatch):
        """College standings count the postseason: Michigan 37-3, and 31-3 on its team page."""
        standings = [{"team_id": "8", "wins": 37, "losses": 3}]
        report = self.run(monkeypatch, "NCAAM", "31-3", season=(2026, 3), standings=standings)
        assert statuses(report, "App: team record") == [v.PASS]

    def test_college_in_its_regular_season_is_checked(self, monkeypatch):
        assert FAIL_IN(self.run(monkeypatch, "NCAAM", "0-2", season=(2027, 2)), "App: team record")

    def test_soccer_has_nothing_to_agree_with(self, monkeypatch):
        import espn_api

        def not_asked(*a):
            raise AssertionError("soccer asked for standings")

        monkeypatch.setattr(espn_api, "core_season", not_asked)
        report = v.Report()
        v.check_team_record(report, league("EPL"), "359", "Arsenal", "8-0-1")
        assert statuses(report, "App: team record") == [v.PASS]

    def test_a_team_not_in_the_standings(self, monkeypatch):
        """A college team's opponent can be outside the coverage setting's conferences."""
        report = self.run(monkeypatch, "NCAAF", "9-1", season=(2026, 2), standings=[])
        assert statuses(report, "App: team record") == [v.PASS]

    def test_not_knowing_the_season_only_warns(self, monkeypatch):
        import espn_api
        from exceptions import ApiError

        def fails(path):
            raise ApiError("no answer")

        monkeypatch.setattr(espn_api, "core_season", fails)
        report = v.Report()
        v.check_team_record(report, league("WNBA"), "8", "Lynx", "33-11")
        assert statuses(report, "App: team record") == [v.WARN]

    def test_the_team_hub_check_asks(self, monkeypatch):
        """Through check_team_hub, on a record that's wrong."""
        app = StubbedApp(monkeypatch)
        app.set("get_team_info", {"name": "T0", "record_overall": "0-2"})
        app.set("core_season", {"year": 2026, "type": {"type": 3}})
        played = event()
        played["date"] = datetime.now(timezone.utc).isoformat()
        team_id = str(played["competitions"][0]["competitors"][0]["team"]["id"])
        app.set("get_standings", [{"team_id": team_id, "wins": 33, "losses": 11}])
        report = v.Report()
        v.check_team_hub(FakeHttp(default=(200, {})), report, league("WNBA"), played, True)
        assert FAIL_IN(report, "App: team record")


class TestAppGame:
    def stub_details(self, monkeypatch, names=("A", "B")):
        import espn_api
        monkeypatch.setattr(espn_api, "get_game_details", lambda *a, **k: {})
        monkeypatch.setattr(espn_api, "extract_meaningful_game_info",
                            lambda *a, **k: {"teams": [{"name": n} for n in names]})

    def summary(self):
        plays = load("plays_NBA_*.json")
        return {"boxscore": box("NBA"), "plays": plays.get("plays", plays) if isinstance(plays, dict) else plays}

    def test_real_game(self, monkeypatch):
        self.stub_details(monkeypatch)
        report = v.Report()
        v.check_app_game(report, league("NBA"), event(), self.summary())
        assert not report.failed
        assert statuses(report, "App: play audio") == [v.PASS]

    def test_no_located_plays(self, monkeypatch):
        self.stub_details(monkeypatch)
        summary = self.summary()
        for play in summary["plays"]:
            play.pop("coordinate", None)
        report = v.Report()
        v.check_app_game(report, league("NBA"), event(), summary)
        assert FAIL_IN(report, "App: play audio")

    def test_a_dropped_player(self, monkeypatch):
        self.stub_details(monkeypatch)
        monkeypatch.setitem(sys.modules, "box_score", type(sys)("box_score"))
        sys.modules["box_score"].build_box_tables = lambda b: [v_table()]
        report = v.Report()
        v.check_app_game(report, league("NBA"), event(), self.summary())
        assert FAIL_IN(report, "App: box score")

    def test_an_unknown_team(self, monkeypatch):
        self.stub_details(monkeypatch, ("A", "Unknown"))
        report = v.Report()
        v.check_app_game(report, league("NBA"), event(), self.summary())
        assert FAIL_IN(report, "App: game details")


def v_table():
    class Table:
        title, headers, rows = "A", ["Name"], [["Nobody"]]
    return Table


class TestStandingsAgainstTheApp:
    def entries(self):
        return v.standings_entries(load("standings_NFL.json"))

    def rows(self):
        rows = []
        for entry in self.entries():
            total = next(s for s in entry["stats"] if s.get("type") == "total")
            wins, losses = v.parse_record(total["summary"])
            rows.append({"team_name": entry["team"]["displayName"], "wins": wins, "losses": losses})
        return rows

    def test_matching(self):
        assert v.standings_row_problems(self.entries(), self.rows()) == ([], [])

    def test_a_missing_team(self):
        missing, _ = v.standings_row_problems(self.entries(), self.rows()[1:])
        assert len(missing) == 1

    def test_right_wins_wrong_losses(self):
        rows = self.rows()
        rows[0]["losses"] += 1
        _, wrong = v.standings_row_problems(self.entries(), rows)
        assert len(wrong) == 1

    @pytest.mark.parametrize("text,expected", [
        ("7-1", (7, 1)), ("10-4-1", (10, 4)), ("", None), (None, None), ("7", None), ("a-b", None)])
    def test_parse_record(self, text, expected):
        assert v.parse_record(text) == expected

    def test_an_unreadable_record_is_a_problem(self):
        data = copy.deepcopy(load("standings_NFL.json"))
        next(s for s in v.standings_entries(data)[0]["stats"] if s.get("type") == "total")["summary"] = "n/a"
        data_stats = v.standings_entries(data)[0]["stats"]
        next(s for s in data_stats if s.get("type") == "total").pop("displayValue", None)
        assert any("can't read" in p for p in v.standings_problems(data, league("NFL")))


class TestRankings:
    def poll(self, **team):
        return [{"name": "AP", "ranks": [{"current": 1, "team": team}]}]

    def test_a_good_rank(self):
        assert v.rankings_problems(self.poll(location="Duke", abbreviation="DUKE")) == []

    def test_no_polls(self):
        assert v.rankings_problems([])

    def test_a_team_with_no_name(self):
        assert v.rankings_problems(self.poll(abbreviation="DUKE"))

    def test_a_team_with_no_abbreviation(self):
        assert v.rankings_problems(self.poll(location="Duke"))

    def test_no_position(self):
        assert v.rankings_problems([{"name": "AP", "ranks": [{"team": {"location": "Duke", "abbreviation": "D"}}]}])


class TestFootballCalendar:
    WEEKS = [{"week": 1, "season_type": 1, "label": "Hall of Fame"}]

    def stub(self, monkeypatch, answer):
        from services import football_calendar
        monkeypatch.setattr(football_calendar, "_fetch_calendar", lambda *a, **k: answer)

    def test_no_calendar_fails(self, monkeypatch):
        self.stub(monkeypatch, (None, []))
        report = v.Report()
        v.check_football_calendar(FakeHttp(), report)
        assert statuses(report, "App: football calendar") == [v.FAIL, v.FAIL]

    def test_a_refused_week_query_fails(self, monkeypatch):
        self.stub(monkeypatch, (2026, self.WEEKS))
        report = v.Report()
        v.check_football_calendar(FakeHttp([("week=1", (400, {}))], default=(200, {"items": [1], "count": 1})), report)
        assert statuses(report, "Week query") == [v.FAIL, v.FAIL]

    def test_the_core_season_is_espn_s_rather_than_this_year(self, monkeypatch):
        """On New Year's Day this year's season isn't published. ESPN's own season number is."""
        self.stub(monkeypatch, (2026, self.WEEKS))
        http = FakeHttp([("/seasons/2026/types/2/weeks", (200, {"count": 18, "items": [1]})),
                         ("week=1", (200, {"events": []}))])
        report = v.Report()
        v.check_football_calendar(http, report)
        assert statuses(report, "Core API: weeks (iPhone)") == [v.PASS, v.PASS]
        assert not report.failed

    def test_college_football_weeks_are_asked_for_on_their_own_path(self, monkeypatch):
        self.stub(monkeypatch, (2026, self.WEEKS))
        http = FakeHttp([("leagues/college-football/seasons/2026/types/2/weeks", (404, None)),
                         ("/weeks", (200, {"count": 18, "items": [1]})), ("week=1", (200, {"events": []}))])
        report = v.Report()
        v.check_football_calendar(http, report)
        assert statuses(report, "Core API: weeks (iPhone)") == [v.PASS, v.FAIL]
        assert any("college-football/scoreboard?groups=90&limit=400&dates=2026&week=1" in u for u in http.urls)

    def test_core_weeks_gone_fails(self, monkeypatch):
        self.stub(monkeypatch, (2026, self.WEEKS))
        http = FakeHttp([("/weeks", (200, {"count": 0, "items": []})), ("week=1", (200, {"events": []}))])
        report = v.Report()
        v.check_football_calendar(http, report)
        assert statuses(report, "Core API: weeks (iPhone)") == [v.FAIL, v.FAIL]


class TestTransactions:
    def test_none_right_now(self):
        report = v.Report()
        v.check_transactions(FakeHttp(default=(200, {"count": 0})), report, league("NHL"))
        assert statuses(report, "Transactions") == [v.WARN]

    def test_the_key_going_away_with_data(self):
        report = v.Report()
        v.check_transactions(FakeHttp(default=(200, {"count": 5})), report, league("NHL"))
        assert statuses(report, "Transactions") == [v.FAIL]

    def test_nfl_date_range_refused(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_transactions", lambda *a, **k: ([{"description": "x"}], False))
        http = FakeHttp([("dates=", (400, {})), ("transactions", (200, {"transactions": [{}]}))])
        report = v.Report()
        v.check_transactions(http, report, league("NFL"))
        assert statuses(report, "Transactions by date (iPhone)") == [v.FAIL]

    def test_app_reads_nothing_though_espn_has_data(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_transactions", lambda *a, **k: ([], False))
        report = v.Report()
        v.check_transactions(FakeHttp(default=(200, {"transactions": [{}]})), report, league("NHL"))
        assert statuses(report, "App: transactions") == [v.FAIL]


class TestLeadersPayload:
    @pytest.mark.parametrize("key", ["NFL", "NBA", "NHL", "NCAAM", "MLB"])
    def test_real_payloads_pass(self, key):
        assert v.leaders_problems(load(f"leaders_v3_{key}.json")) == []

    @pytest.mark.parametrize("data,expected", [
        (None, "no answer"),
        ({"leaders": {"categories": []}}, "categories is empty"),
    ])
    def test_nothing_to_read(self, data, expected):
        assert expected in v.leaders_problems(data)[0]

    @pytest.mark.parametrize("damage,expected", [
        (lambda d: d["requestedSeason"]["type"].pop("type"), "no season type"),
        (lambda d: d["leaders"]["categories"][0].pop("displayName"), "no name or displayName"),
        (lambda d: d["leaders"]["categories"][0]["leaders"][0].pop("athlete"), "no name inside"),
        (lambda d: d["leaders"]["categories"][0]["leaders"][0].pop("team"), "no team inside"),
        (lambda d: d["leaders"]["categories"][0]["leaders"][0].pop("value"), "no value"),
        (lambda d: d["leaders"]["categories"][0]["leaders"][0].pop("displayValue"), "no value"),
    ], ids=["season_type", "display_name", "athlete", "team", "value", "display_value"])
    def test_each_field_the_parser_reads_is_checked(self, damage, expected):
        data = load("leaders_v3_NBA.json")
        damage(data)
        assert any(expected in p for p in v.leaders_problems(data))


class TestPreseasonLeaders:
    REGULAR = "leaders_core_NFL_regular.json"
    PRESEASON = "leaders_core_NFL_preseason.json"

    def as_leaders(self, core):
        return {"leaders": {"categories": load(core)["categories"]}}

    def test_real_regular_season_leaders_pass(self):
        """2246 against the preseason's 509, the case that started this."""
        given_away, can_tell = v.preseason_leaders(load("leaders_v3_NFL.json"), load(self.REGULAR), load(self.PRESEASON))
        assert given_away == []
        assert "passingYards" in can_tell

    def test_real_preseason_numbers_are_caught(self):
        given_away, can_tell = v.preseason_leaders(self.as_leaders(self.PRESEASON), load(self.REGULAR), load(self.PRESEASON))
        assert given_away == can_tell != []

    def test_no_preseason_on_file_can_say_nothing(self):
        assert v.preseason_leaders(load("leaders_v3_NBA.json"), load("leaders_core_NBA.json"), None) == ([], [])

    def test_a_category_alike_in_both_can_say_nothing(self):
        same = {"categories": [{"name": "goals", "leaders": [{"value": 4}]}]}
        assert v.preseason_leaders({"leaders": same}, same, same) == ([], [])

    def test_a_category_without_leaders_is_skipped(self):
        data = {"categories": [{"name": "goals", "leaders": []}]}
        assert v.preseason_leaders({"leaders": data}, data, data) == ([], [])


class TestLeadersDirection:
    @pytest.mark.parametrize("key", ["NFL", "NBA", "NHL", "NCAAM", "MLB"])
    def test_real_payloads_go_the_way_the_app_expects(self, key):
        import espn_api
        assert v.leaders_direction_problems(load(f"leaders_v3_{key}.json"), espn_api.LOW_IS_GOOD_LEADERS) == []

    def test_espns_second_run_of_players_does_not_count(self):
        import espn_api
        assert v.leaders_direction_problems(load("leaders_v3_NCAAM_full.json"), espn_api.LOW_IS_GOOD_LEADERS) == []

    def test_a_low_is_good_list_running_high_to_low(self):
        data = {"leaders": {"categories": [{"name": "ERA", "leaders": [{"value": 3}, {"value": 2}]}]}}
        assert v.leaders_direction_problems(data, {"ERA"}) == ["ERA"]

    def test_all_tied_says_nothing(self):
        data = {"leaders": {"categories": [{"name": "x", "leaders": [{"value": 3}, {"value": 3}]}]}}
        assert v.leaders_direction_problems(data, set()) == []


class TestUnreadableLeaderValues:
    def test_numbers_read(self):
        rows = [{"category": "x", "stats": [{"value": v_} for v_ in ("38.3", ".316", "-3", "2,246", "45")]}]
        assert v.unreadable_leader_values(rows) == []

    @pytest.mark.parametrize("value", ["179-567, 42 HR", "", "None"])
    def test_anything_else_does_not(self, value):
        assert v.unreadable_leader_values([{"category": "x", "stats": [{"value": value}]}]) == [f"x: {value!r}"]

    def test_mlb_rows_have_no_stats_list(self):
        assert v.unreadable_leader_values([{"name": "Home Runs", "leaders": [{"value": "45"}]}]) == []


class TestLeadersFeed:
    """check_leaders: ESPN's /leaders as the app asks for it."""

    @pytest.fixture(autouse=True)
    def season(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "_leaders_season", lambda path: 2026)

    def http(self, *routes):
        core_regular = (200, load("leaders_core_NFL_regular.json"))
        core_preseason = (200, load("leaders_core_NFL_preseason.json"))
        return FakeHttp(list(routes) + [("/types/2/leaders", core_regular), ("/types/1/leaders", core_preseason),
                                        ("/leaders", (200, load("leaders_v3_NFL.json")))])

    def test_real_answers_pass(self):
        report = v.Report()
        http = self.http()
        v.check_leaders(http, report, league("NFL"))
        assert statuses(report, "Leaders") == [v.PASS]
        assert statuses(report, "Leaders aren't the preseason") == [v.PASS]
        assert "2026 Regular Season: 3 categories" in detail(report, "Leaders")
        asked = next(u for u in http.urls if "/site/v3/" in u)
        assert asked.endswith("/football/nfl/leaders?region=us&lang=en&season=2026&seasontype=2&limit=20")
        assert any("/seasons/2026/types/1/leaders" in u for u in http.urls)

    def test_preseason_numbers_fail(self):
        fake = {"requestedSeason": {"displayName": "2026", "year": 2026, "type": {"type": 2, "name": "Regular Season"}},
                "leaders": {"categories": copy.deepcopy(load("leaders_core_NFL_preseason.json")["categories"])}}
        for category in fake["leaders"]["categories"]:
            category["displayName"] = category["name"]
            for leader in category["leaders"]:
                leader.update(athlete={"displayName": "A"}, team={"abbreviation": "B"}, displayValue="1")
        report = v.Report()
        v.check_leaders(self.http(("/site/v3/", (200, fake))), report, league("NFL"))
        assert FAIL_IN(report, "Leaders aren't the preseason")
        assert "passingYards" in detail(report, "Leaders aren't the preseason")

    def test_a_preseason_that_is_a_404_is_fine(self):
        report = v.Report()
        v.check_leaders(self.http(("/types/1/leaders", (404, None))), report, league("NFL"))
        assert statuses(report, "Leaders aren't the preseason") == [v.PASS]
        assert "no preseason leaders" in detail(report, "Leaders aren't the preseason")

    def test_the_core_api_failing_is_only_worth_a_look_here(self):
        report = v.Report()
        v.check_leaders(self.http(("/types/2/leaders", (503, None))), report, league("NFL"))
        assert statuses(report, "Leaders aren't the preseason") == [v.WARN]

    def test_stepping_down_is_worth_a_look_and_says_how_far(self):
        report = v.Report()
        v.check_leaders(self.http(("limit=20", (500, None)), ("limit=10", (500, None))), report, league("NFL"))
        assert statuses(report, "Leaders")[0] == v.WARN
        assert "shows 5 a category" in detail(report, "Leaders")

    def test_a_season_not_yet_on_file_falls_back_as_the_app_does(self):
        """The first week of the NHL or NFL season shouldn't fail the nightly run."""
        report = v.Report()
        http = self.http(("season=2026", (404, None)))
        v.check_leaders(http, report, league("NFL"))
        assert statuses(report, "Leaders") == [v.PASS]
        assert any("season=2025" in u for u in http.urls)

    def test_a_season_with_nobody_on_the_list_falls_back_too(self):
        report = v.Report()
        v.check_leaders(self.http(("season=2026", (200, {"leaders": {"categories": []}}))), report, league("NFL"))
        assert statuses(report, "Leaders") == [v.PASS]

    def test_a_404_does_not_step_down(self):
        http = self.http(("/site/v3/", (404, None)))
        v.check_leaders(http, v.Report(), league("NFL"))
        assert not any("limit=10" in u for u in http.urls)

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    @pytest.mark.parametrize("answer", [(404, None), (200, {"leaders": {"categories": []}})], ids=["404", "empty"])
    def test_nothing_in_either_season_is_seasonal(self, answer, in_season, expected):
        report = v.Report()
        v.check_leaders(self.http(("/site/v3/", answer)), report, league("NFL"), in_season)
        assert statuses(report, "Leaders") == [expected]

    def test_a_list_running_the_wrong_way_is_worth_a_look(self):
        report = v.Report()
        data = load("leaders_v3_NFL.json")
        data["leaders"]["categories"][0]["leaders"].reverse()
        v.check_leaders(self.http(("/site/v3/", (200, data))), report, league("NFL"))
        assert v.WARN in statuses(report, "Leaders")
        assert "passingYards" in detail(report, "Leaders")

    def test_failing_at_every_limit_fails(self):
        report = v.Report()
        v.check_leaders(self.http(("/site/v3/", (500, None))), report, league("NFL"))
        assert statuses(report, "Leaders") == [v.FAIL]

    def test_a_changed_shape_fails(self):
        report = v.Report()
        v.check_leaders(self.http(("/site/v3/", (200, {"leaders": {"categories": [{"name": "x"}]}}))), report, league("NFL"))
        assert statuses(report, "Leaders") == [v.FAIL]

    def test_not_knowing_the_season_fails(self, monkeypatch):
        import espn_api

        def fails(path):
            raise v.ApiError("no")

        monkeypatch.setattr(espn_api, "_leaders_season", fails)
        report = v.Report()
        v.check_leaders(FakeHttp(), report, league("NFL"))
        assert statuses(report, "Core API: season") == [v.FAIL]


class TestNoLeaders:
    def test_the_leagues_match_the_app(self):
        import espn_api
        known = {key for key in v.LEAGUE_KEYS if v.LEAGUE_KEYS[key].player_stats}
        assert known == espn_api.LEADER_LEAGUES

    def test_a_404_is_as_expected(self):
        report = v.Report()
        v.check_no_leaders(FakeHttp(default=(404, None)), report, league("NCAAH"))
        assert statuses(report, "Leaders") == [v.PASS]

    def test_espn_starting_to_have_them_is_news(self):
        report = v.Report()
        v.check_no_leaders(FakeHttp(default=(200, load("leaders_v3_NHL.json"))), report, league("EPL"))
        assert statuses(report, "Leaders") == [v.WARN]


class TestTeamStatistics:
    """Real byteam payloads, through FakeHttp. The season comes from the app, so it's stubbed."""

    @pytest.fixture(autouse=True)
    def a_season(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "core_season", lambda path: {"year": 2026, "type": {"type": 3}})

    def run(self, http, key="NBA", in_season=True):
        report = v.Report()
        v.check_team_statistics(http, report, league(key), in_season)
        return report

    def test_the_leagues_match_the_app(self):
        import espn_api
        assert {key for key in v.LEAGUE_KEYS if v.LEAGUE_KEYS[key].team_stats} == espn_api.TEAM_STAT_LEAGUES

    def test_asks_the_way_the_app_does(self):
        http = FakeHttp(default=(200, load("byteam_NBA.json")))
        report = self.run(http)
        assert statuses(report, "Team statistics") == [v.PASS]
        assert "2026-27 Regular Season: 30 teams" in detail(report, "Team statistics")
        assert http.urls == [f"{v.WEB}/basketball/nba/statistics/byteam?region=us&lang=en&limit=500&season=2026&seasontype=2"]

    def test_a_list_that_fits_has_nothing_to_say(self):
        report = self.run(FakeHttp(default=(200, load("byteam_NBA.json"))))
        assert statuses(report, "Team statistics: every team") == []
        assert statuses(report, "Team statistics: regular season") == []
        assert not report.failed

    def test_college_basketball_over_the_cap_is_expected_and_covered(self):
        """Every night from about December until the next season, 722 of them, 400 at a time."""
        data = load("byteam_NCAAM_2026.json")
        data["teams"] = data["teams"] * 100
        report = self.run(FakeHttp(default=(200, data)), key="NCAAM", in_season=False)
        assert statuses(report, "Team statistics: every team") == [v.PASS]
        assert "722" in detail(report, "Team statistics: every team")
        assert report.count(v.WARN) == 0

    def test_more_than_both_ways_can_reach_warns(self):
        data = load("byteam_NCAAM_2026.json")
        data["pagination"]["count"] = 2 * len(data["teams"]) + 1
        report = self.run(FakeHttp(default=(200, data)), key="NCAAM")
        assert statuses(report, "Team statistics: every team") == [v.WARN]
        assert not report.failed

    def test_a_league_that_starts_to_cut_its_list_short_warns(self):
        """Today only basketball has pagination at all, and football's limit is what it is."""
        data = load("byteam_NFL.json")
        data["pagination"] = {"count": 400}
        report = self.run(FakeHttp(default=(200, data)), key="NFL")
        assert statuses(report, "Team statistics: every team") == [v.WARN]
        assert "no way to ask" in detail(report, "Team statistics: every team")

    def test_no_pagination_at_all_is_normal(self):
        report = self.run(FakeHttp(default=(200, load("byteam_NFL.json"))), key="NFL")
        assert report.count(v.WARN) == 0 and not report.failed

    def test_the_off_season_default_of_playoff_teams_is_no_alarm(self):
        """FakeHttp would answer the bare URL with these. Only the app's own question is asked."""
        http = FakeHttp([("seasontype=2", (200, load("byteam_WNBA.json")))], default=(200, load("byteam_WNBA_default.json")))
        report = self.run(http, key="WNBA", in_season=False)
        assert "15 teams" in detail(report, "Team statistics")
        assert report.count(v.WARN) == 0 and not report.failed
        assert all("seasontype=2" in url for url in http.urls)

    def test_college_footballs_past_season_being_type_3_is_no_alarm(self):
        report = self.run(FakeHttp(default=(200, load("byteam_NCAAF_2025.json"))), key="NCAAF", in_season=False)
        assert statuses(report, "Team statistics") == [v.PASS]
        assert report.count(v.WARN) == 0 and not report.failed

    @pytest.mark.parametrize("key,fixture", [("WNBA", "byteam_WNBA_default.json"), ("MLB", "byteam_MLB_default.json")])
    def test_another_league_answering_playoffs_to_the_regular_season_warns(self, key, fixture):
        report = self.run(FakeHttp(default=(200, load(fixture))), key=key)
        assert statuses(report, "Team statistics: regular season") == [v.WARN]
        assert not report.failed

    def test_a_new_season_with_nothing_yet_is_last_seasons(self):
        http = FakeHttp([("season=2026", (200, {})), ("season=2025", (200, load("byteam_NBA.json")))])
        assert statuses(self.run(http), "Team statistics") == [v.PASS]
        assert len(http.urls) == 2

    def test_a_404_for_a_new_season_too(self):
        http = FakeHttp([("season=2025", (200, load("byteam_NBA.json")))], default=(404, None))
        assert statuses(self.run(http), "Team statistics") == [v.PASS]

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_nothing_for_either_year_depends_on_the_season(self, in_season, expected):
        report = self.run(FakeHttp(default=(200, {})), in_season=in_season)
        assert statuses(report, "Team statistics") == [expected]

    def test_an_error_fails_in_or_out_of_season(self):
        report = self.run(FakeHttp(default=(500, None)), in_season=False)
        assert statuses(report, "Team statistics") == [v.FAIL]

    def test_not_knowing_the_season_fails(self, monkeypatch):
        import espn_api

        def fails(path):
            raise v.ApiError("no")

        monkeypatch.setattr(espn_api, "core_season", fails)
        report = self.run(FakeHttp())
        assert statuses(report, "Core API: season") == [v.FAIL]
        assert statuses(report, "Team statistics") == []

    # A new season's first days, when the nightly run lands in the window every year

    def begun(self, monkeypatch, days_ago):
        import espn_api
        start = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%MZ")
        monkeypatch.setattr(espn_api, "core_season", lambda path: {"year": 2026, "type": {"type": 2, "startDate": start}})

    def test_a_500_as_a_regular_season_begins_is_no_failure(self, monkeypatch):
        self.begun(monkeypatch, days_ago=0.2)
        http = FakeHttp([("season=2026", (500, None)), ("season=2025", (200, load("byteam_NBA.json")))])
        report = self.run(http)
        assert not report.failed
        assert statuses(report, "Team statistics") == [v.WARN, v.PASS]
        assert "only just begun" in detail(report, "Team statistics")

    def test_a_500_a_week_in_fails(self, monkeypatch):
        self.begun(monkeypatch, days_ago=7)
        report = self.run(FakeHttp([("season=2026", (500, None)), ("season=2025", (200, load("byteam_NBA.json")))]))
        assert FAIL_IN(report, "Team statistics")

    def test_last_season_failing_too_fails(self, monkeypatch):
        self.begun(monkeypatch, days_ago=0.2)
        assert FAIL_IN(self.run(FakeHttp(default=(500, None))), "Team statistics")

    # A column nobody has decided about

    def test_every_real_column_passes_without_a_warning(self):
        for key, fixture in (("NFL", "byteam_NFL.json"), ("NBA", "byteam_NBA.json"), ("NHL", "byteam_NHL.json"),
                             ("MLB", "byteam_MLB.json"), ("NCAAF", "byteam_NCAAF.json"), ("NCAAM", "byteam_NCAAM.json")):
            assert statuses(self.run(FakeHttp(default=(200, load(fixture))), key=key), "Team statistics: new columns") == []

    def test_a_new_column_warns_and_names_it(self):
        data = load("byteam_NHL.json")
        next(m for m in data["categories"] if m["name"] == "defensive")["names"].append("giveaways")
        report = self.run(FakeHttp(default=(200, data)), key="NHL")
        assert statuses(report, "Team statistics: new columns") == [v.WARN]
        assert "defensive.giveaways" in detail(report, "Team statistics: new columns")
        assert not report.failed

    def test_a_new_section_warns(self):
        data = load("byteam_NHL.json")
        data["categories"].append({"name": "faceoffs", "names": ["faceoffsWon"], "displayNames": ["Faceoffs Won"]})
        assert v.unknown_team_stats(data, "hockey") == ["faceoffs.faceoffsWon"]

    def test_a_sport_it_knows_nothing_of_has_nothing_to_say(self):
        assert v.unknown_team_stats(load("byteam_NHL.json"), "cricket") == []

    def test_a_copy_of_the_script_with_no_directions_file_has_nothing_to_say(self, monkeypatch):
        monkeypatch.setattr(v, "known_team_stats", lambda: None)
        data = load("byteam_NHL.json")
        data["categories"][0]["names"].append("new")
        assert v.unknown_team_stats(data, "hockey") == []

    def test_the_directions_file_is_found_and_can_go_missing(self, monkeypatch):
        assert "football" in v.known_team_stats()

        def fails(*a, **k):
            raise OSError("no")

        monkeypatch.setattr(v, "open", fails, raising=False)
        assert v.known_team_stats() is None

    def test_a_league_without_them_being_empty_is_expected(self):
        report = v.Report()
        v.check_no_team_statistics(FakeHttp(default=(200, {})), report, league("NCAAH"))
        assert statuses(report, "Team statistics") == [v.PASS]

    def test_soccers_500_is_expected(self):
        report = v.Report()
        v.check_no_team_statistics(FakeHttp(default=(500, None)), report, league("EPL"))
        assert statuses(report, "Team statistics") == [v.PASS]

    def test_espn_starting_to_have_them_is_news(self):
        report = v.Report()
        v.check_no_team_statistics(FakeHttp(default=(200, load("byteam_NHL.json"))), report, league("NCAAH"))
        assert statuses(report, "Team statistics") == [v.WARN]


class TestAppTeamStatistics:
    def app_says(self, monkeypatch, answer):
        import espn_api

        def fake(*a, **k):
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(espn_api, "get_team_statistics", fake)

    def rows(self, teams):
        return {"team_stats": [{"category": "General", "low_is_good": [], "stats": [
            {"team_name": f"T{i}", "stats": {"Wins": "1"}, "values": {"Wins": 1}} for i in range(teams)]}],
            "season": "2026 Regular Season"}

    def run(self, key="NBA", in_season=True):
        report = v.Report()
        v.check_app_team_statistics(report, league(key), in_season)
        return report

    def test_good_rows_pass_and_say_the_season(self, monkeypatch):
        self.app_says(monkeypatch, self.rows(30))
        report = self.run()
        assert statuses(report, "App: team statistics") == [v.PASS]
        assert "30 teams, 1 stats, 2026 Regular Season" in detail(report, "App: team statistics")

    def test_a_short_pro_league_warns(self, monkeypatch):
        self.app_says(monkeypatch, self.rows(2))
        report = self.run(key="NFL")
        assert statuses(report, "App: team statistics") == [v.PASS, v.WARN]
        assert not report.failed

    def test_a_college_league_has_no_floor(self, monkeypatch):
        self.app_says(monkeypatch, self.rows(2))
        assert statuses(self.run(key="NCAAM"), "App: team statistics") == [v.PASS]

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_empty(self, monkeypatch, in_season, expected):
        self.app_says(monkeypatch, {"team_stats": []})
        assert statuses(self.run(in_season=in_season), "App: team statistics") == [expected]

    def test_the_app_giving_up_fails_and_says_what_a_user_was_told(self, monkeypatch):
        import espn_api
        self.app_says(monkeypatch, v.ApiError(espn_api.STATISTICS_UNAVAILABLE))
        report = self.run()
        assert FAIL_IN(report, "App: team statistics")
        assert "Try again" in detail(report, "App: team statistics")

    def test_any_other_error_fails(self, monkeypatch):
        self.app_says(monkeypatch, ValueError("bad"))
        assert "ValueError" in detail(self.run(), "App: team statistics")


class TestStatistics:
    @pytest.fixture(autouse=True)
    def no_team_statistics(self, monkeypatch):
        """TestTeamStatistics has these. They ask the app, which would reach ESPN."""
        monkeypatch.setattr(v, "check_team_statistics", lambda *a: None)
        monkeypatch.setattr(v, "check_app_team_statistics", lambda *a: None)

    def test_a_league_with_them_gets_the_feed_and_app_checks(self, monkeypatch):
        seen = []
        monkeypatch.setattr(v, "check_leaders", lambda *a: None)
        monkeypatch.setattr(v, "check_app_leaders", lambda *a: None)
        monkeypatch.setattr(v, "check_core_statistics", lambda *a: None)
        monkeypatch.setattr(v, "check_team_statistics", lambda http, report, l, s: seen.append(("feed", l.key)))
        monkeypatch.setattr(v, "check_app_team_statistics", lambda report, l, s: seen.append(("app", l.key)))
        v.check_statistics(FakeHttp(), v.Report(), league("NBA"), event(), True)
        assert seen == [("feed", "NBA"), ("app", "NBA")]

    def test_a_league_without_them_is_only_checked_to_still_have_none(self, monkeypatch):
        def never(*a):
            raise AssertionError("no team statistics here")

        monkeypatch.setattr(v, "check_team_statistics", never)
        monkeypatch.setattr(v, "check_app_team_statistics", never)
        report = v.Report()
        v.check_statistics(FakeHttp(default=(500, None)), report, league("EPL"), event(), True)
        assert statuses(report, "Team statistics") == [v.PASS]

    def app_says(self, monkeypatch, answer):
        import espn_api

        def fake(*a, **k):
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(espn_api, "get_player_statistics", fake)
        monkeypatch.setattr(v, "check_leaders", lambda *a: None)

    def rows(self, *values):
        return {"player_stats": [{"category": "x", "stats": [{"player_name": "A", "value": value} for value in values]}],
                "season": "2026 Regular Season"}

    def run(self, in_season=True, key="NHL"):
        report = v.Report()
        v.check_statistics(FakeHttp(default=(200, {})), report, league(key), event(), in_season)
        return report

    def test_the_nba_has_leaders_now(self):
        assert league("NBA").player_stats

    def test_every_league_with_leaders_gets_the_feed_and_app_checks(self, monkeypatch):
        seen = []
        monkeypatch.setattr(v, "check_leaders", lambda http, report, l, s: seen.append(("feed", l.key)))
        monkeypatch.setattr(v, "check_app_leaders", lambda report, l, s: seen.append(("app", l.key)))
        self.run(key="NBA")
        assert seen == [("feed", "NBA"), ("app", "NBA")]

    def test_a_league_without_them_is_not_asked_of_the_app(self, monkeypatch):
        import espn_api

        def never(*a, **k):
            raise AssertionError("no leaders here")

        monkeypatch.setattr(espn_api, "get_player_statistics", never)
        report = self.run(key="NCAAH")
        assert statuses(report, "Leaders") == [v.PASS]

    def test_good_rows_pass_and_say_the_season(self, monkeypatch):
        self.app_says(monkeypatch, self.rows("38.3"))
        report = self.run()
        assert statuses(report, "App: player statistics") == [v.PASS]
        assert "2026 Regular Season" in detail(report, "App: player statistics")

    def team_filter(self, teams_in_answer):
        data = {"leaders": {"categories": [{"leaders": [{"team": {"id": "13"}}]}]}}
        answer = {"leaders": {"categories": [{"leaders": [{"team": {"id": t}} for t in teams_in_answer]}]}}
        http = FakeHttp([("team=13", (200, answer))])
        report = v.Report()
        v.check_leaders_for_a_team(http, report, league("NBA"), data, 2027)
        assert any("season=2027" in u and "team=13" in u for u in http.urls)
        return report

    def test_one_teams_leaders_are_only_that_team(self):
        assert statuses(self.team_filter(["13", "13"]), "Leaders for one team (iPhone)") == [v.PASS]

    def test_espn_ignoring_the_team_fails(self):
        report = self.team_filter(["13", "14"])
        assert FAIL_IN(report, "Leaders for one team (iPhone)")
        assert "14" in detail(report, "Leaders for one team (iPhone)")

    def test_one_teams_leaders_not_answering_only_warns(self):
        http = FakeHttp([("team=13", (500, None))])
        report = v.Report()
        data = {"leaders": {"categories": [{"leaders": [{"team": {"id": "13"}}]}]}}
        v.check_leaders_for_a_team(http, report, league("NBA"), data, 2027)
        assert statuses(report, "Leaders for one team (iPhone)") == [v.WARN]

    def test_invented_players_fail(self, monkeypatch):
        self.app_says(monkeypatch, {"player_stats": [{"player_name": "Sample Player 1"}]})
        assert FAIL_IN(self.run(), "App: player statistics")

    def test_a_stat_line_for_a_value_fails(self, monkeypatch):
        self.app_says(monkeypatch, self.rows("179-567, 42 HR"))
        report = self.run()
        assert FAIL_IN(report, "App: player statistics")
        assert "179-567" in detail(report, "App: player statistics")

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_empty_player_statistics(self, monkeypatch, in_season, expected):
        self.app_says(monkeypatch, {"player_stats": []})
        assert statuses(self.run(in_season), "App: player statistics") == [expected]

    def test_the_app_giving_up_on_espn_fails_and_says_what_a_user_was_told(self, monkeypatch):
        import espn_api
        self.app_says(monkeypatch, v.ApiError(espn_api.STATISTICS_UNAVAILABLE))
        report = self.run()
        assert FAIL_IN(report, "App: player statistics")
        assert "Try again" in detail(report, "App: player statistics")

    def test_any_other_app_error_on_statistics_fails(self, monkeypatch):
        self.app_says(monkeypatch, ValueError("bad"))
        report = self.run()
        assert FAIL_IN(report, "App: player statistics")
        assert "ValueError" in detail(report, "App: player statistics")

    def test_a_team_yet_to_play_falls_back_to_last_season_as_the_iphone_does(self):
        played = event()
        played["season"] = {"year": 2027, "type": 2}
        http = FakeHttp([("/seasons/2026/", (200, {"categories": [1], "splits": {"categories": [1]}}))])
        report = v.Report()
        v.check_core_statistics(http, report, league("NCAAM"), played, True)
        assert statuses(report, "Core API: team statistics (iPhone)") == [v.PASS]

    def test_core_requests_use_the_season_of_the_final(self, monkeypatch):
        self.app_says(monkeypatch, self.rows("38.3"))
        played = event()
        played["season"] = {"year": 2027, "type": 1}
        http = FakeHttp(default=(200, {"categories": [1], "splits": {"categories": [1]}, "teams": [1]}))
        report = v.Report()
        v.check_statistics(http, report, league("NHL"), played, True)
        assert any("/seasons/2027/types/2/teams/T0/statistics" in u for u in http.urls)
        assert not any("/seasons/2027/types/2/leaders" in u for u in http.urls), "NHL has /leaders"
        assert not report.failed

    def test_preseason_having_no_core_statistics_is_not_a_break(self):
        """ESPN answers 404 for the NBA's preseason and play-in. The iPhone asks for the
        regular season first, and so does this."""
        played = event()
        played["season"] = {"year": 2027, "type": 1}
        http = FakeHttp([("/types/1/", (404, None)), ("/types/5/", (404, None)),
                         ("/leaders", (200, {"categories": [1]})),
                         ("/statistics", (200, {"splits": {"categories": [1]}}))])
        report = v.Report()
        v.check_core_statistics(http, report, league("NBA"), played, True)
        assert not report.failed

    def test_core_gone_for_every_season_type_fails_in_season(self):
        report = v.Report()
        v.check_core_statistics(FakeHttp(default=(404, None)), report, league("EPL"), event(), True)
        assert FAIL_IN(report, "Core API: leaders (iPhone)")
        assert FAIL_IN(report, "Core API: team statistics (iPhone)")
        assert "404" in detail(report, "Core API: leaders (iPhone)")

    def test_a_league_with_leaders_isnt_checked_on_the_core_api_for_them(self):
        http = FakeHttp(default=(200, {"splits": {"categories": [1]}}))
        report = v.Report()
        v.check_core_statistics(http, report, league("NBA"), event(), True)
        assert not any(u.endswith("/leaders") for u in http.urls)
        assert statuses(report, "Core API: leaders (iPhone)") == []

    def test_core_team_statistics_gone(self):
        http = FakeHttp([("/leaders", (200, {"categories": [1]}))], default=(200, {"splits": {}}))
        report = v.Report()
        v.check_core_statistics(http, report, league("NHL"), event(), True)
        assert statuses(report, "Core API: team statistics (iPhone)") == [v.FAIL]


class TestOtherSources:
    def test_every_league_either_app_names_is_included(self):
        import espn_api
        paths = v.apps_league_paths()
        assert set(espn_api.LEAGUES.values()) <= paths
        assert {"racing/f1", "racing/irl", "soccer/fifa.wwc"} <= paths
        assert "football/cfl" not in paths

    def test_a_league_outside_the_deep_list_can_fail(self, monkeypatch):
        monkeypatch.setattr(v, "apps_league_paths", lambda: {"racing/f1", "basketball/nba"})
        report = v.Report()
        http = FakeHttp([("racing/f1", (400, {}))], default=(200, {"events": []}))
        v.check_every_league_path(http, report)
        assert [(c.source, c.status) for c in report.checks] == [("racing/f1", v.FAIL)]

    def test_cfl_empty_is_only_a_warning(self):
        report = v.Report()
        v.check_cfl(FakeHttp(default=(200, [])), report)
        assert statuses(report, "Rounds") == [v.WARN]

    def test_cfl_error_fails(self):
        report = v.Report()
        v.check_cfl(FakeHttp(default=(500, None)), report)
        assert statuses(report, "Rounds") == [v.FAIL]

    def test_the_draft_can_be_last_year_s(self, monkeypatch):
        import espn_api
        year = date.today().year
        monkeypatch.setattr(espn_api, "get_draft", lambda y: {"year": y})
        monkeypatch.setattr(espn_api, "get_draft_round", lambda y, r: [{"player_name": "A"}])
        asked = []
        monkeypatch.setattr(espn_api, "get_draft_round", lambda y, r: asked.append(y) or [{"player_name": "A"}])
        # The real shape of a draft yet to happen: its rounds and no picks.
        http = FakeHttp([(f"season={year - 1}", (200, {"picks": [1]})), ("draft", (200, {"picks": [], "rounds": [1]}))])
        report = v.Report()
        v.check_draft(http, report)
        assert not report.failed
        assert asked == [year - 1]

    def test_a_draft_with_no_picks_in_two_years_fails(self):
        report = v.Report()
        v.check_draft(FakeHttp(default=(200, {"picks": [], "rounds": [1]})), report)
        assert FAIL_IN(report, "Draft (iPhone)")

    def test_app_draft_empty_fails(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_draft", lambda y: {"x": 1})
        monkeypatch.setattr(espn_api, "get_draft_round", lambda y, r: [])
        report = v.Report()
        v.check_draft(FakeHttp(default=(200, {"picks": [1]})), report)
        assert FAIL_IN(report, "App: draft")

    def test_match_number_gone(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_world_cup_standings", lambda *a: [])
        report = v.Report()
        v.check_world_cup(FakeHttp(default=(200, {"competitions": [{}]})), report)
        assert FAIL_IN(report, "Core API: match number (iPhone)")

    @pytest.mark.parametrize("in_season,expected", [(True, v.FAIL), (False, v.WARN)])
    def test_wild_card_empty(self, monkeypatch, in_season, expected):
        import espn_api
        monkeypatch.setattr(espn_api, "get_mlb_wildcard_standings", lambda: {})
        report = v.Report()
        v.check_mlb_extras(FakeHttp(default=(200, {"leagueLeaders": []})), report, {"MLB": in_season})
        assert statuses(report, "App: wild card") == [expected]

    def venues_of(self, monkeypatch, venues, info=None, seasons=None):
        """check_venues with these venues for every league, and a team page with this venue."""
        import espn_api
        from services import venue_service

        def get_venues(self, key):
            if isinstance(venues, Exception):
                raise venues
            return venues

        def get_info(league, team):
            if isinstance(info, Exception):
                raise info
            return {"venue_name": "A Stadium"} if info is None else info

        monkeypatch.setattr(venue_service.VenueService, "get_venues_for_league", get_venues)
        monkeypatch.setattr(espn_api, "get_team_info", get_info)
        report = v.Report()
        v.check_venues(FakeHttp(), report, seasons or {})
        return report

    @staticmethod
    def venues(count):
        return {str(i): {"name": f"Venue {i}", "home_teams": [{"id": str(i)}]} for i in range(count)}

    def test_every_league_is_asked_for_by_the_key_the_service_knows(self, monkeypatch):
        """The service's keys are lower case. "NFL" gets nothing, whatever ESPN says."""
        import espn_api
        from services import venue_service
        asked = []

        def fake(self, key):
            asked.append(key)
            assert key in self.leagues
            return TestOtherSources.venues(400)

        monkeypatch.setattr(venue_service.VenueService, "get_venues_for_league", fake)
        monkeypatch.setattr(espn_api, "get_team_info", lambda league, team: {"venue_name": "A Stadium"})
        report = v.Report()
        v.check_venues(FakeHttp(), report, {})
        assert asked == ["mlb", "nfl", "nba", "nhl", "wnba", "ncaaf", "ncaam", "ncaawb", "ncaah", "ncaawh"]
        assert not report.failed
        assert statuses(report, "App: venues") == [v.PASS] * 10
        assert "400 venues, 400 home teams" in detail(report, "App: venues")

    def test_no_venues_fails_even_out_of_season(self, monkeypatch):
        """It reaches back to last season, so an off-season is no excuse."""
        report = self.venues_of(monkeypatch, {}, seasons={"NFL": False})
        assert statuses(report, "App: venues") == [v.FAIL] * 10

    def test_it_raising_is_a_failure(self, monkeypatch):
        report = self.venues_of(monkeypatch, RuntimeError("ESPN did not answer"))
        assert statuses(report, "App: venues") == [v.FAIL] * 10
        assert "ESPN did not answer" in detail(report, "App: venues")

    def test_a_venue_with_no_name_fails(self, monkeypatch):
        report = self.venues_of(monkeypatch, {"1": {"name": "", "home_teams": [{"id": "1"}]}})
        assert statuses(report, "App: venues") == [v.FAIL] * 10
        assert "no name" in detail(report, "App: venues")

    def test_a_venue_with_no_home_team_fails(self, monkeypatch):
        report = self.venues_of(monkeypatch, {"1": {"name": "A Stadium", "home_teams": []}})
        assert statuses(report, "App: venues") == [v.FAIL] * 10
        assert "no home team" in detail(report, "App: venues")

    def test_too_few_home_teams_warns(self, monkeypatch):
        report = self.venues_of(monkeypatch, self.venues(13))
        by_league = {c.source: c.status for c in report.checks if c.name == "App: venues"}
        assert by_league["WNBA"] == v.PASS
        assert by_league["NFL"] == v.WARN
        assert "only 13 home teams" in detail(report, "App: venues")

    def test_a_shared_venue_counts_each_team(self, monkeypatch):
        shared = {"1": {"name": "A", "home_teams": [{"id": str(i)} for i in range(400)]}}
        assert statuses(self.venues_of(monkeypatch, shared), "App: venues") == [v.PASS] * 10

    def test_team_info_venue(self, monkeypatch):
        report = self.venues_of(monkeypatch, {})
        assert statuses(report, "App: team info venue") == [v.PASS, v.PASS]

    def test_team_info_with_no_venue_only_breaks_in_season(self, monkeypatch):
        report = self.venues_of(monkeypatch, {}, info={"venue_name": ""}, seasons={"WNBA": False, "NCAAM": True})
        assert statuses(report, "App: team info venue") == [v.WARN, v.FAIL]

    def test_team_info_raising_is_a_failure(self, monkeypatch):
        report = self.venues_of(monkeypatch, {}, info=RuntimeError("boom"))
        assert statuses(report, "App: team info venue") == [v.FAIL, v.FAIL]


class TestRetries:
    def fake_get(self, monkeypatch, answers):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(v.requests, "get", get)
        monkeypatch.setattr(v.time, "sleep", lambda s: None)
        return calls

    class Answer:
        def __init__(self, status):
            self.status_code = status

    def test_the_app_s_requests_get_retried(self, monkeypatch):
        calls = self.fake_get(monkeypatch, [self.Answer(503), self.Answer(200)])
        v.install_retrying_get()
        assert v.requests.get("u").status_code == 200
        assert len(calls) == 2

    def test_it_gives_back_the_last_error(self, monkeypatch):
        self.fake_get(monkeypatch, [self.Answer(503)] * 3)
        v.install_retrying_get()
        assert v.requests.get("u").status_code == 503

    def test_a_timeout_is_retried_then_raised(self, monkeypatch):
        calls = self.fake_get(monkeypatch, [v.requests.Timeout()] * 3)
        v.install_retrying_get()
        with pytest.raises(v.requests.Timeout):
            v.requests.get("u")
        assert len(calls) == 3

    def test_a_404_is_an_answer(self, monkeypatch):
        calls = self.fake_get(monkeypatch, [self.Answer(404)])
        v.install_retrying_get()
        assert v.requests.get("u").status_code == 404
        assert len(calls) == 1

    def test_past_the_deadline_nothing_waits(self, monkeypatch):
        calls = self.fake_get(monkeypatch, [])
        v.install_retrying_get(deadline=0.0)
        with pytest.raises(v.requests.Timeout):
            v.requests.get("u")
        assert calls == []
        http = v.Http(deadline=0.0)
        assert http.get("u") == ("out of time", None)

    def test_a_league_that_fails_once_only_warns(self, monkeypatch):
        bad, good = v.Report(), v.Report()
        bad.fail("NBA", "News", "blip")
        good.ok("NBA", "News")
        answers = [(bad, True), (good, True)]
        monkeypatch.setattr(v, "check_league", lambda *a: answers.pop(0))
        report, in_season = v.check_league_twice(FakeHttp(), league("NBA"))
        assert not report.failed
        assert "failed once" in detail(report, "News")
        assert in_season

    def test_a_league_that_fails_twice_fails(self, monkeypatch):
        bad = v.Report()
        bad.fail("NBA", "News", "broken")
        monkeypatch.setattr(v, "check_league", lambda *a: (bad, True))
        report, _ = v.check_league_twice(FakeHttp(), league("NBA"))
        assert report.failed

    def test_the_other_sources_get_a_second_run_too(self, monkeypatch):
        bad, good = v.Report(), v.Report()
        bad.fail("World Cup", "Standings", "got 404")
        good.ok("World Cup", "Standings")
        answers = [bad, good]
        monkeypatch.setattr(v, "check_others", lambda *a: answers.pop(0))
        report = v.check_others_twice(FakeHttp(), {})
        assert not report.failed
        assert "failed once" in detail(report, "Standings")

    def test_the_other_sources_failing_twice_fails(self, monkeypatch):
        bad = v.Report()
        bad.fail("World Cup", "Standings", "got 404")
        monkeypatch.setattr(v, "check_others", lambda *a: bad)
        assert v.check_others_twice(FakeHttp(), {}).failed

    def test_a_league_that_passes_runs_once(self, monkeypatch):
        calls = []
        monkeypatch.setattr(v, "check_league", lambda *a: calls.append(1) or (v.Report(), True))
        v.check_league_twice(FakeHttp(), league("NBA"))
        assert len(calls) == 1


class TestMain:
    @pytest.fixture
    def quiet_run(self, monkeypatch):
        import settings
        monkeypatch.setattr(settings, "_cache", settings._cache)
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        original = v.requests.get
        yield monkeypatch
        assert v.requests.get is original, "main left requests.get patched"

    def test_clean_run_exits_zero_and_writes_reports(self, quiet_run, tmp_path):
        import settings
        good = v.Report()
        good.ok("NBA", "News")
        quiet_run.setattr(v, "check_league_twice", lambda *a: (good, True))
        out, results = tmp_path / "r.md", tmp_path / "r.json"
        assert v.main(["--league", "NBA", "--report", str(out), "--json", str(results)]) == 0
        assert "Nothing the apps rely on is broken" in out.read_text(encoding="utf-8")
        assert json.loads(results.read_text(encoding="utf-8"))["in_season"] == {"NBA": True}
        assert settings._cache == {"ncaaf_coverage": "all_d1"}

    def test_a_failure_exits_one(self, quiet_run):
        bad = v.Report()
        bad.fail("NBA", "News", "broken")
        quiet_run.setattr(v, "check_league_twice", lambda *a: (bad, True))
        assert v.main(["--league", "NBA"]) == 1

    def test_the_fake_failure_works_for_the_alarm(self, quiet_run, tmp_path):
        quiet_run.setattr(v, "check_league_twice", lambda *a: (v.Report(), False))
        out = tmp_path / "r.md"
        assert v.main(["--league", "NBA", "--fake-failure", "--report", str(out)]) == 1
        assert "## Failed" in out.read_text(encoding="utf-8")

    def test_one_league_blowing_up_is_reported_not_lost(self, quiet_run):
        def boom(*a):
            raise ValueError("surprise")

        quiet_run.setattr(v, "check_team_list", boom)
        report, _ = v.check_league(FakeHttp(), league("NBA"))
        assert FAIL_IN(report, "Validator")
        assert "surprise" in detail(report, "Validator")

    def test_the_board_the_apps_open_on_is_saved_too(self, tmp_path):
        http = FakeHttp(default=(200, {"events": []}))
        http.save_dir = str(tmp_path)
        v.check_scoreboard(http, v.Report(), league("NBA"))
        assert [p.name for p in tmp_path.iterdir()] == ["scoreboard-NBA-now.json"]

    def test_payloads_are_saved_for_the_iphone(self, tmp_path):
        http = v.Http(save_dir=str(tmp_path))
        http.save("summary", "NBA", {"a": 1})
        http.save("summary", "NFL", None)
        assert [p.name for p in tmp_path.iterdir()] == ["summary-NBA.json"]


class TestAppScores:
    """Whether get_scores lists the game the feed has, by date and by football week."""

    class Response:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def scoreboard(self):
        return load("scoreboard_events_by_status.json")

    def final(self):
        return next(e for e in self.scoreboard()["events"] if e["status"]["type"]["name"] == "STATUS_FINAL")

    def test_the_real_parser_on_a_real_board(self, monkeypatch):
        import espn_api
        data = self.scoreboard()
        monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: self.Response(data))
        report = v.Report()
        v.check_app_scores(report, league("NBA"), self.final())
        assert statuses(report, "App: game list") == [v.PASS]

    def test_a_game_on_the_feed_that_the_app_loses(self, monkeypatch):
        import espn_api
        data = self.scoreboard()
        data["events"] = [e for e in data["events"] if e["id"] != self.final()["id"]]
        monkeypatch.setattr(espn_api, "_http_get", lambda *a, **k: self.Response(data))
        report = v.Report()
        v.check_app_scores(report, league("NBA"), self.final())
        assert FAIL_IN(report, "App: game list")
        assert "didn't list it" in detail(report, "App: game list")

    def test_get_scores_raising(self, monkeypatch):
        import espn_api

        def boom(*a, **k):
            raise ValueError("bad")

        monkeypatch.setattr(espn_api, "get_scores", boom)
        report = v.Report()
        v.check_app_scores(report, league("NBA"), self.final())
        assert "ValueError" in detail(report, "App: game list")

    def test_unreadable_rows(self, monkeypatch):
        import espn_api
        from models import game
        final = self.final()
        monkeypatch.setattr(espn_api, "get_scores", lambda *a, **k: [{"id": final["id"]}])

        class Row:
            def __init__(self, *a):
                pass

            def get_display_text(self):
                return "Unknown at Unknown"

        monkeypatch.setattr(game, "GameData", Row)
        report = v.Report()
        v.check_app_scores(report, league("NBA"), final)
        assert FAIL_IN(report, "App: game list")
        assert "unreadable" in detail(report, "App: game list")

    def test_football_asks_for_the_week_of_the_game(self, monkeypatch):
        import espn_api
        asked = {}

        def fake(key, **kwargs):
            asked.update(kwargs)
            return []

        monkeypatch.setattr(espn_api, "get_scores", fake)
        report = v.Report()
        v.check_app_scores(report, league("NFL"), event())
        assert asked == {"week": 9, "season": 2026, "seasontype": 2}

    def test_a_football_final_with_no_week_fails(self):
        played = event()
        del played["week"]
        report = v.Report()
        v.check_app_scores(report, league("NFL"), played)
        assert "no week number" in detail(report, "App: game list")


class TestRemainingChecks:
    def test_a_tour_with_no_schedule_fails(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_golf_schedule", lambda t: [])
        monkeypatch.setattr(espn_api, "get_golf_leaderboard", lambda t: None)
        report = v.Report()
        v.check_golf(FakeHttp(), report)
        assert FAIL_IN(report, "App: golf schedule")
        assert v.WARN in statuses(report, "App: golf leaderboard")

    def test_a_tournament_with_no_name_fails(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_golf_schedule", lambda t: [{"name": "x"}])
        monkeypatch.setattr(espn_api, "get_golf_leaderboard", lambda t: {"players": []})
        report = v.Report()
        v.check_golf(FakeHttp(), report)
        assert FAIL_IN(report, "App: golf leaderboard")

    @pytest.mark.parametrize("board", [{"players": []}, {"players": [{"name": ""}]}, None])
    def test_a_fantasy_board_with_no_real_players_fails(self, monkeypatch, board):
        import espn_api
        monkeypatch.setattr(espn_api, "get_fantasy_cheatsheet", lambda **k: board)
        report = v.Report()
        v.check_fantasy(FakeHttp(), report)
        assert FAIL_IN(report, "App: cheatsheet")

    def test_the_espn_page_blocking_a_server_is_no_news(self, monkeypatch):
        import espn_api
        finished = event()
        monkeypatch.setattr(v, "find_recent_finals", lambda *a, **k: v.Finals([finished], "u", {}))
        monkeypatch.setattr(espn_api, "_fetch_web_gamepackage_plays", lambda *a: [])
        report = v.Report()
        v.check_hockey_web_page(FakeHttp(), report)
        assert statuses(report, "espn.com game page") == [v.PASS]

    def test_the_espn_page_code_raising_is_worth_a_look(self, monkeypatch):
        import espn_api

        def boom(*a):
            raise ValueError("bad")

        monkeypatch.setattr(v, "find_recent_finals", lambda *a, **k: v.Finals([event()], "u", {}))
        monkeypatch.setattr(espn_api, "_fetch_web_gamepackage_plays", boom)
        report = v.Report()
        v.check_hockey_web_page(FakeHttp(), report)
        assert statuses(report, "espn.com game page") == [v.WARN]

    @pytest.mark.parametrize("answer", [(500, None), (200, {"sports": []}), (200, {"sports": [{"leagues": [{"teams": []}]}]})])
    def test_a_team_list_that_is_gone(self, answer):
        report = v.Report()
        assert v.check_team_list(FakeHttp(default=answer), report, league("NBA")) == set()
        assert FAIL_IN(report, "Teams")

    def test_app_rankings_with_a_nameless_team(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_rankings", lambda k: {"polls": [{"name": "AP", "ranks": [
            {"current": 1, "team": {"abbreviation": "D"}}]}]})
        report = v.Report()
        v.check_rankings(FakeHttp(default=(200, {"rankings": [1]})), report, league("NCAAM"), True)
        assert FAIL_IN(report, "App: rankings")

    def test_app_news_empty_when_espn_has_it(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_news", lambda k: [])
        report = v.Report()
        v.check_news(FakeHttp(default=(200, {"articles": [1]})), report, league("NBA"))
        assert FAIL_IN(report, "App: news")

    def test_world_cup_standings_the_app_can_not_read(self, monkeypatch):
        import espn_api
        data = {"competitions": [{"matchNumber": 99}], "children": [{"standings": {"entries": [{"team": {}}]}}]}
        monkeypatch.setattr(espn_api, "get_world_cup_standings", lambda *a: [])
        report = v.Report()
        v.check_world_cup(FakeHttp(default=(200, data)), report)
        assert FAIL_IN(report, "App: standings")

    def college_football(self, **changes):
        # The fixture keeps every conference but only a team or two of each.
        return dataclasses.replace(league("NCAAF"), standings_min_teams=20, **changes)

    def app_rows(self, data, division=None):
        rows = []
        for conference in v._standing_nodes(data):
            for entry in (conference.get("standings") or {}).get("entries") or []:
                total = next(s for s in entry["stats"] if s.get("type") == "total")
                wins, losses = v.parse_record(total["summary"])
                rows.append({"team_name": entry["team"]["displayName"], "wins": wins, "losses": losses,
                             "division": division or conference["name"]})
        return rows

    def test_college_football_asks_for_all_of_division_one(self, monkeypatch):
        import espn_api
        data = load("standings_NCAAF_group90.json")
        monkeypatch.setattr(espn_api, "get_standings", lambda k: self.app_rows(data))
        http, report = FakeHttp(default=(200, data)), v.Report()
        v.check_standings(http, report, self.college_football(), True)
        assert http.urls == [f"{v.STANDINGS}/football/college-football/standings?group=90"]
        assert statuses(report, "Standings") == [v.PASS]
        assert statuses(report, "App: standings") == [v.PASS]

    def test_college_football_with_only_fbs_fails(self, monkeypatch):
        import espn_api
        monkeypatch.setattr(espn_api, "get_standings", lambda k: [])
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, load("standings_NCAAF.json"))), report, league("NCAAF"), True)
        assert statuses(report, "Standings") == [v.FAIL]
        assert "no FCS conference" in detail(report, "Standings")
        assert "expected at least 200" in detail(report, "Standings")

    def test_app_loses_an_fcs_team(self, monkeypatch):
        """Asks for all of Division I, as the app does in the validator, so a miss is a miss."""
        import espn_api
        data = load("standings_NCAAF_group90.json")
        rows = [r for r in self.app_rows(data) if r["team_name"] != "Montana State Bobcats"]
        monkeypatch.setattr(espn_api, "get_standings", lambda k: rows)
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, data)), report, self.college_football(), True)
        assert "Montana State Bobcats" in detail(report, "App: standings")

    def test_app_names_a_conference_for_the_level_above_it(self, monkeypatch):
        import espn_api
        data = load("standings_NCAAF_group90.json")
        monkeypatch.setattr(espn_api, "get_standings", lambda k: self.app_rows(data, division="FCS"))
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, data)), report, self.college_football(), True)
        assert statuses(report, "App: standings") == [v.FAIL]
        assert "named ['FCS']" in detail(report, "App: standings")

    def test_real_app_rows_match_the_real_payload(self, monkeypatch):
        """The real parser, forced to all of Division I as main() does, on ESPN's real answer."""
        import espn_api
        import settings
        data = load("standings_NCAAF_group90.json")
        monkeypatch.setattr(settings, "_cache", {"ncaaf_coverage": "all_d1"})
        calls = []

        class Response:
            status_code = 200

            def json(self):
                return data

        monkeypatch.setattr(espn_api, "_http_get", lambda url, **k: calls.append(url) or Response())
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, data)), report, self.college_football(), True)
        assert statuses(report, "App: standings") == [v.PASS], detail(report, "App: standings")
        assert calls == [f"{v.STANDINGS}/football/college-football/standings?group=90"]

    def test_app_standings_lose_a_team_or_a_division(self, monkeypatch):
        import espn_api
        data = load("standings_NFL.json")
        entries = v.standings_entries(data)
        rows = []
        for entry in entries:
            total = next(s for s in entry["stats"] if s.get("type") == "total")
            wins, losses = v.parse_record(total["summary"])
            rows.append({"team_name": entry["team"]["displayName"], "wins": wins, "losses": losses, "division": "All"})
        monkeypatch.setattr(espn_api, "get_standings", lambda k: rows)
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, data)), report, league("NFL"), True)
        assert "divisions" in detail(report, "App: standings")

        monkeypatch.setattr(espn_api, "get_standings", lambda k: rows[1:])
        report = v.Report()
        v.check_standings(FakeHttp(default=(200, data)), report, league("NFL"), True)
        assert "missing" in detail(report, "App: standings")
