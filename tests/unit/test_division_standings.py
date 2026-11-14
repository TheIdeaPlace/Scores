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
             "games_back": [d.games_back(e) for e in g["entries"]],
             "shown": [d.shown_games_back(e) for e in g["entries"]]} for g in d.division_groups(data)]


@pytest.mark.parametrize("case", GRID["labels"], ids=lambda c: repr(c["name"]))
def test_labels(case):
    assert d.division_label(case["name"]) == case["label"]


@pytest.mark.parametrize("case", GRID["games_back"], ids=lambda c: c["about"])
def test_games_back(case):
    assert d.games_back(case["entry"]) == case["games_back"]
    assert d.shown_games_back(case["entry"]) == case["shown"]
    assert d.shown_games_back(case["entry"], leader_word=False) == case["shown_level"]


def test_a_leader_is_never_shown_as_a_dash():
    """NVDA said "Minnesota Timberwolves, GB" and nothing more for ESPN's dash."""
    shown = {s for c in GRID["fixtures"] for g in c["groups"] for s in g["shown"]}
    assert d.LEADER in shown
    assert not shown & {"-", "—", ""}


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
def test_every_division_leader_is_at_the_top(fixture):
    """What the grid's real answers show, said as a rule: no leader reads as games back. (Games
    back can rise down a correct table after a bye or a rainout, so that isn't a rule.)"""
    case = next(c for c in GRID["fixtures"] if c["fixture"] == fixture)
    for group in case["groups"]:
        assert group["games_back"][0] == "-", group["name"]


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


def test_college_says_level_not_leader():
    """College games back counts overall record from the conference's top seed: UAB (0-1) reads
    "-" while Charlotte (0-0) reads "+0.5", so "Leader" would be false there."""
    import espn_api
    data = json.loads((FIXTURES / "espn" / "standings_NCAAM.json").read_text(encoding="utf-8"))
    rows = espn_api.parse_college_standings(data)
    shown = {r["games_back"] for r in rows}
    assert d.LEVEL in shown and d.LEADER not in shown and not shown & {"-", "—", ""}


def test_the_wnba_says_leader():
    import espn_api
    data = json.loads((FIXTURES / "espn" / "standings_WNBA.json").read_text(encoding="utf-8"))
    rows = espn_api.parse_college_standings(data, leader_word=True)
    assert d.LEADER in {r["games_back"] for r in rows}


@pytest.mark.parametrize("college,shown", [(False, "Leader"), (True, "0")])
def test_a_games_own_standings_read_as_the_standings_do(college, shown):
    """A game summary's standings carry ESPN's dash too: NBA's "Boston, GB: -" was silent."""
    from game_labels import game_standings_tables
    standings = {"groups": [{"header": "Atlantic Standings", "standings": {"entries": [
        {"team": "Boston", "stats": [{"name": "gamesBehind", "abbreviation": "GB", "displayValue": "-"},
                                     {"name": "wins", "abbreviation": "W", "displayValue": "10"}]},
        {"team": "Philadelphia", "stats": [{"name": "gamesBehind", "abbreviation": "GB", "displayValue": "0.5"},
                                           {"name": "wins", "abbreviation": "W", "displayValue": "10"}]},
    ]}}]}
    table = game_standings_tables(standings, college=college)[0]
    assert table["rows"] == [["Boston", shown, "10"], ["Philadelphia", "0.5", "10"]]
    # A summary with no games back is left as it was.
    nfl = {"groups": [{"standings": {"entries": [{"team": "Bears", "stats": [{"name": "wins", "displayValue": "6"}]}]}}]}
    assert game_standings_tables(nfl)[0]["rows"] == [["Bears", "6"]]


def test_an_unreadable_seed_counts_as_none():
    entries = [{"team": {"id": "1", "abbreviation": "A"}, "stats": [{"name": "playoffSeed", "value": "x"}]},
               {"team": {"id": "2", "abbreviation": "B"}, "stats": [{"name": "playoffSeed", "value": 1}]}]
    assert [e["team"]["abbreviation"] for e in d.standing_order(entries)] == ["B", "A"]
