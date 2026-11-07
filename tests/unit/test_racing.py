"""racing.py on ESPN's real racing answers, and tests/fixtures/racing_grid.json, which holds the
iPhone (RacingGridTests.swift) to the same reading of the race and the standings."""
import copy
import json
from pathlib import Path

import pytest

import racing

FIXTURES = Path(__file__).parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "racing_grid.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FIXTURES / "espn" / name).read_text(encoding="utf-8"))


def event_of(name):
    return racing.parse_race_event(load(name))


def season_of(series):
    return racing.parse_schedule(load(f"racing_season_{series}_2026.json"))


def race(races, name):
    return next(r for r in races if r["name"] == name)


# ------------------------------------------------------------------ the shared grid

@pytest.mark.parametrize("case", GRID["events"], ids=lambda c: c["fixture"])
def test_each_race_reads_as_the_grid_says(case):
    event = event_of(case["fixture"])
    for key in ("name", "date", "state", "status", "completed", "broadcasts", "kind", "winner"):
        assert event[key] == case[key], key
    assert len(event["competitors"]) == case["count"]
    first = [["" if c["position"] is None else str(c["position"]), c["driver"], c["nationality"]]
             for c in event["competitors"][:3]]
    assert first == case["first"]


@pytest.mark.parametrize("case", GRID["standings"], ids=lambda c: c["fixture"])
def test_each_standings_reads_as_the_grid_says(case):
    groups = racing.parse_standings(load(case["fixture"]))
    assert [g["name"] for g in groups] == [g["name"] for g in case["groups"]]
    for group, expected in zip(groups, case["groups"]):
        assert group["constructors"] == expected["constructors"]
        assert len(group["entries"]) == expected["count"]
        first = [[str(e["rank"]), e["name"], e["nationality"], e["points"]] for e in group["entries"][:3]]
        assert first == expected["first"]


def test_the_grid_covers_every_series_and_every_kind_of_field():
    fixtures = {c["fixture"] for c in GRID["events"]} | {c["fixture"] for c in GRID["standings"]}
    for path, *_ in racing.RACING_SERIES.values():
        slug = path.split("/")[1]
        assert f"racing_scoreboard_{slug}.json" in fixtures
        assert f"racing_standings_{slug}.json" in fixtures
    assert {c["kind"] for c in GRID["events"]} == {racing.ENTRY_LIST, racing.RESULTS, ""}


# ------------------------------------------------------------------ the race weekend

class TestRaceEvent:
    def test_formula_1s_race_not_its_first_session_or_its_event(self):
        # The event says Final and its first competition is Practice 1, both finished; the race
        # itself is the next day.
        raw = load("racing_scoreboard_f1.json")
        assert raw["events"][0]["status"]["type"]["description"] == "Final"
        event = racing.parse_race_event(raw)
        assert (event["state"], event["status"], event["date"]) == ("pre", "Scheduled", "2026-11-08T17:00:00Z")
        assert event["circuit"] == "Autodromo Jose Carlos Pace"

    def test_a_field_with_no_order_is_an_entry_list_with_no_positions(self):
        event = event_of("racing_scoreboard_f1.json")
        assert event["kind"] == racing.ENTRY_LIST
        assert all(c["position"] is None for c in event["competitors"])
        assert racing.race_headers(event) == racing.ENTRY_HEADERS
        assert racing.race_rows(event)[0] == ["Lando Norris", "Britain"]

    def test_formula_1s_sessions_by_name_in_order(self):
        sessions = event_of("racing_scoreboard_f1.json")["sessions"]
        assert [s["name"] for s in sessions] == ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"]
        assert [s["state"] for s in sessions] == ["post"] * 4 + ["pre"]
        assert racing.current_row(sessions) == 4

    def test_a_sprint_weekends_sessions(self):
        chinese = next(e for e in load("racing_season_f1_2026.json")["events"] if "Chinese" in e["name"])
        names = [racing.session_name(c) for c in chinese["competitions"]]
        assert names == ["Practice 1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"]

    def test_a_finished_race_has_positions_and_a_winner(self):
        event = event_of("racing_scoreboard_irl.json")
        assert event["kind"] == racing.RESULTS
        assert racing.race_rows(event)[:2] == [["1", "Scott McLaughlin", "New Zealand"], ["2", "Kyle Kirkwood", "USA"]]
        assert event["sessions"] == [{"name": "Race", "date": "2026-09-06T18:30:00Z", "state": "post", "status": "Final"}]

    def test_nascar_lists_nobody_before_race_day(self):
        event = event_of("racing_scoreboard_nascar-premier.json")
        assert event["competitors"] == [] and event["kind"] == ""
        assert event["broadcasts"] == ["NBC", "HBO Max"]

    def test_a_race_under_way_is_a_running_order_with_no_winner(self):
        raw = load("racing_scoreboard_irl.json")
        status = raw["events"][0]["competitions"][0]["status"]["type"]
        status.update(state="in", completed=False, description="In Progress")
        event = racing.parse_race_event(raw)
        assert event["kind"] == racing.RUNNING_ORDER
        assert event["winner"] == ""
        assert event["competitors"][0]["position"] == 1
        assert "In progress" in racing.race_summary(event)

    def test_a_canceled_race_has_no_field_and_says_canceled(self):
        raw = load("racing_season_f1_2026.json")
        bahrain = next(e for e in raw["events"] if e["name"] == "Gulf Air Bahrain Grand Prix")
        event = racing.parse_race_event({"events": [bahrain]})
        assert event["canceled"] and not event["completed"]
        assert event["competitors"] == [] and event["kind"] == "" and event["winner"] == ""
        assert "Canceled" in racing.race_summary(event)

    def test_no_events_is_the_off_season(self):
        assert racing.parse_race_event({"events": []}) is None
        assert racing.parse_race_event(None) is None

    def test_the_season_comes_from_the_scoreboard(self):
        assert racing.season_year(load("racing_scoreboard_f1.json")) == 2026
        assert racing.season_year({"leagues": [{"season": {"year": "2026"}}]}) is None

    def test_what_the_summary_says(self, monkeypatch):
        assert racing.race_summary(event_of("racing_scoreboard_irl.json")) == (
            "Grand Prix of Monterey. Won by Scott McLaughlin. On FOX.")
        summary = racing.race_summary(event_of("racing_scoreboard_f1.json"))
        assert summary.startswith("MSC Cruises São Paulo Grand Prix. Autodromo Jose Carlos Pace. Sunday, November 8, ")
        assert summary.endswith(". On Apple TV.")

    def test_a_missing_name_or_flag_is_never_blank(self):
        event = racing.parse_race_event({"events": [{"name": "X", "competitions": [{
            "status": {"type": {"state": "post", "completed": True}},
            "competitors": [{"order": 2, "athlete": {}}, {"order": 1}]}]}]})
        assert [c["position"] for c in event["competitors"]] == [1, 2]
        assert racing.race_rows(event) == [["1", "Unknown driver", "Not given"], ["2", "Unknown driver", "Not given"]]


# ------------------------------------------------------------------ the season

class TestSchedule:
    def test_every_race_in_date_order(self):
        for series, count in (("f1", 25), ("irl", 18), ("nascar-premier", 40)):
            races = season_of(series)
            assert len(races) == count
            assert [r["date"] for r in races] == sorted(r["date"] for r in races)

    def test_winners_and_what_the_rest_say(self):
        races = season_of("f1")
        rows = dict((r[0], r[3]) for r in racing.schedule_rows(races))
        assert rows["Qatar Airways Australian Grand Prix"] == "Won by George Russell"
        assert rows["Gulf Air Bahrain Grand Prix"] == "Canceled"
        assert rows["Heineken Las Vegas Grand Prix"] == "Upcoming"

    def test_a_weekend_whose_race_is_still_to_come_is_upcoming(self):
        # The event says Final; its race is the next day.
        sao_paulo = race(season_of("f1"), "MSC Cruises São Paulo Grand Prix")
        assert sao_paulo["state"] == "pre" and sao_paulo["winner"] == ""

    def test_the_winner_is_who_finished_first_even_without_the_winner_flag(self):
        mid_ohio = race(season_of("irl"), "Grand Prix of Mid-Ohio")
        assert mid_ohio["winner"] == "Pato O'Ward"

    def test_it_starts_on_the_next_race(self):
        races = season_of("f1")
        assert races[racing.current_row(races)]["name"] == "MSC Cruises São Paulo Grand Prix"
        finished = season_of("irl")
        assert racing.current_row(finished) == len(finished) - 1
        assert racing.current_row([]) == 0

    def test_a_circuit_column_only_when_every_race_has_one(self):
        assert racing.schedule_headers(season_of("f1")) == ["Race", "Circuit", "Date", "Result"]
        assert racing.schedule_headers(season_of("irl")) == ["Race", "Date", "Result"]
        assert racing.schedule_rows(season_of("f1"))[0][1] == "Melbourne Grand Prix Circuit"


# ------------------------------------------------------------------ standings

class TestStandings:
    def test_formula_1_has_drivers_and_constructors(self):
        groups = racing.parse_standings(load("racing_standings_f1.json"))
        drivers, constructors = groups
        assert racing.standings_headers(drivers) == ["Pos", "Driver", "Nationality", "Points"]
        assert racing.standings_headers(constructors) == ["Pos", "Constructor", "Points"]
        assert racing.standings_rows(constructors)[0] == ["1", "Mercedes", "630"]

    def test_an_entry_without_a_rank_is_left_out_and_an_empty_group_too(self):
        body = {"children": [
            {"name": "Standings", "standings": {"entries": [
                {"athlete": {"displayName": "A"}, "stats": [{"name": "rank", "displayValue": "1"},
                                                            {"name": "championshipPts", "displayValue": "10"}]},
                {"athlete": {"displayName": "B"}, "stats": [{"name": "rank", "displayValue": "-"}]},
                {"athlete": {"displayName": "C"}, "stats": []},
            ]}},
            {"name": "Empty", "standings": {"entries": []}},
            {"name": "None"},
        ]}
        groups = racing.parse_standings(body)
        assert [g["name"] for g in groups] == ["Standings"]
        assert [e["name"] for e in groups[0]["entries"]] == ["A"]

    def test_no_points_reads_as_not_given(self):
        group = {"constructors": False, "entries": [{"rank": 1, "name": "A", "nationality": "", "points": ""}]}
        assert racing.standings_rows(group) == [["1", "A", "Not given", "Not given"]]

    def test_rubbish_is_no_standings(self):
        assert racing.parse_standings(None) == []
        assert racing.parse_standings({"children": "no"}) == []


# ------------------------------------------------------------------ the series

def test_the_three_series_and_their_paths():
    assert {k: v[0] for k, v in racing.RACING_SERIES.items()} == {
        "F1": "racing/f1", "IndyCar": "racing/irl", "NASCAR": "racing/nascar-premier"}
    assert racing.has_constructors("F1") and racing.has_sessions("F1")
    assert not racing.has_constructors("NASCAR")
    assert racing.series_path("nope") is None


def test_the_ios_app_names_the_same_paths():
    swift = (Path(__file__).parents[2] / "iOS" / "SportsScoresApp" / "SportsScores" / "Models" / "Sport.swift")
    text = swift.read_text(encoding="utf-8")
    for path, *_ in racing.RACING_SERIES.values():
        assert f'"{path}"' in text


def test_no_table_cell_is_blank():
    tables = []
    for series in ("f1", "irl", "nascar-premier"):
        event = event_of(f"racing_scoreboard_{series}.json")
        tables += [racing.race_rows(event), racing.session_rows(event), racing.schedule_rows(season_of(series))]
        tables += [racing.standings_rows(g) for g in racing.parse_standings(load(f"racing_standings_{series}.json"))]
    cells = [cell for rows in tables for row in rows for cell in row]
    assert cells and all(isinstance(c, str) and c.strip() for c in cells)


def test_dates_read_in_utc():
    assert racing.utc_iso("2026-11-08T17:00Z") == "2026-11-08T17:00:00Z"
    assert racing.utc_iso("2026-11-08T12:00:00-05:00") == "2026-11-08T17:00:00Z"
    assert racing.utc_iso("not a date") == "" and racing.utc_iso(None) == ""


def test_the_parse_leaves_its_input_alone():
    raw = load("racing_scoreboard_f1.json")
    before = copy.deepcopy(raw)
    racing.parse_race_event(raw)
    assert raw == before
