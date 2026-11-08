"""Tests for live games in a single league's scores list.

Live Scores showed the current play for a live game; the league's own list
showed only the score and clock. The league list now reads the same play from
the scoreboard it already loaded, and a football week swaps its live games for
today's scoreboard, which the week-addressed one runs minutes behind.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import espn_api  # noqa: E402


def game(game_id, state, home_score="0", away_score="0", status_name="",
         start="2026-10-09T23:00Z"):
    return {
        "id": game_id,
        "state": state,
        "status_name": status_name,
        "date": start,
        "teams": [
            {"name": "Home", "score": home_score, "home_away": "home"},
            {"name": "Away", "score": away_score, "home_away": "away"},
        ],
    }


NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)  # 9 pm ET on Friday the 9th


class TestFreshenLiveGames:
    def test_week_without_started_games_makes_no_request(self):
        week = [game("1", "pre", start="2026-10-10T23:00Z"), game("2", "post")]
        with patch.object(espn_api, "get_scores") as get_scores:
            assert espn_api.freshen_live_games("NCAAF", week, now=NOW) is week
        get_scores.assert_not_called()

    def test_games_under_way_come_from_their_days_board(self):
        week = [game("1", "in", home_score="6"), game("2", "pre", start="2026-10-10T23:00Z"),
                game("3", "post")]
        today = [game("1", "in", home_score="9")]
        with patch.object(espn_api, "get_scores", return_value=today) as get_scores:
            result = espn_api.freshen_live_games("NCAAF", week, now=NOW)
        get_scores.assert_called_once_with("NCAAF", date=date(2026, 10, 9))
        by_id = {g["id"]: g for g in result}
        assert by_id["1"]["teams"][0]["score"] == "9"
        assert by_id["2"] is week[1] and by_id["3"] is week[2]

    def test_late_game_after_midnight_uses_its_eastern_date(self):
        # 10:30 pm ET Saturday kickoff, still going at 1 am Sunday ET: ESPN
        # files it under Saturday, not the day it now is.
        week = [game("1", "in", start="2026-10-11T02:30Z")]
        now = datetime(2026, 10, 11, 5, 0, tzinfo=timezone.utc)
        with patch.object(espn_api, "get_scores", return_value=[]) as get_scores:
            espn_api.freshen_live_games("NCAAF", week, now=now)
        get_scores.assert_called_once_with("NCAAF", date=date(2026, 10, 10))

    def test_kicked_off_game_the_stale_board_calls_upcoming_is_freshened(self):
        week = [game("1", "pre", start="2026-10-09T23:30Z")]
        today = [game("1", "in", home_score="7")]
        with patch.object(espn_api, "get_scores", return_value=today):
            result = espn_api.freshen_live_games("NCAAF", week, now=NOW)
        assert espn_api.game_section(result[0]) == "in_progress"

    def test_games_on_two_days_fetch_each_day_once(self):
        week = [game("1", "in", start="2026-10-10T02:30Z"),  # Friday ET
                game("2", "in", start="2026-10-10T03:00Z"),  # Friday ET
                game("3", "in", start="2026-10-10T16:00Z")]  # Saturday ET
        now = datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc)
        with patch.object(espn_api, "get_scores", return_value=[]) as get_scores:
            espn_api.freshen_live_games("NCAAF", week, now=now)
        assert [c.kwargs["date"] for c in get_scores.call_args_list] == [
            date(2026, 10, 9), date(2026, 10, 10)]

    def test_game_that_finished_moves_to_completed(self):
        week = [game("1", "in"), game("2", "post")]
        with patch.object(espn_api, "get_scores", return_value=[game("1", "post")]):
            result = espn_api.freshen_live_games("NFL", week, now=NOW)
        assert [espn_api.game_section(g) for g in result] == ["completed", "completed"]

    def test_failure_keeps_the_week(self):
        week = [game("1", "in")]
        with patch.object(espn_api, "get_scores", side_effect=ConnectionError("down")):
            assert espn_api.freshen_live_games("NFL", week, now=NOW) is week

    def test_game_missing_from_its_days_board_keeps_its_week_version(self):
        week = [game("1", "in"), game("2", "in")]
        with patch.object(espn_api, "get_scores", return_value=[game("2", "in", home_score="3")]):
            result = {g["id"]: g for g in espn_api.freshen_live_games("NFL", week, now=NOW)}
        assert result["1"] is week[0]
        assert result["2"]["teams"][0]["score"] == "3"

    def test_unreadable_start_is_skipped(self):
        week = [game("1", "in", start="")]
        with patch.object(espn_api, "get_scores") as get_scores:
            assert espn_api.freshen_live_games("NFL", week, now=NOW) is week
        get_scores.assert_not_called()


class TestLeagueViewLiveText:
    """LeagueView._live_game_text, called with a stand-in for the view."""

    @pytest.fixture(autouse=True)
    def scores_module(self):
        pytest.importorskip("PyQt6")
        import scores
        self.scores = scores

    def text(self, league, game_raw):
        return self.scores.LeagueView._live_game_text(SimpleNamespace(league=league), game_raw)

    def football_game(self, situation):
        comp = {
            "status": {"displayClock": "8:30", "period": 4},
            "competitors": [
                {"homeAway": "home", "score": "20",
                 "team": {"id": "97", "displayName": "Louisville Cardinals", "abbreviation": "LOU"}},
                {"homeAway": "away", "score": "35",
                 "team": {"id": "52", "displayName": "Florida State Seminoles", "abbreviation": "FSU"}},
            ],
            "situation": situation,
        }
        return {
            "id": "1", "name": "FSU at LOU", "state": "in", "status": "In Progress",
            "start_time": "8:30 - 4th",
            "teams": [
                {"name": "Louisville Cardinals", "score": "20", "home_away": "home"},
                {"name": "Florida State Seminoles", "score": "35", "home_away": "away"},
            ],
            "competitions": [comp],
        }

    def test_football_gets_play_and_situation_with_the_clock_once(self):
        raw = self.football_game({
            "lastPlay": {"text": "J.Smith pass complete to K.Jones for 12 yards"},
            "possession": "52", "downDistanceText": "1st & 10 at LOU 40",
        })
        lines = self.text("NCAAF", raw).split("\n")
        assert lines[0] == ("Florida State Seminoles 35 at Louisville Cardinals 20"
                            " | J.Smith pass complete to K.Jones for 12 yards")
        assert lines[1] == "8:30 Q4 | FSU ball | 1st & 10 at LOU 40"

    def test_no_situation_leaves_the_usual_text(self):
        assert self.text("NCAAF", self.football_game({})) is None

    def test_nfl_uses_the_lists_short_team_names(self):
        raw = self.football_game({"lastPlay": {"text": "Kickoff"}, "possession": "52"})
        raw["teams"][0]["name"], raw["teams"][1]["name"] = "Cardinals", "Seminoles"
        first = self.text("NFL", raw).split("\n")[0]
        assert first.startswith("Seminoles 35 at Cardinals 20")

    def test_other_leagues_add_the_last_play(self):
        raw = {
            "id": "2", "name": "Ducks at Jets", "state": "in", "status": "In Progress",
            "start_time": "18:11 - 3rd",
            "teams": [{"name": "Jets", "score": "0", "home_away": "home"},
                      {"name": "Ducks", "score": "2", "home_away": "away"}],
            "competitions": [{"situation": {"lastPlay": {"text": "Shot on goal by Someone"}}}],
        }
        assert self.text("NHL", raw).endswith(" | Shot on goal by Someone")

    def test_game_without_competitions_leaves_the_usual_text(self):
        raw = {"id": "3", "state": "in", "teams": [], "competitions": []}
        assert self.text("NBA", raw) is None

    def test_mlb_gets_three_lines_with_short_names(self):
        comp = {"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "Boston Red Sox"}},
            {"homeAway": "away", "score": "3", "team": {"displayName": "New York Yankees"}},
        ], "situation": {
            "onFirst": True, "balls": 1, "strikes": 2, "outs": 2,
            "batter": {"athlete": {"displayName": "Some Batter"}},
            "lastPlay": {"text": "Pitching change"},
        }}
        raw = {"id": "4", "state": "in", "status": "In Progress", "start_time": "Top 5th",
               "teams": [{"name": "Red Sox", "score": "2", "home_away": "home"},
                         {"name": "Yankees", "score": "3", "home_away": "away"}],
               "competitions": [comp]}
        lines = self.text("MLB", raw).split("\n")
        assert lines[0] == "Yankees 3 at Red Sox 2 (Top 5th)"
        assert lines[1] == "Runner on 1st | 1-2 count, 2 outs | At bat: Some Batter"
        assert lines[2] == "Last: Pitching change"


class TestRefreshKeepsTheGame:
    """F5 in a league list lands back on the selected game."""

    GAMES = [game(str(i), "post") for i in range(1, 5)]

    @pytest.fixture(autouse=True)
    def view(self):
        pytest.importorskip("PyQt6")
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        self.app = QApplication.instance() or QApplication([])
        self.role = Qt.ItemDataRole.UserRole
        import scores
        with patch.object(scores, "_start_detached_thread"):
            self.view = scores.LeagueView(None, "NBA")
            yield

    def land(self, games=None):
        self.view._on_scores_loaded(self.view._scores_generation, None,
                                    self.GAMES if games is None else games, [])
        return self.view.scores_list.currentItem().data(self.role)

    def select(self, game_id):
        lst = self.view.scores_list
        row = next(i for i in range(lst.count()) if lst.item(i).data(self.role) == game_id)
        lst.setCurrentRow(row)

    def test_first_load_lands_on_the_first_row(self):
        assert self.land() is None  # the "Completed, 4 games" header

    def test_refresh_lands_on_the_selected_game(self):
        self.land()
        self.select("3")
        self.view.refresh()
        assert self.land() == "3"

    def test_game_gone_after_refresh_falls_back_to_the_top(self):
        self.land()
        self.select("3")
        self.view.refresh()
        assert self.land([g for g in self.GAMES if g["id"] != "3"]) is None

    def test_double_refresh_still_lands_on_the_game(self):
        self.land()
        self.select("3")
        self.view.refresh()
        self.view.refresh()  # the list now shows "Loading scores..."
        assert self.land() == "3"

    def test_failed_refresh_does_not_carry_to_the_next_day(self):
        self.land()
        self.select("3")
        self.view.refresh()
        import scores
        with patch.object(scores.QMessageBox, "warning"):  # modal; would block the test
            self.view._on_scores_error(self.view._scores_generation, "network down")
        self.view.load_scores()  # next day
        assert self.land() is None

    def test_day_change_during_refresh_lands_on_the_top(self):
        self.land()
        self.select("3")
        self.view.refresh()
        self.view.load_scores()
        assert self.land() is None


class TestLoaderFreshensFootballWeeksOnly:
    @pytest.fixture(autouse=True)
    def scores_module(self):
        pytest.importorskip("PyQt6")
        import scores
        self.scores = scores

    def run_loader(self, request):
        loader = self.scores.LeagueScoresLoader(1, "NFL", request)
        api = self.scores.ApiService
        from services import football_calendar
        with patch.object(api, "get_scores", return_value=[]), \
                patch.object(api, "get_news", return_value=[]), \
                patch.object(football_calendar, "prepare_week") as self.prepared, \
                patch.object(api, "freshen_live_games", return_value=[]) as freshen:
            loader.run()
        return freshen

    def test_week_request_is_freshened(self):
        self.run_loader(dict(week=6, season=2026, seasontype=2)).assert_called_once()

    def test_date_request_is_not(self):
        self.run_loader(dict(date=date(2026, 10, 9))).assert_not_called()

    def test_a_week_s_name_is_fetched_on_the_loader_thread(self):
        """The label and the week arrows read the cache on the UI thread, so the
        loader fetches the week's name (a past season's from the Core API) first."""
        self.run_loader(dict(week=1, season=2024, seasontype=3))
        self.prepared.assert_called_once_with("NFL", 2024, 3, 1)

    def test_a_date_request_fetches_no_week_name(self):
        self.run_loader(dict(date=date(2026, 10, 9)))
        self.prepared.assert_not_called()


class TestFreshenNeverCostsTheWeek:
    def test_non_string_start_keeps_the_week(self):
        week = [game("1", "in", start=12345)]
        with patch.object(espn_api, "get_scores") as get_scores:
            assert espn_api.freshen_live_games("NFL", week, now=NOW) is week
        get_scores.assert_not_called()

    def test_naive_now_keeps_the_week(self):
        week = [game("1", "in")]
        assert espn_api.freshen_live_games("NFL", week, now=datetime(2026, 10, 10)) is week


FAILED = "ESPN isn't providing scores right now. Try again in a minute."


class FailureViews:
    @pytest.fixture(autouse=True)
    def qt(self):
        pytest.importorskip("PyQt6")
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        self.app = QApplication.instance() or QApplication([])
        self.role = Qt.ItemDataRole.UserRole
        import scores
        self.scores = scores
        with patch.object(scores, "_start_detached_thread"), patch.object(scores, "announce") as said, \
                patch.object(scores.QMessageBox, "warning") as box:
            self.said = said
            self.box = box
            yield

    @staticmethod
    def rows(lst):
        return [lst.item(i).text() for i in range(lst.count())]


class TestAFailedLeagueList(FailureViews):
    GAMES = [game(str(i), "post") for i in range(1, 4)]

    @pytest.fixture
    def view(self):
        return self.scores.LeagueView(None, "NBA")

    def land(self, view, games=None):
        view._on_scores_loaded(view._scores_generation, None, self.GAMES if games is None else games, [])

    def test_it_says_so_in_a_row_and_keeps_the_rest_of_the_list(self, view):
        view._on_scores_error(view._scores_generation, FAILED)
        rows = self.rows(view.scores_list)
        assert rows[0] == FAILED
        assert "News Headlines" in rows
        assert "Standings" in rows and "Teams" in rows
        assert not any("No games found" in row for row in rows)
        assert view.scores_list.currentRow() == 0
        self.box.assert_not_called()

    def test_enter_on_the_row_tries_again(self, view):
        view._on_scores_error(view._scores_generation, FAILED)
        before = view._scores_generation
        view._on_score_item_selected(view.scores_list.item(0))
        assert view._scores_generation == before + 1
        assert self.rows(view.scores_list) == ["Loading scores..."]

    def test_a_retry_that_works_shows_the_games(self, view):
        view._on_scores_error(view._scores_generation, FAILED)
        view.refresh()
        self.land(view)
        assert FAILED not in self.rows(view.scores_list)
        assert "Completed, 3 games" in self.rows(view.scores_list)

    def test_a_failed_refresh_keeps_the_games_and_the_place(self, view):
        self.land(view)
        lst = view.scores_list
        lst.setCurrentRow(next(i for i in range(lst.count()) if lst.item(i).data(self.role) == "2"))
        view.refresh()
        self.said.reset_mock()
        view._on_scores_error(view._scores_generation, FAILED)
        assert lst.currentItem().data(self.role) == "2"
        assert FAILED not in self.rows(lst)
        assert "Completed, 3 games" in self.rows(lst)
        self.said.assert_called_once_with(FAILED)
        self.box.assert_not_called()

    def test_another_days_failure_does_not_show_this_days_games(self, view):
        self.land(view)
        view.current_date += timedelta(days=1)
        view.load_scores()
        view._on_scores_error(view._scores_generation, FAILED)
        assert self.rows(view.scores_list)[0] == FAILED
        assert "Completed, 3 games" not in self.rows(view.scores_list)

    def test_an_old_load_failing_changes_nothing(self, view):
        self.land(view)
        before = self.rows(view.scores_list)
        view._on_scores_error(view._scores_generation - 1, FAILED)
        assert self.rows(view.scores_list) == before

    def test_news_that_failed_keeps_its_row_and_no_news_has_none(self, view):
        view._on_scores_loaded(view._scores_generation, None, self.GAMES, None)
        assert "News Headlines" in self.rows(view.scores_list)
        self.land(view)
        assert "News Headlines" not in self.rows(view.scores_list)

    def test_enter_on_a_news_row_with_no_news_asks_again(self, view):
        view._on_scores_loaded(view._scores_generation, None, self.GAMES, None)
        lst = view.scores_list
        row = next(i for i in range(lst.count()) if lst.item(i).data(self.role) == "__news__")
        lst.setCurrentRow(row)
        with patch.object(view, "_fetch_then") as fetch:
            view._on_score_item_selected(lst.item(row))
        assert fetch.call_args.args[0] == "News"

    def test_a_football_league_with_no_week_stops_saying_it_is_finding_one(self):
        view = self.scores.LeagueView(None, "NFL")
        assert view.date_label.text() == "Finding the current week..."
        view._on_scores_error(view._scores_generation, FAILED)
        assert view.date_label.text() == ""
        assert view._calendar_pending is True  # so a retry asks for the calendar again
        self.said.assert_not_called()

    def test_the_loader_says_news_failed_with_none(self):
        loader = self.scores.LeagueScoresLoader(1, "NBA", dict(date=date(2026, 10, 9)))
        api = self.scores.ApiService
        got = []
        loader.data_loaded.connect(lambda *a: got.append(a))
        with patch.object(api, "get_scores", return_value=[]), \
                patch.object(api, "get_news", side_effect=self.scores.ApiError("no")):
            loader.run()
        assert got[0][3] is None

    def test_the_loader_passes_on_a_failure_in_plain_words(self):
        loader = self.scores.LeagueScoresLoader(1, "NBA", dict(date=date(2026, 10, 9)))
        got = []
        loader.error_occurred.connect(lambda *a: got.append(a))
        with patch.object(self.scores.ApiService, "get_scores", side_effect=self.scores.ApiError(FAILED)):
            loader.run()
        assert got == [(1, FAILED)]


class TestAFailureInLiveScores(FailureViews):
    @staticmethod
    def today_game(game_id, league):
        return {"game_id": game_id, "league": league, "state": "completed", "start_time": "",
                "display_text": f"{league} game {game_id}", "raw_data": {"id": game_id, "league": league}}

    @pytest.fixture
    def view(self):
        view = self.scores.LiveScoresView(None)
        view.refresh_timer.stop()
        return view

    def load(self, view, today=(), failed=()):
        view._on_live_scores_loaded([], list(today), [], list(failed))

    def everything(self):
        return self.scores.ApiService.get_leagues()

    def test_every_league_failing_is_not_no_games(self, view):
        self.load(view, failed=self.everything())
        assert self.rows(view.live_scores_list) == [FAILED]

    def test_nothing_failing_with_no_games_is_no_games(self, view):
        self.load(view)
        rows = self.rows(view.live_scores_list)
        assert len(rows) == 1 and rows[0].startswith("No games on")

    def test_one_league_failing_does_not_blank_the_others(self, view):
        self.load(view, [self.today_game("1", "NHL")], ["NBA"])
        rows = self.rows(view.live_scores_list)
        assert "NHL game 1" in rows
        assert rows[-1].startswith("Scores for NBA may be missing or out of date.")

    def test_a_league_failing_on_refresh_keeps_its_games(self, view):
        self.load(view, [self.today_game("1", "NHL"), self.today_game("2", "NBA")])
        self.load(view, [self.today_game("1", "NHL")], ["NBA"])
        rows = self.rows(view.live_scores_list)
        assert "NBA game 2" in rows and "NHL game 1" in rows

    def test_a_league_that_answers_again_loses_the_row(self, view):
        self.load(view, [self.today_game("1", "NHL")], ["NBA"])
        self.load(view, [self.today_game("1", "NHL")])
        assert not any("may be missing" in row for row in self.rows(view.live_scores_list))

    def test_a_refresh_that_gets_nothing_keeps_the_list_and_the_time(self, view):
        self.load(view, [self.today_game("1", "NHL")])
        view.current_time = shown = datetime(2026, 11, 4, 9, 30)
        self.load(view, failed=self.everything())
        rows = self.rows(view.live_scores_list)
        assert "NHL game 1" in rows
        assert rows[-1].startswith("Some leagues' scores may be missing")
        assert view.current_time == shown

    def test_the_timer_stays_quiet(self, view):
        self.load(view, [self.today_game("1", "NHL")])
        for _ in range(3):
            self.load(view, failed=self.everything())
        self.said.assert_not_called()

    def test_a_refresh_someone_asked_for_says_so_each_time(self, view):
        self.load(view, [self.today_game("1", "NHL")])
        for _ in range(2):
            with patch.object(view, "load_live_scores"):
                view.refresh()
            self.load(view, failed=self.everything())
        assert self.said.call_count == 2
        assert self.said.call_args.args[0].startswith("Some leagues' scores may be missing")

    def test_a_monitored_games_league_failing_on_the_timer_is_quiet_too(self, view):
        """Monitoring doesn't speak on its own any more: the row at the end says so."""
        live = {"id": "1", "league": "NBA", "name": "A at B", "status": "Q1", "teams": []}
        view.monitored_games["1"] = "NBA"
        view._on_live_scores_loaded([live], [], [], [])
        for _ in range(3):
            view._on_live_scores_loaded([], [], [], ["NBA"])
        self.said.assert_not_called()

    def test_a_retry_that_works_lands_on_a_row(self, view):
        self.load(view, [self.today_game("1", "NHL")], ["NBA"])
        lst = view.live_scores_list
        lst.setCurrentRow(lst.count() - 1)
        self.load(view, [self.today_game("1", "NHL")])
        assert lst.currentRow() == lst.count() - 1 and lst.count() > 0

    def test_someone_on_the_row_hears_a_changed_row_said_since_it_is_not_rebuilt(self, view):
        self.load(view, failed=["NBA"])
        view.live_scores_list.setCurrentRow(0)
        with patch.object(view, "load_live_scores"):
            view.refresh()
        self.load(view, failed=["NBA", "NHL"])
        assert view.live_scores_list.currentRow() == 0
        self.said.assert_called_once()

    def test_someone_landing_on_the_row_in_a_rebuilt_list_hears_it_once(self, view):
        """The list was showing "Loading live scores...", and arriving on the row reads it."""
        lst = view.live_scores_list
        lst.setCurrentRow(0)
        with patch.object(view, "load_live_scores"), patch.object(lst, "hasFocus", return_value=True):
            view.refresh()
            self.load(view, failed=["NBA"])
        assert lst.currentRow() == 0
        self.said.assert_not_called()

    def test_with_focus_off_the_list_a_rebuilt_row_is_still_said(self, view):
        """Refresh from the combo: nothing read the row, whatever row is current."""
        lst = view.live_scores_list
        lst.setCurrentRow(0)
        with patch.object(view, "load_live_scores"), patch.object(lst, "hasFocus", return_value=False):
            view.refresh()
            self.load(view, failed=["NBA"])
        assert lst.currentRow() == 0
        self.said.assert_called_once()

    def test_a_game_arriving_above_the_failure_row_leaves_you_on_it(self, view):
        one, two = self.today_game("1", "NHL"), self.today_game("2", "NHL")
        self.load(view, [one], ["NBA"])
        lst = view.live_scores_list
        lst.setCurrentRow(lst.count() - 1)
        self.load(view, [one, two], ["NBA"])
        assert lst.currentRow() == lst.count() - 1
        assert lst.currentItem().data(self.scores.Qt.ItemDataRole.UserRole) == self.scores.RETRY_ROW

    def test_the_failure_row_coming_and_going_leaves_the_games_alone(self, view):
        self.load(view, [self.today_game("1", "NHL"), self.today_game("2", "NHL")])
        lst = view.live_scores_list
        lst.setCurrentRow(2)
        kept = lst.item(2)
        games = lst.count()
        with patch.object(lst, "clear") as cleared:
            self.load(view, [self.today_game("1", "NHL"), self.today_game("2", "NHL")], ["NBA"])
            assert lst.count() == games + 1
            assert lst.item(games).text().startswith("Scores for NBA")
            self.load(view, [self.today_game("1", "NHL"), self.today_game("2", "NHL")], ["NBA", "MLB"])
            assert lst.count() == games + 1
            assert lst.item(games).text().startswith("Scores for MLB and NBA")
            self.load(view, [self.today_game("1", "NHL"), self.today_game("2", "NHL")])
            assert lst.count() == games
        cleared.assert_not_called()
        assert lst.item(2) is kept
        assert lst.currentRow() == 2

    def test_refresh_rows_in_place_goes_by_the_games_only(self, view):
        one, two = self.today_game("1", "NHL"), self.today_game("2", "NHL")
        self.load(view, [one])
        view._failed_leagues = ["NBA"]
        assert view._refresh_rows_in_place([], [one], []) is True
        view._failed_leagues = []
        assert view._refresh_rows_in_place([], [one], []) is True
        assert view._refresh_rows_in_place([], [one, two], []) is False

    def test_a_game_that_changes_with_the_row_there_still_rebuilds(self, view):
        one, two = self.today_game("1", "NHL"), self.today_game("2", "NHL")
        self.load(view, [one], ["NBA"])
        self.load(view, [one, two], ["NBA"])
        rows = self.rows(view.live_scores_list)
        assert "NHL game 2" in rows and rows[-1].startswith("Scores for NBA")

    def test_it_says_not_updated_yet_until_something_loads(self, view):
        assert view.current_time is None
        self.load(view, failed=self.everything())
        assert "Not updated yet" in view.time_label.text()
        self.load(view, [self.today_game("1", "NHL")])
        assert "Last updated:" in view.time_label.text()

    def test_the_row_already_saying_so_is_left_alone(self, view):
        view._on_live_scores_error(FAILED)
        row = view.live_scores_list.item(0)
        view._on_live_scores_error(FAILED)
        assert view.live_scores_list.item(0) is row
        self.said.assert_not_called()
        with patch.object(view, "load_live_scores"):
            view.refresh()
        view._on_live_scores_error(FAILED)
        self.said.assert_called_once_with(FAILED)

    def test_someone_on_the_row_hears_an_unchanged_row_said(self, view):
        self.load(view, failed=["NBA"])
        view.live_scores_list.setCurrentRow(0)
        with patch.object(view, "load_live_scores"):
            view.refresh()
        self.load(view, failed=["NBA"])
        self.said.assert_called_once()

    def test_a_refresh_someone_asked_for_failing_whole_says_so(self, view):
        self.load(view, [self.today_game("1", "NHL")])
        with patch.object(view, "load_live_scores"):
            view.refresh()
        view._on_live_scores_error(FAILED)
        self.said.assert_called_once_with(FAILED)
        assert view._refresh_asked_for is False

    def test_another_league_failing_with_a_game_monitored_stays_quiet(self, view):
        live = {"id": "1", "league": "NBA", "name": "A at B", "status": "Q1", "teams": []}
        view.monitored_games["1"] = "NBA"
        view._on_live_scores_loaded([live], [], [], [])
        view._on_live_scores_loaded([live], [], [], ["NHL"])
        self.said.assert_not_called()

    def test_enter_on_the_row_tries_again(self, view):
        self.load(view, failed=self.everything())
        with patch.object(view, "load_live_scores") as load:
            view._on_game_selected(view.live_scores_list.item(0))
        load.assert_called_once()

    def test_the_loader_failing_keeps_the_list(self, view):
        self.load(view, [self.today_game("1", "NHL")])
        view._on_live_scores_error(FAILED)
        assert "NHL game 1" in self.rows(view.live_scores_list)

    def test_the_loader_failing_with_nothing_there_is_a_row(self, view):
        view._on_live_scores_error(FAILED)
        assert self.rows(view.live_scores_list) == [FAILED]

    def test_the_fetch_reports_which_leagues_failed(self):
        def scores_for(league, day):
            if league == "NBA":
                raise self.scores.ApiError(FAILED)
            return []

        def golf(tour):
            raise self.scores.ApiError("no")

        with patch.object(self.scores.ApiService, "get_scores", side_effect=scores_for), \
                patch.object(espn_api, "get_live_golf_tournament", side_effect=golf):
            live, today, tours, failed = self.scores.LiveScoresView._fetch_live_scores()
        assert (live, today, tours) == ([], [], [])
        assert sorted(failed) == ["LPGA", "NBA", "PGA"]


class TestAFailureInAGame(FailureViews):
    @pytest.fixture
    def view(self):
        return self.scores.GameDetailsView(None, "NBA", "1")

    def test_a_row_says_so_and_enter_tries_again(self, view):
        view._on_game_details_error(view._details_generation, FAILED)
        assert self.rows(view.details_list) == [FAILED]
        self.box.assert_not_called()
        before = view._details_generation
        with patch.object(view, "set_focus_and_select_first"):
            view._on_detail_item_selected(view.details_list.item(0))
        assert view._details_generation == before + 1

    def test_a_refresh_that_fails_keeps_the_game(self, view):
        view._shown_details = ({"header": {}}, {"name": "A at B"})
        with patch.object(view, "_on_game_details_loaded") as shown:
            view._on_game_details_error(view._details_generation, FAILED)
        shown.assert_called_once_with(view._details_generation, {"header": {}}, {"name": "A at B"})
        self.said.assert_called_once_with(FAILED)


class TestAFailureInADialog(FailureViews):
    def team_hub(self):
        with patch.object(self.scores.TeamHubDialog, "_on_tab_changed"):
            return self.scores.TeamHubDialog({"team_name": "Packers", "team_id": "9"}, "NFL")

    def test_team_tabs_say_so_and_coming_back_asks_again(self):
        hub = self.team_hub()
        for tab, lst in ((0, hub.info_list), (3, hub.news_list), (4, hub.trans_list)):
            hub._tabs_loaded.add(tab)
            hub._show_list_error(lst, FAILED, tab)
            assert self.rows(lst) == [FAILED]
            assert lst.currentRow() == 0
            assert tab not in hub._tabs_loaded

    def test_the_team_roster_says_so_and_coming_back_asks_again(self):
        hub = self.team_hub()
        hub._tabs_loaded.add(1)
        hub._on_roster_failed(FAILED)
        assert hub.roster_table.item(0, 0).text() == FAILED
        assert 1 not in hub._tabs_loaded

    def transactions(self):
        with patch.object(self.scores.TransactionsDialog, "_load_teams"), \
                patch.object(self.scores.TransactionsDialog, "_load_next"):
            return self.scores.TransactionsDialog("NFL")

    def test_transactions_failing_is_not_no_transactions(self):
        dialog = self.transactions()
        loading = self.scores.QListWidgetItem("Loading transactions...")
        dialog.trans_list.addItem(loading)
        dialog._on_error(FAILED, loading, dialog._generation)
        assert self.rows(dialog.trans_list) == [FAILED]
        assert dialog.trans_list.currentRow() == 0

    def test_load_more_failing_keeps_the_list_and_asks_for_the_same_page_next(self):
        dialog = self.transactions()
        dialog._first_load = False
        dialog._cursor = {"year": 2026, "month": None, "page": 2}
        dialog.trans_list.addItem("2026-11-01 A trade")
        loading = self.scores.QListWidgetItem("Loading older transactions...")
        dialog.trans_list.addItem(loading)
        dialog._on_error(FAILED, loading, dialog._generation)
        assert self.rows(dialog.trans_list) == ["2026-11-01 A trade"]
        assert dialog._cursor == {"year": 2026, "month": None, "page": 2}
        assert dialog.load_more_btn.isEnabled()
        self.said.assert_called_once_with(f"{FAILED} Press F5 or Load More to try again.")

    def test_the_team_filter_failing_says_so_and_f5_asks_again(self):
        dialog = self.transactions()
        dialog._on_teams_failed("no")
        self.said.assert_called_once_with(self.scores.TEAMS_UNAVAILABLE)
        with patch.object(dialog, "_load_teams") as load:
            self.press_f5(dialog)
            self.press_f5(dialog)
        load.assert_called_once()

    def test_the_team_filter_coming_back_says_so_only_after_a_retry(self):
        teams = [{"team_name": "Bears", "team_id": "3"}]
        dialog = self.transactions()
        dialog._on_teams_loaded(teams)
        self.said.assert_not_called()

        dialog = self.transactions()
        dialog._on_teams_failed("no")
        with patch.object(dialog, "_load_teams"):
            self.press_f5(dialog)
        self.said.reset_mock()
        dialog._on_teams_loaded(teams)
        self.said.assert_called_once_with("Teams loaded.")
        assert dialog.team_combo.count() == 2

    def test_a_retry_of_the_team_filter_that_fails_again_says_only_that(self):
        dialog = self.transactions()
        dialog._on_teams_failed("no")
        with patch.object(dialog, "_load_teams"):
            self.press_f5(dialog)
        self.said.reset_mock()
        dialog._on_teams_failed("no")
        self.said.assert_called_once_with(self.scores.TEAMS_UNAVAILABLE)
        assert dialog._teams_retried is False

    def test_a_league_with_no_standings_is_not_a_failed_team_filter(self):
        dialog = self.transactions()
        dialog._on_teams_loaded([])
        dialog._on_teams_loaded(None)
        assert dialog.team_combo.count() == 1
        self.said.assert_not_called()

    def press_f5(self, dialog):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))

    def test_f5_in_transactions_only_tries_again_what_failed(self):
        dialog = self.transactions()
        with patch.object(dialog, "_restart") as load:
            self.press_f5(dialog)
            load.assert_not_called()
            loading = self.scores.QListWidgetItem("Loading transactions...")
            dialog.trans_list.addItem(loading)
            dialog._on_error(FAILED, loading, dialog._generation)
            self.press_f5(dialog)
            load.assert_called_once_with()

    def golf(self):
        with patch.object(self.scores.GolfTournamentDialog, "_load_leaderboard"), \
                patch.object(self.scores.GolfTournamentDialog, "_load_schedule"):
            return self.scores.GolfTournamentDialog("PGA")

    def test_f5_in_golf_only_tries_again_what_failed(self):
        dialog = self.golf()
        dialog._list_error(dialog.leaderboard_list, FAILED)
        assert self.rows(dialog.leaderboard_list) == [FAILED]
        assert dialog.tournament_label.text() == ""
        with patch.object(dialog, "_load_leaderboard") as board, patch.object(dialog, "_load_schedule") as schedule:
            self.press_f5(dialog)
            self.press_f5(dialog)
        board.assert_called_once()
        schedule.assert_not_called()

    def world_cup(self):
        with patch.object(self.scores.WorldCupDialog, "_load_all"):
            return self.scores.WorldCupDialog("WC2026")

    def world_cup_on(self, day):
        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(day.year, day.month, day.day, 12)

        dialog_class = self.scores.WorldCupDialog
        with patch.object(self.scores, "datetime", Frozen), patch.object(dialog_class, "_load_scores"), \
                patch.object(dialog_class, "_load_standings"), patch.object(dialog_class, "_load_news"):
            return dialog_class("WC2026")

    @pytest.mark.parametrize("day,phase,page", [
        (date(2026, 6, 15), "Group Stage", 0),
        (date(2026, 7, 5), "Round of 16", 1),
        (date(2026, 7, 8), "Round of 16", 1),
        (date(2026, 11, 4), "Final", 1),
    ], ids=["group_stage", "round_of_16", "between_rounds", "over"])
    def test_a_world_cup_opens_with_its_phase_page_and_list_agreeing(self, day, phase, page):
        dialog = self.world_cup_on(day)
        assert dialog.phase_combo.currentText() == phase
        assert dialog.bracket_stack.currentIndex() == page
        if page:
            assert self.rows(dialog.bracket_list) == [f"Loading {phase} matches\u2026"]

    def test_a_world_cup_refresh_that_fails_keeps_the_games_and_says_so_once(self):
        dialog = self.world_cup()
        dialog._on_scores_loaded(dialog.current_date, [])
        before = self.rows(dialog.scores_list)
        dialog._on_scores_failed(dialog.current_date, FAILED)
        assert self.rows(dialog.scores_list) == before
        self.said.assert_called_once_with(FAILED)

    def test_world_cup_scores_failing_on_a_new_day_is_a_row(self):
        dialog = self.world_cup()
        dialog._on_scores_loaded(dialog.current_date, [])
        dialog.current_date += timedelta(days=1)
        dialog._on_scores_failed(dialog.current_date, FAILED)
        assert self.rows(dialog.scores_list) == [FAILED]

    def test_a_world_cup_answer_for_a_day_left_behind_is_dropped(self):
        dialog = self.world_cup()
        left = dialog.current_date
        dialog.current_date += timedelta(days=1)
        dialog.scores_list.clear()
        dialog.scores_list.addItem("Loading matches\u2026")
        dialog._on_scores_loaded(left, [])
        dialog._on_scores_failed(left, FAILED)
        assert self.rows(dialog.scores_list) == ["Loading matches\u2026"]
        assert dialog._shown_games is None
        self.said.assert_not_called()

    def test_the_world_cup_loader_says_which_day_it_is_about(self):
        day = date(2026, 6, 20)
        loader = self.scores.WorldCupScoresLoader("WC2026", day)
        got = []
        loader.data_loaded.connect(lambda *a: got.append(a))
        loader.error_occurred.connect(lambda *a: got.append(a))
        with patch.object(self.scores.ApiService, "get_scores", return_value=[]):
            loader.run()
        with patch.object(self.scores.ApiService, "get_scores", side_effect=self.scores.ApiError(FAILED)):
            loader.run()
        assert got == [(day, []), (day, FAILED)]

    def test_world_cup_groups_failing_with_some_showing_keeps_them(self):
        dialog = self.world_cup()
        dialog.current_groups = [{"name": "Group A", "teams": []}]
        before = dialog.groups_layout.count()
        dialog._set_group_error(FAILED)
        assert dialog.groups_layout.count() == before
        self.said.assert_called_once_with(FAILED)

    def test_world_cup_groups_failing_with_none_is_a_row(self):
        dialog = self.world_cup()
        dialog._set_group_error(FAILED)
        row = dialog.groups_layout.itemAt(dialog.groups_layout.count() - 2).widget()
        assert self.rows(row) == [FAILED]

    def draft(self):
        with patch.object(self.scores.NFLDraftDialog, "_load_year"):
            dialog = self.scores.NFLDraftDialog()
        dialog._current_year = 2026
        return dialog

    def test_the_draft_failing_is_a_row(self):
        dialog = self.draft()
        dialog._on_meta_error(FAILED, 2026)
        assert dialog.tab_widget.count() == 1
        assert self.rows(dialog.tab_widget.widget(0)) == [FAILED]
        assert dialog.status_label.text() == ""

    def test_f5_in_the_draft_only_tries_again_what_failed(self):
        dialog = self.draft()
        with patch.object(dialog, "_load_year") as load_year, patch.object(dialog, "_load_round") as load_round:
            dialog._on_meta_error(FAILED, 2026)
            self.press_f5(dialog)
            load_year.assert_called_once_with(2026)
            load_round.assert_not_called()

    def test_a_year_left_behind_failing_changes_nothing(self):
        dialog = self.draft()
        dialog._on_meta_error(FAILED, 2012)
        assert dialog.tab_widget.count() == 0

    def test_a_round_failing_says_so_and_coming_back_asks_again(self):
        dialog = self.draft()
        with patch.object(self.scores.NFLDraftDialog, "_load_round"):
            dialog._on_meta_loaded({"status": "post", "rounds": [{"number": 1, "short_name": "1st"}]})
        dialog._on_round_error(FAILED, 0, 2026)
        assert self.rows(dialog.tab_widget.widget(0)) == [FAILED]
        assert 0 not in dialog._tabs_loaded

    def test_said_never_reads_out_raw_text(self):
        with patch.object(self.scores.error_log, "log_handled") as logged:
            try:
                raise ConnectionError("HTTPSConnectionPool(host='site.api.espn.com', port=443)")
            except ConnectionError as e:
                assert self.scores._said(e) == "Something went wrong. Try again in a minute."
            logged.assert_called_once()
            logged.reset_mock()
            assert self.scores._said(self.scores.ApiError(FAILED)) == FAILED
            logged.assert_not_called()

    def test_said_is_what_the_loaders_pass_on(self):
        loader = self.scores.TeamNewsLoader("9", "NFL")
        got = []
        loader.error_occurred.connect(got.append)
        with patch.object(self.scores.ApiService, "get_team_news", side_effect=self.scores.ApiError(FAILED)):
            loader.run()
        assert got == [FAILED]


class TestMonitoring(FailureViews):
    """Live Scores' Monitoring section: Alt+M copies a game to the top, with its sport, and
    nothing is read out on its own."""

    @staticmethod
    def finished(game_id, league, name=None):
        name = name or f"{league} game {game_id}"
        return {"game_id": game_id, "league": league, "state": "completed", "start_time": "",
                "display_text": name, "raw_data": {"id": game_id, "league": league, "name": name}}

    @staticmethod
    def live(game_id, league, score="7"):
        return {"id": game_id, "league": league, "name": f"Away {game_id} at Home {game_id}",
                "status": "Q2", "teams": [{"name": "Home", "score": score, "home_away": "home"},
                                         {"name": "Away", "score": "3", "home_away": "away"}]}

    @pytest.fixture
    def view(self):
        view = self.scores.LiveScoresView(None)
        view.refresh_timer.stop()
        return view

    def keys(self, view):
        lst = view.live_scores_list
        return [self.scores._row_key(lst.item(i).data(self.role)) for i in range(lst.count())]

    def go_to(self, view, key):
        view.live_scores_list.setCurrentRow(self.keys(view).index(key))

    def current_key(self, view):
        return self.scores._row_key(view.live_scores_list.currentItem().data(self.role))

    def load(self, view, today=(), live=(), failed=()):
        view._on_live_scores_loaded(list(live), list(today), [], list(failed))

    def test_the_section_is_first_and_says_how_to_add_a_game(self, view):
        self.load(view, [self.finished("1", "NHL")])
        rows = self.rows(view.live_scores_list)
        assert rows[0] == self.scores.MONITORING_EMPTY
        assert self.keys(view)[0] == self.scores.MONITORING_HEADER

    def test_each_heading_says_how_many_it_holds(self, view):
        """As the iPhone's headings do: one arrow tells whether a section is worth entering."""
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL"), self.finished("3", "NBA")],
                  live=[self.live("4", "NFL")])
        rows = self.rows(view.live_scores_list)
        assert "Live games, 1" in rows and "NFL, 1" in rows
        assert "Completed games, 3" in rows
        assert "NBA, 1" in rows and "NHL, 2" in rows
        # Bold sets a heading apart now, not "===" or "---", which a screen reader read aloud.
        lst = view.live_scores_list
        keys = self.keys(view)
        headings = [lst.item(i) for i, key in enumerate(keys)
                    if key == self.scores.MONITORING_HEADER
                    or isinstance(key, tuple) and key[0] == self.scores.LIVE_HEADER]
        assert len(headings) == 6 and all(item.font().bold() for item in headings)
        assert not any(lst.item(i).font().bold() for i in range(lst.count()) if lst.item(i) not in headings)

    def test_a_heading_keeps_its_place_when_its_count_changes(self, view):
        """Its data says which heading it is, so a refresh finds it though its text changed."""
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NBA")])
        self.go_to(view, (self.scores.LIVE_HEADER, "completed:NHL"))
        kept = view.live_scores_list.currentItem()
        self.load(view, [self.finished("1", "NHL"), self.finished("5", "NHL"), self.finished("2", "NBA")])
        # The same row, not a rebuilt one found again, which a screen reader would read out.
        assert view.live_scores_list.currentItem() is kept and view._rows_rebuilt is False
        assert kept.text() == "NHL, 2"

    def test_the_monitoring_header_keeps_its_place_as_games_come_and_go(self, view):
        """Its text has a count now; its data still says it's the Monitoring header."""
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NBA")])
        self.go_to(view, "2")
        view._toggle_monitoring()
        self.go_to(view, self.scores.MONITORING_HEADER)
        kept = view.live_scores_list.currentItem()
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NBA"), self.finished("7", "MLB")])
        assert view.live_scores_list.currentItem() is kept and view._rows_rebuilt is False

    def test_enter_on_a_heading_opens_nothing(self, view):
        self.load(view, [self.finished("1", "NHL")])
        self.go_to(view, (self.scores.LIVE_HEADER, "completed"))
        assert view._current_game() is None

    def test_no_games_today_has_no_section(self, view):
        self.load(view)
        rows = self.rows(view.live_scores_list)
        assert len(rows) == 1 and rows[0].startswith("No games on")

    def test_alt_m_copies_the_game_to_the_top_with_its_sport_and_keeps_its_own_row(self, view):
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NBA")])
        self.go_to(view, "2")
        view._toggle_monitoring()
        rows = self.rows(view.live_scores_list)
        assert rows[0] == "Monitoring, 1"
        assert rows[1] == "NBA game 2 | NBA"
        assert "NBA game 2 - monitoring" in rows
        assert "NHL game 1" in rows
        assert self.current_key(view) == "2"  # still on the game's own row
        self.said.assert_called_once_with("Added to monitoring")
        assert view.monitored_games == {"2": "NBA"}

    def test_a_live_football_row_reads_as_it_does_below_with_the_sport_after_it(self, view):
        game = self.live("9", "NCAAF")
        game["recent_play"] = "Shotgun J.Smith pass complete short right for 12 yards"
        game["status"] = "10:58 - 3rd"
        self.load(view, live=[game])
        self.go_to(view, "9")
        own = view.live_scores_list.currentItem().text()
        view._toggle_monitoring()
        rows = self.rows(view.live_scores_list)
        assert rows[1] == f"{own} | NCAAF"
        assert f"{own} - monitoring" in rows
        assert "12 yards" in rows[1]  # all the detail, then the sport

    def test_monitored_games_are_in_the_order_added(self, view):
        games = [self.finished(str(i), "NHL") for i in (1, 2, 3)]
        self.load(view, games)
        for game_id in ("3", "1"):
            self.go_to(view, game_id)
            view._toggle_monitoring()
        assert self.keys(view)[:3] == [self.scores.MONITORING_HEADER, ("monitoring", "3"), ("monitoring", "1")]

    def test_alt_m_on_a_monitoring_row_takes_it_off_and_lands_on_the_next(self, view):
        games = [self.finished(str(i), "NHL") for i in (1, 2, 3)]
        self.load(view, games)
        for game_id in ("1", "2", "3"):
            self.go_to(view, game_id)
            view._toggle_monitoring()
        self.go_to(view, ("monitoring", "2"))
        self.said.reset_mock()
        view._toggle_monitoring()
        assert self.current_key(view) == ("monitoring", "3")
        assert ("monitoring", "2") not in self.keys(view)
        assert "NHL game 2 - monitoring" not in self.rows(view.live_scores_list)
        self.said.assert_called_once_with("NHL game 2 removed from monitoring")

    def test_taking_off_the_last_monitoring_row_lands_on_the_header(self, view):
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        for game_id in ("1", "2"):
            self.go_to(view, game_id)
            view._toggle_monitoring()
        self.go_to(view, ("monitoring", "2"))
        view._toggle_monitoring()
        assert self.current_key(view) == self.scores.MONITORING_HEADER
        self.go_to(view, ("monitoring", "1"))
        view._toggle_monitoring()
        assert self.current_key(view) == self.scores.MONITORING_HEADER
        assert self.rows(view.live_scores_list)[0] == self.scores.MONITORING_EMPTY

    def test_alt_m_on_the_games_own_row_again_takes_it_off_and_stays(self, view):
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        self.go_to(view, "2")
        view._toggle_monitoring()
        view._toggle_monitoring()
        assert self.current_key(view) == "2"
        assert view.monitored_games == {}
        assert not any(row.endswith(" - monitoring") for row in self.rows(view.live_scores_list))

    def test_alt_m_on_a_heading_asks_for_a_game(self, view):
        self.load(view, [self.finished("1", "NHL")])
        view.live_scores_list.setCurrentRow(0)
        view._toggle_monitoring()
        self.said.assert_called_once_with("Choose a game to monitor")
        assert view.monitored_games == {}

    def test_enter_on_a_monitoring_row_opens_the_game(self, view):
        self.load(view, [self.finished("1", "NHL")])
        self.go_to(view, "1")
        view._toggle_monitoring()
        view.parent_app = SimpleNamespace(open_game_details=lambda *a, **k: opened.append((a, k)),
                                          current_league=None)
        opened = []
        self.go_to(view, ("monitoring", "1"))
        view._on_game_selected(view.live_scores_list.currentItem())
        assert opened == [(("1",), {"from_live_scores": True})]

    def test_a_score_change_is_not_read_out(self, view):
        self.load(view, live=[self.live("9", "NCAAF", score="7")])
        self.go_to(view, "9")
        view._toggle_monitoring()
        self.said.reset_mock()
        self.load(view, live=[self.live("9", "NCAAF", score="14")])
        self.said.assert_not_called()
        assert "14" in self.rows(view.live_scores_list)[1]

    def test_a_refresh_keeps_your_monitoring_row(self, view):
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        self.go_to(view, "2")
        view._toggle_monitoring()
        self.go_to(view, ("monitoring", "2"))
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL"), self.finished("3", "NHL")])
        assert self.current_key(view) == ("monitoring", "2")

    def test_an_unchanged_refresh_changes_no_row(self, view):
        """Setting a row's data, even to the same, tells a screen reader the row changed,
        and it read the focused row again at every refresh."""
        games = [self.finished("1", "NHL"), self.finished("2", "NHL")]
        self.load(view, games)
        self.go_to(view, "2")
        view._toggle_monitoring()
        changed = []
        view.live_scores_list.itemChanged.connect(changed.append)
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        assert changed == []

    def test_taking_one_off_skips_a_monitored_game_that_is_not_shown(self, view):
        self.load(view, [self.finished("1", "NHL")])
        self.go_to(view, "1")
        view._toggle_monitoring()
        view.monitored_games["gone"] = "NHL"  # added after it left today's list
        self.load(view, [self.finished("1", "NHL")])
        self.go_to(view, ("monitoring", "1"))
        view._toggle_monitoring()
        assert self.current_key(view) == self.scores.MONITORING_HEADER

    def test_arriving_with_nothing_monitored_starts_after_the_heading(self, view):
        view.live_scores_list.setCurrentRow(0)  # "Loading live scores...", as on_show leaves it
        self.load(view, [self.finished("1", "NHL")])
        assert view.live_scores_list.currentRow() == 1

    def test_games_coming_and_going_keep_the_row_you_are_on(self, view):
        """A game kicking off or finishing rebuilt the list, and the screen reader read the
        row you were on again: once a minute on a busy day."""
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        self.go_to(view, "2")
        view._toggle_monitoring()
        self.go_to(view, ("monitoring", "2"))
        lst = view.live_scores_list
        kept = lst.currentItem()
        moved = []
        lst.currentItemChanged.connect(lambda *a: moved.append(a))
        self.load(view, [self.finished("3", "NBA"), self.finished("1", "NHL"), self.finished("2", "NHL")])
        assert lst.currentItem() is kept
        assert moved == []
        assert "NBA game 3" in self.rows(lst)
        assert self.current_key(view) == ("monitoring", "2")
        assert view._rows_rebuilt is False

    def test_a_row_that_is_gone_is_left_for_the_nearest(self, view):
        self.load(view, [self.finished("1", "NHL"), self.finished("2", "NHL")])
        self.go_to(view, "2")
        self.load(view, [self.finished("1", "NHL")])
        assert view._rows_rebuilt is True
        assert view.live_scores_list.currentItem() is not None

    def test_a_game_no_longer_on_todays_list_is_not_shown(self, view):
        self.load(view, [self.finished("1", "NHL")])
        view.monitored_games["gone"] = "NHL"
        self.load(view, [self.finished("1", "NHL")])
        assert self.rows(view.live_scores_list)[0] == self.scores.MONITORING_EMPTY

    def test_coming_back_from_a_game_lands_on_the_monitoring_row(self, view):
        self.load(view, [self.finished("1", "NHL")])
        self.go_to(view, "1")
        view._toggle_monitoring()
        self.go_to(view, ("monitoring", "1"))
        state = view.capture_state()
        again = self.scores.LiveScoresView(None)
        again.refresh_timer.stop()
        again.monitored_games = view.monitored_games
        again._restore_state = state
        self.load(again, [self.finished("1", "NHL")])
        assert self.current_key(again) == ("monitoring", "1")


class TestMonitoringFromALeague(FailureViews):
    @pytest.fixture
    def view(self):
        view = self.scores.LeagueView(None, "NBA")
        view.parent_app = SimpleNamespace(monitored_games={}, update_window_title=lambda items: None)
        return view

    def land(self, view, games):
        view._on_scores_loaded(view._scores_generation, None, games, [])
        self.said.reset_mock()  # the date the list now shows

    def go_to(self, view, game_id):
        lst = view.scores_list
        lst.setCurrentRow(next(i for i in range(lst.count()) if lst.item(i).data(self.role) == game_id))

    def todays(self, game_id):
        # Noon Eastern on today's scoreboard, which is still yesterday's until 5 AM.
        start = f"{self.scores.scoreboard_today().isoformat()}T17:00Z"
        g = game(game_id, "pre", start=start)
        g["name"] = f"Away {game_id} at Home {game_id}"
        return g

    def test_todays_game_is_added_for_live_scores(self, view):
        self.land(view, [self.todays("5")])
        self.go_to(view, "5")
        view._toggle_monitoring()
        assert view.parent_app.monitored_games == {"5": "NBA"}
        self.said.assert_called_once_with("Added to monitoring, at the top of Live Scores")

    def test_alt_m_again_takes_it_off(self, view):
        self.land(view, [self.todays("5")])
        self.go_to(view, "5")
        view._toggle_monitoring()
        view._toggle_monitoring()
        assert view.parent_app.monitored_games == {}
        assert self.said.call_args.args[0] == "Removed from monitoring"

    def test_another_days_game_is_not(self, view):
        other = game("6", "pre", start="2020-01-04T18:00Z")
        other["name"] = "Old at Game"
        self.land(view, [other])
        self.go_to(view, "6")
        view._toggle_monitoring()
        assert view.parent_app.monitored_games == {}
        self.said.assert_called_once_with("Only today's games can be monitored")

    def test_a_game_whose_time_is_not_set_goes_by_its_utc_date(self, view):
        g = self.todays("7")
        g["competitions"] = [{"timeValid": False}]
        self.land(view, [g])
        self.go_to(view, "7")
        view._toggle_monitoring()
        assert view.parent_app.monitored_games == {"7": "NBA"}

    def test_a_row_that_is_not_a_game_asks_for_one(self, view):
        self.land(view, [self.todays("5")])
        view.scores_list.setCurrentRow(0)  # the section header
        view._toggle_monitoring()
        self.said.assert_called_once_with("Choose a game to monitor")

    def test_alt_m_reaches_it(self, view):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        with patch.object(view, "_toggle_monitoring") as toggle:
            view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_M, Qt.KeyboardModifier.AltModifier))
        toggle.assert_called_once()
