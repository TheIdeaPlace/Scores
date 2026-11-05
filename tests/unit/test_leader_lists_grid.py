"""What a real /leaders answer reads as. The iPhone is held to the same file, in
LeagueLeadersTests.swift, since both apps read their leaders from there."""
import json
from pathlib import Path

import pytest

import espn_api
from team_stats import ranking_rows

FIXTURES = Path(__file__).parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "leader_lists_grid.json").read_text(encoding="utf-8"))


def test_the_grid_has_the_cases_that_matter():
    fixtures = {case["fixture"] for case in GRID["cases"]}
    assert {"leaders_v3_NCAAM.json", "leaders_v3_NCAAM_full.json", "leaders_v3_NCAAF_2025.json"} <= fixtures
    tied = [row for case in GRID["cases"] for category in case["categories"]
            for row, previous in zip(category["rows"][1:], category["rows"]) if row["rank"] == previous["rank"]]
    assert tied, "it should show a tie"


@pytest.mark.parametrize("case", GRID["cases"], ids=lambda case: case["fixture"])
def test_windows_reads_it_as_the_grid_says(case):
    data = json.loads((FIXTURES / "espn" / case["fixture"]).read_text(encoding="utf-8"))
    parsed = espn_api._parse_leaders(data)
    assert parsed.get("season") == case["season"]
    assert [c["category"] for c in parsed["player_stats"]] == [c["title"] for c in case["categories"]]
    for category, expected in zip(parsed["player_stats"], case["categories"]):
        rows = ranking_rows("player", category["stats"])
        assert [{"rank": row[0], "player": row[1], "team": stat["team"], "value": row[3]}
                for row, stat in zip(rows, category["stats"])] == expected["rows"]
