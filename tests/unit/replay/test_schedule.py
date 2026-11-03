"""get_team_schedule on real schedules: its URLs, its local dates, its season fallbacks."""
import re
from datetime import datetime, timedelta, timezone

import pytest

import espn_api

from .support import FakeResponse, HTTP_500, TIMEOUT, load

SITE = espn_api.BASE_URL


def only_regular_season(payload):
    """ESPN returns a different list per seasontype; empty for the other two here."""
    return lambda url: payload if "seasontype=2" in url else {"events": []}


class TestUrls:
    @pytest.mark.parametrize("league,path,team", [
        ("NBA", "basketball/nba", "15"),
        ("NHL", "hockey/nhl", "1"),
        ("MLB", "baseball/mlb", "10"),
        ("NCAAH", "hockey/mens-college-hockey", "1"),
        ("NCAAWH", "hockey/womens-college-hockey", "1"),
        ("NCAAM", "basketball/mens-college-basketball", "275"),
        ("NCAAWB", "basketball/womens-college-basketball", "275"),
    ])
    def test_these_leagues_ask_for_each_season_type(self, espn, league, path, team):
        espn.on("/schedule", load("schedule_NBA_15.json"))
        espn_api.get_team_schedule(league, team, season=2025)
        assert espn.calls == [f"{SITE}/{path}/teams/{team}/schedule?season=2025&seasontype={t}" for t in (1, 2, 3)]

    @pytest.mark.parametrize("league,path", [("NFL", "football/nfl"), ("NCAAF", "football/college-football")])
    def test_football_asks_for_the_regular_season(self, espn, league, path):
        espn.on("/schedule", load("schedule_NFL_9.json"))
        espn_api.get_team_schedule(league, "9", season=2025)
        assert espn.calls == [f"{SITE}/{path}/teams/9/schedule?season=2025&seasontype=2"]

    def test_the_current_season_is_used_when_none_is_given(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", load("schedule_NBA_15.json"))
        espn_api.get_team_schedule("NBA", "15")
        assert all("season=2027&" in url for url in espn.calls), espn.calls

    def test_other_leagues_read_a_month_of_scoreboard_never_a_range(self, espn, freeze_now):
        freeze_now(datetime(2026, 10, 15, 12))
        espn.on("/scoreboard", {"events": []})
        espn_api.get_team_schedule("WNBA", "8", days_ahead=30, days_behind=30)
        assert espn.calls == [f"{SITE}/basketball/wnba/scoreboard?dates={m}&limit=1000" for m in ("202609", "202610", "202611")]

    def test_a_college_scoreboard_league_keeps_its_group_but_widens_the_limit(self, espn, monkeypatch):
        """The scoreboard path no longer runs for any college league, but it's built to."""
        monkeypatch.setitem(espn_api.LEAGUES, "NCAAX", "basketball/mens-college-basketball")
        monkeypatch.setattr(espn_api, "college_scoreboard_params", lambda *a, **k: ["groups=50", "limit=400"])
        espn.on("/scoreboard", {"events": []})
        espn_api.get_team_schedule("NCAAX", "1")
        assert all("groups=50&limit=1000" in url for url in espn.calls), espn.calls


class TestLocalDates:
    """ESPN's dates are UTC, so an evening game is tomorrow in UTC. local_zone fixes the
    offset, or these would prove nothing on CI, which runs in UTC."""

    def nfl(self, espn):
        espn.on("/schedule", load("schedule_NFL_9.json"))
        return espn_api.get_team_schedule("NFL", "9")

    def test_a_thursday_night_game_is_thursday_in_the_us(self, espn, local_zone):
        local_zone(-6)
        game = next(g for g in self.nfl(espn) if g["game_id"] == "401872948")
        assert load_date("schedule_NFL_9.json", "401872948") == "2026-09-25T00:15Z"
        assert game["date"] == "2026-09-24"
        assert game["date_display"] == "Thu, Sep 24"

    def test_the_same_game_in_tokyo_is_friday(self, espn, local_zone):
        local_zone(9)
        game = next(g for g in self.nfl(espn) if g["game_id"] == "401872948")
        assert (game["date"], game["date_display"]) == ("2026-09-25", "Fri, Sep 25")

    def test_a_game_with_no_time_set_keeps_espns_date(self, espn, local_zone):
        local_zone(-6)
        raw = load("schedule_NFL_9.json")
        tbd = next(e for e in raw["events"] if e.get("timeValid") is False)
        game = next(g for g in self.nfl(espn) if g["game_id"] == tbd["id"])
        assert game["date"] == tbd["date"][:10]

    @pytest.mark.parametrize("offset,expected", [(-6, True), (0, False)])
    def test_is_today_uses_the_local_date(self, espn, local_zone, freeze_now, offset, expected):
        """The game is at 7 PM Central on the 26th, which is the 27th in UTC."""
        local_zone(offset)
        freeze_now(datetime(2026, 10, 26, 20))
        real = load("schedule_NBA_15.json")
        assert real["events"][0]["date"] == "2026-10-27T00:00Z"
        espn.on("/schedule", only_regular_season(real))
        rows = espn_api.get_team_schedule("NBA", "15", season=2027)
        assert next(g for g in rows if g["game_id"] == real["events"][0]["id"])["is_today"] is expected

    def test_is_today_true_on_the_day(self, espn):
        """Built from the real clock: the game is at this moment, in whatever zone this is."""
        now = datetime.now(timezone.utc)
        event = load("schedule_NFL_9.json")["events"][0]
        event["date"] = now.strftime("%Y-%m-%dT%H:%MZ")
        event["timeValid"] = True
        espn.on("/schedule", {"events": [event]})
        assert espn_api.get_team_schedule("NFL", "9", season=2026)[0]["is_today"] is True


def load_date(fixture, game_id):
    return next(e["date"] for e in load(fixture)["events"] if e["id"] == game_id)


class TestRows:
    def test_home_game(self, espn, local_zone):
        local_zone(-6)
        espn.on("/schedule", load("schedule_NFL_9.json"))
        game = next(g for g in espn_api.get_team_schedule("NFL", "9") if g["game_id"] == "401873007")
        assert game == {
            "date": "2026-10-18", "date_display": "Sun, Oct 18", "opponent": "Dallas Cowboys", "home_away": "vs",
            "time": "Final", "status": "Final", "venue": "Lambeau Field", "home_score": "23", "away_score": "13",
            "game_id": "401873007", "is_today": False,
        }

    def test_away_game_with_scores_in_displayvalue(self, espn, local_zone):
        local_zone(-6)
        espn.on("/schedule", only_regular_season(load("schedule_MLB_10.json")))
        game = espn_api.get_team_schedule("MLB", "10", season=2026)[0]
        assert (game["opponent"], game["home_away"], game["venue"]) == ("San Francisco Giants", "@", "Oracle Park")
        assert (game["home_score"], game["away_score"]) == ("0", "7")

    def test_rows_are_in_date_order(self, espn):
        espn.on("/schedule", only_regular_season(load("schedule_NBA_15.json")))
        dates = [g["date"] for g in espn_api.get_team_schedule("NBA", "15", season=2027)]
        assert dates == sorted(dates) and dates

    def test_a_past_season_shows_the_year_and_the_current_one_does_not(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", load("schedule_NFL_9.json"))
        past = espn_api.get_team_schedule("NFL", "9", season=2025)
        assert past and all(re.search(r", 20\d\d$", g["date_display"]) for g in past)
        current = espn_api.get_team_schedule("NFL", "9", season=2026)
        assert current and not any(re.search(r", 20\d\d$", g["date_display"]) for g in current)

    def test_a_game_this_team_is_not_in_is_skipped(self, espn):
        espn.on("/schedule", load("schedule_NFL_9.json"))
        assert espn_api.get_team_schedule("NFL", "99999") == []

    @pytest.mark.parametrize("bad", [{"date": ""}, {"date": "not a date"}, {"competitions": []}])
    def test_an_unusable_event_is_skipped_and_the_rest_kept(self, espn, bad):
        good = load("schedule_NFL_9.json")["events"]
        espn.on("/schedule", {"events": [dict(good[0], **bad)] + good[1:]})
        ids = {g["game_id"] for g in espn_api.get_team_schedule("NFL", "9", season=2026)}
        assert ids == {e["id"] for e in good[1:]}

    def test_a_status_with_only_detail_is_used_and_no_status_reads_tbd(self, espn):
        event = load("schedule_NFL_9.json")["events"][0]
        event["competitions"][0]["status"] = {"type": {"detail": "Sun 1:00 PM"}}
        espn.on("/schedule", {"events": [event]})
        assert espn_api.get_team_schedule("NFL", "9", season=2026)[0]["time"] == "Sun 1:00 PM"
        event["competitions"][0]["status"] = {"type": {}}
        game = espn_api.get_team_schedule("NFL", "9", season=2026)[0]
        assert (game["time"], game["status"]) == ("TBD", "Unknown")

    def test_a_plain_score_is_read(self, espn):
        event = load("schedule_NFL_9.json")["events"][0]
        for competitor, score in zip(event["competitions"][0]["competitors"], (21, 14)):
            competitor["score"] = score
        espn.on("/schedule", {"events": [event]})
        game = espn_api.get_team_schedule("NFL", "9", season=2026)[0]
        assert {game["home_score"], game["away_score"]} == {"21", "14"}

    def test_unsortable_dates_keep_espns_order(self, espn):
        espn.on("/schedule", only_regular_season({"events": [{"date": None}, {"date": "x"}]}))
        assert espn_api.get_team_schedule("NBA", "15", season=2027) == []

    def test_unknown_league(self, espn):
        assert espn_api.get_team_schedule("CRICKET", "1") == []
        assert espn.calls == []


class TestSeasonFallback:
    def test_an_empty_current_season_falls_back_to_the_last_one(self, espn, freeze_now):
        freeze_now(datetime(2026, 7, 15, 12))
        real = load("schedule_NBA_15.json")
        espn.on("/schedule", lambda url: real if "season=2026" in url and "seasontype=2" in url else {"events": []})
        rows = espn_api.get_team_schedule("NBA", "15")
        assert any("season=2027" in url for url in espn.calls)
        assert rows and all(g["date_display"].endswith(", 2026") for g in rows)

    def test_a_season_you_asked_for_does_not_fall_back(self, espn):
        espn.on("/schedule", {"events": []})
        assert espn_api.get_team_schedule("NBA", "15", season=2020) == []
        assert all("season=2020" in url for url in espn.calls)


class TestFailures:
    @pytest.mark.parametrize("reply", [HTTP_500, FakeResponse(status=404)])
    def test_football_http_failure_is_empty(self, espn, reply):
        espn.on("/schedule", reply)
        assert espn_api.get_team_schedule("NFL", "9") == []

    def test_a_football_timeout_reaches_the_caller_to_report(self, espn):
        espn.on("/schedule", TIMEOUT)
        with pytest.raises(type(TIMEOUT)):
            espn_api.get_team_schedule("NFL", "9")

    def test_a_timeout_on_one_basketball_season_type_keeps_the_others(self, espn):
        real = load("schedule_NBA_15.json")
        espn.on("/schedule", lambda url: TIMEOUT if "seasontype=1" in url else (real if "seasontype=2" in url else {"events": []}))
        assert len(espn_api.get_team_schedule("NBA", "15", season=2027)) == len({e["id"] for e in real["events"]})

    def test_scoreboard_path_failure_is_empty(self, espn):
        espn.on("/scoreboard", TIMEOUT)
        assert espn_api.get_team_schedule("WNBA", "8") == []


class TestScoreboardPath:
    """WNBA and soccer: a window of months, filtered to one team and trimmed to the days asked."""

    def board(self):
        """A real NWSL scoreboard, its first game moved to tomorrow and second far away."""
        data = load("scoreboard_NWSL.json")
        first, second = data["events"]
        now = datetime.now(timezone.utc)
        first["date"] = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ")
        second["date"] = (now + timedelta(days=300)).strftime("%Y-%m-%dT%H:%MZ")
        return data

    def test_only_this_teams_games_within_the_window(self, espn):
        data = self.board()
        for event in data["events"]:
            event["competitions"][0]["competitors"][0]["team"]["id"] = "TEAM"
        espn.on("/scoreboard", data)
        rows = {g["game_id"]: g for g in espn_api.get_team_schedule("NWSL", "TEAM", days_ahead=30, days_behind=30)}
        first, second = data["events"]
        assert first["id"] in rows and second["id"] not in rows
        competitors = first["competitions"][0]["competitors"]
        away = next(c for c in competitors if c["homeAway"] == "away")
        home = next(c for c in competitors if c["homeAway"] == "home")
        game = rows[first["id"]]
        if home["team"]["id"] == "TEAM":
            assert (game["home_away"], game["opponent"]) == ("vs", away["team"]["displayName"])
        else:
            assert (game["home_away"], game["opponent"]) == ("@", home["team"]["displayName"])
        assert game["venue"] == first["competitions"][0]["venue"]["fullName"]

    def test_another_team_gets_nothing(self, espn):
        espn.on("/scoreboard", self.board())
        assert espn_api.get_team_schedule("NWSL", "not-a-team") == []


class TestParseScheduleFromApi:
    URL = f"{SITE}/soccer/usa.nwsl/scoreboard?dates=202610"
    TODAY = datetime(2026, 10, 3)

    def event(self):
        return load("scoreboard_NWSL.json")["events"][0]

    def parse(self, espn, event, season=None, today=None):
        espn.on("/scoreboard", {"events": [event]})
        team_id = event["competitions"][0]["competitors"][0]["team"]["id"]
        return espn_api.parse_schedule_from_api(self.URL, team_id, today or self.TODAY, season)

    def test_a_row(self, espn):
        event = self.event()
        row = self.parse(espn, event)[0]
        comp = event["competitions"][0]
        home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
        away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
        assert row["game_id"] == event["id"]
        assert row["status"] == comp["status"]["type"]["description"]
        assert (row["home_score"], row["away_score"]) == (home["score"], away["score"])
        # The team asked for is the first competitor; the other is the opponent.
        team_is_home = comp["competitors"][0] is home
        assert row["home_away"] == ("vs" if team_is_home else "@")
        assert row["opponent"] == (away if team_is_home else home)["team"]["displayName"]

    def test_past_season_shows_the_year(self, espn):
        assert re.search(r", \d{4}$", self.parse(espn, self.event(), season=2001)[0]["date_display"])

    def test_bad_date_falls_back_to_today(self, espn):
        event = self.event()
        event["date"] = "garbage"
        row = self.parse(espn, event)[0]
        assert row["date"] == "2026-10-03" and row["is_today"] is True

    def test_missing_date_falls_back_to_today(self, espn):
        event = self.event()
        del event["date"]
        assert self.parse(espn, event)[0]["date"] == "2026-10-03"

    def test_dict_scores_and_detail_only_status(self, espn):
        event = self.event()
        comp = event["competitions"][0]
        for competitor in comp["competitors"]:
            competitor["score"] = {"displayValue": "3"}
        comp["status"] = {"type": {"detail": "Sat 7:00 PM"}}
        row = self.parse(espn, event)[0]
        assert (row["home_score"], row["away_score"], row["time"]) == ("3", "3", "Sat 7:00 PM")

    def test_no_competitions_skipped(self, espn):
        event = self.event()
        event["competitions"] = []
        espn.on("/scoreboard", {"events": [event]})
        assert espn_api.parse_schedule_from_api(self.URL, "1", self.TODAY) == []

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_failures_are_empty(self, espn, reply):
        espn.on("/scoreboard", reply)
        assert espn_api.parse_schedule_from_api(self.URL, "1", self.TODAY) == []
