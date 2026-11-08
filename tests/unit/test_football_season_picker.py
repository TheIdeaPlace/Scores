"""Choosing a past football season in an NFL or NCAAF league list (Ctrl+G, #192).

The iPhone's season menu offers each league's earliest season through the
current one, opens a past season on regular season Week 1, and treats the
season under way as "back to the current week". Windows does the same from a
Go to Season dialog. The rules are pure functions in services/football_calendar;
the view is driven offscreen with its loader thread stubbed out, so nothing here
touches the network.
"""

import os
import sys
from datetime import date
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services import football_calendar as fc  # noqa: E402


CACHES = ("_SEASON_WEEKS_CACHE", "_WEEK_DATE_CACHE", "_SERVED_SEASON",
          "_CORE_SEASON_CACHE", "_CORE_WEEK_TEXT_CACHE")


@pytest.fixture(autouse=True)
def clear_caches():
    for name in CACHES:
        getattr(fc, name).clear()
    yield
    for name in CACHES:
        getattr(fc, name).clear()


class TestSeasonChoices:
    def test_nfl_runs_from_the_current_season_back_to_2001_newest_first(self):
        seasons = fc.season_choices("NFL", 2026, today=date(2026, 11, 7))
        assert seasons[0] == 2026 and seasons[-1] == 2001
        assert seasons == sorted(seasons, reverse=True)
        assert len(seasons) == 26

    def test_ncaaf_starts_at_2005_as_on_the_iphone(self):
        assert fc.season_choices("NCAAF", 2026, today=date(2026, 11, 7))[-1] == 2005

    def test_january_still_belongs_to_last_years_season(self):
        assert fc.season_choices("NFL", 2026, today=date(2027, 1, 20))[0] == 2026

    def test_spring_tops_the_list_with_the_season_espn_serves(self):
        # From March the calendar names 2027 while ESPN serves 2026 until late July;
        # 2027 has no games yet, and the top row has to be the way back to now.
        seasons = fc.season_choices("NFL", 2026, today=date(2027, 4, 1))
        assert seasons[0] == 2026

    def test_espn_ahead_of_the_calendar_is_still_the_top(self):
        assert fc.season_choices("NFL", 2027, today=date(2026, 11, 7))[0] == 2027

    def test_without_a_known_live_season_the_calendar_decides(self):
        assert fc.season_choices("NFL", None, today=date(2026, 11, 7))[0] == 2026

    def test_other_leagues_have_none(self):
        assert fc.season_choices("NBA", 2026) == []


class TestSeasonStart:
    def test_a_past_season_opens_on_regular_season_week_1(self):
        assert fc.season_start(2019, 2026) == (2019, fc.SEASON_TYPE_REGULAR, 1)

    def test_the_season_under_way_goes_back_to_the_current_week(self):
        assert fc.season_start(2026, 2026) is None

    def test_a_coming_season_opens_on_its_week_1(self):
        assert fc.season_start(2027, 2026) == (2027, fc.SEASON_TYPE_REGULAR, 1)


# The 2019 NFL season as prepare_week leaves it in the caches: its weeks from the
# Core API and the names of those already visited.
PAST_WEEKS = [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)]


def seed_past_season(league="NFL", season=2019, served=2026):
    fc._SERVED_SEASON[league] = served
    fc._CORE_SEASON_CACHE[(league, season)] = list(PAST_WEEKS)
    fc._CORE_WEEK_TEXT_CACHE[(league, season, 2, 1)] = "Week 1"
    fc._CORE_WEEK_TEXT_CACHE[(league, season, 3, 1)] = "Wild Card"
    fc._CORE_WEEK_TEXT_CACHE[(league, season, 3, 2)] = "Super Bowl"
    fc._CORE_WEEK_TEXT_CACHE[(league, season, 1, 1)] = "Hall of Fame Weekend"


class QtCase:
    @pytest.fixture(autouse=True)
    def qt(self):
        pytest.importorskip("PyQt6")
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        import scores
        self.scores = scores
        self.loaders = []
        with patch.object(scores, "_start_detached_thread", side_effect=self.loaders.append), \
                patch.object(scores, "announce") as said:
            self.said = said
            yield

    def football_view(self, league="NFL", season=2026, season_type=2, week=10):
        """A league list whose first load has landed on ESPN's current week."""
        view = self.scores.LeagueView(None, league)
        view._on_scores_loaded(view._scores_generation, (season, season_type, week), [], [])
        self.said.reset_mock()
        return view


class TestTheView(QtCase):
    def test_the_first_load_records_the_season_under_way(self):
        view = self.football_view()
        assert view._live_season == 2026
        assert view.date_label.text() == "Week 10"  # no season named for the current one

    def test_choosing_a_past_season_loads_its_week_1_on_the_loader_thread(self):
        view = self.football_view()
        view.show_season(2019, 2026)
        loader = self.loaders[-1]
        assert loader.request == dict(week=1, season=2019, seasontype=2)
        assert loader.resolve_calendar is False
        assert (view.current_season, view.current_season_type, view.current_week) == (2019, 2, 1)

    def test_the_week_label_names_the_season_and_is_announced(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        assert view.date_label.text() == "Week 1, 2019 season"
        self.said.assert_called_once_with("Week 1, 2019 season")

    def test_a_named_week_reads_with_its_prefix_and_season(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view.current_season_type, view.current_week = 3, 1
        assert view._week_label() == "Week: Wild Card, 2019 season"

    def test_the_window_title_names_the_week_and_season(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        assert view._title_items() == ["Week 1, 2019 season", "NFL"]

    def test_the_arrows_step_through_the_chosen_season_and_stop_at_its_end(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        for _ in range(3):
            view.next_week()
            view._on_scores_loaded(view._scores_generation, None, [], [])
        assert (view.current_season, view.current_season_type, view.current_week) == (2019, 3, 2)
        assert self.loaders[-1].request == dict(week=2, season=2019, seasontype=3)
        loads = len(self.loaders)
        view.next_week()
        assert len(self.loaders) == loads  # nothing past the Super Bowl
        assert view.date_label.text() == "Week: Super Bowl, 2019 season — last week of the season"

    def test_the_arrows_stop_at_the_seasons_first_week(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view.current_season_type, view.current_week = 1, 1
        loads = len(self.loaders)
        view.previous_week()
        assert len(self.loaders) == loads
        assert view.date_label.text().endswith("— first week of the season")

    def test_choosing_the_season_under_way_returns_to_the_current_week(self):
        seed_past_season()
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        self.said.reset_mock()
        view.show_season(2026, 2026)
        assert self.loaders[-1].resolve_calendar is True
        assert self.loaders[-1].requested_week is None
        assert view.date_label.text() == "Finding the current week..."
        view._on_scores_loaded(view._scores_generation, (2026, 2, 10), [], [])
        assert view.date_label.text() == "Week 10"
        self.said.assert_called_once_with("Week 10")

    def test_choosing_the_week_already_shown_is_still_heard(self):
        view = self.football_view()
        view.show_season(2026, 2026)
        view._on_scores_loaded(view._scores_generation, (2026, 2, 10), [], [])
        self.said.assert_called_once_with("Week 10")

    def test_a_failed_return_says_so_rather_than_keeping_the_old_seasons_games(self):
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        view.show_season(2026, 2026)
        view._on_scores_error(view._scores_generation, "ESPN isn't providing scores right now.")
        assert view.scores_list.item(0).text() == "ESPN isn't providing scores right now."
        assert view._calendar_pending is True  # Enter on that row asks for the calendar again

    def test_after_a_failed_return_a_season_can_still_be_chosen(self):
        view = self.football_view()
        view.show_season(2019, 2026)
        view.show_season(2026, 2026)
        view._on_scores_error(view._scores_generation, "ESPN isn't providing scores right now.")
        with patch.object(self.scores, "SeasonPickerDialog") as dialog:
            dialog.return_value.exec.return_value = self.scores.QDialog.DialogCode.Accepted
            dialog.return_value.selected_season.return_value = 2015
            view.go_to_season()
        assert view._calendar_pending is False
        assert self.loaders[-1].resolve_calendar is False
        assert self.loaders[-1].request == dict(week=1, season=2015, seasontype=2)

    def test_a_failed_return_takes_the_old_season_out_of_the_title(self):
        from unittest.mock import MagicMock
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        view.parent_app = MagicMock()
        view.show_season(2026, 2026)
        view._on_scores_error(view._scores_generation, "ESPN isn't providing scores right now.")
        view.parent_app.update_window_title.assert_called_with(["NFL"])

    def test_the_live_season_is_espns_not_the_calendar_guess(self):
        fc._SERVED_SEASON["NFL"] = 2026
        view = self.scores.LeagueView(None, "NFL")
        # ESPN has answered for 2026, whatever year the load was resolved to.
        view._on_scores_loaded(view._scores_generation, (2027, 2, 1), [], [])
        assert view._live_season == 2026
        fc._SERVED_SEASON.clear()
        failed = self.scores.LeagueView(None, "NFL")  # calendar failed: the guess is all there is
        failed._on_scores_loaded(failed._scores_generation, (2027, 2, 1), [], [])
        assert failed._live_season == 2027

    def test_back_from_a_game_keeps_the_chosen_season(self):
        view = self.football_view()
        view.show_season(2019, 2026)
        view._on_scores_loaded(view._scores_generation, None, [], [])
        state = view.capture_state()
        again = self.scores.LeagueView(None, "NFL", state=state)
        assert again._live_season == 2026
        assert (again.current_season, again.current_week) == (2019, 1)
        assert self.loaders[-1].request == dict(week=1, season=2019, seasontype=2)

    def test_ctrl_g_before_the_calendar_has_loaded_says_why_nothing_opens(self):
        view = self.scores.LeagueView(None, "NFL")
        with patch.object(self.scores, "SeasonPickerDialog") as dialog:
            view.go_to_season()
        dialog.assert_not_called()
        self.said.assert_called_once_with("Seasons can be chosen once the current week has loaded")

    def test_ctrl_g_offers_the_seasons_and_opens_the_choice(self):
        view = self.football_view()
        with patch.object(self.scores, "SeasonPickerDialog") as dialog:
            dialog.return_value.exec.return_value = self.scores.QDialog.DialogCode.Accepted
            dialog.return_value.selected_season.return_value = 2010
            view.go_to_season()
        league, seasons, live, shown = dialog.call_args.args[:4]
        assert (league, live, shown) == ("NFL", 2026, 2026)
        assert seasons[0] >= 2026 and seasons[-1] == 2001
        assert self.loaders[-1].request == dict(week=1, season=2010, seasontype=2)

    def test_cancel_changes_nothing(self):
        view = self.football_view()
        loads = len(self.loaders)
        with patch.object(self.scores, "SeasonPickerDialog") as dialog:
            dialog.return_value.exec.return_value = self.scores.QDialog.DialogCode.Rejected
            view.go_to_season()
        assert len(self.loaders) == loads
        assert view.current_season == 2026

    def test_the_button_is_there_for_football_only(self):
        from PyQt6.QtWidgets import QPushButton
        nfl = self.football_view()
        texts = [b.text() for b in nfl.findChildren(QPushButton)]
        assert "Go to Season (Ctrl+G)" in texts
        nba = self.scores.LeagueView(None, "NBA")
        assert "Go to Season (Ctrl+G)" not in [b.text() for b in nba.findChildren(QPushButton)]

    def test_other_leagues_do_nothing(self):
        view = self.scores.LeagueView(None, "NBA")
        with patch.object(self.scores, "SeasonPickerDialog") as dialog:
            view.go_to_season()
        dialog.assert_not_called()


class TestTheDialog(QtCase):
    def dialog(self, shown=2019):
        return self.scores.SeasonPickerDialog("NFL", list(range(2026, 2000, -1)), 2026, shown)

    def test_it_opens_on_the_season_shown(self):
        dlg = self.dialog()
        assert dlg.season_list.currentItem().text() == "2019"
        assert dlg.selected_season() == 2019

    def test_the_season_under_way_is_first_and_says_so(self):
        dlg = self.dialog()
        assert dlg.season_list.item(0).text() == "2026, current season"
        assert dlg.season_list.item(0).data(self.scores.Qt.ItemDataRole.UserRole) == 2026

    def test_it_is_named_for_a_screen_reader(self):
        dlg = self.dialog()
        assert dlg.windowTitle() == "Go to Season - NFL"
        assert dlg.season_list.accessibleName() == "Season"

    def test_enter_chooses_the_season(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        dlg = self.dialog()
        dlg.season_list.setCurrentRow(0)
        QTest.keyClick(dlg.season_list, Qt.Key.Key_Return)
        assert dlg.result() == self.scores.QDialog.DialogCode.Accepted
        assert dlg.selected_season() == 2026

    def test_a_season_not_listed_opens_at_the_top(self):
        assert self.dialog(shown=1990).season_list.currentRow() == 0
