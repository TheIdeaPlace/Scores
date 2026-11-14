"""division_standings against the grid the iPhone's DivisionStandingsGridTests reads too."""
import json
from pathlib import Path

import pytest

import division_standings as d

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "division_standings_grid.json").read_text(encoding="utf-8"))


def groups(data):
    return [{"name": g["name"], "conference": g["conference"],
             "teams": [e["team"]["abbreviation"] for e in g["entries"]],
             "games_back": [d.games_back(e) for e in g["entries"]]} for g in d.division_groups(data)]


@pytest.mark.parametrize("case", GRID["labels"], ids=lambda c: repr(c["name"]))
def test_labels(case):
    assert d.division_label(case["name"]) == case["label"]


@pytest.mark.parametrize("case", GRID["games_back"], ids=lambda c: c["about"])
def test_games_back(case):
    assert d.games_back(case["entry"]) == case["games_back"]


@pytest.mark.parametrize("case", GRID["order"], ids=lambda c: c["about"])
def test_order(case):
    assert [e["team"]["abbreviation"] for e in d.standing_order(case["entries"])] == case["order"]


@pytest.mark.parametrize("case", GRID["trees"], ids=lambda c: c["about"])
def test_trees(case):
    assert groups(case["data"]) == case["groups"]


@pytest.mark.parametrize("case", GRID["fixtures"], ids=lambda c: c["fixture"])
def test_real_answers(case):
    data = json.loads((FIXTURES / "espn" / case["fixture"]).read_text(encoding="utf-8"))
    assert groups(data) == case["groups"]


@pytest.mark.parametrize("fixture", ["standings_NFL_divisions.json", "standings_NBA_divisions.json",
                                     "standings_NHL_divisions.json", "standings_MLB_divisions.json"])
def test_every_division_leader_is_at_the_top_and_games_back_never_falls(fixture):
    """What the grid's real answers show, said as a rule: no leader reads as games back."""
    case = next(c for c in GRID["fixtures"] if c["fixture"] == fixture)
    for group in case["groups"]:
        figures = [0.0 if gb == "-" else float(gb) for gb in group["games_back"]]
        assert group["games_back"][0] == "-", group["name"]
        assert figures == sorted(figures), group["name"]


def test_the_nfl_bug_is_gone():
    """The iPhone had Denver 0.5 back while leading the AFC West: the conference figure."""
    nfl = next(c for c in GRID["fixtures"] if c["fixture"] == "standings_NFL_divisions.json")
    west = next(g for g in nfl["groups"] if g["name"] == "AFC West")
    assert list(zip(west["teams"], west["games_back"]))[:2] == [("DEN", "-"), ("KC", "0.5")]


def test_team_divisions_and_conference_entries():
    data = json.loads((FIXTURES / "espn" / "standings_MLB_divisions.json").read_text(encoding="utf-8"))
    divisions = d.team_divisions(data)
    assert len(divisions) == 30 and divisions["10"] == "AL East"
    assert len(d.conference_entries(data, "American League")) == 15
    assert d.conference_entries(data, "Nowhere") == []


@pytest.mark.parametrize("data", [None, [], "text", {}, {"children": None}, {"children": [None, 3]}])
def test_nothing_readable_is_no_groups(data):
    assert d.division_groups(data) == []
    assert d.team_divisions(data) == {}


def test_an_unreadable_seed_counts_as_none():
    entries = [{"team": {"id": "1", "abbreviation": "A"}, "stats": [{"name": "playoffSeed", "value": "x"}]},
               {"team": {"id": "2", "abbreviation": "B"}, "stats": [{"name": "playoffSeed", "value": 1}]}]
    assert [e["team"]["abbreviation"] for e in d.standing_order(entries)] == ["B", "A"]
