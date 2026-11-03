"""Scoreboards, news, rankings, golf and the World Cup on real payloads."""
from datetime import date, datetime

import pytest
import pytz

import espn_api
import settings

from .support import FakeResponse, HTTP_500, TIMEOUT, load

SITE = espn_api.BASE_URL


class TestScoreboardUrls:
    def url(self, espn, *args, **kwargs):
        espn.on("/scoreboard", load("scoreboard_events_by_status.json"))
        espn_api.get_scores(*args, **kwargs)
        return espn.calls[0]

    @pytest.mark.parametrize("args,kwargs,expected", [
        (("NBA",), {}, "basketball/nba/scoreboard"),
        (("NBA",), {"date": date(2026, 11, 3)}, "basketball/nba/scoreboard?dates=20261103"),
        (("NFL",), {"week": 5, "season": 2025, "seasontype": 3}, "football/nfl/scoreboard?week=5&dates=2025&seasontype=3"),
        (("NFL",), {"week": 5, "season": 2025}, "football/nfl/scoreboard?week=5&dates=2025&seasontype=2"),
        (("NFL",), {"week": 5}, "football/nfl/scoreboard?week=5"),
        (("NFL",), {"season": 2025}, "football/nfl/scoreboard?season=2025"),
        (("NBA",), {"week": 5, "season": 2025}, "basketball/nba/scoreboard"),
        (("NCAAM",), {}, "basketball/mens-college-basketball/scoreboard?groups=50&limit=400"),
        (("NCAAWB",), {"date": date(2026, 11, 3)}, "basketball/womens-college-basketball/scoreboard?dates=20261103&groups=50&limit=400"),
        (("NCAAF",), {}, "football/college-football/scoreboard?groups=90&limit=400"),
    ])
    def test_each_shape(self, espn, args, kwargs, expected):
        assert self.url(espn, *args, **kwargs) == f"{SITE}/{expected}"

    def test_the_football_coverage_setting_picks_the_group(self, espn):
        settings.set("ncaaf_coverage", "fbs")
        assert self.url(espn, "NCAAF") == f"{SITE}/football/college-football/scoreboard?groups=80&limit=400"

    def test_an_empty_division_one_week_retries_as_fbs(self, espn):
        real = load("bowls_NCAAF.json")
        espn.on("groups=90", {"events": []}).on("groups=80", real)
        games = espn_api.get_scores("NCAAF", seasontype=3)
        assert [u.split("?")[1] for u in espn.calls] == ["seasontype=3&groups=90&limit=400", "seasontype=3&groups=80&limit=400"]
        assert len(games) == len(real["events"])

    def test_no_retry_for_fbs_coverage(self, espn):
        settings.set("ncaaf_coverage", "fbs")
        espn.on("groups=80", {"events": []})
        assert espn_api.get_scores("NCAAF") == []
        assert len(espn.calls) == 1

    def test_a_failed_retry_leaves_it_empty(self, espn):
        espn.on("groups=90", {"events": []}).on("groups=80", HTTP_500)
        assert espn_api.get_scores("NCAAF") == []


class TestScoreboardGames:
    @pytest.fixture
    def games(self, espn):
        espn.on("/scoreboard", load("scoreboard_events_by_status.json"))
        return espn_api.get_scores("NBA")

    def test_every_real_event_comes_through(self, games):
        raw = load("scoreboard_events_by_status.json")["events"]
        assert {g["id"] for g in games} == {e["id"] for e in raw}

    def test_sections_are_in_order(self, games):
        sections = [espn_api.game_section(g) for g in games]
        assert sections == ["in_progress"] * 4 + ["upcoming"] + ["completed"] * 2 + ["postponed"]
        names = {g["status_name"]: espn_api.game_section(g) for g in games}
        assert names["STATUS_DELAYED"] == "in_progress"
        assert names["STATUS_POSTPONED"] == "postponed"
        assert names["STATUS_FORFEIT"] == "completed"

    def test_a_game(self, games):
        scheduled = next(g for g in games if g["status_name"] == "STATUS_SCHEDULED")
        raw = next(e for e in load("scoreboard_events_by_status.json")["events"] if e["id"] == scheduled["id"])
        comp = raw["competitions"][0]
        assert scheduled["name"] == raw["name"]
        assert scheduled["date"] == raw["date"]
        assert scheduled["state"] == "pre"
        assert scheduled["status"] == comp["status"]["type"]["description"]
        assert scheduled["competitions"][0]["id"] == comp["id"]
        home = next(t for t in scheduled["teams"] if t["home_away"] == "home")
        assert home == {"name": "Zips", "abbreviation": "AKR", "score": "0", "record": "1-7", "home_away": "home"}

    def test_a_0_0_record_says_nothing(self, espn):
        event = load("scoreboard_events_by_status.json")["events"][0]
        event["competitions"][0]["competitors"][0]["records"] = [{"type": "total", "summary": "0-0"}]
        espn.on("/scoreboard", {"events": [event]})
        assert espn_api.get_scores("NBA")[0]["teams"][0]["record"] == ""

    def test_the_record_is_matched_on_type_not_position(self, espn):
        event = load("scoreboard_events_by_status.json")["events"][0]
        event["competitions"][0]["competitors"][0]["records"] = [{"type": "home", "summary": "1-1"}, {"type": "total", "summary": "5-2"}]
        espn.on("/scoreboard", {"events": [event]})
        assert espn_api.get_scores("NBA")[0]["teams"][0]["record"] == "5-2"

    def test_college_names_are_full_and_ranked(self, espn):
        event = load("scoreboard_events_by_status.json")["events"][0]
        first, second = event["competitions"][0]["competitors"]
        first["curatedRank"] = {"current": 4}
        second["curatedRank"] = {"current": 99}  # ESPN's value for unranked
        espn.on("/scoreboard", {"events": [event]})
        home, away = espn_api.get_scores("NCAAM")[0]["teams"]
        assert home["name"] == f"#4 {first['team']['displayName']}"
        assert away["name"] == second["team"]["displayName"]

    def test_a_status_with_only_detail(self, espn):
        event = load("scoreboard_events_by_status.json")["events"][0]
        event["competitions"][0]["status"] = {"type": {"detail": "Halftime"}}
        espn.on("/scoreboard", {"events": [event]})
        assert espn_api.get_scores("NBA")[0]["start_time"] == "Halftime"

    def test_an_event_without_competitions_is_skipped(self, espn):
        espn.on("/scoreboard", {"events": [{"id": "1", "competitions": []}]})
        assert espn_api.get_scores("NBA") == []

    def test_unknown_league(self, espn):
        assert espn_api.get_scores("CRICKET") == []
        assert espn.calls == []


class TestFreshenLiveGames:
    NOW = pytz.utc.localize(datetime(2026, 10, 10, 1, 30))

    def week_game(self, status="STATUS_IN_PROGRESS", state="in", start="2026-10-10T00:00Z", score="6"):
        return {"id": "G", "status_name": status, "state": state, "date": start,
                "teams": [{"name": "Aggies", "score": score}]}

    def test_a_live_game_comes_from_the_daily_board(self, espn):
        """ESPN files a game under its Eastern date: 8 PM on the 9th, not the UTC 10th."""
        event = load("scoreboard_events_by_status.json")["events"][0]
        event["id"] = "G"
        espn.on("dates=20261009", {"events": [event]})
        games = espn_api.freshen_live_games("NFL", [self.week_game()], now=self.NOW)
        assert espn.calls == [f"{SITE}/football/nfl/scoreboard?dates=20261009"]
        assert games[0]["teams"][0]["name"] != "Aggies"

    @pytest.mark.parametrize("game", [
        {"status": "STATUS_FINAL", "state": "post"},
        {"status": "STATUS_POSTPONED", "state": "pre"},
        {"start": "2026-10-11T00:00Z", "state": "pre", "status": "STATUS_SCHEDULED"},
        {"start": "no date"},
    ])
    def test_no_request_without_a_game_under_way(self, espn, game):
        original = [self.week_game(**game)]
        assert espn_api.freshen_live_games("NFL", original, now=self.NOW) is original
        assert espn.calls == []

    def test_a_scheduled_game_past_its_start_counts_as_under_way(self, espn):
        espn.on("/scoreboard", {"events": []})
        espn_api.freshen_live_games("NFL", [self.week_game("STATUS_SCHEDULED", "pre")], now=self.NOW)
        assert len(espn.calls) == 1

    def test_seconds_in_the_start_time(self, espn):
        espn.on("/scoreboard", {"events": []})
        espn_api.freshen_live_games("NFL", [self.week_game(start="2026-10-10T00:00:30Z")], now=self.NOW)
        assert len(espn.calls) == 1

    def test_a_failed_refresh_keeps_the_weeks_games(self, espn):
        espn.on("/scoreboard", TIMEOUT)
        original = [self.week_game()]
        assert espn_api.freshen_live_games("NFL", original, now=self.NOW) is original

    def test_a_game_not_on_the_board_keeps_the_weeks_version(self, espn):
        other = load("scoreboard_events_by_status.json")["events"][0]
        espn.on("/scoreboard", {"events": [other]})
        games = espn_api.freshen_live_games("NFL", [self.week_game()], now=self.NOW)
        assert games[0]["teams"][0]["name"] == "Aggies"

    def test_a_bad_game_cannot_cost_the_week(self, espn):
        original = [self.week_game(), "not a game"]
        assert espn_api.freshen_live_games("NFL", original, now=self.NOW) is original

    def test_now_defaults_to_the_clock(self, espn):
        original = [self.week_game(start="2099-01-01T00:00Z", state="pre", status="STATUS_SCHEDULED")]
        assert espn_api.freshen_live_games("NFL", original) is original


class TestLiveDetail:
    def test_other_sports_use_the_last_play(self):
        comp = {"situation": {"lastPlay": {"text": "Tatum makes a three"}}}
        assert espn_api.scoreboard_live_detail("NBA", comp) == "Tatum makes a three"

    def test_nothing_to_add(self):
        assert espn_api.scoreboard_live_detail("NBA", {}) is None
        assert espn_api.scoreboard_live_detail("NFL", {}) is None
        assert espn_api.scoreboard_live_detail("MLB", {}) is None

    def test_a_bad_entry_is_no_detail_not_an_exception(self):
        assert espn_api.scoreboard_live_detail("NFL", {"situation": {"down": 1}, "competitors": "bad"}) is None

    def baseball(self, situation):
        return {"competitors": [
            {"homeAway": "home", "score": "3", "team": {"displayName": "Yankees"}},
            {"homeAway": "away", "score": "2", "team": {"displayName": "Red Sox"}},
        ], "situation": situation}

    @pytest.mark.parametrize("bases,text", [
        ({}, "Bases empty"),
        ({"onFirst": True}, "Runner on 1st"),
        ({"onSecond": True}, "Runner on 2nd"),
        ({"onThird": True}, "Runner on 3rd"),
        ({"onFirst": True, "onSecond": True}, "Runners on 1st and 2nd"),
        ({"onFirst": True, "onThird": True}, "Runners on 1st and 3rd"),
        ({"onSecond": True, "onThird": True}, "Runners on 2nd and 3rd"),
        ({"onFirst": True, "onSecond": True, "onThird": True}, "Bases loaded"),
    ])
    def test_baseball_bases(self, bases, text):
        situation = dict(bases, balls=1, strikes=2, outs=1, batter={"athlete": {"displayName": "Judge"}},
                         lastPlay={"text": "Strike two"})
        assert espn_api.scoreboard_live_detail("MLB", self.baseball(situation)) == (
            f"Red Sox 2 at Yankees 3\n{text} | 1-2 count, 1 out | At bat: Judge\nLast: Strike two")

    def test_baseball_long_play_and_no_batter(self):
        detail = espn_api.scoreboard_live_detail("MLB", self.baseball({"outs": 2, "lastPlay": {"text": "x" * 60}}))
        assert "0-0 count, 2 outs | At bat: Unknown" in detail
        assert detail.endswith("Last: " + "x" * 47 + "...")

    def test_baseball_needs_two_teams_on_a_board(self):
        extract = espn_api.extract_baseball_enhanced_display
        assert extract({}) is None
        assert extract({"competitions": [{"competitors": [{}]}]}) is None
        assert extract({"competitions": [{"competitors": [{"homeAway": "home"}, {"homeAway": "home"}]}]}) is None
        assert extract({"header": {"competitions": [self.baseball({})]}}) is None  # no situation
        assert extract({"competitions": "bad"}) is None


class TestSeasons:
    @pytest.mark.parametrize("league,moment,season", [
        ("NBA", datetime(2026, 7, 1), 2027), ("NBA", datetime(2026, 6, 30), 2026),
        ("NHL", datetime(2026, 11, 3), 2027), ("NCAAH", datetime(2027, 1, 15), 2027),
        ("NFL", datetime(2027, 2, 1), 2026), ("NFL", datetime(2027, 3, 1), 2027), ("NCAAF", datetime(2026, 11, 3), 2026),
        ("MLB", datetime(2026, 1, 1), 2026), ("WNBA", datetime(2026, 12, 1), 2026), ("EPL", datetime(2026, 9, 1), 2026),
    ])
    def test_current_year(self, freeze_now, league, moment, season):
        freeze_now(moment)
        assert espn_api.get_current_season_year(league) == season

    def test_season_lists(self, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        seasons = espn_api.get_available_seasons("NHL")
        assert seasons[0] == (2027, "2026-27 Season")
        assert seasons[-1] == (2001, "2000-01 Season")
        assert espn_api.get_available_seasons("NCAAWH")[-1] == (2012, "2011-12 Season")
        assert espn_api.get_available_seasons("NCAAF")[-1] == (2005, "2005 Season")
        assert espn_api.get_available_seasons("MLB")[:1] == [(2026, "2026 Season")]
        assert espn_api.get_available_seasons("NFL")[-1] == (2001, "2001 Season")
        wnba = espn_api.get_available_seasons("WNBA")
        assert (wnba[0], len(wnba)) == ((2026, "2026 Season"), 10)

    def test_leagues(self):
        assert espn_api.get_leagues()[:3] == ["NFL", "NBA", "MLB"]
        assert "WC2026" in espn_api.get_leagues()


class TestNews:
    def test_url_and_articles(self, espn):
        espn.on("/news", load("news_NFL.json"))
        first, second = espn_api.get_news("NFL", 20)
        assert espn.calls == [f"{SITE}/football/nfl/news?limit=20"]
        assert first["headline"].startswith("Knockout league pickups")
        assert first["byline"] == "Tristan H. Cockcroft"
        assert first["web_url"].startswith("https://www.espn.com/fantasy/football/story/")
        assert first["mobile_url"] == "http://m.espn.go.com/wireless/story?storyId=50370154"
        assert first["published"] == "2026-11-03T18:13:34Z"
        assert second["mobile_url"] == ""

    def test_espns_default_page_size_needs_no_parameter(self, espn):
        espn.on("/news", load("news_NFL.json"))
        espn_api.get_news("NFL", 6)
        assert espn.calls == [f"{SITE}/football/nfl/news"]

    def test_a_placeholder_in_a_description_is_cleaned(self, espn):
        data = load("news_NFL.json")
        data["articles"][0]["description"] = "{{123}} threw for 300 yards"
        espn.on("/news", data)
        assert "{{" not in espn_api.get_news("NFL", 20)[0]["description"]

    def test_unknown_league(self, espn):
        assert espn_api.get_news("CRICKET") == []
        assert espn.calls == []


class TestRankings:
    def test_url_and_polls(self, espn):
        espn.on("/rankings", load("rankings_NCAAF.json"))
        polls = espn_api.get_rankings("NCAAF")["polls"]
        assert espn.calls == [f"{SITE}/football/college-football/rankings"]
        assert [p["name"] for p in polls] == ["AP Top 25", "AFCA Coaches Poll"]
        top = polls[0]["ranks"][0]
        assert (top["current"], top["team"]["nickname"], top["recordSummary"]) == (1, "Miami", "8-0")

    def test_unknown_league(self, espn):
        assert espn_api.get_rankings("CRICKET") == {"polls": []}
        assert espn.calls == []


class TestGolf:
    def test_schedule(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        espn.on("/scoreboard", load("golf_schedule_PGA.json"))
        cancelled, played, upcoming = espn_api.get_golf_schedule("PGA")
        assert cancelled == {"name": "The Sentry", "start_date": "2026-01-08", "end_date": "2026-01-11",
                             "status": "Canceled", "state": "post", "winner": ""}
        assert (played["name"], played["winner"], played["status"]) == ("Sony Open in Hawaii", "Chris Gotterup (-16)", "Final")
        assert (upcoming["state"], upcoming["winner"]) == ("pre", "")

    def test_leaderboard(self, espn):
        espn.on("/golf/pga/scoreboard", load("golf_scoreboard_PGA.json"))
        board = espn_api.get_golf_leaderboard("PGA")
        assert espn.calls == [f"{SITE}/golf/pga/scoreboard"]
        assert board["name"] == "World Wide Technology Championship"
        assert (board["date"], board["end_date"], board["round_num"]) == ("2026-11-05", "2026-11-08", 0)
        assert board["players"][0] == {"position": 1, "name": "Brice Garnett", "country": "USA", "total_score": "E", "rounds": []}

    def test_leaderboard_with_rounds_played(self, espn):
        """A final from the schedule fixture, so its golfers have real rounds."""
        event = load("golf_schedule_PGA.json")["events"][1]
        espn.on("/golf/pga/scoreboard", {"events": [event]})
        leader = espn_api.get_golf_leaderboard("PGA")["players"][0]
        assert leader["name"] == "Chris Gotterup"
        assert leader["rounds"][:2] == ["-7", "-1"]
        lines = event["competitions"][0]["competitors"][0]["linescores"]
        assert len(leader["rounds"]) == len([l for l in lines if "value" in l])

    def test_no_event_this_week(self, espn):
        espn.on("/scoreboard", {"events": []})
        assert espn_api.get_golf_leaderboard("PGA") is None
        espn.on("/scoreboard", {"events": [{"name": "No competitions"}]})
        assert espn_api.get_golf_leaderboard("PGA") is None

    def test_live_tournament_only_while_it_is_being_played(self, espn):
        espn.on("/scoreboard", load("golf_scoreboard_PGA.json"))
        assert espn_api.get_live_golf_tournament("PGA") is None

    def test_live_tournament_has_ties_and_totals(self, espn):
        data = load("golf_schedule_PGA.json")
        event = data["events"][1]
        event["competitions"][0]["status"]["type"]["state"] = "in"
        event["competitions"][0]["status"]["type"]["detail"] = "Round 3"
        espn.on("/scoreboard", {"events": [data["events"][0], event]})
        live = espn_api.get_live_golf_tournament("PGA")
        assert (live["tour"], live["tour_name"], live["name"], live["status"]) == ("PGA", "PGA Tour", "Sony Open in Hawaii", "Round 3")
        assert live["leaders"][0][:2] == ("1", "Chris Gotterup")
        assert live["leaders"][0][2] == "-16"
        assert len(live["leaders"]) == 3

    @pytest.mark.parametrize("call", [espn_api.get_golf_leaderboard, espn_api.get_live_golf_tournament])
    def test_unknown_tour(self, espn, call):
        assert call("CRICKET") is None
        assert espn_api.get_golf_schedule("CRICKET") == []
        assert espn.calls == []


class TestWorldCup:
    def test_standings(self, espn):
        espn.on("/standings", load("worldcup_standings_WC2026.json"))
        groups = espn_api.get_world_cup_standings("WC2026")
        assert espn.calls == ["https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"]
        assert [(g["id"], g["name"], len(g["teams"])) for g in groups] == [("1", "Group A", 4), ("2", "Group B", 4)]
        assert groups[0]["teams"][0] == {
            "team_id": "203", "team_name": "Mexico", "abbreviation": "MEX", "rank": 1, "games_played": 3,
            "wins": 3, "draws": 0, "losses": 0, "goals_for": 6, "goals_against": 0, "goal_difference": 6,
            "points": 9, "advancement_note": "Advance to Round of 32",
        }
        assert [t["rank"] for t in groups[1]["teams"]] == [1, 2, 3, 4]

    def test_scores_day_by_day_without_repeats(self, espn):
        real = load("worldcup_scoreboard_20260620.json")
        espn.on("dates=20260620", real).on("dates=20260621", real).on("dates=20260622", TIMEOUT)
        games = espn_api.get_world_cup_scores_range("WC2026", date(2026, 6, 20), date(2026, 6, 22))
        assert sorted(g["id"] for g in games) == sorted(e["id"] for e in real["events"])
        assert [u.split("dates=")[1] for u in espn.calls] == ["20260620", "20260621", "20260622"]
        assert games[0]["status_name"] == "STATUS_FULL_TIME"

    def test_unknown_league(self, espn):
        assert espn_api.get_world_cup_standings("CRICKET") == []
        assert espn_api.get_world_cup_scores_range("CRICKET", date(2026, 6, 20), date(2026, 6, 20)) == []
        assert espn.calls == []

    def test_no_groups(self, espn):
        espn.on("/standings", FakeResponse({"children": []}))
        assert espn_api.get_world_cup_standings("WWC2027") == []
