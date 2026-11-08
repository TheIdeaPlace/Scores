"""win_probability.py against the shared grid the iPhone's WinProbability.swift is held
to, and the per-play tables Windows shows from a real MLB summary."""

import json
from pathlib import Path

import pytest

import win_probability as wp

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "win_probability_grid.json").read_text(encoding="utf-8"))


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _summary(case):
    return _load(case["fixture"]) if "fixture" in case else case["summary"]


FINAL = "espn/summary_final_MLB_401817091.json"
WORLD_SERIES = "espn/summary_final_MLB_401908045_WS.json"


@pytest.mark.parametrize("case", GRID["percent_cases"], ids=lambda c: str(c["fraction"]))
def test_percent_grid(case):
    assert wp.percent(case["fraction"]) == case["percent"]


@pytest.mark.parametrize("case", GRID["leader_cases"], ids=lambda c: str(c["home_fraction"]))
def test_leader_grid(case):
    assert wp.leader_text(case["home_fraction"], case["home"], case["away"]) == case["text"]


@pytest.mark.parametrize("case", GRID["summary_cases"], ids=lambda c: c["name"])
def test_summary_grid(case):
    summary = _summary(case)
    points = wp.entries(summary)
    assert len(points) == case["expected_count"]
    if case["expected_leader"] is None:
        assert wp.summary_line(summary) == ""
        return
    assert wp.percent(points[0]["home"]) == case["expected_first_home_percent"]
    assert wp.leader_text(points[-1]["home"], case["home"], case["away"]) == case["expected_leader"]
    if "fixture" in case:
        assert wp.team_names(summary) == {"home": case["home"], "away": case["away"]}
        assert wp.summary_line(summary) == f"Win probability: {case['expected_leader']}"


def test_every_play_is_joined_to_its_play():
    rows = wp.play_rows(_load(FINAL))
    assert len(rows) == 74
    first, last = rows[0], rows[-1]
    assert first == {"number": 1, "inning": "Top 1st", "half_key": (1, "Top"),
                     "play": "Lindor popped out to shortstop.", "score": "Mets 0, Nationals 0",
                     "away": 30, "home": 70, "delta": None, "change": ""}
    assert (last["inning"], last["play"], last["score"], last["away"], last["home"], last["change"]) == (
        "Bottom 9th", "Lile flied out to center.", "Mets 7, Nationals 1", 100, 0, "No change")
    assert all(row["away"] + row["home"] == 100 for row in rows)
    assert wp.table_row(first) == ["Top 1st", "Lindor popped out to shortstop.", "Mets 0, Nationals 0",
                                   "30%", "70%", ""]
    assert wp.headers(wp.team_names(_load(FINAL))) == [
        "Inning", "Play", "Score", "Mets chance", "Nationals chance", "Change"]


def test_change_says_who_gained():
    rows = wp.play_rows(_load(FINAL))
    # Soto's single: 70 to 67 for the Nationals, a gain of 3 for the Mets.
    assert (rows[1]["delta"], rows[1]["change"]) == (-3, "Mets +3")
    assert (rows[2]["delta"], rows[2]["change"]) == (2, "Nationals +2")


def test_by_inning_is_the_last_play_of_each_half():
    halves = wp.by_inning(wp.play_rows(_load(FINAL)))
    assert len(halves) == 18  # the home team trailed, so it batted in the 9th
    assert [h["inning"] for h in halves[:3]] == ["Top 1st", "Bottom 1st", "Top 2nd"]
    assert halves[-1]["inning"] == "Bottom 9th"


def test_biggest_swings():
    swings = wp.biggest_swings(wp.play_rows(_load(FINAL)))
    assert len(swings) == wp.TOP_SWINGS
    assert (swings[0]["inning"], swings[0]["change"]) == ("Top 7th", "Mets +50")
    assert swings[0]["play"].startswith("Ewing homered")
    assert [abs(s["delta"]) for s in swings] == sorted((abs(s["delta"]) for s in swings), reverse=True)


def test_overview():
    assert wp.overview(_load(FINAL)) == (
        "Mets 100%, Nationals 0% after the last play. Biggest swing: Mets +50, Top 7th, "
        "Ewing homered to right center (396 feet), Benge scored and Alvarez scored.")
    assert wp.overview({}) == "ESPN has no win probability for this game."


def test_a_summary_without_plays_names_them_by_number():
    summary = _load(WORLD_SERIES)
    rows = wp.play_rows(summary)
    assert len(rows) == 92
    assert rows[0]["inning"] == "" and rows[0]["score"] == ""
    assert wp.table_row(rows[0])[1] == "Play 1"
    assert wp.by_inning(rows) == []
    assert wp.overview(summary) == "Brewers 0%, Rays 100% after the last play. Biggest swing: Brewers +34."


def test_ties_in_swings_keep_the_earlier_play_first():
    rows = [{"delta": None}, {"delta": 5, "n": 1}, {"delta": -5, "n": 2}, {"delta": 0, "n": 3}]
    assert [r["n"] for r in wp.biggest_swings(rows)] == [1, 2]


@pytest.mark.parametrize("summary", [None, [], "junk", {"winprobability": "x"}, {"winprobability": [None, 3]},
                                     {"header": {"competitions": "x"}, "winprobability": [True]}])
def test_bad_shapes_are_nothing(summary):
    assert wp.entries(summary) == []
    assert wp.summary_line(summary) == ""
    assert wp.play_rows(summary) == []


def test_names_fall_back():
    assert wp.team_names({}) == {"home": "Home", "away": "Away"}
    summary = {"header": {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "WSH"}},
        {"homeAway": "away", "team": {"displayName": "New York Mets"}}]}]}}
    assert wp.team_names(summary) == {"home": "WSH", "away": "New York Mets"}
