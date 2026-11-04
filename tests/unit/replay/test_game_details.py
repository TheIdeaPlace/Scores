"""Game details end to end: a saved summary through get_game_details and
extract_meaningful_game_info to what the details list shows."""
import pytest

import espn_api

from .support import FakeResponse, HTTP_404, load

SUMMARY = f"{espn_api.BASE_URL}/football/nfl/summary?event=401873035"


def details_for(espn, league, game_id, fixture):
    espn.on("/summary", load(fixture))
    return espn_api.extract_meaningful_game_info(espn_api.get_game_details(league, game_id))


class TestNflSummary:
    @pytest.fixture
    def info(self, espn):
        return details_for(espn, "NFL", "401873035", "details_NFL_pieces.json")

    def test_requests_the_summary_for_this_game(self, espn, info):
        assert espn.calls == [SUMMARY]

    def test_tv_comes_from_the_header_when_the_summary_list_is_empty(self, info):
        assert load("details_NFL_pieces.json")["broadcasts"] == []
        assert info["broadcast"] == "NBC"

    def test_odds_come_from_pickcenter_when_odds_is_empty(self, info):
        raw = load("details_NFL_pieces.json")
        assert not any(line.get("details") for line in raw["odds"])
        assert info["betting_line"] == "WSH -5.5"
        assert info["over_under"] == "O/U 40.5"

    def test_injuries_count_players_not_teams(self, info):
        raw = load("details_NFL_pieces.json")["injuries"]
        assert len(raw) == 2  # teams
        assert info["injuries"] == "10 players listed"

    def test_teams_scores_and_status(self, info):
        washington, philadelphia = info["teams"]
        assert washington == {"name": "Washington Commanders", "team_id": "28", "abbreviation": "WSH",
                              "record": "2-4-1", "home_away": "home", "score": "27"}
        assert (philadelphia["name"], philadelphia["home_away"], philadelphia["score"]) == ("Philadelphia Eagles", "away", "10")
        assert info["scores"] == ["Commanders: 27", "Eagles: 10"]
        assert info["status"] == "Final"
        assert info["detailed_status"] == "Final"
        assert info["date"] == "2026-11-02T01:20Z"

    def test_venue(self, info):
        assert (info["venue"], info["venue_city"], info["venue_state"]) == ("Northwest Stadium", "Landover", "MD")

    def test_no_weather_is_made_up_when_espn_sends_none(self, info):
        assert "weather" not in info and "temperature" not in info


class TestCollegeHockeySummary:
    @pytest.fixture
    def info(self, espn):
        espn.on("espn.com/mens-college-hockey/playbyplay", FakeResponse(status=202, text=""))
        return details_for(espn, "NCAAH", "401923148", "details_NCAAH_pieces.json")

    def test_tv_and_three_part_records(self, info):
        assert info["broadcast"] == "BTN"
        assert [t["record"] for t in info["teams"]] == ["3-5-0", "8-1-0"]
        assert info["detailed_status"] == "Final/OT"

    def test_nothing_invented_where_the_payload_has_nothing(self, info):
        for key in ("betting_line", "over_under", "injuries", "weather"):
            assert key not in info


def test_weather_when_espn_has_it():
    info = espn_api.extract_meaningful_game_info({"gameInfo": {"weather": {"displayValue": "Sunny", "temperature": 72}}})
    assert (info["weather"], info["temperature"]) == ("Sunny", "72°F")


def test_one_injured_player_is_singular():
    assert espn_api.extract_meaningful_game_info({"injuries": [{"injuries": [{}]}, {"injuries": []}]})["injuries"] == "1 player listed"


def test_no_injuries_says_nothing():
    assert "injuries" not in espn_api.extract_meaningful_game_info({"injuries": [{"injuries": []}]})


def test_article_is_carried_when_it_has_a_headline():
    article = {"headline": "Recap", "description": "d", "story": "s", "published": "p", "source": "AP"}
    info = espn_api.extract_meaningful_game_info({"article": article})
    assert info["article"]["headline"] == "Recap"
    assert info["article"]["type"] == "Article"
    assert "article" not in espn_api.extract_meaningful_game_info({"article": {"description": "no headline"}})


@pytest.mark.parametrize("bad", [None, {}, [], "text"])
def test_extract_with_nothing_usable_is_empty(bad):
    assert espn_api.extract_meaningful_game_info(bad) == {}


@pytest.mark.parametrize("league", ["NHL", "NCAAH", "NCAAWH", "NBA"])
def test_a_game_is_one_request(espn, league):
    """Hockey also fetched espn.com's page, which has stopped giving any plays. College hockey's
    has none to give: it and the summary are both empty."""
    plays = [{"id": "1", "text": "Faceoff"}]
    espn.on("/summary", {"plays": plays})
    assert espn_api.get_game_details(league, "7")["plays"] == plays
    assert len(espn.calls) == 1


def test_unknown_league_requests_nothing(espn):
    assert espn_api.get_game_details("CRICKET", "1") == {}
    assert espn.calls == []


class TestFormatComplexData:
    """What the game details list shows for each field of a real summary."""

    def fmt(self, key, value=None):
        if value is None:
            value = load("details_NFL_pieces.json")[key]
        return espn_api.format_complex_data(key, value)

    def test_game_info_from_a_real_summary(self):
        assert self.fmt("gameInfo") == "Venue: Northwest Stadium\nAttendance: 64,195"

    def test_zero_attendance_is_not_shown(self):
        value = load("details_NCAAH_pieces.json")["gameInfo"]
        assert espn_api.format_complex_data("gameInfo", value) == "Venue: Schottenstein Center"

    def test_real_odds(self):
        assert self.fmt("odds", load("details_NFL_pieces.json")["pickcenter"]) == "• DraftKings: WSH -5.5 (O/U: 40.5)"

    def test_real_broadcasts(self):
        value = load("details_NFL_pieces.json")["header"]["competitions"][0]["broadcasts"]
        assert self.fmt("broadcasts", value) == "NBC"

    @pytest.mark.parametrize("value", [None, [], {}, "", 0])
    @pytest.mark.parametrize("key", ["gameInfo", "news", "leaders", "standings", "injuries", "broadcasts", "odds", "boxscore", "other"])
    def test_nothing_says_no_data(self, key, value):
        assert espn_api.format_complex_data(key, value) == "No data available"

    @pytest.mark.parametrize("key,value,expected", [
        ("gameInfo", {"weather": {"displayValue": "Rain", "temperature": 50}}, "Weather: Rain (50°F)"),
        ("gameInfo", {"weather": {"temperature": 50}}, "Weather: 50°F"),
        ("gameInfo", {"venue": {"displayName": "Dome"}}, "Venue: Dome"),
        ("gameInfo", {"officials": [1]}, "No additional game info available"),
        ("x", {"header": "Only"}, "No content data available"),
        ("x", {"header": "H", "list": [1, 2]}, "List with 2 items: 1, 2"),
        ("news", [{"headline": "A"}, {"title": "B"}, {"neither": 1}, {"headline": "late"}], "• A\n• B"),
        ("news", [{"neither": 1}], "No headlines available"),
        ("news", {"articles": [{"headline": "A"}, {"nope": 1}]}, "• A"),
        ("news", {"articles": [{"nope": 1}]}, "No headlines found"),
        ("news", {"other": 1}, "News section available"),
        ("news", "text", "News available"),
        ("leaders", [{}, {}], "Statistical leaders available (2 categories)"),
        ("leaders", {"a": 1, "b": 2, "c": 3}, "Statistical leaders available (3 categories)"),
        ("leaders", "text", "Leaders data available"),
        ("standings", [{}, {}], "Standings available for 2 teams"),
        ("standings", {"entries": [{}]}, "Standings available for 1 teams"),
        ("standings", {"other": 1}, "Standings data available"),
        ("standings", "text", "Standings available"),
        ("broadcasts", [{"nope": 1}], "No networks listed"),
        ("broadcasts", {"other": 1}, "Broadcast data available"),
        ("broadcasts", "text", "Broadcast section available"),
        ("odds", ["text"], "No odds details"),
        ("odds", {"other": 1}, "Odds data available"),
        ("odds", "text", "Odds section available"),
        ("boxscore", {"teams": [{"team": {"displayName": "A"},
                                 "statistics": [{"name": "yards", "displayValue": "300"}, {"name": "", "displayValue": "x"}]},
                                {"team": {"displayName": "B"}, "statistics": []}, "text"]},
         "• A: yards: 300"),
        ("boxscore", {"teams": [{"team": {"displayName": "A"}, "statistics": []}]}, "No boxscore data"),
        ("boxscore", {"other": 1}, "No team stats available"),
        ("other", [1, 2, 3, 4], "List with 4 items: 1, 2, 3"),
        ("other", [{"long": "x" * 60}], "List with 1 items"),
        ("other", {"a": 1, "b": "two"}, "a: 1; b: two"),
        ("other", {"a": [1]}, "Dict with 1 items"),
        ("other", {"a": 1, "b": 2, "c": 3, "d": 4}, "Dict with 4 items: a, b, c, d"),
        ("other", 7, "7"),
        ("other", "x" * 120, "x" * 100 + "..."),
    ])
    def test_each_shape(self, key, value, expected):
        assert espn_api.format_complex_data(key, value) == expected
