"""Pins play_geometry's output to a fixed grid of ESPN coordinates.

`tests/fixtures/play_geometry_grid.json` is the shared reference for the
Windows and iOS mappings: PlayAudioGeometry.swift is meant to give the same
note, length, balance and words for every case in it. The iOS project has no
test target yet, so only the Python side is checked automatically; check the
Swift side by hand against the same file when it changes.

A deliberate change to the mapping means regenerating the fixture from
`audio_params` and making the same change in Swift.
"""

import json
from pathlib import Path

import pytest

from play_geometry import audio_params

GRID = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "play_geometry_grid.json").read_text()
)["cases"]


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
