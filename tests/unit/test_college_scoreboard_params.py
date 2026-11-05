"""Tests for college scoreboard `groups=`/`limit=` params (espn_api).

ESPN silently drops most of a college slate when `groups=` is missing, and the
failure is invisible — a 200 response with a short list. These pin down which
leagues get the parameter, which must not, and the limit ceilings, since all of
that was established by measurement rather than documentation.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import espn_api  # noqa: E402


def params(league_key, coverage="all_d1"):
    with patch("settings.get", return_value=coverage):
        return espn_api.college_scoreboard_params(league_key)


@pytest.mark.parametrize("league_key", ["NFL", "NBA", "NHL", "MLB", "WNBA", "EPL", "PGA"])
def test_non_college_leagues_get_nothing(league_key):
    """NFL in particular returns *zero* games if sent groups=."""
    assert params(league_key) == []


@pytest.mark.parametrize("league_key", ["NCAAH", "NCAAWH"])
def test_college_hockey_gets_nothing(league_key):
    """groups= returns 0 games for college hockey; the plain call is already full."""
    assert params(league_key) == []


@pytest.mark.parametrize("league_key", ["NCAAM", "NCAAWB"])
def test_college_basketball_asks_for_division_one(league_key):
    assert params(league_key) == ["groups=50", "limit=400"]


def test_football_follows_the_coverage_setting():
    assert params("NCAAF", "all_d1") == ["groups=90", "limit=400"]
    assert params("NCAAF", "fbs") == ["groups=80", "limit=400"]


def test_football_falls_back_to_all_division_one_for_a_bad_setting():
    assert params("NCAAF", "nonsense") == ["groups=90", "limit=400"]


def test_football_limit_stays_within_espns_doubling_ceiling():
    """CFB doubles limit on undated queries and collapses to 25 past an
    effective 1000, so the sent value must stay at or below 500."""
    assert espn_api.NCAAF_SCOREBOARD_LIMIT <= 500
    assert espn_api.NCAAF_SCOREBOARD_LIMIT * 2 <= 1000
    # Still has to clear a full Division I week, which runs past 200 games.
    assert espn_api.NCAAF_SCOREBOARD_LIMIT > 220


def test_basketball_limit_clears_a_full_day():
    """Basketball honours limit exactly (no doubling); a big day is ~145 games."""
    assert espn_api.NCAAB_SCOREBOARD_LIMIT > 150


def test_old_helper_name_still_works():
    assert espn_api.ncaaf_scoreboard_params is espn_api.college_scoreboard_params
