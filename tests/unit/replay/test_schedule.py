"""get_team_schedule on real schedules: its URLs, its local dates, its season fallbacks."""
import re
from datetime import datetime, timedelta, timezone

import pytest

import espn_api
from game_labels import schedule_game_is_over, schedule_row_text

from .support import FakeResponse, HTTP_500, TIMEOUT, load

SITE = espn_api.BASE_URL


@pytest.fixture
def no_schedule_league(monkeypatch):
    """Every real league now has a team schedule, so the last-resort path needs a made-up one."""
    monkeypatch.setitem(espn_api.LEAGUES, "UFL", "football/ufl")
    return "UFL"


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
        ("WNBA", "basketball/wnba", "8"),
    ])
    def test_these_leagues_ask_for_each_season_type(self, espn, league, path, team):
        espn.on("/schedule", load("schedule_NBA_15.json"))
        espn_api.get_team_schedule(league, team, season=2025)
        assert espn.calls == [f"{SITE}/{path}/teams/{team}/schedule?season=2025&seasontype={t}" for t in (1, 2, 3)]

    @pytest.mark.parametrize("league,path", [("NFL", "football/nfl"), ("NCAAF", "football/college-football")])
    def test_football_asks_for_each_season_type_regular_first(self, espn, league, path):
        espn.on("/schedule", load("schedule_NFL_9.json"))
        espn_api.get_team_schedule(league, "9", season=2025)
        assert espn.calls == [f"{SITE}/{path}/teams/9/schedule?season=2025&seasontype={t}" for t in (2, 1, 3)]

    def test_the_current_season_is_used_when_none_is_given(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", load("schedule_NBA_15.json"))
        espn_api.get_team_schedule("NBA", "15")
        assert all("season=2027&" in url for url in espn.calls), espn.calls

    @pytest.mark.parametrize("league,path", [
        ("EPL", "soccer/eng.1"), ("MLS", "soccer/usa.1"), ("NWSL", "soccer/usa.nwsl"), ("La Liga", "soccer/esp.1"),
        ("Bundesliga", "soccer/ger.1"), ("Serie A", "soccer/ita.1"), ("Ligue 1", "soccer/fra.1"),
        ("UCL", "soccer/uefa.champions"), ("UEL", "soccer/uefa.europa"), ("Liga MX", "soccer/mex.1"),
        ("CONCACAF", "soccer/concacaf.champions"), ("WC2026", "soccer/fifa.world"), ("WWC2027", "soccer/fifa.wwc"),
    ])
    def test_every_soccer_league_asks_for_results_and_fixtures_with_no_season_type(self, espn, freeze_now, league, path):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", load("schedule_EPL_359_results.json"))
        espn_api.get_team_schedule(league, "359")
        assert espn.calls == [f"{SITE}/{path}/teams/359/schedule?season=2026",
                              f"{SITE}/{path}/teams/359/schedule?fixture=true"]

    def test_a_league_with_no_team_schedule_reads_a_month_of_scoreboard_never_a_range(self, espn, freeze_now, no_schedule_league):
        freeze_now(datetime(2026, 10, 15, 12))
        espn.on("/scoreboard", {"events": []})
        espn_api.get_team_schedule(no_schedule_league, "8", days_ahead=30, days_behind=30)
        assert espn.calls == [f"{SITE}/football/ufl/scoreboard?dates={m}&limit=1000" for m in ("202609", "202610", "202611")]


class TestFootballSeason:
    """The whole season as ESPN gives it: Seattle's 2025 ended in the Super Bowl, Alabama's in
    the playoff. These rows are read aloud as they are, so they're checked as whole strings."""

    def seahawks(self, espn, local_zone, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        local_zone(-6)
        by_type = {"seasontype=1": "schedule_NFL_26_pre.json", "seasontype=2": "schedule_NFL_26_reg.json",
                   "seasontype=3": "schedule_NFL_26_post.json"}
        espn.on("/schedule", lambda url: next(load(name) for key, name in by_type.items() if key in url))
        return espn_api.get_team_schedule("NFL", "26", season=2025)

    def test_the_seahawks_have_preseason_regular_season_and_the_super_bowl_in_order(self, espn, local_zone, freeze_now):
        rows = self.seahawks(espn, local_zone, freeze_now)
        assert [schedule_row_text(g) for g in rows] == [
            "Thu, Aug 07, 2025: vs Las Vegas Raiders - T 23-23, Preseason Week 1",
            "Fri, Aug 15, 2025: vs Kansas City Chiefs - W 33-16, Preseason Week 2",
            "Sat, Aug 23, 2025: @ Green Bay Packers - L 7-20, Preseason Week 3",
            "Sun, Sep 07, 2025: vs San Francisco 49ers - L 13-17",
            "Sun, Sep 14, 2025: @ Pittsburgh Steelers - W 31-17",
            "Sat, Jan 17, 2026: vs San Francisco 49ers - W 41-6, NFC Divisional Playoffs",
            "Sun, Jan 25, 2026: vs Los Angeles Rams - W 31-27, NFC Championship",
            "Sun, Feb 08, 2026: vs New England Patriots - W 29-13, Super Bowl LX",
        ]

    def test_the_super_bowl_is_at_a_neutral_site_with_seattle_filed_as_away(self, espn, local_zone, freeze_now):
        game = self.seahawks(espn, local_zone, freeze_now)[-1]
        assert (game["home_away"], game["neutral_site"]) == ("@", True)
        assert (game["home_score"], game["away_score"]) == ("13", "29")

    def test_alabama_has_the_sec_championship_and_the_playoff(self, espn, local_zone, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        local_zone(-6)
        espn.on("/schedule", lambda url: {"seasontype=1": {"events": []}, "seasontype=2": load("schedule_NCAAF_333_reg.json"),
                                          "seasontype=3": load("schedule_NCAAF_333_post.json")}[url[url.index("seasontype"):]])
        assert [schedule_row_text(g) for g in espn_api.get_team_schedule("NCAAF", "333", season=2025)] == [
            "Sat, Dec 06, 2025: vs Georgia Bulldogs - L 7-28, SEC Championship",
            "Fri, Dec 19, 2025: @ Oklahoma Sooners - W 34-24, College Football Playoff First Round Game",
            "Thu, Jan 01, 2026: vs Indiana Hoosiers - L 3-38, "
            "College Football Playoff Quarterfinal at the Rose Bowl Presented by Prudential",
        ]

    def test_a_game_the_regular_season_and_postseason_both_list_appears_once(self, espn):
        game = load("schedule_NFL_26_post.json")["events"][-1]
        espn.on("/schedule", {"events": [game]})
        assert len(espn_api.get_team_schedule("NFL", "26", season=2025)) == 1

    def test_a_team_that_missed_the_playoffs_has_no_postseason_rows(self, espn):
        regular = load("schedule_NFL_26_reg.json")
        espn.on("/schedule", lambda url: regular if "seasontype=2" in url else {"events": []})
        assert {g["game_id"] for g in espn_api.get_team_schedule("NFL", "26", season=2025)} == {e["id"] for e in regular["events"]}

    @pytest.mark.parametrize("failing", ["seasontype=1", "seasontype=2", "seasontype=3"])
    def test_a_timeout_on_any_season_type_reaches_the_caller(self, espn, failing):
        """Not a schedule that looks complete with its playoffs missing."""
        regular = load("schedule_NFL_26_reg.json")
        espn.on("/schedule", lambda url: TIMEOUT if failing in url else regular)
        with pytest.raises(type(TIMEOUT)):
            espn_api.get_team_schedule("NFL", "26", season=2025)

    def test_a_failed_regular_season_shows_nothing_rather_than_only_the_rest(self, espn):
        post = load("schedule_NFL_26_post.json")
        espn.on("/schedule", lambda url: HTTP_500 if "seasontype=2" in url else post)
        assert espn_api.get_team_schedule("NFL", "26", season=2025) == []

    @pytest.mark.parametrize("failing", ["seasontype=1", "seasontype=3"])
    def test_an_error_on_preseason_or_postseason_leaves_out_only_that(self, espn, failing):
        regular = load("schedule_NFL_26_reg.json")
        espn.on("/schedule", lambda url: HTTP_500 if failing in url else (regular if "seasontype=2" in url else {"events": []}))
        assert {g["game_id"] for g in espn_api.get_team_schedule("NFL", "26", season=2025)} == {e["id"] for e in regular["events"]}


class TestChosenSeason:
    """A season you pick is that season or nothing."""

    def test_an_empty_ncaaf_season_does_not_become_another_season(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        real = load("schedule_NCAAF_333_reg.json")
        espn.on("/schedule", lambda url: real if "season=2025" in url else {"events": []})
        assert espn_api.get_team_schedule("NCAAF", "333", season=2010) == []
        assert all("season=2010" in url for url in espn.calls)

    def test_a_past_wnba_season_asks_for_that_season_and_not_the_scoreboard(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3))
        espn.on("/schedule", {"events": []})
        espn_api.get_team_schedule("WNBA", "8", season=2024)
        assert espn.calls == [f"{SITE}/basketball/wnba/teams/8/schedule?season=2024&seasontype={t}" for t in (1, 2, 3)]

    def test_a_past_soccer_season_asks_for_its_results_and_never_for_fixtures(self, espn, freeze_now):
        """fixture=true ignores season and answers with the games to come, which is how 2020
        came to show this season's games. schedule_EPL_359_2025.json is 2025-26."""
        freeze_now(datetime(2026, 11, 3))
        real = load("schedule_EPL_359_2025.json")
        espn.on("/schedule", real)
        rows = espn_api.get_team_schedule("EPL", "359", season=2025)
        assert espn.calls == [f"{SITE}/soccer/eng.1/teams/359/schedule?season=2025"]
        assert {g["game_id"] for g in rows} == {e["id"] for e in real["events"]}
        assert all(g["date_display"].endswith(", 2026") for g in rows)

    def test_a_past_season_on_the_scoreboard_path_is_nothing_rather_than_todays_games(self, espn, freeze_now, no_schedule_league):
        freeze_now(datetime(2026, 11, 3))
        assert espn_api.get_team_schedule(no_schedule_league, "8", season=2020) == []
        assert espn.calls == []


class TestWnba:
    def test_preseason_regular_season_and_playoffs(self, espn, local_zone, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        local_zone(-6)
        pre, regular, post = (load(f"schedule_WNBA_8{part}.json") for part in ("_pre", "", "_post"))
        espn.on("/schedule", lambda url: {"1": pre, "2": regular, "3": post}[url[-1]])
        rows = {g["game_id"]: g for g in espn_api.get_team_schedule("WNBA", "8", season=2026)}
        assert rows[pre["events"][0]["id"]]["label"] == "Preseason"
        assert rows[post["events"][0]["id"]]["label"] == "First Round - Game 1"
        everyday = next(e for e in regular["events"] if not e["competitions"][0]["notes"])
        assert rows[everyday["id"]]["label"] == ""

    def test_a_game_outside_any_window_of_today_is_still_there(self, espn, freeze_now):
        """The Lynx's last game was on Sep 30, and in December the old path returned nothing."""
        freeze_now(datetime(2026, 12, 25, 12))
        regular = load("schedule_WNBA_8.json")
        espn.on("/schedule", lambda url: regular if "seasontype=2" in url else {"events": []})
        assert len(espn_api.get_team_schedule("WNBA", "8")) == len(regular["events"])


class TestSoccer:
    def arsenal(self, espn, results=None, fixtures=None):
        results = load("schedule_EPL_359_results.json") if results is None else results
        fixtures = load("schedule_EPL_359_fixture.json") if fixtures is None else fixtures
        espn.on("/schedule", lambda url: fixtures if "fixture=true" in url else results)
        return results, fixtures

    def test_results_then_games_to_come_in_date_order_read_as_results(self, espn, local_zone, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        local_zone(-6)
        self.arsenal(espn)
        text = [schedule_row_text(g) for g in espn_api.get_team_schedule("EPL", "359")]
        assert text[:3] == ["Sun, Oct 18: @ Nottingham Forest - W 1-0", "Sat, Oct 24: vs Everton - W 2-0",
                            "Sun, Nov 01: @ Liverpool - W 1-0"]
        assert text[3].startswith("Sat, Nov 07: vs Hull City - 11/7") and text[3].endswith("(Emirates Stadium)")
        assert len(text) == 6

    def test_full_time_counts_as_over_and_the_list_lands_on_the_next_game(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        self.arsenal(espn)
        rows = espn_api.get_team_schedule("EPL", "359")
        assert [schedule_game_is_over(g) for g in rows] == [True, True, True, False, False, False]

    def test_a_game_in_both_lists_keeps_its_result(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        results, fixtures = load("schedule_EPL_359_results.json"), load("schedule_EPL_359_fixture.json")
        played = results["events"][0]
        still_listed = load("schedule_EPL_359_fixture.json")["events"][0]
        still_listed["id"] = played["id"]
        fixtures["events"].append(still_listed)
        self.arsenal(espn, results, fixtures)
        rows = [g for g in espn_api.get_team_schedule("EPL", "359") if g["game_id"] == played["id"]]
        assert len(rows) == 1 and rows[0]["completed"] is True and rows[0]["status"] == "Full Time"

    def test_a_penalty_shootout_is_a_finished_draw_with_espns_note(self, espn, local_zone, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        local_zone(-6)
        espn.on("/schedule", load("schedule_UCL_359_2025.json"))
        rows = {g["game_id"]: g for g in espn_api.get_team_schedule("UCL", "359", season=2025)}
        final = rows["401862897"]
        assert final["status"] == "Final Score - After Penalties" and final["completed"] is True
        assert schedule_row_text(final) == "Sat, May 30, 2026: @ Paris Saint-Germain - T 1-1, Paris Saint-Germain win 4-3 on penalties"

    def test_a_note_with_no_headline_is_no_label(self, espn):
        espn.on("/schedule", load("schedule_UCL_359_2025.json"))
        rows = espn_api.get_team_schedule("UCL", "359", season=2025)
        assert "" in {g["label"] for g in rows} and len(rows) == 3

    def test_a_league_with_a_new_season_coming_shows_the_games_espn_lists(self, espn, freeze_now):
        """In November 2026 MLS has finished 2026, and fixture=true answers with 2027's Sprint games."""
        freeze_now(datetime(2026, 11, 3, 12))
        fixtures = load("schedule_MLS_18418_fixture.json")
        assert fixtures["season"]["year"] == 2026 and fixtures["requestedSeason"]["year"] == 2027
        espn.on("/schedule", lambda url: fixtures if "fixture=true" in url else {"events": [], "season": {"year": 2026}})
        rows = espn_api.get_team_schedule("MLS", "18418", season=2026)
        assert {g["game_id"] for g in rows} == {e["id"] for e in fixtures["events"]}

    class TestAcrossNewYear:
        """February 2027: our calendar says 2027, while ESPN's Premier League is still in
        season=2026, the 2026-27 season. ESPN answered season=2027 with no events and
        season.year 2026 when this was tried in November."""

        def nothing_yet(self):
            answer = load("schedule_EPL_359_results.json")
            del answer["requestedSeason"]
            answer["events"] = []
            return answer

        def replies(self, url):
            if "fixture=true" in url:
                return load("schedule_EPL_359_fixture.json")
            return self.nothing_yet() if "season=2027" in url else load("schedule_EPL_359_results.json")

        def test_the_new_year_still_shows_the_season_in_play(self, espn, freeze_now):
            freeze_now(datetime(2027, 2, 1, 12))
            espn.on("/schedule", self.replies)
            rows = espn_api.get_team_schedule("EPL", "359", season=2027)
            assert espn.calls == [f"{SITE}/soccer/eng.1/teams/359/schedule?season=2027",
                                  f"{SITE}/soccer/eng.1/teams/359/schedule?season=2026",
                                  f"{SITE}/soccer/eng.1/teams/359/schedule?fixture=true"]
            assert sum(g["completed"] for g in rows) == 3 and len(rows) == 6

        def test_picking_the_season_espn_calls_current_includes_the_games_to_come(self, espn, freeze_now):
            freeze_now(datetime(2027, 2, 1, 12))
            espn.on("/schedule", self.replies)
            rows = espn_api.get_team_schedule("EPL", "359", season=2026)
            assert espn.urls("fixture=true")
            assert len(rows) == 6

        def test_a_timeout_on_the_seasons_results_reaches_the_caller(self, espn, freeze_now):
            freeze_now(datetime(2027, 2, 1, 12))
            espn.on("/schedule", lambda url: TIMEOUT if "season=2026" in url else self.replies(url))
            with pytest.raises(type(TIMEOUT)):
                espn_api.get_team_schedule("EPL", "359", season=2027)

        def test_an_error_on_the_seasons_results_keeps_the_games_to_come(self, espn, freeze_now):
            freeze_now(datetime(2027, 2, 1, 12))
            espn.on("/schedule", lambda url: HTTP_500 if "season=2026" in url else self.replies(url))
            assert len(espn_api.get_team_schedule("EPL", "359", season=2027)) == 3

    def test_no_games_at_all_with_no_season_chosen_falls_back_a_year(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        past = load("schedule_EPL_359_2025.json")
        espn.on("/schedule", lambda url: past if "season=2025" in url else {"events": [], "season": {"year": 2026}})
        rows = espn_api.get_team_schedule("EPL", "359")
        assert {g["game_id"] for g in rows} == {e["id"] for e in past["events"]}
        assert all(re.search(r", 20\d\d$", g["date_display"]) for g in rows)

    def test_a_response_that_names_no_season_is_taken_as_the_season_asked_for(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", {"events": load("schedule_EPL_359_results.json")["events"]})
        assert len(espn_api.get_team_schedule("EPL", "359", season=2026)) == 3
        assert espn.urls("fixture=true")

    @pytest.mark.parametrize("failing", ["season=2026", "fixture=true"])
    def test_a_timeout_on_either_list_reaches_the_caller(self, espn, freeze_now, failing):
        freeze_now(datetime(2026, 11, 3, 12))
        results = load("schedule_EPL_359_results.json")
        espn.on("/schedule", lambda url: TIMEOUT if failing in url else results)
        with pytest.raises(type(TIMEOUT)):
            espn_api.get_team_schedule("EPL", "359")

    def test_an_error_on_the_results_shows_nothing(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        fixtures = load("schedule_EPL_359_fixture.json")
        espn.on("/schedule", lambda url: fixtures if "fixture=true" in url else HTTP_500)
        assert espn_api.get_team_schedule("EPL", "359", season=2026) == []

    def test_an_error_on_the_fixtures_keeps_the_results(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        results = load("schedule_EPL_359_results.json")
        espn.on("/schedule", lambda url: HTTP_500 if "fixture=true" in url else results)
        assert len(espn_api.get_team_schedule("EPL", "359", season=2026)) == 3


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
            "game_id": "401873007", "is_today": False, "label": "", "completed": True, "neutral_site": False,
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

    def test_unusable_dates_leave_no_rows(self, espn):
        espn.on("/schedule", only_regular_season({"events": [{"date": None}, {"date": "x"}]}))
        assert espn_api.get_team_schedule("NBA", "15", season=2027) == []

    def test_events_with_no_id_are_all_kept(self, espn):
        """Nothing says they're the same game. Unlikely, and a repeat beats a lost game."""
        events = load("schedule_NFL_9.json")["events"][:2]
        for event in events:
            del event["id"]
        espn.on("/schedule", only_regular_season({"events": events}))
        assert len(espn_api.get_team_schedule("NFL", "9", season=2026)) == 2

    def test_a_doubleheader_stays_in_time_order(self, espn):
        first, second = load("schedule_MLB_10.json")["events"][:2]
        first["date"], second["date"] = "2026-06-01T17:00Z", "2026-06-01T23:00Z"
        espn.on("/schedule", only_regular_season({"events": [second, first]}))
        rows = espn_api.get_team_schedule("MLB", "10", season=2026)
        assert [g["game_id"] for g in rows] == [first["id"], second["id"]]

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

    def test_a_timeout_on_every_wnba_season_type_is_empty(self, espn):
        espn.on("/schedule", TIMEOUT)
        assert espn_api.get_team_schedule("WNBA", "8", season=2026) == []

    def test_scoreboard_path_failure_is_empty(self, espn, no_schedule_league):
        espn.on("/scoreboard", TIMEOUT)
        assert espn_api.get_team_schedule(no_schedule_league, "8") == []


class TestScoreboardPath:
    """The last resort: a window of months, filtered to one team and trimmed to the days asked."""

    def board(self):
        """A real NWSL scoreboard, its first game moved to tomorrow and second far away."""
        data = load("scoreboard_NWSL.json")
        first, second = data["events"]
        now = datetime.now(timezone.utc)
        first["date"] = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%MZ")
        second["date"] = (now + timedelta(days=300)).strftime("%Y-%m-%dT%H:%MZ")
        return data

    def test_only_this_teams_games_within_the_window(self, espn, no_schedule_league):
        data = self.board()
        for event in data["events"]:
            event["competitions"][0]["competitors"][0]["team"]["id"] = "TEAM"
        espn.on("/scoreboard", data)
        rows = {g["game_id"]: g for g in espn_api.get_team_schedule(no_schedule_league, "TEAM", days_ahead=30, days_behind=30)}
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

    def test_another_team_gets_nothing(self, espn, no_schedule_league):
        espn.on("/scoreboard", self.board())
        assert espn_api.get_team_schedule(no_schedule_league, "not-a-team") == []


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
        assert row["completed"] is comp["status"]["type"]["completed"]
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
