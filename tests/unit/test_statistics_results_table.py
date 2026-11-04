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
from PyQt6.QtWidgets import QApplication  # noqa: E402

import accessible_table  # noqa: E402
import espn_api  # noqa: E402
import scores  # noqa: E402
from accessible_table import AccessibleTable  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
TABLE, QUICK, FULL = AccessibleTable.VIEW_TABLE, AccessibleTable.VIEW_QUICK_LIST, AccessibleTable.VIEW_FULL_LIST

NBA_LEADERS = espn_api._parse_leaders(json.loads((FIXTURES / "leaders_v3_NBA.json").read_text(encoding="utf-8")))
# What espn_api gives the dialog from the MLB Stats API: no season, and a team's full name.
MLB_LEADERS = {"player_stats": [
    {"name": "Home Runs", "display_name": "Home Runs", "abbreviation": "homeRuns", "leaders": [
        {"name": "Aaron Judge", "value": "53", "team": "New York Yankees", "position": None},
        {"name": "No Team", "value": "40", "team": "N/A", "position": None},
    ]},
    {"name": "Nobody Yet", "display_name": "Nobody Yet", "abbreviation": "none", "leaders": []},
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
    item = next(view.stats_list.item(row) for row in range(view.stats_list.count())
                if view.stats_list.item(row).text() == name)
    view._on_working_stat_selected(item)
    QApplication.instance().processEvents()


def press(key, modifiers=Qt.KeyboardModifier.NoModifier, widget=None):
    target = widget or QApplication.focusWidget()
    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    QApplication.instance().processEvents()


def row_cells(table, row):
    return [table.table_widget.item(row, col).text() for col in range(table.columnCount())]


def header_labels(table):
    return [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]


def test_results_stay_hidden_until_a_stat_is_chosen(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    assert not view.results_table.isVisible()
    view.stats_list.setFocus()
    press(Qt.Key.Key_F6, widget=view.stats_list)
    assert view.focusWidget() is view.stats_list  # nothing to move to yet


def test_player_rows_in_all_three_views(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = view.results_table
    assert header_labels(table) == ["Rank", "Player", "Team", "Value"]
    assert row_cells(table, 0) == ["1", "Luka Doncic", "LAL", "38.3"]
    assert table.quick_list.item(0).text() == "1, Luka Doncic, LAL, 38.3"
    assert table.full_list.item(0).text() == "Rank: 1; Player: Luka Doncic; Team: LAL; Value: 38.3"


def test_team_rows_keep_the_shared_rank_and_read_best_first(open_dialog):
    view = open_dialog("NBA", "team", TEAM_STATS)
    select_stat(view, "Turnovers (Offense)")
    table = view.results_table
    assert header_labels(table) == ["Rank", "Team", "Value"]
    assert [row_cells(table, row) for row in range(3)] == [
        ["1", "Celtics", "9"], ["2", "Heat", "11"], ["3", "Bulls", "15"]]

    select_stat(view, "Points (Offense)")
    assert [row_cells(table, row) for row in range(3)] == [
        ["1", "Bulls", "120"], ["1", "Celtics", "120"], ["3", "Heat", "99"]]
    assert table.full_list.item(2).text() == "Rank: 3; Team: Heat; Value: 99"


def test_mlb_has_no_season_and_full_team_names(open_dialog):
    view = open_dialog("MLB", "player", MLB_LEADERS)
    select_stat(view, "Home Runs")
    table = view.results_table
    assert view.results_label.text() == "Season Leaders: Home Runs"
    assert row_cells(table, 0) == ["1", "Aaron Judge", "New York Yankees", "53"]
    assert row_cells(table, 1) == ["2", "No Team", "N/A", "40"]


def test_a_row_says_whose_it_is(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    spoken = [view.results_table.table_widget.item(0, col).data(Qt.ItemDataRole.AccessibleTextRole)
              for col in range(4)]
    assert spoken == ["Luka Doncic, Rank, 1", "Player, Luka Doncic",
                      "Luka Doncic, Team, LAL", "Luka Doncic, Value, 38.3"]


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_choosing_a_stat_focuses_the_first_row_of_the_saved_view(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = view.results_table
    shown = [table.table_widget, table.quick_list, table.full_list][mode]
    assert table.stacked_widget.currentWidget() is shown
    assert view.focusWidget() is shown
    assert table.currentRow() == 0


def test_the_heading_names_the_table_in_every_view(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    heading = view.results_label.text()
    assert heading.endswith("Leaders: Points Per Game") and NBA_LEADERS["season"] in heading
    table = view.results_table
    assert table.accessibleName() == heading
    assert table.table_widget.accessibleName() == heading
    assert table.quick_list.accessibleName() == f"{heading} - Quick List"
    assert table.full_list.accessibleName() == f"{heading} - Full List"


def test_the_view_keys_work_and_are_saved(open_dialog, saved_view):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = view.results_table
    press(Qt.Key.Key_V, Qt.KeyboardModifier.AltModifier, table.table_widget)
    assert view.focusWidget() is table.quick_list and saved_view["default_view_mode"] == QUICK
    press(Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier, table.quick_list)
    assert view.focusWidget() is table.full_list and saved_view["default_view_mode"] == FULL
    press(Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier, table.full_list)
    assert view.focusWidget() is table.quick_list
    press(Qt.Key.Key_T, Qt.KeyboardModifier.AltModifier, table.quick_list)
    assert view.focusWidget() is table.table_widget and saved_view["default_view_mode"] == TABLE


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_f6_and_tab_move_between_the_stat_list_and_the_results(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    table = view.results_table
    shown = table.stacked_widget.currentWidget()
    press(Qt.Key.Key_F6, widget=shown)
    assert view.focusWidget() is view.stats_list
    press(Qt.Key.Key_F6, widget=view.stats_list)
    assert view.focusWidget() is shown
    press(Qt.Key.Key_F6, widget=shown)
    assert view.focusWidget() is view.stats_list
    press(Qt.Key.Key_Tab, widget=view.stats_list)
    assert view.focusWidget() is shown  # not the wrapper, and not an empty stop


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_enter_stays_and_escape_closes(open_dialog, saved_view, mode):
    saved_view["default_view_mode"] = mode
    view = open_dialog("NBA", "player", NBA_LEADERS)
    select_stat(view, "Points Per Game")
    shown = view.results_table.stacked_widget.currentWidget()
    press(Qt.Key.Key_Return, widget=shown)
    assert view.isVisible() and view.focusWidget() is shown
    press(Qt.Key.Key_Escape, widget=shown)
    assert not view.isVisible()


def test_another_stat_replaces_the_rows_and_starts_at_the_top(open_dialog):
    view = open_dialog("NBA", "player", NBA_LEADERS)
    names = [view.stats_list.item(row).text() for row in range(view.stats_list.count())]
    select_stat(view, names[0])
    table = view.results_table
    table.table_widget.setCurrentCell(1, 2)
    first = row_cells(table, 0)
    select_stat(view, names[1])
    assert row_cells(table, 0) != first
    assert table.currentRow() == 0 and table.currentColumn() == 0
    assert table.quick_list.count() == table.full_list.count() == table.rowCount()


def test_a_stat_with_no_rows_leaves_focus_on_the_stat_list(open_dialog):
    view = open_dialog("MLB", "player", MLB_LEADERS)
    select_stat(view, "Home Runs")
    view.stats_list.setFocus()
    select_stat(view, "Nobody Yet")
    table = view.results_table
    assert table.rowCount() == table.quick_list.count() == table.full_list.count() == 0
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
    table = view.results_table

    started = time.perf_counter()
    select_stat(view, "Points (Offense)")
    view.grab()
    elapsed = time.perf_counter() - started

    assert table.rowCount() == table.quick_list.count() == table.full_list.count() == 302
    assert row_cells(table, 301) == ["302", "School 0", "0"]
    assert table.quick_list.item(301).text() == "302, School 0, 0"
    assert elapsed < 3, f"302 rows took {elapsed:.2f}s"
