"""golf.py against tests/fixtures/golf_grid.json, the grid the iPhone's GolfRules.swift is
held to by GolfGridTests.swift. A change to one app's rule that isn't made to the other
fails here or there."""
import json
from pathlib import Path

import pytest

import golf

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "golf_grid.json").read_text(encoding="utf-8"))


def _name(case):
    return case.get("name") or f"{case['file']} {case.get('event_id')}"


@pytest.mark.parametrize("case", GRID["state_cases"], ids=_name)
def test_state(case):
    assert golf.event_state(case["event"]) == case["expected"]


@pytest.mark.parametrize("case", GRID["pick_cases"], ids=_name)
def test_pick(case):
    picked = golf.pick_event(case["events"], case["event_id"])
    assert (picked or {}).get("id") == case["expected_id"]


@pytest.mark.parametrize("case", GRID["winner_cases"], ids=_name)
def test_winner(case):
    assert golf.winner_text(golf.winner(case["event"])) == case["expected"]


@pytest.mark.parametrize("case", GRID["fixture_cases"], ids=_name)
def test_real_fixtures(case):
    answer = json.loads((FIXTURES / case["file"]).read_text(encoding="utf-8"))
    events = answer["events"]
    assert len(events) == case["event_count"]
    assert golf.pick_event(events, case["event_id"])["id"] == case["expected_pick"]
    winners = {e["id"]: golf.winner_text(golf.winner(e)) for e in events}
    assert sum(1 for text in winners.values() if text) == case["winner_count"]
    for event_id, expected in case["winners"].items():
        assert winners[event_id] == expected


def test_grid_covers_every_rule():
    # The Swift side reads the same keys; an empty section would test nothing on either.
    for key in ("state_cases", "pick_cases", "winner_cases", "fixture_cases"):
        assert GRID[key], key
