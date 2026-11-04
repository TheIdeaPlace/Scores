"""services/, settings.py, timezone_utils.py, text_utils.py and models/ with no Qt
and no network. Settings go to a temp folder: see the isolated fixture in conftest.py.
"""
import json
from datetime import date, datetime

import pytest
import requests

import espn_api
import settings
import timezone_utils
from exceptions import ApiError
from models.game import GameData
from models.news import NewsData
from models.standings import StandingsData
from services import football_calendar, updater
from services.api_service import ApiService
from services.venue_service import VenueService
from text_utils import ESPNTextProcessor, text_processor

from .support import FakeResponse, HTTP_404, HTTP_500, TIMEOUT, load


class TestApiService:
    @pytest.mark.parametrize("method,target,args", [
        ("get_leagues", "get_leagues", ()),
        ("get_scores", "get_scores", ("NBA", date(2026, 11, 3), 1, 2, 2026)),
        ("freshen_live_games", "freshen_live_games", ("NFL", [])),
        ("get_mlb_wildcard_standings", "get_mlb_wildcard_standings", ()),
        ("get_news", "get_news", ("NFL", 25)),
        ("get_standings", "get_standings", ("NFL",)),
        ("get_team_schedule", "get_team_schedule", ("NFL", "9", 10, 20, 2025)),
        ("get_available_seasons", "get_available_seasons", ("NFL",)),
        ("get_game_details", "get_game_details", ("NFL", "1")),
        ("extract_meaningful_game_info", "extract_meaningful_game_info", ({},)),
        ("format_complex_data", "format_complex_data", ("news", [])),
        ("get_player_statistics", "get_player_statistics", ("NFL",)),
        ("get_team_statistics", "get_team_statistics", ("NFL",)),
        ("get_rankings", "get_rankings", ("NCAAF",)),
        ("get_transactions", "get_transactions", ("NFL", "9", 5, 2)),
        ("get_team_info", "get_team_info", ("NFL", "9")),
        ("get_team_roster", "get_team_roster", ("NFL", "9")),
        ("get_team_news", "get_team_news", ("NFL", "9", 5)),
        ("get_team_transactions", "get_team_transactions", ("NFL", "9", 5)),
        ("get_draft", "get_draft", (2026,)),
        ("get_draft_round", "get_draft_round", (2026, 1)),
        ("get_golf_leaderboard", "get_golf_leaderboard", ("PGA",)),
        ("get_golf_schedule", "get_golf_schedule", ("PGA",)),
        ("get_world_cup_standings", "get_world_cup_standings", ("WC2026",)),
        ("get_world_cup_scores_range", "get_world_cup_scores_range", ("WC2026", date(2026, 6, 20), date(2026, 6, 21))),
        ("get_fantasy_cheatsheet", "get_fantasy_cheatsheet", (2026, 100)),
    ])
    def test_forwards_its_arguments_and_wraps_failures(self, monkeypatch, method, target, args):
        seen = []
        monkeypatch.setattr(espn_api, target, lambda *a: seen.append(a) or "result")
        assert getattr(ApiService, method)(*args) == "result"
        assert seen == [args]

        def boom(*a):
            raise ValueError("it broke")

        monkeypatch.setattr(espn_api, target, boom)
        with pytest.raises(ApiError, match="it broke") as info:
            getattr(ApiService, method)(*args)
        assert isinstance(info.value.__cause__, ValueError)

    def test_defaults_it_fills_in(self, monkeypatch):
        seen = []
        monkeypatch.setattr(espn_api, "get_news", lambda *a: seen.append(a))
        monkeypatch.setattr(espn_api, "get_team_schedule", lambda *a: seen.append(a))
        monkeypatch.setattr(espn_api, "get_mlb_wildcard_standings", lambda: None)
        ApiService.get_news("NFL")
        ApiService.get_team_schedule("NFL", "9")
        assert seen == [("NFL", 20), ("NFL", "9", 30, 30, None)]
        assert ApiService.get_mlb_wildcard_standings() == {}


class TestVenueService:
    def board(self):
        return load("scoreboard_NWSL.json")

    def test_urls_are_months_not_a_range(self, espn, freeze_now):
        freeze_now(datetime(2026, 10, 15, 12))
        espn.on("/scoreboard", {"events": []})
        VenueService().get_venues_for_league("nfl")
        assert espn.calls == [f"{espn_api.BASE_URL}/football/nfl/scoreboard?dates={m}&limit=100"
                              for m in ("202608", "202609", "202610", "202611")]

    def test_venues_from_a_real_board(self, espn):
        board = self.board()
        espn.on("/scoreboard", board).on("/teams$", load("teams_NFL.json"))
        venues = VenueService().get_venues_for_league("nfl")
        raw = board["events"][0]["competitions"][0]["venue"]
        venue = venues[raw["id"]]
        assert venue["name"] == raw["fullName"]
        assert venue["city"] == raw["address"]["city"]
        assert venue["indoor"] == raw.get("indoor", False)
        assert venue["home_teams"] == []

    def test_a_team_with_this_venue_is_its_home_team(self, espn):
        board = self.board()
        venue_id = board["events"][0]["competitions"][0]["venue"]["id"]
        espn.on("/scoreboard", board)
        espn.on("/teams$", {"sports": [{"leagues": [{"teams": [
            {"team": {"id": "9", "displayName": "Packers", "shortDisplayName": "GB", "abbreviation": "GB", "venue": {"id": venue_id}}},
            {"team": {"id": "1", "displayName": "Elsewhere", "venue": {"id": "nowhere"}}},
        ]}]}]})
        service = VenueService()
        teams = service.get_venues_for_league("nfl")[venue_id]["home_teams"]
        assert teams == [{"name": "Packers", "short_name": "GB", "abbreviation": "GB", "id": "9"}]

    def test_the_result_is_cached(self, espn):
        espn.on("/scoreboard", self.board()).on("/teams$", {"sports": []})
        service = VenueService()
        first = service.get_venues_for_league("nfl")
        count = len(espn.calls)
        assert service.get_venues_for_league("nfl") is first
        assert len(espn.calls) == count

    def test_a_failure_is_not_cached(self, espn):
        espn.on("/scoreboard", TIMEOUT)
        service = VenueService()
        assert service.get_venues_for_league("nfl") == {}
        assert service.venue_cache == {}

    def test_a_failed_month_keeps_the_others(self, espn, freeze_now):
        freeze_now(datetime(2026, 10, 15, 12))
        espn.on("/scoreboard", lambda url: self.board() if "202610" in url else HTTP_500)
        espn.on("/teams$", TIMEOUT)
        assert VenueService().get_venues_for_league("nfl")

    def test_unknown_league(self, espn):
        assert VenueService().get_venues_for_league("cricket") == {}
        assert espn.calls == []

    def test_unknown_league_finds_no_home_teams(self, espn):
        venues = {"1": {"home_teams": []}}
        VenueService()._find_home_teams(venues, "cricket")
        assert venues == {"1": {"home_teams": []}} and espn.calls == []

    def test_details(self, espn):
        board = self.board()
        raw = board["events"][0]["competitions"][0]["venue"]
        espn.on("/scoreboard", board).on("/teams$", {"sports": []})
        details = VenueService().get_venue_details(raw["id"], "nfl")
        assert details["basic_info"]["name"] == raw["fullName"]
        assert details["basic_info"]["league"] == "nfl"
        assert details["home_teams"] == []
        assert details["basic_info"]["city"] == raw["address"]["city"]
        assert any(f.startswith(f"Located in {raw['address']['city']}, ") for f in details["interesting_facts"])
        assert "National Football League venue" in details["interesting_facts"]

    def test_details_of_a_venue_nobody_knows(self, espn):
        espn.on("/scoreboard", {"events": []})
        assert VenueService().get_venue_details("nope", "nfl") is None

    @pytest.mark.parametrize("venue,league,fact", [
        ({"grass": True}, "nfl", "Natural grass playing surface"),
        ({"grass": False}, "nfl", "Artificial turf playing surface"),
        ({"indoor": True}, "nfl", "Indoor stadium with climate control"),
        ({"indoor": True}, "nfl", "Weather never affects games here"),
        ({}, "nfl", "Open-air stadium exposed to weather"),
        ({"capacity": 90000}, "nfl", "Massive stadium seating 90,000 fans"),
        ({"capacity": 70000}, "nfl", "Large stadium seating 70,000 fans"),
        ({"capacity": 20000}, "nba", "Intimate venue seating 20,000 fans"),
        ({"name": "Wrigley Field"}, "mlb", "Classic baseball 'Field' naming"),
        ({"name": "Fenway Park"}, "mlb", "Traditional baseball 'Park' naming"),
        ({"home_teams": [{"name": "Cubs"}]}, "mlb", "Home of the Cubs"),
        ({"home_teams": [{}, {}]}, "nba", "Shared by 2 teams"),
    ])
    def test_facts(self, venue, league, fact):
        assert fact in VenueService()._generate_interesting_facts(venue, league)

    def test_a_capacity_that_is_not_a_number_adds_nothing(self):
        assert not any("seating" in f for f in VenueService()._generate_interesting_facts({"capacity": "big"}, "nfl"))


class TestSettings:
    def test_defaults(self):
        assert settings.get("ncaaf_coverage") == "all_d1"
        assert settings.get("auto_refresh_interval") == "1 minute"
        assert settings.get("unknown") is None
        assert settings.get("unknown", "fallback") == "fallback"

    def test_set_writes_the_file_and_it_reads_back(self, monkeypatch):
        settings.set("fantasy_scoring", "Standard")
        assert json.loads(settings._SETTINGS_FILE.read_text(encoding="utf-8")) == {"fantasy_scoring": "Standard"}
        monkeypatch.setattr(settings, "_cache", None)
        assert settings.get("fantasy_scoring") == "Standard"

    def test_a_corrupt_file_reads_as_defaults(self):
        settings._SETTINGS_DIR.mkdir(parents=True)
        settings._SETTINGS_FILE.write_text("{not json", encoding="utf-8")
        assert settings.get("fantasy_scoring") == "PPR"

    def test_a_save_that_fails_keeps_the_value_and_warns(self, monkeypatch, capsys):
        def fail(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(settings.Path, "mkdir", fail)
        settings.set("fantasy_scoring", "Standard")
        assert settings.get("fantasy_scoring") == "Standard"
        assert "disk full" in capsys.readouterr().out

    def test_favorites(self):
        assert settings.get_favorites() == []
        assert settings.toggle_favorite(9, "Packers", "NFL", "GB") is True
        assert settings.get_favorites() == [{"team_id": "9", "team_name": "Packers", "league": "NFL", "abbreviation": "GB"}]
        assert settings.is_favorite("9", "NFL") is True
        assert settings.is_favorite("9", "NBA") is False  # the same id in another league
        assert settings.toggle_favorite("9", "Packers", "NFL") is False
        assert settings.get_favorites() == []
        assert json.loads(settings._SETTINGS_FILE.read_text(encoding="utf-8"))["favorites"] == []


class TestTimezone:
    @pytest.fixture
    def central(self, monkeypatch):
        monkeypatch.setattr(timezone_utils, "_local_offset_and_dst", lambda: (-6, False))

    @pytest.mark.parametrize("text", ["TBD", "N/A", "Unknown", "", None, "Final", "Halftime", "Final/OT", "7:00 PM"])
    def test_text_with_no_zone_is_unchanged(self, central, text):
        assert timezone_utils.convert_espn_time_to_local(text) == text

    def test_a_standalone_time(self, central):
        assert timezone_utils.convert_espn_time_to_local("7:00 PM EST").startswith("6:00 PM ")

    def test_a_dated_time_keeps_the_date(self, central):
        assert timezone_utils.convert_espn_time_to_local("8/28 - 5:30 PM EDT").startswith("8/28 - 4:30 PM ")

    @pytest.mark.parametrize("text,expected", [
        ("7:00 PM CST", "7:00 PM"), ("7:00 PM CT", "7:00 PM"), ("7:00 PM ET", "6:00 PM"),
        ("7:00 PM MT", "8:00 PM"), ("7:00 PM PST", "9:00 PM"), ("19:00 EST", "6:00 PM"), ("7:00PM EST", "6:00 PM"),
    ])
    def test_each_zone_and_format(self, central, text, expected):
        assert timezone_utils.convert_espn_time_to_local(text).startswith(expected + " ")

    def test_an_unparseable_time_is_unchanged(self, central):
        assert timezone_utils.convert_espn_time_to_local("soon EST") == "soon EST"
        assert timezone_utils.convert_espn_time_to_local("8/28 - soon EST") == "8/28 - soon EST"

    def test_a_zone_inside_another_word_is_unchanged(self, central):
        assert timezone_utils.convert_espn_time_to_local("7:00 PM ESTABLISHED") == "7:00 PM ESTABLISHED"

    def test_without_pytz_everything_is_unchanged(self, monkeypatch):
        monkeypatch.setattr(timezone_utils, "PYTZ_AVAILABLE", False)
        assert timezone_utils.convert_espn_time_to_local("7:00 PM EST") == "7:00 PM EST"
        assert timezone_utils._convert_time_with_timezone("7:00 PM EST") == "7:00 PM EST"
        assert timezone_utils.get_user_timezone() == "US/Central"

    def test_the_real_machine_gives_a_zone_pytz_knows(self):
        import pytz
        assert timezone_utils.get_user_timezone() in pytz.all_timezones

    def test_the_real_offset_is_a_number(self):
        offset, is_dst = timezone_utils._local_offset_and_dst()
        assert -14 <= offset <= 14
        assert isinstance(is_dst, bool)

    @pytest.mark.parametrize("name,daylight,zone", [
        ("EST", 0, "US/Eastern"), ("CST", 0, "US/Central"), ("MST", 0, "US/Mountain"), ("PST", 0, "US/Pacific"),
        ("Tokyo Standard Time", 0, "US/Central"),
    ])
    def test_when_the_offset_fails_it_reads_the_zone_name(self, monkeypatch, name, daylight, zone):
        def fail():
            raise OSError("no clock")

        monkeypatch.setattr(timezone_utils, "_local_offset_and_dst", fail)
        monkeypatch.setattr("time.tzname", (name, name))
        monkeypatch.setattr("time.daylight", daylight)
        assert timezone_utils.get_user_timezone() == zone

    def test_when_everything_fails_it_is_central(self, monkeypatch):
        def fail():
            raise OSError("no clock")

        monkeypatch.setattr(timezone_utils, "_local_offset_and_dst", fail)
        monkeypatch.setattr("time.tzname", ())
        assert timezone_utils.get_user_timezone() == "US/Central"

    def test_a_conversion_that_raises_returns_the_original(self, monkeypatch):
        monkeypatch.setattr(timezone_utils, "get_user_timezone", lambda: "Not/AZone")
        assert timezone_utils.convert_espn_time_to_local("7:00 PM EST") == "7:00 PM EST"


class TestTextProcessor:
    GAME = {
        "leaders": [{"leaders": [{"name": "passingYards", "leaders": [{"athlete": {"displayName": "Jordan Love"}}, {"athlete": {}}]},
                                 {"name": "tackles", "leaders": [{"athlete": {"displayName": "Not Priority"}}]}]}],
        "boxscore": {"players": [{"statistics": [
            {"name": "passing", "athletes": [{"athlete": {"displayName": "Jordan Love"}}, {"athlete": {"displayName": "Backup QB"}}, {"athlete": {}}]},
            {"name": "rushing", "athletes": [{"athlete": {"displayName": "Josh Jacobs"}}, {"athlete": {}}]},
            {"name": "kicking", "athletes": [{"athlete": {"displayName": "A Kicker"}}]},
        ]}]},
    }

    @pytest.mark.parametrize("text", ["", None, "Jordan Love threw for 300 yards."])
    def test_clean_text_is_untouched(self, text):
        assert text_processor.clean_description(text) == text

    def test_player_order_is_leaders_then_passers_then_others_without_repeats(self):
        assert ESPNTextProcessor()._extract_player_names_from_article(self.GAME) == ["Jordan Love", "Backup QB", "Josh Jacobs"]

    def test_control_characters_become_the_players_they_stand_for(self):
        assert text_processor.clean_description("\x01 found \x02 for six", self.GAME) == "Jordan Love found Backup QB for six"

    def test_escaped_numbers_too(self):
        assert text_processor.clean_description("\\1 found \\3", self.GAME) == "Jordan Love found Josh Jacobs"

    @pytest.mark.parametrize("text,expected", [
        ("\x01 scored", "[Player 1] scored"),
        ("\\2 scored", "[Player 2] scored"),
    ])
    def test_with_no_players_known_it_says_so(self, text, expected):
        assert text_processor.clean_description(text, {"leaders": []}) == expected

    @pytest.mark.parametrize("text", ["{{123}} scored", "{456} scored", "[789] scored", "#123456 scored", "player_12 scored", "athlete_12 scored"])
    def test_other_placeholders_are_named_as_such(self, text):
        assert text_processor.clean_description(text) == "[Player Name] scored"

    def test_when_placeholders_survive_it_points_at_the_article(self):
        processor = ESPNTextProcessor()
        processor._attempt_placeholder_resolution = lambda text, data: text
        assert processor.clean_description("{{1}}", {"headline": "Big win"}) == "Story details available in full article: Big win"
        assert processor.clean_description("{{1}}") == "Full story details available in the complete article."


class TestGameData:
    def teams(self, away="10", home="20"):
        return [{"name": "Away", "abbreviation": "AWY", "score": away, "record": "1-2", "home_away": "away"},
                {"name": "Home", "abbreviation": "HOM", "score": home, "record": "3-4", "home_away": "home"}]

    def test_a_real_scoreboard_game_through_get_scores(self, espn):
        espn.on("/scoreboard", load("scoreboard_events_by_status.json"))
        games = espn_api.get_scores("NBA")
        scheduled = GameData(next(g for g in games if g["status_name"] == "STATUS_SCHEDULED"), "NBA")
        assert scheduled.was_never_played is True
        assert "Zips (1-7)" in scheduled.get_display_text()
        played = GameData(next(g for g in games if g["status_name"] == "STATUS_FINAL"), "NBA")
        assert played.was_never_played is False
        assert played.has_scores() is True
        assert "Tigers 89" in played.get_display_text()

    @pytest.mark.parametrize("raw,never", [
        ({"status_name": "STATUS_SCHEDULED"}, True), ({"status_name": "STATUS_POSTPONED"}, True),
        ({"status_name": "STATUS_CANCELED"}, True), ({"status_name": "STATUS_SUSPENDED"}, False),
        ({"status_name": "STATUS_FINAL"}, False), ({"status": "Postponed"}, True), ({"status": "Final"}, False), ({}, False),
        ({"status_name": "STATUS_DELAYED", "teams": [{"score": "0"}, {"score": None}]}, True),
        ({"status_name": "STATUS_DELAYED", "teams": [{"score": "2"}, {"score": "0"}]}, False),
    ])
    def test_was_never_played(self, raw, never):
        assert GameData(raw).was_never_played is never

    def test_neutral_site_says_vs(self):
        raw = {"teams": self.teams(), "status": "Final", "competitions": [{"neutralSite": True}]}
        assert GameData(raw, "NBA").get_display_text() == "Away 10 vs Home 20 [Final]"

    def test_no_home_away_keeps_espns_order(self):
        teams = [{"name": "A", "score": "1"}, {"name": "B", "score": "2"}]
        assert GameData({"teams": teams, "status": "Final"}, "NBA").get_display_text() == "A 1 at B 2 [Final]"

    def test_no_teams_shows_the_name(self):
        assert GameData({"name": "Game", "status": "Final"}, "NBA").get_display_text() == "Game [Final]"
        assert GameData(None).name == "Unknown Game"

    @pytest.mark.parametrize("start,status,tail", [
        ("Top 5th", "In Progress", "[Top 5th]"),
        ("3rd 4:12", "In Progress", "[3rd 4:12]"),
        ("2 - Period 3", "In Progress", "[2 - Period 3]"),
        ("whenever", "In Progress", "[In Progress]"),
        ("", "In Progress", "[In Progress]"),
        ("Final/OT", "Final", "[Final/OT]"),
        ("whenever", "Final", "[Final]"),
        ("7:00 PM", "Scheduled", "(7:00 PM)"),
        ("11/2 - 7:00 PM", "Scheduled", "(7:00 PM)"),
        ("", "Scheduled", "[Scheduled]"),
        ("whenever", "Delayed", "[Delayed]"),
        ("7:00 PM", "", "(7:00 PM)"),
    ])
    def test_status_tails(self, monkeypatch, start, status, tail):
        monkeypatch.setattr("models.game.convert_espn_time_to_local", lambda text: text)
        raw = {"teams": self.teams(), "start_time": start, "status": status}
        assert GameData(raw, "NBA").get_display_text().endswith(" " + tail)

    def test_football_times_get_the_day_of_the_week(self, monkeypatch):
        monkeypatch.setattr("models.game.convert_espn_time_to_local", lambda text: text)
        raw = {"teams": self.teams(), "start_time": "9/10 - 8:20 PM EDT", "status": "Scheduled"}
        text = GameData(raw, "NFL").get_display_text()
        assert text.endswith(" 9/10 8:20PM)")

    def test_football_is_spotted_without_a_league(self, monkeypatch):
        monkeypatch.setattr("models.game.convert_espn_time_to_local", lambda text: text)
        raw = {"name": "NFL Game", "start_time": "9/10 - 8:20 PM", "status": ""}
        assert GameData(raw).get_display_text().endswith(" 9/10 8:20PM)")

    @pytest.mark.parametrize("month,today_month,year", [(1, 10, 2027), (6, 10, 2025), (10, 10, 2026), (9, 10, 2026)])
    def test_football_year_is_guessed_from_the_month(self, monkeypatch, month, today_month, year):
        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, today_month, 15)

        monkeypatch.setattr("models.game.datetime", Frozen)
        day = datetime(year, month, 15).strftime("%a")
        assert GameData({})._format_football_time(f"{month}/15 - 8:00 PM ET") == f"{day} {month}/15 8:00PM"

    @pytest.mark.parametrize("text", ["", "Sunday", "bad/date - 8:00 PM", "13/45 - 8:00 PM", "nodate - 8:00 PM"])
    def test_football_times_it_cannot_read_are_unchanged(self, text):
        assert GameData({})._format_football_time(text) == text

    def test_has_scores(self):
        assert GameData({"teams": [{"score": ""}]}).has_scores() is False


class TestNewsData:
    def test_from_get_news(self, espn):
        espn.on("/news", load("news_NFL.json"))
        article = NewsData(espn_api.get_news("NFL", 20)[0])
        text = article.get_display_text()
        assert text.startswith("Knockout league pickups")
        assert "| Tristan H. Cockcroft | 2026-11-03\n" in text
        assert article.has_web_url() is True

    def test_links_in_espns_own_shape(self):
        article = NewsData({"title": "T", "links": {"web": {"href": "w"}, "mobile": {"href": "m"}}})
        assert (article.headline, article.web_url, article.mobile_url) == ("T", "w", "m")

    def test_a_long_description_is_cut(self):
        assert NewsData({"headline": "H", "description": "x" * 150}).get_display_text() == "H\n  " + "x" * 100 + "..."

    def test_a_plain_string(self):
        article = NewsData("Just a headline")
        assert article.get_display_text() == "Just a headline"
        assert article.has_web_url() is False

    def test_no_headline(self):
        assert NewsData({}).headline == "No headline"


class TestStandingsData:
    def test_nothing(self):
        assert StandingsData([]).teams == []
        assert StandingsData(None).divisions == {}

    def test_not_a_dict_is_skipped(self):
        assert StandingsData(["text"]).teams == []

    def test_normalises_field_names(self):
        team = StandingsData([{"displayName": "A", "record": "5-2", "winPercent": ".714", "gb": "1.0", "division": "East"}]).teams[0]
        assert (team["team_name"], team["wins"], team["losses"], team["win_pct"], team["games_back"], team["record"]) == (
            "A", "5", "2", ".714", "1.0", "5-2")

    def test_ties_join_the_record_and_expanded_fields_survive(self):
        team = StandingsData([{"team_name": "A", "wins": 5, "losses": 2, "ties": 1, "points_for": 100}]).teams[0]
        assert team["record"] == "5-2-1"
        assert team["points_for"] == 100
        assert team["streak"] == "N/A"
        assert team["games_back"] == "—"

    def test_hockey_ranks_by_points_and_bad_numbers_sink(self):
        data = StandingsData([
            {"team_name": "A", "wins": 10, "losses": 1, "points": 20, "win_percentage": "0.900", "division": "D"},
            {"team_name": "B", "wins": 9, "losses": 1, "points": 30, "win_percentage": "0.800", "division": "D"},
            {"team_name": "C", "wins": "x", "losses": 1, "points": "n/a", "win_percentage": "n/a", "division": "D"},
        ])
        assert [t["team_name"] for t in data.divisions["D"]] == ["B", "A", "C"]


class TestFootballCalendarFailures:
    """The calendar's happy paths are in test_football_calendar.py."""

    @pytest.mark.parametrize("reply", [HTTP_404, HTTP_500, TIMEOUT, {}, {"leagues": []}])
    def test_no_calendar_means_week_one_of_the_regular_season(self, espn, reply):
        espn.on("/scoreboard", reply)
        assert football_calendar.get_season_weeks("NFL", 2026) == []
        assert football_calendar.get_current_week_and_type("NFL", 2026, date(2026, 10, 1)) == (2, 1)

    def test_current_season_week_falls_back_to_the_heuristic(self, espn):
        espn.on("/scoreboard", TIMEOUT)
        assert football_calendar.get_current_season_week_and_type("NFL", date(2026, 10, 1)) == (2026, 2, 1)

    def test_another_league_has_no_calendar(self, espn):
        assert football_calendar._fetch_calendar("NBA") == (None, [])
        assert football_calendar.get_season_weeks("NBA") == []
        assert football_calendar.get_current_football_week("NBA") is None
        assert espn.calls == []

    def test_unreadable_blocks_and_entries_are_skipped(self, espn):
        espn.on("/scoreboard", {"leagues": [{"season": {"year": "x"}, "calendar": [
            {"value": "x", "entries": []},
            {"value": "4", "entries": [{"value": "1", "startDate": "2026-01-01T07:00Z", "endDate": "2026-01-08T06:59Z"}]},
            {"value": "2", "entries": [
                {"value": "x", "startDate": "2026-09-01T07:00Z", "endDate": "2026-09-08T06:59Z"},
                {"value": "1", "startDate": "bad", "endDate": "bad"},
                {"value": "0", "startDate": "2026-09-01T07:00Z", "endDate": "2026-09-08T06:59Z"},
                {"value": "2", "startDate": "2026-09-08T07:00Z", "endDate": "2026-09-15T06:59Z"},
            ]},
        ]}]})
        season, weeks = football_calendar._fetch_calendar("NFL")
        assert season is None
        assert [(w["season_type"], w["week"], w["label"]) for w in weeks] == [(2, 2, "Week 2")]

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT, {"startDate": ""}])
    def test_week_dates_failures_are_not_cached(self, espn, reply):
        espn.on("/scoreboard", {"leagues": []}).on("/weeks/3", reply)
        assert football_calendar.get_week_dates("NFL", 3, 2026) == (None, None)
        assert football_calendar._WEEK_DATE_CACHE == {}


class TestUpdaterFailures:
    """The version logic is in test_updater.py."""

    def releases(self, *tags):
        return [{"tag_name": tag, "assets": [{"name": "Scores-Setup.exe", "browser_download_url": f"https://x/{tag}"}], "body": "notes"} for tag in tags]

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, requests.ConnectionError("down")])
    def test_a_failed_check_raises_so_it_cannot_read_as_up_to_date(self, espn, reply):
        espn.on("api.github.com", reply)
        with pytest.raises(requests.RequestException):
            updater.check_for_update("1.0.0")

    def test_no_releases(self, espn):
        espn.on("api.github.com", FakeResponse(None))
        assert updater.check_for_update("1.0.0") is None

    def test_a_newer_release_with_its_installer(self, espn):
        espn.on("api.github.com", self.releases("v1.0.0", "v2.0.0", "venue-fix"))
        assert updater.check_for_update("1.0.0") == {"version": "2.0.0", "url": "https://x/v2.0.0", "notes": "notes"}
        assert espn.calls == [updater.RELEASES_URL]
        assert espn.kwargs[0]["timeout"] == 15

    def test_a_release_with_no_installer(self, espn):
        espn.on("api.github.com", [{"tag_name": "v9.0.0", "assets": [{"name": "readme.txt"}], "body": None}])
        assert updater.check_for_update("1.0.0") == {"version": "9.0.0", "url": None, "notes": ""}

    def test_not_frozen_means_not_installed(self):
        assert updater.is_frozen() is False
        assert updater.is_installed() is False

    def test_frozen_in_the_install_folder(self, monkeypatch, tmp_path):
        target = tmp_path / "Programs" / "Scores"
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setattr("sys.executable", str(target / "Scores.exe"))
        assert updater.is_installed() is True
        monkeypatch.setattr("sys.executable", str(tmp_path / "Downloads" / "Scores.exe"))
        assert updater.is_installed() is False
        monkeypatch.delenv("LOCALAPPDATA")
        assert updater.is_installed() is False

    def test_a_failed_download_raises(self, espn):
        espn.on("x.invalid", HTTP_500)
        with pytest.raises(requests.HTTPError):
            updater.download_installer("https://x.invalid/Scores-Setup.exe")
