"""Bugs the replay tests found and the fixes made for them. The ones not fixed yet
are in test_known_gaps.py."""
from datetime import datetime

import espn_api

from .support import load


def test_golf_schedule_asks_for_the_year_not_a_range(espn, freeze_now):
    """Same 49 events either way when checked against ESPN; only the year is safe."""
    freeze_now(datetime(2026, 11, 3, 12))
    espn.on("/golf/pga/scoreboard", load("golf_schedule_PGA.json"))
    espn_api.get_golf_schedule("PGA")
    assert espn.calls == [f"{espn_api.BASE_URL}/golf/pga/scoreboard?dates=2026"]
