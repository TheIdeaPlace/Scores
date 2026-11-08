"""game_labels.on_todays_scoreboard against tests/fixtures/scoreboard_date_grid.json, the grid the
iPhone's ScoreboardDay.isOnTodaysScoreboard is held to as well (ScoreboardDateGridTests in MonitoringTests.swift).
Only today's games can be monitored, on both apps (#185)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from game_labels import on_todays_scoreboard

GRID = Path(__file__).resolve().parents[1] / "fixtures" / "scoreboard_date_grid.json"
CASES = json.loads(GRID.read_text(encoding="utf-8"))["cases"]


def test_the_grid_has_both_answers():
    assert {case["today"] for case in CASES} == {True, False}


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_on_todays_scoreboard(case):
    now = datetime.fromisoformat(case["now"])
    assert on_todays_scoreboard(case["date"], case["time_valid"], now=now) is case["today"]
