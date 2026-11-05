"""College football's Standings and Teams dialogs, and the cache behind Standings, on ESPN's real
group=90 answer. Builds Qt objects: CI or the VM only."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QTabWidget, QToolButton  # noqa: E402

from accessible_table import ListPages  # noqa: E402
import espn_api  # noqa: E402
import scores  # noqa: E402
import settings  # noqa: E402
import soccer  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn", "standings_NCAAF_group90.json")


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    """No real %APPDATA% settings, and nothing left in the cache, which is a singleton."""
    monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
    monkeypatch.setattr(settings, "_cache", None)
    monkeypatch.setattr(scores.DataCache(), "standings_cache", {})


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rows():
    with open(FIXTURE, encoding="utf-8") as f:
        return espn_api.parse_college_standings(json.load(f))


def tab_names(dialog):
    return [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]


class TestTabs:
    def test_standings_and_teams_list_the_conferences_in_the_same_order(self, app, rows):
        standings_dialog = scores.StandingsDialog(rows, "NCAAF")
        teams_dialog = scores.SimpleTeamsDialog(rows, "NCAAF")
        standings = tab_names(standings_dialog)
        assert standings == tab_names(teams_dialog)
        assert len(standings) == 25
        assert standings[0] == "Southeastern Conference"
        assert standings[10] == "FBS Independents"
        assert standings[11] == "Big Sky Conference"
        assert standings[11:] == sorted(standings[11:])

    @pytest.mark.parametrize("dialog_class", ["StandingsDialog", "SimpleTeamsDialog"])
    def test_the_25_conferences_are_a_named_list_with_one_tab_stop(self, app, rows, dialog_class):
        tabs = getattr(scores, dialog_class)(rows, "NCAAF").tab_widget
        assert isinstance(tabs, ListPages)
        assert tabs.tabBar().accessibleName() == "Conferences"
        assert tabs.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tabs.tabBar().focusPolicy() & Qt.FocusPolicy.TabFocus

    def test_a_shorter_area_stays_tabs_with_one_tab_stop(self, app, rows):
        """Without its scroll buttons a tab bar asks for the width of every tab."""
        division = ["AFC East", "AFC North", "NFC East", "NFC North"]
        short = [dict(row, division=division[i % 4]) for i, row in enumerate(rows)]
        tabs = scores.SimpleTeamsDialog(short, "NFL").tab_widget
        assert isinstance(tabs, QTabWidget)
        assert tabs.usesScrollButtons()
        assert tabs.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tabs.tabBar().focusPolicy() == Qt.FocusPolicy.TabFocus
        buttons = tabs.tabBar().findChildren(QToolButton)
        assert buttons and all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in buttons)


class TestCache:
    def test_changing_the_setting_doesnt_read_the_other_coverages_standings(self, rows):
        settings.set("ncaaf_coverage", "all_d1")
        cache = scores.DataCache()
        cache.set_standings(espn_api.standings_cache_key("NCAAF"), rows)
        assert cache.get_standings("NCAAF") == rows
        settings.set("ncaaf_coverage", "fbs")
        assert cache.get_standings("NCAAF") is None
        settings.set("ncaaf_coverage", "all_d1")
        assert cache.get_standings("NCAAF") == rows

    def test_the_key_is_taken_when_the_fetch_starts(self, app, rows):
        """All of Division I asked for, FBS only chosen while it loads: that answer isn't FBS's."""
        settings.set("ncaaf_coverage", "all_d1")
        started = scores.StandingsLoader("NCAAF").cache_key
        settings.set("ncaaf_coverage", "fbs")
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "StandingsDialog"):
            scores.LeagueView._on_standings_data_loaded(view, started, rows)
        assert scores.DataCache().get_standings("NCAAF") is None
        settings.set("ncaaf_coverage", "all_d1")
        assert scores.DataCache().get_standings("NCAAF") == rows

    def test_the_view_hands_on_the_key_from_when_it_asked(self, app, rows):
        settings.set("ncaaf_coverage", "all_d1")
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "_start_detached_thread"):  # no loading from ESPN
            scores.LeagueView._show_standings_dialog(view)
        settings.set("ncaaf_coverage", "fbs")
        view.standings_loader.data_loaded.emit(rows)
        view._on_standings_data_loaded.assert_called_once_with("standings_NCAAF_group90", rows)

    def test_a_new_answer_opens_the_dialog_with_it(self, app, rows):
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "StandingsDialog") as dialog:
            scores.LeagueView._on_standings_data_loaded(view, "standings_NCAAF_group90", rows)
        dialog.assert_called_once_with(rows, "NCAAF", view)
        dialog.return_value.exec.assert_called_once()


def soccer_rows(name):
    path = os.path.join(os.path.dirname(FIXTURE), name)
    with open(path, encoding="utf-8") as f:
        return soccer.parse_soccer_standings(json.load(f))


ARSENAL = ["1", "Arsenal", "9", "8", "0", "1", "14", "5", "+9", "24", "Champions League"]


class TestSoccerStandings:
    def test_a_league_is_one_table_named_for_what_it_is(self, app):
        dialog = scores.StandingsDialog(soccer_rows("standings_EPL.json"), "EPL")
        assert dialog.tab_widget is None
        assert dialog.windowTitle() == "EPL Standings - 2026-27 English Premier League"
        assert dialog.single_table.table_widget.accessibleName() == "2026-27 English Premier League Standings"

    def test_all_three_views_show_a_whole_row(self, app):
        table = scores.StandingsDialog(soccer_rows("standings_EPL.json"), "EPL").single_table
        cells = [table.item(0, column).text() for column in range(table.columnCount())]
        assert cells == ARSENAL
        assert table.quick_list.item(0).text() == ", ".join(ARSENAL)
        assert table.full_list.item(0).text() == (
            "Pos: 1; Team: Arsenal; GP: 9; W: 8; D: 0; L: 1; GF: 14; GA: 5; GD: +9; Pts: 24; Status: Champions League")

    def test_the_team_says_whose_row_it_is(self, app):
        table = scores.StandingsDialog(soccer_rows("standings_EPL.json"), "EPL").single_table
        assert table.item(0, 9).data(Qt.ItemDataRole.AccessibleTextRole) == "Arsenal, Pts, 24"

    def test_a_cups_league_phase_is_named(self, app):
        dialog = scores.StandingsDialog(soccer_rows("standings_UCL.json"), "UCL")
        assert dialog.single_table.table_widget.accessibleName() == "League Phase Standings"
        assert dialog.windowTitle() == "UCL Standings - 2026-27 UEFA Champions League"

    def test_mls_is_two_tabs_with_the_season_in_the_title(self, app):
        dialog = scores.StandingsDialog(soccer_rows("standings_MLS.json"), "MLS")
        assert isinstance(dialog.tab_widget, QTabWidget)
        assert tab_names(dialog) == ["Eastern Conference", "Western Conference"]
        assert dialog.windowTitle() == "MLS Standings - 2026 MLS"
        ranks = [dialog.tab_widget.widget(0).table.item(row, 0).text() for row in range(3)]
        assert ranks == sorted(ranks, key=int), "by ESPN's rank, not the order of its answer"

    def test_eight_groups_stay_tabs(self, app):
        dialog = scores.StandingsDialog(soccer_rows("standings_UCL_2023.json"), "UCL")
        assert isinstance(dialog.tab_widget, QTabWidget)
        assert tab_names(dialog)[0] == "Group A"

    def test_more_groups_are_a_named_list(self, app):
        rows = soccer_rows("standings_UCL_2023.json")
        rows = [dict(row, division=f"Group {i}") for i, row in enumerate(rows)]
        dialog = scores.StandingsDialog(rows, "UCL")
        assert isinstance(dialog.tab_widget, ListPages)
        assert dialog.tab_widget.tabBar().accessibleName() == "Groups"

    def test_no_table_is_an_answer_and_not_an_error(self, app):
        answers, errors = [], []
        loader = scores.StandingsLoader("CONCACAF")
        loader.data_loaded.connect(answers.append)
        loader.error_occurred.connect(errors.append)
        with patch.object(scores.ApiService, "get_standings", return_value=[]):
            loader.run()
        assert answers == [[]]
        assert errors == []

    def test_no_table_is_a_row_that_takes_focus_and_no_alarm(self, app):
        dialog = scores.StandingsDialog([], "CONCACAF")
        dialog.show()
        app.processEvents()
        assert dialog.tab_widget is None and dialog.single_table is None
        assert dialog.message_row.item(0).text() == soccer.no_table_message("CONCACAF")
        assert dialog.message_row.accessibleName() == "CONCACAF Standings"
        assert dialog.message_row.currentRow() == 0
        dialog._focus_content()
        assert dialog.focusWidget() is dialog.message_row
        dialog.close()

    def test_another_league_with_no_standings_still_has_its_label(self, app):
        dialog = scores.StandingsDialog([], "NFL")
        assert dialog.message_row is None

    def test_a_failed_request_says_so_differently(self, app):
        errors = []
        loader = scores.StandingsLoader("EPL")
        loader.error_occurred.connect(errors.append)
        with patch.object(scores.ApiService, "get_standings", side_effect=espn_api.ApiError(espn_api.STANDINGS_UNAVAILABLE)):
            loader.run()
        assert errors == [f"Failed to load standings: {espn_api.STANDINGS_UNAVAILABLE}"]


class TestSoccerTeams:
    def test_a_team_row_has_draws_and_points_and_opens_the_team(self, app):
        dialog = scores.SimpleTeamsDialog(soccer_rows("standings_EPL.json"), "EPL")
        table = dialog.tab_widget.widget(0).teams_table
        assert [table.horizontalHeaderItem(column).text() for column in range(table.columnCount())] == soccer.SOCCER_TEAM_HEADERS
        assert [table.item(0, column).text() for column in range(6)] == ["Arsenal", "9", "8", "0", "1", "24"]
        for column in range(6):  # Enter opens the team from wherever on its row it's pressed
            assert table.item(0, column).data(Qt.ItemDataRole.UserRole)["team_id"] == "359"
        with patch.object(scores, "TeamScheduleDialog") as opened:
            dialog.on_team_selected(table.item(0, 5))
        opened.assert_called_once()
        assert opened.call_args.args[1] == "EPL"

    def test_all_three_views_show_a_whole_row_and_the_team_says_whose_it_is(self, app):
        table = scores.SimpleTeamsDialog(soccer_rows("standings_EPL.json"), "EPL").tab_widget.widget(0).teams_table
        assert table.quick_list.item(0).text() == "Arsenal, 9, 8, 0, 1, 24"
        assert table.full_list.item(0).text() == "Team: Arsenal; Played: 9; Wins: 8; Draws: 0; Losses: 1; Points: 24"
        assert table.item(0, 5).data(Qt.ItemDataRole.AccessibleTextRole) == "Arsenal, Points, 24"

    def test_the_title_says_which_season_the_records_are_from(self, app):
        assert scores.SimpleTeamsDialog(soccer_rows("standings_MLS.json"), "MLS").windowTitle() == "MLS Teams - 2026 MLS"
        rows = [{"team_name": "A", "team_id": "1", "division": soccer.TEAMS_WITH_NO_GROUP}]
        assert scores.SimpleTeamsDialog(rows, "CONCACAF").windowTitle() == "CONCACAF Teams"

    def test_opening_a_team_doesnt_close_the_list_behind_it(self, app):
        """A table passes Enter on after activating a row, and a default button would take it."""
        dialog = scores.SimpleTeamsDialog(soccer_rows("standings_EPL.json"), "EPL")
        assert not dialog.close_button.autoDefault()

    def test_a_cups_teams_are_names_and_say_so(self, app):
        rows = [{"team_name": "B", "team_id": "2", "division": soccer.TEAMS_WITH_NO_GROUP},
                {"team_name": "A", "team_id": "1", "division": soccer.TEAMS_WITH_NO_GROUP}]
        table = scores.SimpleTeamsDialog(rows, "CONCACAF").tab_widget.widget(0).teams_table
        assert table.columnCount() == 1
        assert table.item(0, 0).text() == "A"
        assert table.table_widget.accessibleName() == "CONCACAF Teams"
        assert "wins" not in table.accessible_description

    @pytest.mark.parametrize("team,shown", [({"record": "8-0-1", "wins": 8, "losses": 1}, ["(8-0-1)"]),
                                            ({"record": "5-3-0", "wins": 5, "losses": 0}, ["(5-3-0)"]),
                                            ({"record": "N/A"}, []),
                                            ({}, [])], ids=["record", "no_losses", "from_a_game_with_none", "none"])
    def test_a_team_page_reads_wins_draws_losses(self, app, team, shown):
        with patch.object(scores.TeamHubDialog, "_on_tab_changed"):
            dialog = scores.TeamHubDialog({"team_name": "Arsenal", "team_id": "359", **team}, "EPL")
        labels = [label.text() for label in dialog.findChildren(QLabel) if label.text().startswith("(")]
        assert labels == shown


class TestSoccerSections:
    def test_a_league_offers_standings_statistics_and_teams(self, app):
        view = MagicMock(league="EPL", scores_list=QListWidget())
        scores.LeagueView._add_common_sections(view)
        rows = [view.scores_list.item(i) for i in range(view.scores_list.count())]
        assert [row.text() for row in rows] == ["--- Standings ---", "--- Statistics ---", "--- Teams ---"]
        assert [row.data(Qt.ItemDataRole.UserRole) for row in rows] == ["__standings__", "__statistics__", "__teams__"]

    def test_a_league_with_no_team_statistics_offers_no_choice_of_them(self, app):
        view = MagicMock(league="EPL")
        with patch.object(scores, "StatisticsChoiceDialog") as choice, patch.object(scores, "StatisticsViewDialog") as stats:
            scores.LeagueView._show_statistics_dialog(view)
        choice.assert_not_called()
        stats.assert_called_once_with("EPL", "player", view)
        stats.return_value.exec.assert_called_once()
        view.parent_app.update_window_title.assert_called_with(view._title_items.return_value)

    def test_teams_asks_for_the_list_that_a_cup_also_has(self, app):
        view = MagicMock(league="CONCACAF")
        with patch.object(scores.ApiService, "get_soccer_teams", return_value=[]) as teams:
            scores.LeagueView._show_teams_dialog(view)
            view._fetch_then.call_args.args[1]()
        teams.assert_called_once_with("CONCACAF")
