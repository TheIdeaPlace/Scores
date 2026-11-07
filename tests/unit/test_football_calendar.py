"""Tests for football week resolution (services/football_calendar.py).

The scoreboard calendar is faked rather than fetched. These cover the places
where a wrong answer shows the user the wrong games entirely: the week-end
boundary, resolving today's week during preseason, and stepping across a
season-type boundary.
"""

import json
import os
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services import football_calendar as fc  # noqa: E402


def entry(label, value, start, end):
    return {"label": label, "value": str(value), "startDate": start, "endDate": end}


# A trimmed 2026 NFL calendar in ESPN's exact shape, including the Pacific-midnight
# bounds (T07:00Z start, T06:59Z end) that the date maths has to account for.
NFL_CALENDAR = [
    {"label": "Preseason", "value": "1", "entries": [
        entry("Hall of Fame Weekend", 1, "2026-08-06T07:00Z", "2026-08-13T06:59Z"),
        entry("Preseason Week 1", 2, "2026-08-13T07:00Z", "2026-08-20T06:59Z"),
        entry("Preseason Week 2", 3, "2026-08-20T07:00Z", "2026-08-27T06:59Z"),
        entry("Preseason Week 3", 4, "2026-08-27T07:00Z", "2026-09-09T06:59Z"),
    ]},
    {"label": "Regular Season", "value": "2", "entries": [
        entry("Week 1", 1, "2026-09-09T07:00Z", "2026-09-16T06:59Z"),
        entry("Week 2", 2, "2026-09-16T07:00Z", "2026-09-23T06:59Z"),
    ]},
    {"label": "Postseason", "value": "3", "entries": [
        entry("Wild Card", 1, "2027-01-13T08:00Z", "2027-01-20T07:59Z"),
    ]},
    # Carries no games; must never appear in navigation.
    {"label": "Off Season", "value": "4", "entries": [
        entry("All-Star", 1, "2027-01-28T08:00Z", "2027-02-01T07:59Z"),
    ]},
]


CACHES = ("_SEASON_WEEKS_CACHE", "_WEEK_DATE_CACHE", "_SERVED_SEASON",
          "_CORE_SEASON_CACHE", "_CORE_WEEK_TEXT_CACHE")


@pytest.fixture(autouse=True)
def clear_caches():
    for name in CACHES:
        getattr(fc, name).clear()
    yield
    for name in CACHES:
        getattr(fc, name).clear()


def calendar_payload(season_year=2026):
    return {"leagues": [{"season": {"year": season_year}, "calendar": NFL_CALENDAR}]}


@pytest.fixture
def nfl_calendar():
    """ESPN serving its 2026 calendar, whatever season is asked for.

    That is the real behaviour: the scoreboard ignores `season=` and always
    answers with the season it considers current.
    """
    with patch.object(fc, "requests") as fake_requests:
        fake_requests.get.return_value.status_code = 200
        fake_requests.get.return_value.json.return_value = calendar_payload(2026)
        yield fake_requests


@pytest.fixture
def calendar_loaded(nfl_calendar):
    """The calendar as the loader thread leaves it: fetched and cached. The label
    and the week arrows read only the cache, since the UI thread calls them."""
    fc.prepare_week("NFL", 2026, 2, 1)
    return nfl_calendar


class TestBoundDates:
    def test_end_bound_is_the_last_day_the_week_covers(self):
        # ESPN's T06:59Z end is 23:59 Pacific the day before. Reading the UTC date
        # would give Aug 20 and pull the next week's Thursday games into this one.
        start, end = fc._bound_dates("2026-08-13T07:00Z", "2026-08-20T06:59Z")
        assert start == date(2026, 8, 13)
        assert end == date(2026, 8, 19)

    def test_holds_across_daylight_saving(self):
        # In Pacific standard time the offset moves to 08:00Z / 07:59Z.
        start, end = fc._bound_dates("2027-01-13T08:00Z", "2027-01-20T07:59Z")
        assert start == date(2027, 1, 13)
        assert end == date(2027, 1, 19)

    def test_single_day_week_does_not_invert(self):
        start, end = fc._bound_dates("2026-08-06T07:00Z", "2026-08-06T06:59Z")
        assert start == end == date(2026, 8, 6)


class TestSeasonWeeks:
    def test_orders_preseason_before_regular_before_post(self, nfl_calendar):
        weeks = fc.get_season_weeks("NFL", 2026)
        assert [(w["season_type"], w["week"]) for w in weeks] == [
            (1, 1), (1, 2), (1, 3), (1, 4), (2, 1), (2, 2), (3, 1)]

    def test_keeps_espn_labels(self, nfl_calendar):
        labels = [w["label"] for w in fc.get_season_weeks("NFL", 2026)]
        assert labels[:2] == ["Hall of Fame Weekend", "Preseason Week 1"]
        assert "Wild Card" in labels

    def test_off_season_is_not_navigable(self, nfl_calendar):
        assert all(w["season_type"] != 4 for w in fc.get_season_weeks("NFL", 2026))

    def test_seeds_the_week_date_cache(self, nfl_calendar):
        fc.get_season_weeks("NFL", 2026)
        # Preseason Week 1 is week 2 of season type 1.
        assert fc._WEEK_DATE_CACHE[("NFL", 2026, 1, 2)] == ("20260813", "20260819")

    def test_is_cached_so_navigation_makes_one_request(self, nfl_calendar):
        fc.get_season_weeks("NFL", 2026)
        fc.get_season_weeks("NFL", 2026)
        assert nfl_calendar.get.call_count == 1

    def test_unknown_league_returns_empty(self):
        assert fc.get_season_weeks("MLB", 2026) == []

    def test_a_season_espn_does_not_serve_returns_empty(self, nfl_calendar):
        # ESPN ignores season= and answers with 2026 regardless. Handing those
        # weeks back as if they were 2025's would mean showing 2026 dates for a
        # 2025 week; callers must fall through to the season-aware Core API.
        assert fc.get_season_weeks("NFL", 2025) == []

    def test_the_season_espn_did_serve_is_cached_under_its_real_year(self, nfl_calendar):
        fc.get_season_weeks("NFL", 2025)          # asked 2025, got 2026
        assert nfl_calendar.get.call_count == 1
        assert len(fc.get_season_weeks("NFL", 2026)) == 7   # served from cache
        assert nfl_calendar.get.call_count == 1

    def test_week_bounds_are_seeded_under_the_real_year_only(self, nfl_calendar):
        fc.get_season_weeks("NFL", 2025)
        assert ("NFL", 2026, 1, 2) in fc._WEEK_DATE_CACHE
        assert ("NFL", 2025, 1, 2) not in fc._WEEK_DATE_CACHE


class TestCurrentSeasonWeekAndType:
    def test_takes_the_season_from_espn_not_the_calendar_year(self, nfl_calendar):
        # get_football_season_year rolls over on 1 March, but ESPN keeps serving
        # the previous season until about late July. Trusting the heuristic in
        # that window puts every date past the end of the season, landing the
        # view on the last Super Bowl.
        season, season_type, week = fc.get_current_season_week_and_type(
            "NFL", today=date(2027, 4, 1))
        assert season == 2026
        assert (season_type, week) == (3, 1)   # the last week ESPN knows about

    def test_resolves_the_live_preseason_week(self, nfl_calendar):
        assert fc.get_current_season_week_and_type("NFL", today=date(2026, 8, 15)) == (2026, 1, 2)

    def test_falls_back_when_the_calendar_is_unavailable(self):
        with patch.object(fc, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 503
            season, season_type, week = fc.get_current_season_week_and_type(
                "NFL", today=date(2026, 8, 15))
        assert (season_type, week) == (2, 1)
        assert season == 2026   # falls back to the calendar-year heuristic


class TestCurrentWeek:
    def test_preseason_date_resolves_to_a_preseason_week(self, nfl_calendar):
        # The bug this fixes: ESPN's week.number is 1 here, which read as the
        # regular season opener a month away.
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 8, 9)) == (1, 1)
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 8, 15)) == (1, 2)

    def test_regular_season_date(self, nfl_calendar):
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 9, 12)) == (2, 1)

    def test_last_day_of_a_week_still_belongs_to_it(self, nfl_calendar):
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 8, 19)) == (1, 2)
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 8, 20)) == (1, 3)

    def test_before_the_season_picks_the_first_week(self, nfl_calendar):
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 5, 1)) == (1, 1)

    def test_after_the_season_picks_the_last_week(self, nfl_calendar):
        assert fc.get_current_week_and_type("NFL", 2026, today=date(2027, 6, 1)) == (3, 1)

    def test_falls_back_to_regular_week_one_without_a_calendar(self):
        with patch.object(fc, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 503
            assert fc.get_current_week_and_type("NFL", 2026, today=date(2026, 8, 9)) == (2, 1)

    def test_bare_week_number_helper_agrees(self, nfl_calendar):
        assert fc.get_current_football_week("NFL", 2026, today=date(2026, 8, 15)) == 2
        assert fc.get_current_football_week("MLB", 2026) is None


class TestStepWeek:
    def test_forward_within_a_season_type(self, calendar_loaded):
        assert fc.step_week("NFL", 2026, 1, 1, +1) == (1, 2)

    def test_forward_rolls_into_the_regular_season(self, calendar_loaded):
        assert fc.step_week("NFL", 2026, 1, 4, +1) == (2, 1)

    def test_back_rolls_into_the_preseason(self, calendar_loaded):
        # Without this there is no route to preseason at all once the regular
        # season is the default view.
        assert fc.step_week("NFL", 2026, 2, 1, -1) == (1, 4)

    def test_stops_at_the_first_week(self, calendar_loaded):
        assert fc.step_week("NFL", 2026, 1, 1, -1) == (1, 1)

    def test_stops_at_the_last_week(self, calendar_loaded):
        assert fc.step_week("NFL", 2026, 3, 1, +1) == (3, 1)

    def test_unknown_week_is_left_alone(self, calendar_loaded):
        assert fc.step_week("NFL", 2026, 2, 99, +1) == (2, 99)


class TestWeekLabel:
    def test_preseason_labels_are_not_bare_week_numbers(self, calendar_loaded):
        assert fc.get_week_label("NFL", 2026, 1, 1) == "Hall of Fame Weekend"
        assert fc.get_week_label("NFL", 2026, 1, 2) == "Preseason Week 1"

    def test_regular_and_post_labels(self, calendar_loaded):
        assert fc.get_week_label("NFL", 2026, 2, 1) == "Week 1"
        assert fc.get_week_label("NFL", 2026, 3, 1) == "Wild Card"

    def test_unknown_week_falls_back(self, calendar_loaded):
        assert fc.get_week_label("NFL", 2026, 2, 99) == "Week 99"


class TestWeekDates:
    def test_uses_the_calendar_without_a_core_api_call(self, nfl_calendar):
        assert fc.get_week_dates("NFL", 2, 2026, season_type=1) == ("20260813", "20260819")
        assert nfl_calendar.get.call_count == 1  # the calendar only

    def test_season_type_selects_between_same_numbered_weeks(self, nfl_calendar):
        preseason = fc.get_week_dates("NFL", 1, 2026, season_type=1)
        regular = fc.get_week_dates("NFL", 1, 2026, season_type=2)
        assert preseason != regular
        assert preseason[0].startswith("202608")
        assert regular[0].startswith("202609")

    def test_a_past_season_is_not_answered_from_the_live_calendar(self, nfl_calendar):
        # The calendar only ever describes the current season, so a 2025 week must
        # reach the Core API rather than being handed 2026 dates. Here the Core
        # API call also fails, and (None, None) is the honest answer.
        assert fc.get_week_dates("NFL", 1, 2025, season_type=2) == (None, None)

    def test_failures_are_not_cached(self):
        # A single timeout must not degrade a week for the rest of the session.
        with patch.object(fc, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 503
            assert fc.get_week_dates("NFL", 1, 2026, season_type=2) == (None, None)
            assert ("NFL", 2026, 2, 1) not in fc._WEEK_DATE_CACHE


# --- A past season: the Core API, as the iPhone reads it (#192) -------------------

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "espn")


def core_fixture(key):
    """Real Core API answers for the 2024 season, keyed by the path after the league."""
    with open(os.path.join(FIXTURES, f"core_weeks_{key}_2024.json"), encoding="utf-8") as f:
        return json.load(f)


class FakeEspn:
    """The scoreboard serving its 2026 calendar, and the Core API answering from the
    saved 2024 responses. `fail` maps a URL fragment to a status code or exception."""

    def __init__(self, calendar=True):
        self.core = {"nfl": core_fixture("NFL"), "college-football": core_fixture("NCAAF")}
        self.calendar = calendar
        self.fail = {}
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        for fragment, failure in self.fail.items():
            if fragment in url:
                if isinstance(failure, Exception):
                    raise failure
                return SimpleNamespace(status_code=failure, json=lambda: {})
        if "/scoreboard" in url:
            if not self.calendar:
                return SimpleNamespace(status_code=503, json=lambda: {})
            return SimpleNamespace(status_code=200, json=lambda: calendar_payload(2026))
        league, path = url.split("/football/leagues/")[1].split("?")[0].split("/", 1)
        answer = self.core[league].get(path)
        if answer is None:
            return SimpleNamespace(status_code=404, json=lambda: {"error": {"code": 404}})
        return SimpleNamespace(status_code=200, json=lambda: answer)

    def core_urls(self):
        return [u for u in self.urls if "sports.core.api" in u]


@pytest.fixture
def espn():
    fake = FakeEspn()
    with patch.object(fc.requests, "get", fake.get):
        yield fake


def visit(league, season, season_type, week):
    """What the loader does for a week, then what the UI thread shows for it."""
    fc.prepare_week(league, season, season_type, week)
    return fc.get_week_label(league, season, season_type, week)


class TestPastSeasonWeekNames:
    def test_the_nfl_postseason_has_its_names(self, espn):
        names = [visit("NFL", 2024, 3, week) for week in range(1, 6)]
        assert names == ["Wild Card", "Divisional Round", "Conference Championship",
                         "Pro Bowl", "Super Bowl"]

    def test_the_nfl_preseason_is_told_apart_from_the_regular_season(self, espn):
        assert visit("NFL", 2024, 1, 1) == "Hall of Fame Weekend"
        assert visit("NFL", 2024, 1, 2) == "Preseason Week 1"
        assert visit("NFL", 2024, 2, 1) == "Week 1"

    def test_college_bowls(self, espn):
        assert visit("NCAAF", 2024, 3, 1) == "Bowls"
        assert visit("NCAAF", 2024, 2, 16) == "Week 16"

    def test_every_saved_week_reads_as_espn_s_text(self, espn):
        """The whole rule, on every real week: the label is ESPN's `text`."""
        for key, league in (("NFL", "nfl"), ("NCAAF", "college-football")):
            for path, answer in core_fixture(key).items():
                if path.endswith("/weeks"):
                    continue
                _, _, _, season_type, _, week = path.split("/")
                assert visit(key, 2024, int(season_type), int(week)) == answer["text"], path

    def test_the_current_season_keeps_the_scoreboard_calendar(self, espn):
        assert visit("NFL", 2026, 3, 1) == "Wild Card"
        assert espn.core_urls() == []

    def test_a_season_is_listed_once_and_a_week_named_once(self, espn):
        visit("NFL", 2024, 3, 1)
        visit("NFL", 2024, 3, 1)
        visit("NFL", 2024, 3, 2)
        lists = [u for u in espn.core_urls() if u.endswith("/weeks?limit=100")]
        weeks = [u for u in espn.core_urls() if "/weeks/" in u]
        assert len(lists) == 3      # preseason, regular season, postseason
        assert len(weeks) == 2      # week 1 once, week 2 once
        # The scoreboard was asked once, and then known not to describe 2024.
        assert len([u for u in espn.urls if "/scoreboard" in u]) == 1

    def test_without_the_calendar_the_core_api_still_names_the_week(self):
        """If the scoreboard fails, the week shown is named from the Core API
        rather than left as a number."""
        fake = FakeEspn(calendar=False)
        with patch.object(fc.requests, "get", fake.get):
            assert visit("NFL", 2024, 3, 5) == "Super Bowl"

    def test_the_dates_come_with_the_name(self, espn):
        visit("NFL", 2024, 3, 5)
        # 2025-02-06T08:00Z to 2025-02-14T07:59Z: the end is Pacific midnight.
        assert fc._WEEK_DATE_CACHE[("NFL", 2024, 3, 5)] == ("20250206", "20250213")

    def test_week_dates_for_a_past_season_cache_the_name_too(self, espn):
        assert fc.get_week_dates("NFL", 1, 2024, season_type=3) == ("20250108", "20250115")
        assert fc.get_week_label("NFL", 2024, 3, 1) == "Wild Card"


class TestPastSeasonWeekNameFailures:
    """The iPhone falls back to "Week N" without a word when the Core API fails, and
    so does Windows: the games come from their own request, which says if it fails."""

    @pytest.mark.parametrize("failure", [500, 404, TimeoutError("timed out")])
    def test_a_failed_name_is_week_n_and_is_asked_again(self, espn, failure):
        espn.fail["/types/3/weeks/1"] = failure
        assert visit("NFL", 2024, 3, 1) == "Week 1"
        assert ("NFL", 2024, 3, 1) not in fc._CORE_WEEK_TEXT_CACHE
        del espn.fail["/types/3/weeks/1"]
        assert visit("NFL", 2024, 3, 1) == "Wild Card"

    def test_a_week_with_no_text_is_week_n(self, espn):
        espn.core["nfl"]["seasons/2024/types/3/weeks/1"] = {"number": 1, "text": "  "}
        assert visit("NFL", 2024, 3, 1) == "Week 1"

    def test_an_answer_that_is_not_an_object_is_week_n(self, espn):
        espn.core["nfl"]["seasons/2024/types/3/weeks/1"] = ["not", "a", "week"]
        assert visit("NFL", 2024, 3, 1) == "Week 1"

    def test_a_failed_season_list_is_not_cached(self, espn):
        espn.fail["/types/2/weeks?limit=100"] = 503
        fc.prepare_week("NFL", 2024, 1, 4)
        assert ("NFL", 2024) not in fc._CORE_SEASON_CACHE
        del espn.fail["/types/2/weeks?limit=100"]
        fc.prepare_week("NFL", 2024, 1, 4)
        assert fc.step_week("NFL", 2024, 1, 4, +1) == (2, 1)

    def test_prepare_week_never_raises(self, espn):
        espn.fail["/scoreboard"] = RuntimeError("boom")
        espn.fail["sports.core.api"] = RuntimeError("boom")
        fc.prepare_week("NFL", 2024, 3, 1)
        assert fc.get_week_label("NFL", 2024, 3, 1) == "Week 1"

    def test_other_leagues_and_missing_weeks_ask_nothing(self, espn):
        fc.prepare_week("NBA", 2024, 2, 1)
        fc.prepare_week("NFL", 2024, 2, None)
        fc.prepare_week("NFL", None, 2, 1)
        assert espn.urls == []


class TestPastSeasonStepping:
    """Stepping through a past season crosses preseason, regular season and
    postseason as the current season's calendar does."""

    @pytest.fixture(autouse=True)
    def loaded(self, espn):
        fc.prepare_week("NFL", 2024, 2, 1)
        fc.prepare_week("NCAAF", 2024, 2, 1)

    def test_preseason_into_the_regular_season(self):
        assert fc.step_week("NFL", 2024, 1, 4, +1) == (2, 1)
        assert fc.step_week("NFL", 2024, 2, 1, -1) == (1, 4)

    def test_regular_season_into_the_postseason(self):
        assert fc.step_week("NFL", 2024, 2, 18, +1) == (3, 1)
        assert fc.step_week("NFL", 2024, 3, 1, -1) == (2, 18)

    def test_through_the_playoffs_to_the_super_bowl_and_no_further(self):
        assert fc.step_week("NFL", 2024, 3, 4, +1) == (3, 5)
        assert fc.step_week("NFL", 2024, 3, 5, +1) == (3, 5)
        assert fc.step_week("NFL", 2024, 1, 1, -1) == (1, 1)

    def test_college_into_the_bowls(self):
        assert fc.step_week("NCAAF", 2024, 2, 16, +1) == (3, 1)
        assert fc.step_week("NCAAF", 2024, 3, 1, +1) == (3, 1)
        assert fc.step_week("NCAAF", 2024, 1, 1, +1) == (2, 1)

    def test_the_names_along_the_way(self, espn):
        season_type, week, heard = 2, 18, []
        for _ in range(3):
            season_type, week = fc.step_week("NFL", 2024, season_type, week, +1)
            heard.append(visit("NFL", 2024, season_type, week))
        assert heard == ["Wild Card", "Divisional Round", "Conference Championship"]


class TestNoNetworkOnTheUiThread:
    def test_label_and_step_only_read_the_cache(self):
        with patch.object(fc.requests, "get", side_effect=AssertionError("network")):
            assert fc.get_week_label("NFL", 2024, 3, 1) == "Week 1"
            assert fc.step_week("NFL", 2024, 2, 18, +1) == (2, 19)
            assert fc.get_week_label("NFL", 2026, 3, 1) == "Week 1"
            assert fc.step_week("NFL", 2026, 2, 1, -1) == (2, 1)


class TestCoreTypeWeeks:
    def test_week_numbers_come_from_the_references(self):
        answer = {"count": 2, "items": [{"$ref": ".../types/3/weeks/1?lang=en"},
                                        {"$ref": ".../types/3/weeks/999?lang=en"}]}
        with patch.object(fc.requests, "get",
                          return_value=SimpleNamespace(status_code=200, json=lambda: answer)):
            assert fc._core_type_weeks("NCAAF", 2024, 3) == [1, 999]

    def test_without_references_the_count_numbers_them_from_one(self):
        answer = {"count": 3, "items": [{}]}
        with patch.object(fc.requests, "get",
                          return_value=SimpleNamespace(status_code=200, json=lambda: answer)):
            assert fc._core_type_weeks("NFL", 2024, 1) == [1, 2, 3]
