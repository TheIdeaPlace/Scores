"""drive_results.py: who scored on a drive and how many points (#204).

Held to tests/fixtures/drive_results_grid.json, which the iPhone's
DriveResultsGridTests.swift reads too, and run on the real ESPN drives of the two
games the NVDA bug bash found the problem in.
"""

import json
from pathlib import Path

import pytest

from drive_results import (
    DriveResult, chronological_drives, drive_badge, drive_results, summary_teams,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "drive_results_grid.json").read_text(encoding="utf-8"))


def _drives(case):
    return [{
        "team": {"id": d["team_id"]} if d["team_id"] is not None else {},
        "plays": [{"awayScore": a, "homeScore": h, "scoringPlay": i in d["scoring_plays"]}
                  for i, (a, h) in enumerate(d["plays"])],
    } for d in case["drives"]]


def _shown(result, names):
    other = "home" if result.scorer == "away" else "away"
    return {
        "kind": result.kind,
        "points": result.points,
        "scorer": result.scorer,
        "by_opponent": result.by_opponent,
        "other_points": result.other_points,
        "badge": drive_badge(result, names.get(result.scorer, ""), names.get(other, "")),
    }


@pytest.mark.parametrize("case", GRID["cases"], ids=lambda c: c["name"])
def test_grid_case(case):
    names = {"away": case["away"]["name"], "home": case["home"]["name"]}
    results = drive_results(_drives(case), case["away"]["id"], case["home"]["id"])
    assert [_shown(r, names) for r in results] == case["expected"]


@pytest.mark.parametrize("case", GRID["fixture_cases"], ids=lambda c: c["fixture"])
def test_real_drives(case):
    summary = json.loads((FIXTURES / "espn" / case["fixture"]).read_text(encoding="utf-8"))
    teams = summary_teams(summary)
    names = {side: teams[side]["name"] for side in teams}
    drives = chronological_drives(summary["drives"])
    results = drive_results(drives, teams["away"]["id"], teams["home"]["id"])
    scored = {d["id"]: _shown(r, names) for d, r in zip(drives, results) if r.kind}
    assert scored == case["expected"]


def test_the_return_touchdown_is_credited_to_the_team_that_scored():
    """NC State missed a 50-yard field goal and Duke ran it back 100 yards."""
    summary = json.loads((FIXTURES / "espn" / "drives_NCAAF_401858286.json").read_text(encoding="utf-8"))
    teams = summary_teams(summary)
    drives = chronological_drives(summary["drives"])
    results = drive_results(drives, teams["away"]["id"], teams["home"]["id"])
    by_id = dict(zip((d["id"] for d in drives), results))
    missed = by_id["40185828616"]
    assert next(d for d in drives if d["id"] == "40185828616")["team"]["abbreviation"] == "NCSU"
    assert teams[missed.scorer]["name"] == "Duke Blue Devils"
    assert missed.by_opponent
    # NC State's only points in the game were one field goal.
    assert sum(r.points for r in results if r.scorer == "home") == 3


def test_points_add_up_to_the_final_score():
    # drives_NCAAF_2OT.json is left out: it keeps only the overtime drives.
    for name in ("drives_NCAAF_401858286.json", "drives_NCAAF_401866682_2OT.json"):
        summary = json.loads((FIXTURES / "espn" / name).read_text(encoding="utf-8"))
        teams = summary_teams(summary)
        drives = chronological_drives(summary["drives"])
        results = drive_results(drives, teams["away"]["id"], teams["home"]["id"])
        totals = {"away": 0, "home": 0}
        for r in results:
            if r.scorer:
                totals[r.scorer] += r.points
                totals["home" if r.scorer == "away" else "away"] += r.other_points
        competitors = summary["header"]["competitions"][0]["competitors"]
        final = {c["homeAway"]: int(c["score"]) for c in competitors if c.get("score") not in (None, "")}
        if final:
            assert totals == final, name


def test_drives_missing_before_the_first_one_kept_are_nobodys_points():
    """drives_NCAAF_2OT.json starts at overtime: the score it opens with isn't the first OT drive's."""
    summary = json.loads((FIXTURES / "espn" / "drives_NCAAF_2OT.json").read_text(encoding="utf-8"))
    teams = summary_teams(summary)
    drives = chronological_drives(summary["drives"])
    results = drive_results(drives, teams["away"]["id"], teams["home"]["id"])
    assert all(r.points <= 8 for r in results)


def test_live_current_drive_is_added_once():
    previous = [{"id": "1", "plays": []}, {"id": "2", "plays": []}]
    assert [d["id"] for d in chronological_drives({"previous": previous, "current": {"id": "2"}})] == ["1", "2"]
    assert [d["id"] for d in chronological_drives({"previous": previous, "current": {"id": "3"}})] == ["1", "2", "3"]
    assert chronological_drives(None) == []
    assert chronological_drives({"previous": None}) == []


def test_bad_data_reads_as_no_score():
    results = drive_results([None, {"plays": None}, {"plays": [None, {"awayScore": "x", "homeScore": 1}]}], "1", "2")
    assert results == [DriveResult(), DriveResult(), DriveResult()]
    assert drive_badge(DriveResult()) is None


def test_string_scores_count():
    results = drive_results([{"team": {"id": 1}, "plays": [{"awayScore": "0", "homeScore": "0"},
                                                          {"awayScore": "7", "homeScore": "0", "scoringPlay": True}]}], 1, 2)
    assert results[0].kind == "TD" and results[0].points == 7 and not results[0].by_opponent


@pytest.mark.parametrize("value,expected", [
    (7, 7), ("7", 7), (7.0, 7), ("7.0", 7), ("1,000", 1000), (" 3 ", 3),
    (None, None), ("", None), ("x", None), (True, None), (float("nan"), None),
])
def test_scores_read_as_the_iphone_reads_them(value, expected):
    """The iPhone's lenientNumber takes the same values."""
    from drive_results import _score
    assert _score(value) == expected


def test_without_scoring_play_marks_nothing_is_credited():
    """A feed with no scoringPlay flags gives no scorer, so the badge falls back to ESPN's result."""
    results = drive_results([{"team": {"id": "1"}, "plays": [{"awayScore": 0, "homeScore": 0},
                                                            {"awayScore": 7, "homeScore": 0}]}], "1", "2")
    assert results == [DriveResult()]


def test_summary_teams_without_a_header():
    assert summary_teams({}) == {}
    assert summary_teams(None) == {}
    assert summary_teams({"header": {"competitions": []}}) == {}
