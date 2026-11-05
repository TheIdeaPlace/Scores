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
        with patch.object(api, "get_scores", return_value=[]), \
                patch.object(api, "get_news", return_value=[]), \
                patch.object(api, "freshen_live_games", return_value=[]) as freshen:
            loader.run()
        return freshen

    def test_week_request_is_freshened(self):
        self.run_loader(dict(week=6, season=2026, seasontype=2)).assert_called_once()

    def test_date_request_is_not(self):
        self.run_loader(dict(date=date(2026, 10, 9))).assert_not_called()


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
        assert "--- News Headlines ---" in rows
        assert "--- Standings ---" in rows and "--- Teams ---" in rows
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
        assert "--- News Headlines ---" in self.rows(view.scores_list)
        self.land(view)
        assert "--- News Headlines ---" not in self.rows(view.scores_list)

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

    def test_a_monitored_game_hears_it_once_until_it_answers_again(self, view):
        live = {"id": "1", "league": "NBA", "name": "A at B", "status": "Q1", "teams": []}
        view.monitored_games.add("1")
        view._on_live_scores_loaded([live], [], [], [])
        for _ in range(3):
            view._on_live_scores_loaded([], [], [], ["NBA"])
        assert self.said.call_count == 1
        view._on_live_scores_loaded([live], [], [], [])
        view._on_live_scores_loaded([], [], [], ["NBA"])
        assert self.said.call_count == 2

    def test_a_monitored_league_is_still_heard_after_another_failed_quietly(self, view):
        live = {"id": "1", "league": "NBA", "name": "A at B", "status": "Q1", "teams": []}
        view.monitored_games.add("1")
        view._on_live_scores_loaded([live], [], [], [])
        view._on_live_scores_loaded([live], [], [], ["NHL"])
        self.said.assert_not_called()
        view._on_live_scores_loaded([], [], [], ["NHL", "NBA"])
        self.said.assert_called_once()

    def test_a_retry_that_works_lands_on_a_row(self, view):
        self.load(view, [self.today_game("1", "NHL")], ["NBA"])
        lst = view.live_scores_list
        lst.setCurrentRow(lst.count() - 1)
        self.load(view, [self.today_game("1", "NHL")])
        assert lst.currentRow() == lst.count() - 1 and lst.count() > 0

    def test_someone_on_the_row_hears_a_changed_row_once(self, view):
        self.load(view, failed=["NBA"])
        view.live_scores_list.setCurrentRow(0)
        with patch.object(view, "load_live_scores"):
            view.refresh()
        self.load(view, failed=["NBA", "NHL"])
        assert view.live_scores_list.currentRow() == 0
        self.said.assert_not_called()

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

    def test_a_league_nobody_is_monitoring_stays_quiet(self, view):
        live = {"id": "1", "league": "NBA", "name": "A at B", "status": "Q1", "teams": []}
        view.monitored_games.add("1")
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
                patch.object(self.scores.TransactionsDialog, "_load_transactions"):
            return self.scores.TransactionsDialog("NFL")

    def test_transactions_failing_is_not_no_transactions(self):
        dialog = self.transactions()
        loading = self.scores.QListWidgetItem("Loading transactions...")
        dialog.trans_list.addItem(loading)
        dialog._on_error(FAILED, loading)
        assert self.rows(dialog.trans_list) == [FAILED]
        assert dialog.trans_list.currentRow() == 0

    def test_load_more_failing_keeps_the_list_and_asks_for_the_same_page_next(self):
        dialog = self.transactions()
        dialog.trans_list.addItem("2026-11-01 A trade")
        dialog.current_page = 2
        loading = self.scores.QListWidgetItem("Loading transactions...")
        dialog.trans_list.addItem(loading)
        dialog._on_error(FAILED, loading)
        assert self.rows(dialog.trans_list) == ["2026-11-01 A trade"]
        assert dialog.current_page == 1
        assert dialog.load_more_btn.isEnabled()
        self.said.assert_called_once_with(FAILED)

    def press_f5(self, dialog):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))

    def test_f5_in_transactions_only_tries_again_what_failed(self):
        dialog = self.transactions()
        with patch.object(dialog, "_load_transactions") as load:
            self.press_f5(dialog)
            load.assert_not_called()
            loading = self.scores.QListWidgetItem("Loading transactions...")
            dialog.trans_list.addItem(loading)
            dialog._on_error(FAILED, loading)
            self.press_f5(dialog)
            load.assert_called_once_with(reset=True)

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

    def test_a_world_cup_refresh_that_fails_keeps_the_games_and_says_so_once(self):
        dialog = self.world_cup()
        dialog._on_scores_loaded([])
        dialog._shown_games = (dialog.current_date, [])
        before = self.rows(dialog.scores_list)
        dialog._on_scores_failed(FAILED)
        assert self.rows(dialog.scores_list) == before
        dialog._say_refresh_failed(FAILED)
        self.said.assert_called_once_with(FAILED)

    def test_world_cup_scores_failing_on_another_day_is_a_row(self):
        dialog = self.world_cup()
        dialog._on_scores_failed(FAILED)
        assert self.rows(dialog.scores_list) == [FAILED]

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
