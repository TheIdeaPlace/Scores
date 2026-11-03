"""The accessible table's three views and its keys. Builds Qt widgets (offscreen),
so run this in the test VM or CI, not on a PC someone is using."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget, QVBoxLayout, QWidget

import accessible_table
from accessible_table import AccessibleTable, StandingsTable, prepare_table_tabs

HEADERS = ["Player", "Pos", "PTS"]
ROWS = [["A", "G", "10"], ["B", "F", "4"], ["C", "C"]]


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def view_setting(monkeypatch):
    saved = {"default_view_mode": 0}
    monkeypatch.setattr(accessible_table.settings, "get", lambda k, d=None: saved.get(k, d))
    monkeypatch.setattr(accessible_table.settings, "set", saved.__setitem__)
    return saved


def make_table(app):
    table = AccessibleTable(accessible_name="T", accessible_description="D")
    table.setup_columns(HEADERS)
    table.populate_data(ROWS, set_focus=False)
    return table


def alt(key):
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.AltModifier)


def test_wrapper_is_not_a_tab_stop(app):
    assert make_table(app).focusPolicy() == Qt.FocusPolicy.NoFocus


def test_views_have_a_current_row_before_focus(app):
    table = make_table(app)
    assert table.quick_list.currentRow() == 0
    assert table.full_list.currentRow() == 0
    assert table.table_widget.currentRow() == 0


def test_list_text_and_short_rows(app):
    table = make_table(app)
    assert table.quick_list.item(0).text() == "A, G, 10"
    assert table.full_list.item(0).text() == "Player: A; Pos: G; PTS: 10"
    assert table.full_list.item(2).text() == "Player: C; Pos: C"


def test_view_keys_cycle_and_go_direct(app):
    table = make_table(app)
    assert table.handle_view_key(alt(Qt.Key.Key_V))
    assert table._current_view == table.VIEW_QUICK_LIST
    assert table.handle_view_key(alt(Qt.Key.Key_F))
    assert table._current_view == table.VIEW_FULL_LIST
    assert table.handle_view_key(alt(Qt.Key.Key_T))
    assert table._current_view == table.VIEW_TABLE
    assert not table.handle_view_key(alt(Qt.Key.Key_X))


def test_description_does_not_grow_on_switching(app):
    table = make_table(app)
    before = table.quick_list.accessibleDescription()
    for _ in range(4):
        table.handle_view_key(alt(Qt.Key.Key_V))
    assert table.quick_list.accessibleDescription() == before


def test_row_and_column_survive_a_round_trip(app):
    table = make_table(app)
    table.table_widget.setCurrentCell(1, 2)
    table.handle_view_key(alt(Qt.Key.Key_Q))
    assert table.quick_list.currentRow() == 1
    table.handle_view_key(alt(Qt.Key.Key_T))
    assert (table.table_widget.currentRow(), table.table_widget.currentColumn()) == (1, 2)


def test_saved_view_used_by_a_new_table(app, view_setting):
    view_setting["default_view_mode"] = 2
    table = make_table(app)
    assert table.stacked_widget.currentWidget() is table.full_list
    assert table.full_list.count() == 3


def test_setitem_table_in_a_saved_list_view_has_data_when_shown(app, view_setting):
    from PyQt6.QtWidgets import QTableWidgetItem
    view_setting["default_view_mode"] = 1
    table = AccessibleTable(accessible_name="T", accessible_description="D")
    table.setup_columns(HEADERS)
    table.setRowCount(1)
    for col, value in enumerate(ROWS[0]):
        table.setItem(0, col, QTableWidgetItem(value))
    assert table.quick_list.count() == 0
    table.show()
    assert table.quick_list.count() == 1
    assert table.quick_list.item(0).text() == "A, G, 10"
    table.close()


def test_enter_in_a_list_view_activates_the_row(app):
    table = make_table(app)
    seen = []
    table.itemActivated.connect(lambda item: seen.append(item.row()))
    table.handle_view_key(alt(Qt.Key.Key_Q))
    table.quick_list.itemActivated.emit(table.quick_list.item(1))
    assert seen == [1]


def test_tab_bar_scroll_buttons_are_not_tab_stops_and_view_keys_work_there(app):
    from PyQt6.QtWidgets import QToolButton
    tabs = QTabWidget()
    prepare_table_tabs(tabs)
    page = QWidget()
    layout = QVBoxLayout(page)
    table = make_table(app)
    layout.addWidget(table)
    tabs.addTab(page, "One")
    assert all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in tabs.tabBar().findChildren(QToolButton))
    QApplication.sendEvent(tabs.tabBar(), alt(Qt.Key.Key_Q))
    assert table._current_view == table.VIEW_QUICK_LIST


@pytest.mark.parametrize("league,expanded,headers", [
    ("NHL", True, ["Pos", "Team", "W", "L", "OTL", "Pts", "PCT", "Streak", "GF", "GA", "Diff", "Seed"]),
    ("NHL", False, ["Pos", "Team", "W", "L", "OTL", "Pts", "PCT", "Streak"]),
    ("NCAAF", False, ["Pos", "Team", "W", "L", "PCT", "Conf", "Streak"]),
    ("NCAAH", False, ["Pos", "Team", "W", "L", "T", "PCT", "Conf", "Streak"]),
])
def test_standings_rows_line_up_with_headers(app, league, expanded, headers):
    table = StandingsTable(division_name="X", league=league, expanded=expanded)
    assert table._headers == headers
    team = {"team_name": "Montreal", "wins": 9, "losses": 4, "ties": 1, "ot_losses": 2, "points": 20,
            "win_percentage": "0.714", "streak": "W2", "conference_record": "3-1",
            "goals_for": 40, "goals_against": 30, "goal_differential": 10, "playoff_seed": 1}
    row = table._build_expanded_row(1, team) if expanded else table._build_basic_row(1, team)
    assert len(row) == len(headers)
    cells = dict(zip(headers, row))
    assert cells["Team"] == "Montreal"
    assert cells["W"] == "9"
    if league == "NHL":
        assert cells["OTL"] == "2" and cells["Pts"] == "20" and cells["PCT"] == "0.714"
    else:
        assert cells["Conf"] == "3-1"
