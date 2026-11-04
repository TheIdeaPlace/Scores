"""The team dialog's data: info, roster, news and transactions on real payloads."""
from concurrent.futures import ThreadPoolExecutor

import pytest

import espn_api
from exceptions import ApiError

from .support import HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, load

SITE = espn_api.BASE_URL
SEASON = "/season$"
ANY_SEASON = r"/teams/\w+\?season="


class TestTeamInfo:
    @pytest.fixture(autouse=True)
    def no_home_games(self, espn):
        """Most of these aren't about the venue. A team with no games keeps franchise.venue,
        and with the league in its regular season and no answer for it the page keeps its record."""
        espn.on("/schedule", {"events": []})
        espn.on(SEASON, load("season_NFL.json"))
        espn.on(ANY_SEASON, HTTP_404)

    def info(self, espn, league="NFL", team="9", fixture="team_NFL_9.json"):
        espn.on(f"/teams/{team}$", load(fixture))
        return espn_api.get_team_info(league, team)

    def test_urls(self, espn):
        self.info(espn)
        assert espn.calls == [f"{SITE}/football/nfl/teams/9", f"{SITE}/football/nfl/teams/9/schedule?seasontype=2",
                              f"{espn_api.CORE_BASE_URL}/football/leagues/nfl/season",
                              f"{SITE}/football/nfl/teams/9?season=2026&seasontype=2"]

    def test_soccer_has_no_season_type_two(self, espn):
        espn.on("/teams/359$", load("team_EPL_359.json"))
        espn_api.get_team_info("EPL", "359")
        assert espn.calls == [f"{SITE}/soccer/eng.1/teams/359", f"{SITE}/soccer/eng.1/teams/359/schedule"]

    @pytest.mark.parametrize("league,path", [("WC2026", "fifa.world"), ("WWC2027", "fifa.wwc")])
    def test_a_world_cup_team_has_no_home_venue(self, espn, league, path):
        """Its "home" games are tournament draws. Brazil read MetLife Stadium."""
        data = load("team_EPL_359.json")
        espn.on("/teams/359$", data)
        info = espn_api.get_team_info(league, "359")
        assert espn.calls == [f"{SITE}/soccer/{path}/teams/359"]
        assert (info["name"], info["venue_name"], info["venue_location"]) == (data["team"]["displayName"], "", "")

    def test_a_venue_not_shown_costs_no_request(self, espn):
        """Favorites asks for a team's record and next game, once per favorite."""
        espn.on("/teams/9$", load("team_NFL_9.json"))
        info = espn_api.get_team_info("NFL", "9", home_venue=False)
        assert not espn.urls("/schedule")
        assert info["venue_name"] == "Lambeau Field"

    class TestHomeVenue:
        def nets(self, espn):
            espn.on("/teams/17$", load("team_NBA_17.json"))
            return espn_api.get_team_info("NBA", "17")

        def test_the_fixture_has_the_stale_name(self):
            assert load("team_NBA_17.json")["team"]["franchise"]["venue"]["fullName"] == "Prudential Center"

        def test_the_nets_play_at_barclays(self, espn):
            espn.on("/schedule", load("schedule_NBA_17.json"))
            info = self.nets(espn)
            assert (info["venue_name"], info["venue_location"]) == ("Barclays Center", "Brooklyn, NY")

        def test_an_opponents_home_is_theirs(self):
            venue = espn_api.most_used_home_venue(load("schedule_NBA_17.json")["events"], "2")
            assert venue["fullName"] == "TD Garden"

        def test_most_of_the_games_beats_the_latest(self):
            """The Athletics played most of their season in Sacramento, then some in Las Vegas."""
            events = load("schedule_MLB_11.json")["events"]
            assert events[-1]["competitions"][0]["venue"]["fullName"] == "Las Vegas Ballpark"
            assert espn_api.most_used_home_venue(events, "11")["fullName"] == "Sutter Health Park"

        def test_the_later_venue_wins_a_tie(self):
            events = load("schedule_MLB_11.json")["events"]
            sutter = [e for e in events if e["competitions"][0]["venue"]["fullName"] == "Sutter Health Park"]
            events.remove(sutter[0])
            assert espn_api.most_used_home_venue(events, "11")["fullName"] == "Las Vegas Ballpark"

        def test_a_neutral_site_does_not_count(self):
            """ESPN lists the Falcons as home in Madrid, and that game is the later one."""
            events = load("schedule_NFL_1.json")["events"]
            madrid = events[-1]["competitions"][0]
            assert madrid["neutralSite"] and madrid["venue"]["fullName"].startswith("Santiago")
            assert espn_api.most_used_home_venue(events, "1")["fullName"] == "Mercedes-Benz Stadium"

        @pytest.mark.parametrize("events", [None, [], [None, {}, {"competitions": None}, {"competitions": [None]}]])
        def test_no_usable_games(self, events):
            assert espn_api.most_used_home_venue(events, "17") is None

        def test_a_team_with_no_home_game_listed(self):
            assert espn_api.most_used_home_venue(load("schedule_NBA_17.json")["events"], "99999") is None

        def test_a_home_game_with_no_venue_name_does_not_count(self):
            events = load("schedule_NBA_17.json")["events"]
            for event in events:
                event["competitions"][0]["venue"]["fullName"] = None
            assert espn_api.most_used_home_venue(events, "17") is None

        @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, {"events": None}, {}, []],
                                 ids=["timeout", "500", "not_json", "null", "no_key", "a_list"])
        def test_losing_the_schedule_falls_back_and_keeps_the_page(self, espn, reply):
            espn.on("/schedule", reply)
            info = self.nets(espn)
            assert (info["name"], info["venue_name"]) == ("Brooklyn Nets", "Prudential Center")

        def test_it_does_not_wait_long_for_one_line(self, espn):
            self.nets(espn)
            asked = next(i for i, url in enumerate(espn.calls) if url.endswith("/schedule?seasontype=2"))
            assert espn.kwargs[asked]["timeout"] == 8

    def test_names(self, espn):
        info = self.info(espn)
        assert (info["name"], info["abbreviation"], info["nickname"], info["location"]) == (
            "Green Bay Packers", "GB", "Packers", "Green Bay")

    def test_venue_lives_under_franchise(self, espn):
        assert "venue" not in load("team_NFL_9.json")["team"]
        info = self.info(espn)
        assert (info["venue_name"], info["venue_location"]) == ("Lambeau Field", "Green Bay, WI")

    def test_a_venue_directly_on_the_team_wins(self, espn):
        data = load("team_NFL_9.json")
        data["team"]["venue"] = {"displayName": "Dome", "address": {"state": "IN"}}
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["venue_name"], info["venue_location"]) == ("Dome", "IN")

    def test_no_venue_leaves_it_blank(self, espn):
        data = load("team_NFL_9.json")
        del data["team"]["franchise"]
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["venue_name"], info["venue_location"]) == ("", "")

    def test_record_splits(self, espn):
        info = self.info(espn)
        assert (info["record_overall"], info["record_home"], info["record_road"]) == ("5-3", "3-1", "2-2")

    def test_hockey_overall_includes_overtime_losses(self, espn):
        info = self.info(espn, "NHL", "129764", "team_NHL_utah.json")
        assert load("team_NHL_utah.json")["team"]["record"]["items"][0]["summary"] == "9-6"
        assert info["record_overall"] == "9-6-0"

    def test_football_ot_losses_stat_does_not_add_a_part(self, espn):
        """Football's OTLosses is capitalised and isn't part of its record."""
        assert self.info(espn)["record_overall"].count("-") == 1

    def test_a_soccer_three_part_summary_is_left_alone(self, espn):
        assert self.info(espn, "EPL", "359", "team_EPL_359.json")["record_overall"] == "8-0-1"

    def test_standing(self, espn):
        assert self.info(espn)["standing"] == "7th in National Football Conference"

    def test_the_payload_has_no_division_or_coach_so_neither_is_invented(self, espn):
        info = self.info(espn, "NHL", "129764", "team_NHL_utah.json")
        assert (info["division"], info["conference"]) == ("", "")
        assert "head_coach" not in info

    def test_groups_and_coach_when_present(self, espn):
        data = load("team_NFL_9.json")
        data["team"]["groups"] = {"name": "NFC North", "parent": {"name": "NFC"}}
        data["team"]["coaches"] = [{"firstName": "Matt", "lastName": "LaFleur"}]
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["division"], info["conference"], info["head_coach"]) == ("NFC North", "NFC", "Matt LaFleur")

    class TestNextGame:
        def test_a_null_competition_does_not_lose_the_team_view(self, espn):
            """The filter raised, get_team_info caught it and returned {}."""
            data = load("team_NFL_9.json")
            data["team"]["nextEvent"][0]["competitions"] = [None]
            espn.on("/teams/9$", data)
            info = espn_api.get_team_info("NFL", "9")
            assert (info["name"], info["venue_name"]) == ("Green Bay Packers", "Lambeau Field")
            assert "next_game_opponent" not in info

        def test_a_finished_game_is_not_the_next_game(self, espn):
            """For a while after a game ESPN's nextEvent is still that game."""
            data = load("team_NFL_9.json")
            state = data["team"]["nextEvent"][0]["competitions"][0]["status"]["type"]["state"]
            assert state == "post"
            espn.on("/teams/9$", data)
            info = espn_api.get_team_info("NFL", "9")
            assert not {"next_game_opponent", "next_game_home_away", "next_game_date"} & set(info)

        def test_away(self, espn):
            espn.on("/teams/129764$", load("team_NHL_utah.json"))
            info = espn_api.get_team_info("NHL", "129764")
            assert (info["next_game_opponent"], info["next_game_home_away"]) == ("Toronto Maple Leafs", "@")

        def test_home(self, espn):
            espn.on("/teams/21$", load("team_NHL_utah.json"))
            info = espn_api.get_team_info("NHL", "21")
            assert (info["next_game_opponent"], info["next_game_home_away"]) == ("Utah Mammoth", "vs")

        @pytest.mark.parametrize("offset,day", [(-6, "Tue, Nov 3"), (9, "Wed, Nov 4")])
        def test_the_date_is_local(self, espn, local_zone, offset, day):
            local_zone(offset)
            data = load("team_NHL_utah.json")
            assert data["team"]["nextEvent"][0]["date"] == "2026-11-04T00:00Z"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == day

        def test_a_leading_zero_day_is_trimmed(self, espn, local_zone):
            local_zone(0)
            data = load("team_NHL_utah.json")
            data["team"]["nextEvent"][0]["date"] = "2026-11-05T12:00Z"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == "Thu, Nov 5"

        def test_an_unreadable_date_falls_back_to_its_first_ten_characters(self, espn):
            data = load("team_NHL_utah.json")
            data["team"]["nextEvent"][0]["date"] = "2026-11-04 sometime"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == "2026-11-04"

    def test_no_team_id_requests_nothing(self, espn):
        assert espn_api.get_team_info("NFL", "") == {}
        assert espn_api.get_team_info("CRICKET", "1") == {}
        assert espn.calls == []


def asks(espn, team, season_file, plain_file, regular):
    """ESPN as it answered on Nov 4, 2026, with the league in whatever season_file says."""
    espn.on(SEASON, load(season_file))
    espn.on("/schedule", {"events": []})
    espn.on(f"/teams/{team}$", load(plain_file))
    espn.on(rf"/teams/{team}\?season=\d+&seasontype=2$", load(regular) if isinstance(regular, str) else regular)


def splits(info):
    return info.get("record_overall"), info.get("record_home"), info.get("record_road"), info["standing"]


class TestTheRegularSeasonRecord:
    """/teams/{id} with no season answers with whatever the league is doing now."""

    def lynx(self, espn, regular="team_WNBA_8_regular.json"):
        asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", regular)

    def test_the_fixture_is_the_bug(self):
        team = load("team_WNBA_8.json")["team"]
        assert (team["record"]["items"][0]["summary"], team["standingSummary"]) == ("0-2", "8th in Western Conference Division")

    def test_a_team_in_the_playoffs(self, espn):
        self.lynx(espn)
        assert splits(espn_api.get_team_info("WNBA", "8")) == ("33-11", "15-7", "18-4", "1st in Western Conference")

    def test_a_team_that_missed_them(self, espn):
        """Seattle is 8-36 and last, and read 0-0 and 4th."""
        assert load("team_WNBA_14.json")["team"]["record"]["items"][0]["summary"] == "0-0"
        asks(espn, "14", "season_WNBA.json", "team_WNBA_14.json", "team_WNBA_14_regular.json")
        assert splits(espn_api.get_team_info("WNBA", "14")) == ("8-36", "6-16", "2-20", "8th in Western Conference")

    def test_it_asks_for_the_season_as_well_as_the_type(self, espn):
        """seasontype=2 alone doesn't work: Atlanta stays 8-4."""
        self.lynx(espn)
        espn_api.get_team_info("WNBA", "8")
        assert f"{SITE}/basketball/wnba/teams/8?season=2026&seasontype=2" in espn.calls

    def test_a_favorite_gets_it_too_with_no_schedule_request(self, espn):
        self.lynx(espn)
        info = espn_api.get_team_info("WNBA", "8", home_venue=False)
        assert info["record_overall"] == "33-11"
        assert not espn.urls("/schedule")

    def test_the_rest_of_the_page_is_kept(self, espn):
        self.lynx(espn)
        info = espn_api.get_team_info("WNBA", "8")
        assert (info["name"], info["abbreviation"], info["location"]) == ("Minnesota Lynx", "MIN", "Minnesota")

    def test_mlb_in_its_playoffs_keeps_the_record_and_corrects_the_standing(self, espn):
        """The Dodgers won the NL West, and read 5th in it, with the right record."""
        asks(espn, "19", "season_MLB.json", "team_MLB_19.json", "team_MLB_19_regular.json")
        info = espn_api.get_team_info("MLB", "19")
        assert splits(info) == ("100-62", "51-30", "49-32", "1st in NL West")

    def test_the_next_game_is_not_the_regular_season_answers(self, espn):
        """Asked for a season, ESPN has no next game for the Dodgers, whose next is in spring."""
        assert "nextEvent" not in load("team_MLB_19_regular.json")["team"]
        asks(espn, "19", "season_MLB.json", "team_MLB_19.json", "team_MLB_19_regular.json")
        info = espn_api.get_team_info("MLB", "19")
        assert info["next_game_opponent"] == "Chicago White Sox"

    def test_a_league_in_its_regular_season(self, espn):
        """Asked for a season, ESPN has the Nets' next game in January, not tomorrow's."""
        regular = load("team_NBA_17_regular.json")["team"]
        assert regular["nextEvent"][0]["date"].startswith("2027-01")
        asks(espn, "17", "season_NBA.json", "team_NBA_17.json", "team_NBA_17_regular.json")
        info = espn_api.get_team_info("NBA", "17")
        assert splits(info) == ("1-6", "0-3", "1-3", "5th in Atlantic Division")
        assert (info["next_game_opponent"], info["next_game_home_away"]) == ("Charlotte Hornets", "vs")
        assert f"{SITE}/basketball/nba/teams/17?season=2027&seasontype=2" in espn.calls

    def test_college_hockey_has_a_record_only_this_way(self, espn):
        assert "record" not in load("team_NCAAH_130.json")["team"]
        asks(espn, "130", "season_NBA.json", "team_NCAAH_130.json", "team_NCAAH_130_regular.json")
        info = espn_api.get_team_info("NCAAH", "130")
        assert info["record_overall"] == "8-1"
        assert info["next_game_opponent"] == "Penn State Nittany Lions"

    @pytest.mark.parametrize("league", ["NCAAH", "NCAAWH"])
    def test_a_standing_in_nothing_is_not_shown(self, espn, league):
        """College hockey says "1st" of every team, Alaska Fairbanks at 1-7 included."""
        assert load("team_NCAAH_130_regular.json")["team"]["standingSummary"] == "1st"
        asks(espn, "130", "season_NBA.json", "team_NCAAH_130.json", "team_NCAAH_130_regular.json")
        assert espn_api.get_team_info(league, "130")["standing"] == ""

    def test_a_preseason_shows_the_last_season(self, espn):
        season = load("season_NBA.json")
        season["type"]["type"] = 1
        asks(espn, "17", "season_NBA.json", "team_NBA_17.json", "team_NBA_17_regular.json")
        espn.on(SEASON, season)
        espn_api.get_team_info("NBA", "17")
        assert f"{SITE}/basketball/nba/teams/17?season=2026&seasontype=2" in espn.calls

    def test_college_hockey_ties_read_as_ties(self, espn):
        """Niagara, 5-4-1. Without any, Army is 5-1 on both apps: no third part from a stat."""
        regular = load("team_NCAAH_130_regular.json")
        regular["team"]["record"]["items"][0]["summary"] = "5-4-1"
        asks(espn, "130", "season_NBA.json", "team_NCAAH_130.json", regular)
        assert espn_api.get_team_info("NCAAH", "130")["record_overall"] == "5-4-1"

    def test_a_conference_is_not_called_a_division(self, espn):
        regular = load("team_NBA_17_regular.json")
        regular["team"]["standingSummary"] = "10th in Eastern Conference Division"
        asks(espn, "17", "season_NBA.json", "team_NBA_17.json", regular)
        assert espn_api.get_team_info("NBA", "17")["standing"] == "10th in Eastern Conference"

    @pytest.mark.parametrize("league,season_type,expected", [
        ("NCAAH", 3, True), ("NCAAH", 4, True), ("NCAAH", 1, True), ("NCAAH", 2, False),
        ("NCAAF", 3, True), ("NCAAM", 3, True), ("NBA", 3, False), ("WNBA", 4, False), ("MLB", 1, False),
    ])
    def test_a_college_record_says_when_it_leaves_out_the_postseason(self, espn, league, season_type, expected):
        """Michigan basketball's 2026 reads 31-3 here and 37-3 in Standings."""
        season = load("season_NBA.json")
        season["type"]["type"] = season_type
        asks(espn, "130", "season_NBA.json", "team_NCAAH_130.json", "team_NCAAH_130_regular.json")
        espn.on(SEASON, season)
        assert espn_api.get_team_info(league, "130")["record_regular_season_only"] is expected

    def test_soccer_never_says_regular_season(self, espn):
        espn.on("/teams/359$", load("team_EPL_359.json"))
        info = espn_api.get_team_info("EPL", "359", home_venue=False)
        assert (info["record_regular_season_only"], info["record_unavailable"]) == (False, False)

    @pytest.mark.parametrize("league,path", [("EPL", "soccer/eng.1"), ("MLS", "soccer/usa.1")])
    def test_soccer_asks_for_no_season(self, espn, league, path):
        """Its team page is the league season, and season type 2 can name another competition."""
        espn.on("/teams/359$", load("team_EPL_359.json"))
        info = espn_api.get_team_info(league, "359", home_venue=False)
        assert espn.calls == [f"{SITE}/{path}/teams/359"]
        assert (info["record_overall"], info["standing"]) == ("8-0-1", "1st in English Premier League")

    class TestWhenItCannotBeHad:
        LOOKUP_FAILURES = dict(argvalues=[TIMEOUT, HTTP_500, NOT_JSON, {"year": "soon"}, {}, []],
                               ids=["timeout", "500", "not_json", "no_year", "nothing", "a_list"])
        FAILURES = dict(argvalues=[TIMEOUT, HTTP_500, HTTP_404, NOT_JSON, {}, [], {"team": None},
                                   {"team": {"record": {"items": []}}}],
                        ids=["timeout", "500", "404", "not_json", "nothing", "a_list", "null_team", "no_records"])

        def page_is_there(self, info):
            assert (info["name"], info["abbreviation"]) == ("Minnesota Lynx", "MIN")

        @pytest.mark.parametrize("reply", **LOOKUP_FAILURES)
        def test_no_season_keeps_the_page_and_no_record_from_the_playoffs(self, espn, reply):
            asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", "team_WNBA_8_regular.json")
            espn.on(SEASON, reply)
            info = espn_api.get_team_info("WNBA", "8")
            self.page_is_there(info)
            assert splits(info) == (None, None, None, "")
            assert info["record_unavailable"] is True

        @pytest.mark.parametrize("reply", **FAILURES)
        def test_no_regular_season_in_the_playoffs_has_no_playoff_record(self, espn, reply):
            asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", reply)
            info = espn_api.get_team_info("WNBA", "8")
            self.page_is_there(info)
            assert splits(info) == (None, None, None, "")

        @pytest.mark.parametrize("reply,expected", [
            (TIMEOUT, True), (HTTP_500, True), (NOT_JSON, True),
            (HTTP_404, False), ({}, False), ({"team": {"record": {"items": []}}}, False),
        ], ids=["timeout", "500", "not_json", "404", "nothing", "no_records"])
        def test_a_failure_is_told_from_a_team_with_no_record(self, espn, reply, expected):
            asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", reply)
            assert espn_api.get_team_info("WNBA", "8")["record_unavailable"] is expected

        def test_a_record_there_is_not_unavailable(self, espn):
            asks(espn, "17", "season_NBA.json", "team_NBA_17.json", HTTP_500)
            info = espn_api.get_team_info("NBA", "17")
            assert (info["record_overall"], info["record_unavailable"]) == ("1-6", False)

        @pytest.mark.parametrize("reply", **FAILURES)
        def test_no_regular_season_in_it_keeps_the_same_numbers(self, espn, reply):
            asks(espn, "17", "season_NBA.json", "team_NBA_17.json", reply)
            info = espn_api.get_team_info("NBA", "17")
            assert splits(info) == ("1-6", "0-3", "1-3", "5th in Atlantic Division")

        def test_a_standing_with_no_record_is_kept(self, espn):
            regular = load("team_WNBA_8_regular.json")
            del regular["team"]["record"]
            asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", regular)
            assert splits(espn_api.get_team_info("WNBA", "8")) == (None, None, None, "1st in Western Conference")

        def test_it_does_not_wait_long(self, espn):
            asks(espn, "8", "season_WNBA.json", "team_WNBA_8.json", "team_WNBA_8_regular.json")
            espn_api.get_team_info("WNBA", "8")
            asked = next(i for i, url in enumerate(espn.calls) if "?season=" in url)
            assert espn.kwargs[asked]["timeout"] == 8


class TestCoreSeasonIsKept:
    """Favorites asks once per team, each time it rebuilds."""

    PATH = "basketball/wnba"

    def asked(self, espn):
        return len(espn.urls("/season$"))

    def test_a_good_answer_is_asked_for_once(self, espn):
        espn.on(SEASON, load("season_WNBA.json"))
        first = espn_api.core_season(self.PATH)
        assert espn_api.core_season(self.PATH) == first
        assert self.asked(espn) == 1

    def test_each_league_has_its_own(self, espn):
        espn.on(SEASON, load("season_WNBA.json"))
        espn_api.core_season(self.PATH)
        espn_api.core_season("basketball/nba")
        assert self.asked(espn) == 2

    def test_it_asks_again_after_a_few_minutes(self, espn, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(espn_api.time, "monotonic", lambda: now[0])
        espn.on(SEASON, load("season_WNBA.json"))
        espn_api.core_season(self.PATH)
        now[0] += espn_api.CORE_SEASON_CACHE_SECONDS - 1
        espn_api.core_season(self.PATH)
        assert self.asked(espn) == 1
        now[0] += 1
        espn_api.core_season(self.PATH)
        assert self.asked(espn) == 2

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON, {}], ids=["timeout", "500", "not_json", "nothing"])
    def test_a_failure_is_not_kept(self, espn, reply):
        espn.on(SEASON, reply)
        with pytest.raises(ApiError):
            espn_api.core_season(self.PATH)
        espn.on(SEASON, load("season_WNBA.json"))
        assert espn_api.core_season(self.PATH)["year"] == 2026

    def test_threads_asking_at_once(self, espn):
        espn.on(SEASON, load("season_WNBA.json"))
        with ThreadPoolExecutor(8) as pool:
            years = list(pool.map(lambda _: espn_api.core_season(self.PATH)["year"], range(32)))
        assert years == [2026] * 32

    def test_favorites_ask_once_per_league(self, espn):
        espn.on(SEASON, load("season_WNBA.json"))
        espn.on(r"/teams/\w+", load("team_WNBA_8.json"))
        for team in ("8", "14", "3"):
            espn_api.get_team_info("WNBA", team, home_venue=False)
        assert self.asked(espn) == 1


class TestRoster:
    def test_url(self, espn):
        espn.on("/roster", load("roster_NFL_9.json"))
        espn_api.get_team_roster("NFL", "9")
        assert espn.calls == [f"{SITE}/football/nfl/teams/9/roster"]

    def test_grouped_shape_with_float_heights_and_weights(self, espn):
        raw = load("roster_NFL_9.json")["athletes"]
        assert isinstance(raw[0]["items"][0]["height"], float)
        espn.on("/roster", {"athletes": raw})
        players = espn_api.get_team_roster("NFL", "9")
        assert players[0] == {"jersey": "65", "name": "Aaron Banks", "position": "G", "age": "29",
                              "height": "6'5\"", "weight": "325 lbs"}
        assert len(players) == sum(len(group["items"]) for group in raw)

    def test_flat_shape(self, espn):
        raw = load("roster_NBA_15.json")["athletes"]
        assert "items" not in raw[0]
        espn.on("/roster", {"athletes": raw})
        players = espn_api.get_team_roster("NBA", "15")
        assert players[0] == {"jersey": "15", "name": "Nate Ament", "position": "F", "age": "19",
                              "height": "6'10\"", "weight": "211 lbs"}
        assert len(players) == len(raw)

    def test_no_height_stays_blank_not_0_0(self, espn):
        espn.on("/roster", {"athletes": [{"displayName": "A", "position": "QB", "height": 0, "weight": None}]})
        player = espn_api.get_team_roster("NFL", "9")[0]
        assert (player["position"], player["height"], player["weight"]) == ("QB", "", "")

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_roster("NFL", "") == []
        assert espn.calls == []


class TestTeamNews:
    def test_the_url_is_news_with_a_team_parameter(self, espn):
        """/teams/9/news answers 200 with {}; only /news?team=9 has articles."""
        espn.on("/news", load("team_news_NFL_9.json"))
        espn_api.get_team_news("NFL", "9")
        assert espn.calls == [f"{SITE}/football/nfl/news?team=9&limit=15"]

    def test_articles(self, espn):
        espn.on("/news", load("team_news_NFL_9.json"))
        first, second = espn_api.get_team_news("NFL", "9", limit=2)
        assert first["headline"] == "Stephen A.: Right now, the Bears look like the NFL's best team"
        assert first["web_url"] == "https://www.espn.com/video/clip/_/id/50369297/right-now-bears-look-nfl-best-team"
        assert first["published"] == "2026-11-03T15:50:13Z"
        assert second["byline"] == "NFL Nation"
        assert second["description"].startswith("How does every NFL team stack up")
        assert espn.calls == [f"{SITE}/football/nfl/news?team=9&limit=2"]

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_news("NFL", "") == []
        assert espn.calls == []


class TestTransactions:
    def test_league_url_and_paging(self, espn):
        espn.on("/transactions", load("transactions_NFL.json"))
        rows, has_more = espn_api.get_transactions("NFL", limit=5, page=2)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=5&page=2"]
        assert has_more is True
        assert rows[0] == {"date": "2026-11-02", "team": "ATL",
                           "description": "Waived OLB Jared Ivey. Released OLB Drake Jackson from the practice squad.",
                           "type": "", "player": "", "position": ""}

    def test_the_last_page_has_no_more(self, espn):
        espn.on("/transactions", load("transactions_NFL.json"))
        assert espn_api.get_transactions("NFL", page=407)[1] is False

    def test_team_filter(self, espn):
        espn.on("/transactions", load("transactions_NFL_9.json"))
        rows, _ = espn_api.get_transactions("NFL", team_id="9", limit=5)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=5&page=1&team=9"]
        assert rows[0]["team"] == ""  # ESPN leaves it off a team-filtered list
        assert rows[0]["date"] == "2026-10-26"

    def test_items_key_and_a_bad_date(self, espn):
        espn.on("/transactions", {"items": [{"timestamp": "bad-date-here", "description": "x", "team": "text"}]})
        rows, has_more = espn_api.get_transactions("NFL")
        assert (rows[0]["date"], rows[0]["team"], has_more) == ("bad-date-h", "", False)

    def test_unknown_league(self, espn):
        assert espn_api.get_transactions("CRICKET") == ([], False)
        assert espn.calls == []


class TestTeamTransactions:
    def test_url_and_rows(self, espn):
        espn.on("/transactions", load("transactions_NFL_9.json"))
        rows = espn_api.get_team_transactions("NFL", "9", limit=5)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?team=9&limit=5"]
        assert rows[0]["date"] == "2026-10-26"
        assert rows[1]["description"].startswith("Activated RB Josh Jacobs")

    def test_a_bad_date_keeps_what_it_can(self, espn):
        espn.on("/transactions", {"transactions": [{"date": "bad-date-here", "description": "x"}, {"description": "y"}]})
        assert [r["date"] for r in espn_api.get_team_transactions("NFL", "9")] == ["bad-date-h", ""]

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_transactions("NFL", "") == []
        assert espn.calls == []
