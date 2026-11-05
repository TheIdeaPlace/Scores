"""Every public data function against a timeout, a 404, a 500, an empty body and a
body that isn't JSON. Nothing is invented from any of them, and only the functions
whose caller reports the failure let an exception out.
"""
from datetime import date

import pytest
import requests

import espn_api
from exceptions import ApiError
from services.api_service import ApiService

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, FakeResponse

DAY = date(2026, 6, 20)

# name, call, what it returns when a request fails or has nothing in it. This is what
# they do today, not what they should: all but the wild card read as "nothing to show"
# when the request failed, which test_known_gaps.py records.
QUIET = [
    ("get_rankings", lambda: espn_api.get_rankings("NCAAF"), {"polls": []}),
    ("get_team_info", lambda: espn_api.get_team_info("NFL", "9"), {}),
    ("get_team_roster", lambda: espn_api.get_team_roster("NFL", "9"), []),
    ("get_team_news", lambda: espn_api.get_team_news("NFL", "9"), []),
    ("get_transactions", lambda: espn_api.get_transactions("NFL"), ([], False)),
    ("get_team_transactions", lambda: espn_api.get_team_transactions("NFL", "9"), []),
    ("get_draft_round", lambda: espn_api.get_draft_round(2026, 1), []),
    ("get_golf_leaderboard", lambda: espn_api.get_golf_leaderboard("PGA"), None),
    ("get_golf_schedule", lambda: espn_api.get_golf_schedule("PGA"), []),
    ("get_world_cup_standings", lambda: espn_api.get_world_cup_standings("WC2026"), []),
    ("get_mlb_wildcard_standings", espn_api.get_mlb_wildcard_standings, {}),
]


def quiet_cases(replies):
    return [pytest.param(call, expected, reply, id=f"{name}-{reply_name}")
            for name, call, expected in QUIET for reply_name, reply in replies]


FAILED_REQUESTS = [("timeout", TIMEOUT), ("connection", requests.ConnectionError("refused")),
                   ("404", HTTP_404), ("500", HTTP_500), ("not_json", NOT_JSON)]


@pytest.mark.parametrize("call,expected,reply", quiet_cases(FAILED_REQUESTS))
def test_a_failed_request_returns_the_empty_shape(espn, call, expected, reply):
    espn.on(".*", reply)
    assert call() == expected


@pytest.mark.parametrize("call,expected,reply", quiet_cases([("empty", EMPTY_JSON)]))
def test_an_empty_body_returns_the_empty_shape(espn, call, expected, reply):
    espn.on(".*", reply)
    # get_draft and friends get their own test; these have nothing to show at all.
    assert call() == expected


@pytest.mark.parametrize("league,team,season", [
    ("NFL", "9", 2026), ("NCAAF", "333", 2026), ("NBA", "15", 2027), ("NHL", "1", 2027), ("MLB", "10", 2026),
    ("WNBA", "8", 2026), ("NCAAM", "275", 2027), ("NCAAWB", "275", 2027), ("NCAAH", "1", 2027), ("NCAAWH", "1", 2027),
    ("EPL", "359", 2026),
])
class TestScheduleFailures:
    """A schedule with a part missing looks complete, and one with everything missing looks
    like an off-season, so a failure reaches the dialog. ESPN saying it has nothing doesn't."""

    @pytest.mark.parametrize("reply", [HTTP_500, FakeResponse({}, status=503), FakeResponse({}, status=403),
                                       FakeResponse({}, status=429), NOT_JSON],
                             ids=["500", "503", "403", "429", "not_json"])
    def test_a_failure_comes_out_and_the_service_wraps_it(self, espn, league, team, season, reply):
        espn.on(".*", reply)
        with pytest.raises(Exception):
            espn_api.get_team_schedule(league, team, season=season)
        with pytest.raises(ApiError):
            ApiService.get_team_schedule(league, team, season=season)

    @pytest.mark.parametrize("reply", [HTTP_404, FakeResponse({}, status=400), EMPTY_JSON], ids=["404", "400", "empty"])
    def test_nothing_there_is_empty(self, espn, league, team, season, reply):
        espn.on(".*", reply)
        assert espn_api.get_team_schedule(league, team, season=season) == []


class TestGetDraft:
    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_404, HTTP_500, NOT_JSON])
    def test_failure_is_none(self, espn, reply):
        espn.on(".*", reply)
        assert espn_api.get_draft(2026) is None

    def test_an_empty_body_is_no_draft(self, espn):
        """Not a finished seven-round one. The dialog says the year isn't available."""
        espn.on(".*", EMPTY_JSON)
        assert espn_api.get_draft(2026) is None
        assert len(espn.calls) == 1


# These let a failed request out on purpose. Each caller runs on a loader thread and
# shows the error, which is better than "no games". The tests pin the contract, and
# ApiService's wrapping of it, so one can't quietly start reading as no data.
RAISING = [
    ("get_scores", lambda: espn_api.get_scores("NBA"), lambda: ApiService.get_scores("NBA")),
    ("get_news", lambda: espn_api.get_news("NFL"), lambda: ApiService.get_news("NFL")),
    ("get_game_details", lambda: espn_api.get_game_details("NFL", "1"), lambda: ApiService.get_game_details("NFL", "1")),
    ("get_team_schedule NFL", lambda: espn_api.get_team_schedule("NFL", "9"), lambda: ApiService.get_team_schedule("NFL", "9")),
    ("get_team_schedule NCAAF", lambda: espn_api.get_team_schedule("NCAAF", "333"), lambda: ApiService.get_team_schedule("NCAAF", "333")),
    ("get_team_schedule EPL", lambda: espn_api.get_team_schedule("EPL", "359"), lambda: ApiService.get_team_schedule("EPL", "359")),
    ("get_team_schedule NBA", lambda: espn_api.get_team_schedule("NBA", "15"), lambda: ApiService.get_team_schedule("NBA", "15")),
    ("get_team_schedule WNBA", lambda: espn_api.get_team_schedule("WNBA", "8"), lambda: ApiService.get_team_schedule("WNBA", "8")),
    ("get_standings NFL", lambda: espn_api.get_standings("NFL"), lambda: ApiService.get_standings("NFL")),
]


@pytest.mark.parametrize("direct,through_service", [pytest.param(d, s, id=n) for n, d, s in RAISING])
class TestTimeoutsReachTheCaller:
    def test_the_timeout_comes_out(self, espn, direct, through_service):
        espn.on(".*", TIMEOUT)
        with pytest.raises(requests.Timeout):
            direct()

    def test_the_service_wraps_it_as_an_api_error(self, espn, direct, through_service):
        espn.on(".*", TIMEOUT)
        with pytest.raises(ApiError, match="read timed out"):
            through_service()


@pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON],
                         ids=["timeout", "connection", "404", "500", "not_json"])
def test_standings_with_no_fallback_say_a_failed_request_failed(espn, reply):
    """Not as no data, and not with the text of a requests exception, through the service too."""
    espn.on(".*", reply)
    with pytest.raises(ApiError, match="Try again"):
        espn_api.get_standings("NCAAM")
    with pytest.raises(ApiError, match="Try again"):
        ApiService.get_standings("NCAAM")


@pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON, EMPTY_JSON],
                         ids=["timeout", "connection", "404", "500", "not_json", "empty"])
def test_statistics_say_a_failed_request_failed(espn, reply, monkeypatch):
    """The Statistics dialog has a row for it, which says to try again."""
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)
    espn.on(".*", reply)
    for name in ("get_player_statistics", "get_team_statistics"):
        with pytest.raises(ApiError, match="Try again"):
            getattr(espn_api, name)("NBA")
        with pytest.raises(ApiError, match="Try again"):
            getattr(ApiService, name)("NBA")


@pytest.mark.parametrize("call,expected", [
    (lambda: espn_api.get_scores("NBA"), []),
    (lambda: espn_api.get_news("NFL"), []),
    (lambda: espn_api.get_game_details("NFL", "1"), {}),
    (lambda: espn_api.get_standings("NFL"), []),
    (lambda: espn_api.get_standings("MLB"), []),
    (lambda: espn_api.get_standings("NHL"), []),
    (lambda: espn_api.get_standings("NBA"), []),
    (lambda: espn_api.get_live_golf_tournament("PGA"), None),
], ids=["scores", "news", "details", "nfl", "mlb", "nhl", "nba", "live_golf"])
class TestHttpErrorsOnTheOthers:
    @pytest.mark.parametrize("reply", [HTTP_404, HTTP_500], ids=["404", "500"])
    def test_are_empty(self, espn, call, expected, reply):
        espn.on(".*", reply)
        assert call() == expected


@pytest.mark.parametrize("call,expected", [
    (lambda: espn_api.get_scores("NBA"), []),
    (lambda: espn_api.get_news("NFL"), []),
    (lambda: espn_api.get_game_details("NFL", "1"), {}),
    (lambda: espn_api.extract_meaningful_game_info({}), {}),
    (lambda: espn_api.get_standings("NFL"), []),
    (lambda: espn_api.get_standings("MLB"), []),
    (lambda: espn_api.get_standings("NHL"), []),
    (lambda: espn_api.get_live_golf_tournament("PGA"), None),
], ids=["scores", "news", "details", "extract", "nfl", "mlb", "nhl", "live_golf"])
def test_an_empty_body_on_the_others_is_empty(espn, call, expected):
    espn.on(".*", EMPTY_JSON)
    assert call() == expected


def test_a_live_golf_timeout_reaches_the_live_scores_view_which_handles_it(espn):
    espn.on(".*", TIMEOUT)
    with pytest.raises(requests.Timeout):
        espn_api.get_live_golf_tournament("PGA")


def test_world_cup_scores_keep_going_past_a_failed_day(espn):
    espn.on(".*", TIMEOUT)
    assert espn_api.get_world_cup_scores_range("WC2026", DAY, DAY) == []
    assert len(espn.calls) == 1


def test_every_espn_request_has_a_timeout(monkeypatch):
    """One stalled response without one would block its caller forever."""
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse({})

    monkeypatch.setattr(requests, "get", fake_get)
    espn_api._http_get("https://example.invalid/")
    assert seen["timeout"] == espn_api.DEFAULT_TIMEOUT
    espn_api._http_get("https://example.invalid/", timeout=90)
    assert seen["timeout"] == 90


def test_the_guard_stops_a_real_request():
    """The harness itself: without a stub, a request fails rather than reaching ESPN."""
    with pytest.raises(AssertionError, match="reached the network"):
        requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", timeout=1)


def test_the_harness_records_an_unstubbed_url(espn):
    from .support import UnstubbedRequest
    with pytest.raises(UnstubbedRequest):
        espn_api._http_get("https://example.invalid/never-stubbed")
    assert espn.unstubbed == ["https://example.invalid/never-stubbed"]
    espn.unstubbed.clear()  # expected here; the fixture fails the test otherwise
