"""radio_links.py against the shared grid, and its reading of a real scoreboard."""

import json
from pathlib import Path

import pytest

import radio_links

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "radio_links_grid.json").read_text(encoding="utf-8"))
DATA = GRID["data"]


@pytest.mark.parametrize("case", GRID["game_cases"], ids=lambda c: c["name"])
def test_game_options(case):
    assert radio_links.game_options(
        DATA, case["league"], case["away_id"], case["away_name"],
        case["home_id"], case["home_name"]) == case["expected"]


@pytest.mark.parametrize("case", GRID["team_cases"], ids=lambda c: c["name"])
def test_team_listen_options(case):
    assert radio_links.team_listen_options(
        DATA, case["league"], case["team_id"], case["team_name"]) == case["expected"]


@pytest.mark.parametrize("case", GRID["directory_cases"], ids=lambda c: c["league"])
def test_directory(case):
    rows = radio_links.directory(DATA, case["league"])
    assert [row["name"] for row in rows] == case["expected_names"]
    assert [len(row["links"]) for row in rows] == case["expected_link_counts"]


@pytest.mark.parametrize("case", GRID["covers_cases"], ids=lambda c: c["league"])
def test_covers(case):
    assert radio_links.covers(DATA, case["league"]) is case["expected"]


def test_competitors_from_a_real_scoreboard():
    board = json.loads((FIXTURES / "espn" / "scoreboard_NFL_202611.json").read_text(encoding="utf-8"))
    comp = board["events"][0]["competitions"][0]
    away_id, away_name, home_id, home_name = radio_links.competitors(comp)
    by_side = {c["homeAway"]: c["team"] for c in comp["competitors"]}
    assert (away_id, home_id) == (by_side["away"]["id"], by_side["home"]["id"])
    assert away_name == by_side["away"]["displayName"]
    assert home_name == by_side["home"]["displayName"]


@pytest.mark.parametrize("competition", [None, {}, {"competitors": None},
                                         {"competitors": ["junk", {"homeAway": "home"}]}])
def test_competitors_survive_bad_shapes(competition):
    assert radio_links.competitors(competition) == ("", "", "", "")


def test_bad_data_is_no_links():
    for data in ({}, {"tables": None}, {"tables": {"NFL": "junk"}}, {"tables": {"NFL": {"teams": []}}}):
        assert radio_links.game_options(data, "NFL", "9", "Packers", "3", "Bears") == []
        assert radio_links.directory(data, "NFL") == []


def test_unreadable_file_is_empty(tmp_path):
    assert radio_links.load(str(tmp_path / "missing.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert radio_links.load(str(bad)) == {}
