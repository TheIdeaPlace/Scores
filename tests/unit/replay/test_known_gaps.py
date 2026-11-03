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

from .support import HTTP_500, TIMEOUT, load
from .test_failure_paths import QUIET


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason, raises=(AssertionError, pytest.fail.Exception))


FAILED_REQUEST_READS_AS_NOTHING = gap(
    'A failed request, or a body with a null where its list should be, returns the same '
    'empty result as "ESPN has nothing", so the screen says "No games found" or the like '
    "when it should say the request failed. The fix is to raise, and every caller's empty "
    "state needs checking.")


@FAILED_REQUEST_READS_AS_NOTHING
@pytest.mark.parametrize("call", [
    lambda: espn_api.get_scores("NBA"),
    lambda: espn_api.get_news("NFL"),
    lambda: espn_api.get_game_details("NFL", "1"),
    lambda: espn_api.get_standings("NFL"),
    lambda: espn_api.get_team_schedule("NFL", "9", season=2026),
], ids=["scores", "news", "details", "standings", "schedule"])
def test_a_server_error_is_told_apart_from_no_data(espn, call):
    espn.on(".*", HTTP_500)
    with pytest.raises(Exception):
        call()


@FAILED_REQUEST_READS_AS_NOTHING
@pytest.mark.parametrize("route,payload,call", [
    ("/scoreboard", {"events": None}, lambda: espn_api.get_scores("NBA")),
    ("/scoreboard", {"events": None}, lambda: espn_api.get_scores("NCAAF")),
    ("/news", {"articles": None}, lambda: espn_api.get_news("NFL")),
    ("/news", {"articles": None}, lambda: espn_api.get_team_news("NFL", "9")),
    ("/schedule", {"events": None}, lambda: espn_api.get_team_schedule("NFL", "9", season=2026)),
    ("/schedule", {"events": None}, lambda: espn_api.get_team_schedule("NBA", "15", season=2027)),
], ids=["scores", "scores_ncaaf_retry", "news", "team_news", "schedule_nfl", "schedule_nba"])
def test_a_null_list_is_told_apart_from_an_empty_one(espn, route, payload, call):
    espn.on(route, payload)
    with pytest.raises(Exception):
        call()


# get_mlb_wildcard_standings is left out: its {} reads as "unavailable", which is honest.
READ_AS_NOTHING = [pytest.param(call, id=name) for name, call, _ in QUIET if name != "get_mlb_wildcard_standings"]


@FAILED_REQUEST_READS_AS_NOTHING
@pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500], ids=["timeout", "500"])
@pytest.mark.parametrize("call", READ_AS_NOTHING)
def test_a_failure_elsewhere_is_told_apart_from_no_data(espn, call, reply):
    """These catch everything, so even a timeout reads as nothing to show. test_failure_paths
    pins what they do today, and changes with them."""
    espn.on(".*", reply)
    with pytest.raises(Exception):
        call()


@gap("get_team_schedule swallows a failed season type, so losing the regular season "
     "shows the preseason and playoffs as if they were the whole schedule.")
def test_a_failed_season_type_is_not_silently_left_out(espn):
    real = load("schedule_NBA_15.json")
    espn.on("/schedule", lambda url: HTTP_500 if "seasontype=2" in url else real)
    with pytest.raises(Exception):
        espn_api.get_team_schedule("NBA", "15", season=2027)


@gap("Every season type failing looks like an off-season, so a network problem shows "
     "last season's games as the schedule, with no sign anything went wrong.")
def test_failing_requests_do_not_show_last_season(espn, freeze_now):
    freeze_now(datetime(2026, 11, 3))
    real = load("schedule_NBA_15.json")
    espn.on("/schedule", lambda url: real if "season=2026" in url else HTTP_500)
    assert espn_api.get_team_schedule("NBA", "15") == []


@gap("A college football season you pick that comes back empty falls back to last "
     "calendar year's schedule, shown as if it were the season you asked for.")
def test_an_empty_ncaaf_season_does_not_become_another_season(espn, freeze_now):
    freeze_now(datetime(2026, 11, 3))
    real = load("schedule_NFL_9.json")
    espn.on("/schedule", lambda url: real if "season=2025" in url else {"events": []})
    assert espn_api.get_team_schedule("NCAAF", "9", season=2010) == []


@gap("get_available_seasons offers WNBA and soccer ten past seasons, but their schedule "
     "reads a window of months around today and ignores the season. schedule_WNBA_8.json "
     "shows ESPN has a schedule endpoint that would work.")
def test_a_past_wnba_season_asks_for_that_season(espn, freeze_now):
    freeze_now(datetime(2026, 11, 3))
    espn.on("/scoreboard", {"events": []}).on("/schedule", {"events": []})
    espn_api.get_team_schedule("WNBA", "8", season=2024)
    assert any("2024" in url for url in espn.calls), espn.calls


@gap("The slow standings path gives a team whose record request failed 0-0, a record it "
     "doesn't have. Blank would be honest. This is every team if the failure is general.")
def test_a_failed_team_record_is_not_shown_as_0_0(espn):
    espn.on("/wnba/teams$", load("teams_NBA.json"))
    espn.on(r"/wnba/teams/\d+$", HTTP_500)
    assert all(row["wins"] != 0 or row["losses"] != 0 for row in espn_api.get_standings("WNBA"))


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


@gap("_find_home_teams reads team.venue from /teams, and the real list has no venue on "
     "any team (teams_NFL.json), so a venue's home teams are always empty. The scoreboard "
     "that supplied the venue also names its home team.")
def test_a_venue_knows_its_home_team(espn):
    data = load("scoreboard_NWSL.json")
    espn.on("/scoreboard", data).on("/teams$", load("teams_NFL.json"))
    venues = VenueService().get_venues_for_league("nfl")
    assert any(venue["home_teams"] for venue in venues.values())


@gap("VenueService only knows nfl, nba, mlb, nhl and ncaaf among the league keys scores.py "
     "sends, so college basketball and the rest always read \"No venue data available\".")
@pytest.mark.parametrize("league", ["ncaam", "ncaawb", "wnba", "ncaah"])
def test_every_league_with_venues_is_mapped(league):
    assert league in VenueService().leagues


@gap("The placeholder pattern for long ID numbers also matches real long numbers, so "
     'a story saying "100000 fans" comes out as "[Player Name] fans".')
def test_a_long_real_number_is_not_treated_as_a_placeholder():
    assert text_processor.clean_description("A crowd of 100000 fans") == "A crowd of 100000 fans"
