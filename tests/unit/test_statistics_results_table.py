"""The statistics dialog's results are an accessible table, in all three views, for players and
teams. Builds Qt objects: CI or the VM only."""
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QPushButton  # noqa: E402

import accessible_table  # noqa: E402
import espn_api  # noqa: E402
import scores  # noqa: E402
from accessible_table import AccessibleTable, RankingsTable  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
TABLE, QUICK, FULL = AccessibleTable.VIEW_TABLE, AccessibleTable.VIEW_QUICK_LIST, AccessibleTable.VIEW_FULL_LIST

NBA_LEADERS = espn_api._parse_leaders(json.loads((FIXTURES / "leaders_v3_NBA.json").read_text(encoding="utf-8")))
# No season named, and a team's full name, such as a row with no abbreviation has.
NO_SEASON_LEADERS = {"player_stats": [
    {"category": "Home Runs", "stats": [
        {"player_name": "Aaron Judge", "value": "53", "team": "New York Yankees", "stat_name": "Home Runs"},
        {"player_name": "No Team", "value": "40", "team": "", "stat_name": "Home Runs"},
        {"player_name": "Nobody Else", "value": "39", "team": "New York Yankees", "stat_name": "Home Runs"},
    ]},
    {"category": "Saves", "stats": [
        {"player_name": "Nobody Yet", "value": "1", "team": "", "stat_name": "Saves"},
    ]},
], "team_stats": []}
TEAM_STATS = {"season": "2026-27 Regular Season", "player_stats": [], "team_stats": [{
    "category": "Offense", "low_is_good": ["Turnovers"],
    "stats": [{"team_name": name, "stats": {"Points": points, "Turnovers": turnovers},
               "values": {"Points": float(points), "Turnovers": float(turnovers)}}
              for name, points, turnovers in (("Celtics", "120", "9"), ("Bulls", "120", "15"), ("Heat", "99", "11"))],
}]}


@pytest.fixture(autouse=True)
def saved_view(monkeypatch):
    saved = {"default_view_mode": TABLE}
    monkeypatch.setattr(accessible_table.settings, "get", lambda k, d=None: saved.get(k, d))
    monkeypatch.setattr(accessible_table.settings, "set", saved.__setitem__)
    return saved


@pytest.fixture
def open_dialog():
    app = QApplication.instance() or QApplication([])
    made = []

    def build(league, stat_type, data):
        with patch.object(scores, "_start_detached_thread"):  # no loading from ESPN
            view = scores.StatisticsViewDialog(league, stat_type)
        made.append(view)
        view.show()
        app.processEvents()
        view._on_statistics_loaded(data)
        app.processEvents()
        return view

    yield build
    for view in made:
        view.close()
        view.deleteLater()
    app.processEvents()


def select_stat(view, name):
    """Go back to the list if need be, go to the stat's row and press Enter on it."""
    pages = view.stat_pages
    pages.close_page()
    pages.setCurrentIndex(next(row for row in range(view.stats_list.count())
                               if view.stats_list.item(row).text() == name))
    QApplication.instance().processEvents()
    press(Qt.Key.Key_Return, widget=view.stats_list)


def results(view):
    """The table on the stat that's open, if it has one."""
    return view.stat_pages.currentWidget().findChild(RankingsTable)


def heading(view):
    return view.stat_pages.currentWidget().findChild(QLabel).text()


def press(key, modifiers=Qt.KeyboardModifier.NoModifier, widget=None):
    target = widget or QApplication.focusWidget()
    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    QApplication.instance().processEvents()


def row_cells(table, row):
    return [table.table_widget.item(row, col).text() for col in range(table.columnCount())]


def header_labels(table):
    return [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]


def test_the_stat_list_stands_alone_until_one_is_opened(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    assert view.stats_list.isVisible()
    assert view.focusWidget() is view.stats_list
    assert not view.stat_pages.is_open()
    assert results(view) is None  # built only when it's wanted


def test_enter_puts_the_results_in_the_lists_place_and_the_title_says_which(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    title = view.windowTitle()
    select_stat(view, "Points Per Game")
    assert view.stat_pages.is_open()
    assert not view.stats_list.isVisible()
    assert results(view).isVisible()
    assert view.windowTitle() == f"Points Per Game - {title}"


def test_arrowing_the_list_builds_nothing(open_dialog):
    """A college league has 300 rows on each of dozens of statistics."""
    view = open_dialog("NBA", "player", NBA_LEADERS)
    opening = []
    view.stat_pages.pageOpening.connect(opening.append)
    press(Qt.Key.Key_Down, widget=view.stats_list)
    assert view.stat_pages.currentIndex() == 1
    assert opening == []
    assert results(view) is None


def test_a_stat_that_cant_be_built_says_so_and_escape_comes_back(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    name = view.stats_list.item(0).text()
    with patch.object(scores, "ranking_rows", side_effect=ValueError("bad row")), \
            patch.object(scores.error_log, "log_handled") as logged:
        select_stat(view, name)
    logged.assert_called_once()
    row = view.focusWidget()
    assert isinstance(row, QListWidget) and row.item(0).text() == f"Unable to show {name}."
    press(Qt.Key.Key_Escape, widget=row)
    assert view.focusWidget() is view.stats_list


@pytest.mark.parametrize("start_on_back", [False, True], ids=["from the table", "from Back"])
def test_ctrl_tab_onto_a_stat_with_no_rows_lands_on_its_message(open_dialog, start_on_back):
    view = open_dialog("MLB", "player", NO_SEASON_LEADERS)
    view._stat_infos[1]["data"] = []
    select_stat(view, "Home Runs")
    start = results(view).table_widget
    if start_on_back:
        press(Qt.Key.Key_Tab, widget=start)
        start = view.focusWidget()
        assert isinstance(start, QPushButton)
    press(Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier, start)
    row = view.focusWidget()
    assert isinstance(row, QListWidget) and row is not view.stats_list
    assert row.item(0).text() == "No rankings are available for Saves."


def test_ctrl_tab_keeps_the_chosen_view(open_dialog, saved_view):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    names = [view.stats_list.item(row).text() for row in range(view.stats_list.count())]
    select_stat(view, names[0])
    press(Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier, results(view).table_widget)
    press(Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier, results(view).quick_list)
    assert view.windowTitle().startswith(f"{names[1]} - ")
    assert view.focusWidget() is results(view).quick_list


def test_escape_from_close_comes_back_to_the_list_and_then_closes(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    close = next(b for b in view.findChildren(QPushButton) if b.text() == "Close")
    close.setFocus()
    press(Qt.Key.Key_Escape, widget=close)
    assert view.isVisible()
    assert view.focusWidget() is view.stats_list
    close.setFocus()
    press(Qt.Key.Key_Escape, widget=close)
    assert not view.isVisible()


@pytest.mark.parametrize("where", ["list", "table", "back"])
def test_alt_d_opens_the_definitions_from_anywhere(open_dialog, where):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    target = view.stats_list
    if where != "list":
        select_stat(view, "Points Per Game")
        target = results(view).table_widget
    if where == "back":
        press(Qt.Key.Key_Tab, widget=target)
        target = view.focusWidget()
    with patch.object(view, "_show_stat_definitions") as shown:
        press(Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier, target)
    shown.assert_called_once()


def test_ctrl_tab_goes_on_to_the_next_stats_results(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    names = [view.stats_list.item(row).text() for row in range(view.stats_list.count())]
    select_stat(view, names[0])
    first = results(view)
    press(Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier, first.table_widget)
    assert view.stat_pages.currentIndex() == 1
    assert results(view) is not first
    assert view.focusWidget() is results(view).table_widget
    assert view.windowTitle().startswith(f"{names[1]} - ")


def test_player_rows_in_all_three_views(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = results(view)
    assert header_labels(table) == ["Rank", "Player", "Team", "Value"]
    assert row_cells(table, 0) == ["1", "Luka Doncic", "LAL", "38.3"]
    assert table.quick_list.item(0).text() == "1, Luka Doncic, LAL, 38.3"
    assert table.full_list.item(0).text() == "Rank: 1; Player: Luka Doncic; Team: LAL; Value: 38.3"


def test_team_rows_keep_the_shared_rank_and_read_best_first(open_dialog):
    view = open_dialog("NBA", "team", TEAM_STATS)
    select_stat(view, "Turnovers (Offense)")
    table = results(view)
    assert header_labels(table) == ["Rank", "Team", "Value"]
    assert [row_cells(table, row) for row in range(3)] == [
        ["1", "Celtics", "9"], ["2", "Heat", "11"], ["3", "Bulls", "15"]]

    select_stat(view, "Points (Offense)")
    table = results(view)
    assert [row_cells(table, row) for row in range(3)] == [
        ["1", "Bulls", "120"], ["1", "Celtics", "120"], ["3", "Heat", "99"]]
    assert table.full_list.item(2).text() == "Rank: 3; Team: Heat; Value: 99"


def test_mlb_has_no_season_and_full_team_names(open_dialog):
    view = open_dialog("MLB", "player", NO_SEASON_LEADERS)
    select_stat(view, "Home Runs")
    table = results(view)
    assert heading(view) == "Season Leaders: Home Runs"
    assert row_cells(table, 0) == ["1", "Aaron Judge", "New York Yankees", "53"]
    assert row_cells(table, 1) == ["2", "No Team", "N/A", "40"]


def test_players_level_on_the_number_share_a_rank(open_dialog):
    stats = [{"player_name": name, "value": value, "team": "NYY", "stat_name": "Home Runs"}
             for name, value in (("A", "45"), ("B", "45"), ("C", "44"))]
    view = open_dialog("MLB", "player", {"player_stats": [{"category": "Home Runs", "stats": stats}]})
    select_stat(view, "Home Runs")
    ranks = [row_cells(results(view), row)[0] for row in range(results(view).rowCount())]
    assert ranks == ["1", "1", "3"]


def test_a_row_says_whose_it_is(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    spoken = [results(view).table_widget.item(0, col).data(Qt.ItemDataRole.AccessibleTextRole)
              for col in range(4)]
    assert spoken == ["Luka Doncic, Rank, 1", "Player, Luka Doncic",
                      "Luka Doncic, Team, LAL", "Luka Doncic, Value, 38.3"]


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_choosing_a_stat_focuses_the_first_row_of_the_saved_view(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = results(view)
    shown = [table.table_widget, table.quick_list, table.full_list][mode]
    assert table.stacked_widget.currentWidget() is shown
    assert shown.isVisible()
    assert view.focusWidget() is shown
    assert table.currentRow() == 0


def test_the_heading_names_the_table_in_every_view(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    text = heading(view)
    assert text.endswith("Leaders: Points Per Game") and NBA_LEADERS["season"] in text
    table = results(view)
    assert table.accessibleName() == text
    assert table.table_widget.accessibleName() == text
    assert table.quick_list.accessibleName() == f"{text} - Quick List"
    assert table.full_list.accessibleName() == f"{text} - Full List"


def test_the_view_keys_work_and_are_saved(open_dialog, saved_view):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = results(view)
    press(Qt.Key.Key_V, Qt.KeyboardModifier.AltModifier, table.table_widget)
    assert view.focusWidget() is table.quick_list and saved_view["default_view_mode"] == QUICK
    press(Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier, table.quick_list)
    assert view.focusWidget() is table.full_list and saved_view["default_view_mode"] == FULL
    press(Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier, table.full_list)
    assert view.focusWidget() is table.quick_list
    press(Qt.Key.Key_T, Qt.KeyboardModifier.AltModifier, table.quick_list)
    assert view.focusWidget() is table.table_widget and saved_view["default_view_mode"] == TABLE


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_f6_goes_back_and_forth_and_tab_goes_to_the_back_button(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    shown = results(view).stacked_widget.currentWidget()
    press(Qt.Key.Key_F6, widget=shown)
    assert view.focusWidget() is view.stats_list
    assert not view.stat_pages.is_open()
    press(Qt.Key.Key_F6, widget=view.stats_list)
    assert view.focusWidget() is shown
    press(Qt.Key.Key_Tab, widget=shown)
    back = view.focusWidget()
    assert isinstance(back, QPushButton) and back.text() == "&Back to Player Statistics"


def test_f6_from_close_goes_to_what_is_on_show(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    close = next(b for b in view.findChildren(QPushButton) if b.text() == "Close")
    close.setFocus()
    press(Qt.Key.Key_F6, widget=close)
    assert view.focusWidget() is view.stats_list
    select_stat(view, "Points Per Game")
    close.setFocus()
    press(Qt.Key.Key_F6, widget=close)
    assert view.focusWidget() is results(view).stacked_widget.currentWidget()


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_escape_comes_back_to_the_same_stat_and_then_closes(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    names = [view.stats_list.item(row).text() for row in range(view.stats_list.count())]
    title = view.windowTitle()
    select_stat(view, names[2])
    shown = results(view).stacked_widget.currentWidget()
    press(Qt.Key.Key_Return, widget=shown)
    assert view.isVisible() and view.focusWidget() is shown
    press(Qt.Key.Key_Escape, widget=shown)
    assert view.isVisible()
    assert view.focusWidget() is view.stats_list
    assert view.stats_list.currentRow() == 2
    assert view.windowTitle() == title
    press(Qt.Key.Key_Escape, widget=view.stats_list)
    assert not view.isVisible()


def test_each_stat_keeps_its_own_rows_and_place(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    names = [view.stats_list.item(row).text() for row in range(view.stats_list.count())]
    select_stat(view, names[0])
    table = results(view)
    table.table_widget.setCurrentCell(1, 2)
    first = row_cells(table, 0)
    select_stat(view, names[1])
    other = results(view)
    assert row_cells(other, 0) != first
    assert other.currentRow() == 0 and other.currentColumn() == 0
    assert other.quick_list.count() == other.full_list.count() == other.rowCount()
    select_stat(view, names[0])
    assert results(view) is table
    assert table.currentRow() == 1 and table.currentColumn() == 2


def test_a_stat_with_no_rows_says_so_and_escape_comes_back(open_dialog):
    view = open_dialog("MLB", "player", NO_SEASON_LEADERS)
    view._stat_infos[1]["data"] = []
    select_stat(view, "Saves")
    assert results(view) is None
    row = view.focusWidget()
    assert isinstance(row, QListWidget) and row is not view.stats_list
    assert row.item(0).text() == "No rankings are available for Saves."
    press(Qt.Key.Key_Escape, widget=row)
    assert view.focusWidget() is view.stats_list


def test_the_failure_row_has_no_results_to_move_to(open_dialog):
    with patch.object(scores, "_start_detached_thread"):
        view = scores.StatisticsViewDialog("NBA", "player")
    view.show()
    view._on_statistics_error("ESPN isn't providing these right now.")
    QApplication.instance().processEvents()
    press(Qt.Key.Key_F6, widget=view.stats_list)
    assert view.focusWidget() is view.stats_list
    assert "Unable to load" in view.stats_list.item(0).text()
    view.close()
    view.deleteLater()


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_a_whole_college_league_fills_and_draws_quickly(open_dialog, saved_view, mode):
    """NCAAM ranks 302 teams or more. A list took no time at all; this builds a table and two
    lists. The limit is far above what it should take: it's here to catch something going badly
    wrong, not to measure."""
    saved_view["default_view_mode"] = mode
    teams = [{"team_name": f"School {n}", "stats": {"Points": str(n)}, "values": {"Points": float(n)}}
             for n in range(302)]
    view = open_dialog("NCAAM", "team", {"player_stats": [], "team_stats": [
        {"category": "Offense", "low_is_good": [], "stats": teams}]})

    started = time.perf_counter()
    select_stat(view, "Points (Offense)")
    view.grab()
    elapsed = time.perf_counter() - started

    table = results(view)
    assert table.rowCount() == table.quick_list.count() == table.full_list.count() == 302
    assert row_cells(table, 301) == ["302", "School 0", "0"]
    assert table.quick_list.item(301).text() == "302, School 0, 0"
    assert elapsed < 3, f"302 rows took {elapsed:.2f}s"
