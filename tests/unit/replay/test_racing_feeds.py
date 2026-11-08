"""Racing's requests on Windows: the iPhone's URLs, ESPN's real answers, and a failed request that
says so rather than reading as no race."""
import pytest

import espn_api
from exceptions import ApiError
from services.api_service import ApiService

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, FakeResponse, load

SCOREBOARD = r"/apis/site/v2/sports/racing/f1/scoreboard$"
SEASON = r"/apis/site/v2/sports/racing/f1/scoreboard\?dates=2026$"
STANDINGS = r"/apis/v2/sports/racing/f1/standings$"


class TestTheRace:
    def test_the_url_and_what_it_reads(self, espn):
        espn.on(SCOREBOARD, load("racing_scoreboard_f1.json"))
        answer = ApiService.get_race_event("F1")
        assert espn.calls == ["https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard"]
        assert answer["season"] == 2026
        assert answer["event"]["name"] == "MSC Cruises São Paulo Grand Prix"

    @pytest.mark.parametrize("series,path", [("IndyCar", "irl"), ("NASCAR", "nascar-premier")])
    def test_the_other_series(self, espn, series, path):
        espn.on(rf"/racing/{path}/scoreboard$", load(f"racing_scoreboard_{path}.json"))
        assert ApiService.get_race_event(series)["event"]["state"] in ("pre", "post")

    def test_no_events_is_the_off_season(self, espn):
        espn.on(SCOREBOARD, {"leagues": [{"season": {"year": 2027}}], "events": []})
        assert ApiService.get_race_event("F1") == {"event": None, "season": 2027}

    def test_a_404_is_nothing_there(self, espn):
        espn.on(SCOREBOARD, HTTP_404)
        assert ApiService.get_race_event("F1") == {"event": None, "season": None}

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, FakeResponse({"events": None})])
    def test_a_failed_request_says_so(self, espn, reply):
        espn.on(SCOREBOARD, reply)
        with pytest.raises(ApiError) as caught:
            ApiService.get_race_event("F1")
        assert str(caught.value) == espn_api.RACE_UNAVAILABLE

    def test_an_unknown_series_asks_nothing(self, espn):
        assert ApiService.get_race_event("Karting") == {"event": None, "season": None}
        assert espn.calls == []


class TestTheSchedule:
    def test_a_bare_year_never_a_range(self, espn):
        espn.on(SEASON, load("racing_season_f1_2026.json"))
        races = ApiService.get_racing_schedule("F1", 2026)
        assert espn.calls == ["https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard?dates=2026"]
        assert len(races) == 25

    def test_no_season_asks_nothing(self, espn):
        assert ApiService.get_racing_schedule("F1", None) == []
        assert espn.calls == []

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON])
    def test_a_failed_request_says_so(self, espn, reply):
        espn.on(SEASON, reply)
        with pytest.raises(ApiError) as caught:
            ApiService.get_racing_schedule("F1", 2026)
        assert str(caught.value) == espn_api.SCHEDULE_UNAVAILABLE


class TestTheStandings:
    def test_the_url_and_both_championships(self, espn):
        espn.on(STANDINGS, load("racing_standings_f1.json"))
        groups = ApiService.get_racing_standings("F1")
        assert espn.calls == ["https://site.api.espn.com/apis/v2/sports/racing/f1/standings"]
        assert [g["name"] for g in groups] == ["Driver Standings", "Constructor Standings"]

    def test_empty_is_none_yet(self, espn):
        espn.on(STANDINGS, EMPTY_JSON)
        assert ApiService.get_racing_standings("F1") == []

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, FakeResponse({"children": None})])
    def test_a_failed_request_says_so(self, espn, reply):
        espn.on(STANDINGS, reply)
        with pytest.raises(ApiError) as caught:
            ApiService.get_racing_standings("F1")
        assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE


class TestTheNews:
    def test_racing_news_from_the_series_path(self, espn):
        espn.on(r"/racing/f1/news", load("racing_news_f1.json"))
        news = ApiService.get_news("F1", 25)
        assert espn.calls == ["https://site.api.espn.com/apis/site/v2/sports/racing/f1/news?limit=25"]
        assert len(news) == 3 and news[0]["headline"]

    def test_nascar_has_none_right_now(self, espn):
        espn.on(r"/racing/nascar-premier/news", load("racing_news_nascar-premier.json"))
        assert ApiService.get_news("NASCAR", 25) == []
