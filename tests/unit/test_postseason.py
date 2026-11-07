"""postseason.py: the Bowls & Playoffs list's headings (#202).

The rule matches the iPhone's Models/Postseason.swift: the round from ESPN's note
headline, the type id only when there's no headline. tests/fixtures/postseason_grid.json
holds both apps to it.
"""

import json
from pathlib import Path

import pytest

from postseason import (
    BOWLS, CHAMPIONSHIP, FIRST_ROUND, PLAYOFF_ROUNDS, QUARTERFINALS, ROUNDS, SEMIFINALS,
    game_headline, game_round, heading_text, postseason_round, postseason_sections,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "espn" / "bowls_NCAAF.json"
GRID = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "postseason_grid.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", GRID["round_cases"], ids=lambda c: f"{c['headline']}|{c['type_id']}")
def test_grid_round(case):
    """The iPhone's PostseasonGridTests.swift reads the same cases."""
    assert postseason_round(case["headline"], case["type_id"]) == case["expected"]


def test_grid_heading_order():
    assert list(ROUNDS) == GRID["headings"]


def bowls():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]


def test_the_real_postseason_files_every_game_under_its_round():
    rounds = {game_headline(g): game_round(g) for g in bowls()}
    assert rounds == {
        "College Football Playoff National Championship Presented by AT&T": CHAMPIONSHIP,
        "College Football Playoff Semifinal at the Capital One Orange Bowl": SEMIFINALS,
        "College Football Playoff Quarterfinal at the Vrbo Fiesta Bowl": QUARTERFINALS,
        "Cricket Celebration Bowl": BOWLS,
        # ESPN gives the first-round games type 1, a plain game.
        "College Football Playoff First Round Game": FIRST_ROUND,
    }


def test_the_first_round_game_is_type_1():
    first = next(g for g in bowls() if "First Round" in game_headline(g))
    assert first["competitions"][0]["type"]["id"] == "1"


def test_sections_run_in_playoff_order_then_bowls():
    sections = postseason_sections(bowls())
    assert [name for name, _ in sections] == [FIRST_ROUND, QUARTERFINALS, SEMIFINALS, CHAMPIONSHIP, BOWLS]
    assert all(len(games) == 1 for _, games in sections)


def test_each_round_is_in_kickoff_order():
    games = [
        {"id": "b", "date": "2026-12-20T01:00Z", "competitions": [{"notes": [{"headline": "College Football Playoff First Round Game"}]}]},
        {"id": "a", "date": "2026-12-19T01:00Z", "competitions": [{"notes": [{"headline": "College Football Playoff First Round Game"}]}]},
    ]
    assert [g["id"] for g in postseason_sections(games)[0][1]] == ["a", "b"]


def test_empty_rounds_are_left_out():
    assert postseason_sections([]) == []
    assert postseason_sections(None) == []
    games = [{"date": "2026-12-12T17:00Z", "competitions": [{"notes": [{"headline": "Cricket Celebration Bowl"}]}]}]
    assert [name for name, _ in postseason_sections(games)] == [BOWLS]


@pytest.mark.parametrize("headline,type_id,expected", [
    ("", "33", CHAMPIONSHIP),
    (None, 35, SEMIFINALS),
    ("", "40", BOWLS),
    ("", None, BOWLS),
    ("", "x", BOWLS),
    ("CFP First Round", "1", FIRST_ROUND),
    ("NCAA Division II Football Championship", "1", BOWLS),
    ("FCS Playoffs - First Round", "1", BOWLS),
    ("College Football Playoff Semifinal at the Rose Bowl", "42", SEMIFINALS),
    ("College Football Playoff Game", "1", BOWLS),
])
def test_round_rule(headline, type_id, expected):
    assert postseason_round(headline, type_id) == expected


def test_headings_say_how_many_games():
    assert heading_text(BOWLS, 36) == "Bowl Games, 36 games"
    assert heading_text(CHAMPIONSHIP, 1) == "National Championship, 1 game"


def test_playoff_rounds():
    assert PLAYOFF_ROUNDS == set(ROUNDS) - {BOWLS}


def test_bad_games_are_skipped_not_fatal():
    assert game_headline({}) == ""
    assert game_headline({"competitions": [{"notes": [None, {"headline": "  "}, {"headline": "Rose Bowl"}]}]}) == "Rose Bowl"
    assert postseason_sections([None, {"competitions": []}]) == [(BOWLS, [{"competitions": []}])]
