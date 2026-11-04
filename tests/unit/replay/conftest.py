"""Fixtures for the replay tests. Pure: no Qt, no network, no real settings file."""
import datetime as datetime_module

import pytest
import requests

import espn_api
import game_labels
import settings
from services import football_calendar, venue_service

from .support import DATE_RANGE, FakeEspn


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real sockets, no real %APPDATA% settings, no caches carried between tests."""

    def blocked(self, request, **kwargs):
        raise AssertionError(f"A replay test reached the network: {request.url}")

    monkeypatch.setattr(requests.sessions.Session, "send", blocked)
    monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
    monkeypatch.setattr(settings, "_cache", None)
    monkeypatch.setattr(espn_api, "_DRAFT_CACHE", {})
    monkeypatch.setattr(espn_api, "_CORE_SEASON_CACHE", {})
    monkeypatch.setattr(football_calendar, "_WEEK_DATE_CACHE", {})
    monkeypatch.setattr(football_calendar, "_SEASON_WEEKS_CACHE", {})


@pytest.fixture
def espn(monkeypatch):
    """The stubbed ESPN. Fails the test if any URL went unanswered or used a date range."""
    fake = FakeEspn()
    monkeypatch.setattr(espn_api, "_http_get", fake)
    # venue_service, football_calendar and updater call requests.get themselves.
    monkeypatch.setattr(requests, "get", fake)
    yield fake
    assert not fake.unstubbed, f"Requests no route answered: {fake.unstubbed}"
    ranges = [url for url in fake.calls if DATE_RANGE.search(url)]
    assert not ranges, f"ESPN rejects dates=A-B ranges: {ranges}"


@pytest.fixture
def local_zone(monkeypatch):
    """Make `.astimezone()` with no argument use a fixed UTC offset, so an expected
    local date doesn't depend on the machine: CI runs in UTC, Kelly in US Central."""

    def set_offset(hours):
        zone = datetime_module.timezone(datetime_module.timedelta(hours=hours))

        class InZone(datetime_module.datetime):
            def astimezone(self, tz=None):
                return super().astimezone(tz or zone)

        monkeypatch.setattr(datetime_module, "datetime", InZone)
        monkeypatch.setattr(espn_api, "datetime", InZone)
        monkeypatch.setattr(game_labels, "datetime", InZone)

    return set_offset


@pytest.fixture
def freeze_now(monkeypatch):
    """Fix what datetime.now() returns, for code that decides by today's date."""

    def freeze(moment):
        class Frozen(datetime_module.datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return cls.fromtimestamp(moment.timestamp())
                return cls.fromtimestamp(moment.timestamp(), tz)

        monkeypatch.setattr(datetime_module, "datetime", Frozen)
        monkeypatch.setattr(espn_api, "datetime", Frozen)
        monkeypatch.setattr(venue_service, "datetime", Frozen)

    return freeze
