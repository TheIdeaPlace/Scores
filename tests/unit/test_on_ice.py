"""on_ice.py against the shared grid the iPhone's OnIce.swift is held to, and a real summary."""

import json
from pathlib import Path

import pytest

import on_ice

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "on_ice_grid.json").read_text(encoding="utf-8"))


def _summary(case):
    if "fixture" in case:
        return json.loads((FIXTURES / case["fixture"]).read_text(encoding="utf-8"))
    return case["summary"]


@pytest.mark.parametrize("case", GRID["cases"], ids=lambda c: c["name"])
def test_grid(case):
    teams = on_ice.lineup(_summary(case))
    assert teams == case["expected_teams"]
    assert on_ice.summary_line(teams) == case["expected_line"]
    assert [on_ice.team_heading(t) for t in teams] == case["expected_headings"]
    assert [[on_ice.player_text(p) for p in t["players"]] for t in teams] == case["expected_player_texts"]


def test_the_live_fixture_is_live_and_has_the_block():
    summary = json.loads((FIXTURES / "espn" / "summary_live_NHL_401892664.json").read_text(encoding="utf-8"))
    assert on_ice.is_live(summary)
    assert [len(t["entries"]) for t in summary["onIce"]] == [6, 6]


@pytest.mark.parametrize("summary", [None, [], "junk", {}, {"header": None}, {"header": {"competitions": "x"}},
                                     {"header": {"competitions": [{"status": {"type": {"state": "in"}}}]},
                                      "onIce": "junk"}])
def test_bad_shapes_are_nothing(summary):
    assert on_ice.lineup(summary) == []
    assert on_ice.summary_line([]) == ""
