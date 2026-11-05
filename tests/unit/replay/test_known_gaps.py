"""Real gaps left as they are because the fix is a decision, not a bug fix.

Each is written as the behaviour we'd want, marked xfail with strict=True, so the
day it's fixed this file fails and the marker comes off. Only a failed assertion or a
"did not raise" counts: a KeyError or a renamed function fails here instead of staying
a quiet xfail.
"""
from datetime import datetime

import pytest

import espn_api
import timezone_utils
from services.venue_service import VenueService
from text_utils import text_processor

from .support import HTTP_500, load


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason, raises=(AssertionError, pytest.fail.Exception))


@gap("The slow standings path gives a team whose record request failed 0-0, a record it "
     "doesn't have. Blank would be honest. This is every team if the failure is general.")
def test_a_failed_team_record_is_not_shown_as_0_0(espn):
    espn.on(r"/soccer/eng\.1/teams$", load("teams_EPL.json"))
    espn.on(r"/soccer/eng\.1/teams/\d+$", HTTP_500)
    assert all(row["wins"] != 0 or row["losses"] != 0 for row in espn_api.get_standings("EPL"))


@gap("An empty standings response for the NBA is taken to mean a new season and lists "
     "every team at 0-0. That's right in October, but it's invented if ESPN just sends "
     "nothing in March. The date could tell them apart.")
def test_an_empty_nba_standings_midseason_does_not_read_0_0(espn, freeze_now):
    freeze_now(datetime(2027, 3, 1))
    espn.on("/nba/standings", {}).on("/nba/teams$", load("teams_NBA.json"))
    assert espn_api.get_standings("NBA") == []


@gap("Only the time is converted, so a late game shown in another zone keeps the Eastern "
     "date: 12:30 AM EST on 11/2 is 9:30 PM on 11/1 in Los Angeles, but reads 11/2.")
def test_a_time_crossing_midnight_moves_the_date(monkeypatch):
    monkeypatch.setattr(timezone_utils, "_local_offset_and_dst", lambda: (-8, False))
    assert timezone_utils.convert_espn_time_to_local("11/2 - 12:30 AM EST").startswith("11/1 - ")


def test_a_venue_knows_its_home_team(espn):
    espn.on("/scoreboard", load("scoreboard_NWSL.json"))
    venues = VenueService().get_venues_for_league("nfl")
    assert any(venue["home_teams"] for venue in venues.values())


@pytest.mark.parametrize("league", ["ncaam", "ncaawb", "ncaah", "ncaawh"])
def test_every_league_with_venues_is_mapped(league):
    assert league in VenueService().leagues


@gap("The placeholder pattern for long ID numbers also matches real long numbers, so "
     'a story saying "100000 fans" comes out as "[Player Name] fans".')
def test_a_long_real_number_is_not_treated_as_a_placeholder():
    assert text_processor.clean_description("A crowd of 100000 fans") == "A crowd of 100000 fans"
