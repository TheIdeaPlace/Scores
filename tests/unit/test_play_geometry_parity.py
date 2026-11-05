"""Pins play_geometry's output to a fixed grid of ESPN coordinates.

`tests/fixtures/play_geometry_grid.json` is the shared reference for the
Windows and iOS mappings: PlayAudioGeometry.swift is meant to give the same
note, length, balance and words for every case in it. This holds the Python
side to it, and PlayAudioGeometryGridTests.swift holds the Swift side, in the
iOS Build Check workflow.

A deliberate change to the mapping means regenerating the fixture from
`audio_params` and making the same change in Swift.
"""

import json
from pathlib import Path

import pytest

from play_geometry import audio_params, has_coordinate, play_position

_FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "play_geometry_grid.json").read_text()
)
GRID = _FIXTURE["cases"]
LOCATED = _FIXTURE["located"]
FOULS = _FIXTURE["fouls"]


@pytest.mark.parametrize(
    "case", GRID, ids=[f"{c['league']}({c['x']},{c['y']})" for c in GRID]
)
def test_matches_the_shared_grid(case):
    frequency, duration_ms, balance, description = audio_params(
        case["league"], case["x"], case["y"]
    )
    assert frequency == case["frequency"]
    assert duration_ms == case["duration_ms"]
    assert balance == pytest.approx(case["balance"], abs=1e-6)
    assert description == case["description"]


@pytest.mark.parametrize(
    "case", LOCATED, ids=[f"{c['league']}({c['x']},{c['y']})" for c in LOCATED]
)
def test_agrees_on_which_plays_have_a_location(case):
    play = {"coordinate": {"x": case["x"], "y": case["y"]}}
    assert has_coordinate(play, case["league"]) is case["located"]


@pytest.mark.parametrize(
    "case", FOULS, ids=[f"{c['league']} {c['type']}({c['x']},{c['y']})" for c in FOULS]
)
def test_college_fouls_past_half_court_are_mirrored(case):
    play = {"type": {"text": case["type"]}, "coordinate": {"x": case["x"], "y": case["y"]}}
    assert play_position(play, case["league"]) == (case["to_x"], case["to_y"])


def test_a_foul_with_the_placeholder_still_has_no_location():
    play = {"type": {"text": "PersonalFoul"}, "coordinate": {"x": 25, "y": 0}}
    assert play_position(play, "NCAAM") is None


def test_a_play_with_no_type_keeps_its_place():
    assert play_position({"coordinate": {"x": 20, "y": 60}}, "NCAAM") == (20, 60)
    assert play_position({"type": None, "coordinate": {"x": 20, "y": 60}}, "NCAAM") == (20, 60)


def test_a_foul_under_the_basket_reads_and_sounds_that_way():
    """It read "deep, 78 feet out", and played a far away note on the wrong side."""
    play = {"type": {"text": "PersonalFoul"}, "coordinate": {"x": 24, "y": 81}}
    x, y = play_position(play, "NCAAWB")
    assert audio_params("NCAAWB", x, y)[3] == "at the rim"


@pytest.mark.parametrize("bad", ["PersonalFoul", 7, ["PersonalFoul"], True])
def test_a_type_that_isnt_a_dict_keeps_its_place(bad):
    assert play_position({"type": bad, "coordinate": {"x": 20, "y": 60}}, "NCAAM") == (20, 60)


@pytest.mark.parametrize("fixture", ["plays_NCAAM_401845838_3OT.json", "plays_NCAAWB_401911736.json"])
def test_no_real_college_foul_is_left_past_half_court(fixture):
    league = "NCAAM" if "NCAAM" in fixture else "NCAAWB"
    plays = json.loads((Path(__file__).parent.parent / "fixtures" / "espn" / fixture).read_text(encoding="utf-8"))["plays"]
    fouls = [p for p in plays if "foul" in p["type"]["text"].lower() and has_coordinate(p, league)]
    assert fouls and any(p["coordinate"]["y"] > 47 for p in fouls), "the fixture should show the problem"
    assert all(play_position(p, league)[1] <= 47 for p in fouls)
