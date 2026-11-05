"""Bits of a game's details on Windows. Imports scores.py, so CI or the VM only."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt6")

import scores  # noqa: E402

PLAY = {"period": {"number": 1}, "team": {"displayName": "Bears"}, "clock": {"displayValue": "5:25"}, "text": "TD"}


def wrap_up_heading(league, number):
    play = dict(PLAY, period={"number": number})
    html = scores.GameDetailsView._format_scoring_plays_html(SimpleNamespace(league=league), [play])
    return html.split('<div class="quarter">')[1].split("</div>")[0]


@pytest.mark.parametrize("number,reads", [(1, "Quarter 1"), (4, "Quarter 4"), (5, "OT"), (6, "2OT")])
@pytest.mark.parametrize("league", ["NFL", "NCAAF"])
def test_football_scoring_plays_read_as_its_plays_do(league, number, reads):
    assert wrap_up_heading(league, number) == reads


def test_other_leagues_keep_what_they_had():
    assert wrap_up_heading("NHL", 2) == "Period 2"
