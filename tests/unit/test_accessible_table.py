"""The accessible table's three views and its keys. Builds Qt widgets (offscreen),
so run this in the test VM or CI, not on a PC someone is using."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget, QVBoxLayout, QWidget

import accessible_table
from accessible_table import AccessibleTable, RankingsTable, StandingsTable, prepare_table_tabs

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


VIEW_KEYS = {"table": Qt.Key.Key_T, "quick": Qt.Key.Key_Q, "full": Qt.Key.Key_F}
SWITCHES = [("table", "quick"), ("quick", "full"), ("full", "table"), ("quick", "table")]


def view_widget(table, name):
    return {"table": table.table_widget, "quick": table.quick_list, "full": table.full_list}[name]


def go_to_row(table, name, row):
    """Move one view only, leaving the others on the row they were last left on."""
    view = view_widget(table, name)
    if name == "table":
        view.setCurrentCell(row, 0)
    else:
        view.setCurrentRow(row)


@pytest.mark.parametrize("source,target", SWITCHES)
def test_a_view_has_its_row_before_it_is_shown(app, source, target):
    """Showing a view moves focus to it, so a stale row there gets announced first."""
    table = make_table(app)
    table.handle_view_key(alt(VIEW_KEYS[source]))
    go_to_row(table, source, 2)
    assert view_widget(table, target).currentRow() == 0

    seen = []
    show = table.stacked_widget.setCurrentIndex
    focus = table._set_focus_to_current_view

    def spy_show(index):
        seen.append(("shown", view_widget(table, target).currentRow()))
        show(index)

    def spy_focus():
        seen.append(("focused", view_widget(table, target).currentRow()))
        focus()

    table.stacked_widget.setCurrentIndex = spy_show
    table._set_focus_to_current_view = spy_focus
    table.handle_view_key(alt(VIEW_KEYS[target]))
    assert seen == [("shown", 2), ("focused", 2)]


@pytest.mark.parametrize("source,target", SWITCHES)
def test_a_views_row_is_on_screen_after_a_switch(app, source, target):
    """The row is set while the view is hidden, so the scroll has to happen on show."""
    table = AccessibleTable(accessible_name="T", accessible_description="D")
    table.setup_columns(HEADERS)
    table.populate_data([[f"P{i}", "G", str(i)] for i in range(200)], set_focus=False)
    table.resize(400, 200)
    table.show()
    app.processEvents()
    try:
        table.handle_view_key(alt(VIEW_KEYS[source]))
        app.processEvents()
        go_to_row(table, source, 150)
        table.handle_view_key(alt(VIEW_KEYS[target]))
        app.processEvents()

        view = view_widget(table, target)
        assert view.currentRow() == 150
        assert view.viewport().rect().contains(view.visualItemRect(view.currentItem()))
    finally:
        table.close()


def test_holding_enter_activates_a_row_once(app):
    """It may be a row the same press has just brought up, opening a list's table."""
    table = make_table(app)
    activated = []
    table.table_widget.itemActivated.connect(activated.append)
    held = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r", True)
    QApplication.sendEvent(table.table_widget, held)
    assert activated == []


def test_adopting_the_saved_view_keeps_the_row_and_takes_no_focus(app, view_setting):
    table = make_table(app)
    table.table_widget.setCurrentCell(2, 0)
    focused = []
    table.quick_list.setFocus = lambda: focused.append("quick")
    view_setting["default_view_mode"] = table.VIEW_QUICK_LIST
    table.adopt_saved_view()
    assert table._current_view == table.VIEW_QUICK_LIST
    assert table.quick_list.currentRow() == 2
    assert focused == []


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


def cell_speech(table, row):
    return [table.table_widget.item(row, col).data(Qt.ItemDataRole.AccessibleTextRole)
            for col in range(table.columnCount())]


def three_views(table, row):
    """What each view holds for one row: the table's cells, the Quick List's line, the Full List's."""
    cells = [table.table_widget.item(row, col).text() for col in range(table.columnCount())]
    return cells, table.quick_list.item(row).text(), table.full_list.item(row).text()


@pytest.fixture
def nhl_rows(monkeypatch):
    """The NHL's real standings, through the app's own parser."""
    import espn_api
    from tests.unit.replay.support import FakeEspn, load
    fake = FakeEspn().on("/nhl/standings", load("standings_NHL.json"))
    monkeypatch.setattr(espn_api, "_http_get", fake)
    return espn_api.get_standings("NHL")


@pytest.mark.parametrize("expanded", [False, True], ids=["basic", "expanded"])
def test_nhl_standings_from_espn_line_up_in_every_view(app, nhl_rows, expanded):
    """Issue 90: from column 4 on, the expanded headers once said the wrong thing ("OTL: .550")."""
    bruins = [r for r in nhl_rows if r["team_name"] == "Boston Bruins"]
    table = StandingsTable(division_name="Atlantic", league="NHL", expanded=expanded)
    table.populate_standings(bruins, set_focus=False)
    cells, quick, full = three_views(table, 0)
    headers = table._headers
    assert len(cells) == len(headers)
    by_header = dict(zip(headers, cells))
    assert (by_header["Team"], by_header["W"], by_header["L"], by_header["OTL"], by_header["Pts"]) == (
        "Boston Bruins", "10", "4", "1", "21")
    assert by_header["PCT"] == "0.700" and by_header["Streak"] == "W1"
    if expanded:
        assert (by_header["GF"], by_header["GA"], by_header["Diff"], by_header["Seed"]) == ("55", "36", "+19", "2")
    assert quick == ", ".join(cells)
    assert full == "; ".join(f"{h}: {v}" for h, v in zip(headers, cells))
    assert "OTL: 1" in full and "Pts: 21" in full and "PCT: 0.700" in full
    assert cell_speech(table, 0)[headers.index("OTL")] == "Boston Bruins, OTL, 1"


def test_an_injury_cell_says_whose_injury_it_is_in_every_view(app):
    """Issue 90: the injury table's own accessibility method called one QTableWidgetItem lacks.
    It's gone; the shared row context says the player, as every table's cells do."""
    from tests.unit.replay.support import load
    from scores import INJURY_HEADERS
    injuries = load("summary_final_NFL_401873036.json")["injuries"]
    table = accessible_table.InjuryTable(title="Injury Report")
    table.setColumnCount(len(INJURY_HEADERS))
    table.setHorizontalHeaderLabels(INJURY_HEADERS)
    table.populate_injury_data(injuries, set_focus=False)
    assert not hasattr(table, "enhance_cell_accessibility")
    cells, quick, full = three_views(table, 0)
    assert cells[:4] == ["Rashid Shaheed", "WR", "Seattle Seahawks (SEA)", "Questionable"]
    assert quick.startswith("Rashid Shaheed, WR, Seattle Seahawks (SEA), Questionable, Knee")
    assert full.startswith("Player: Rashid Shaheed; Position: WR; Team: Seattle Seahawks (SEA); Status: Questionable")
    speech = cell_speech(table, 0)
    assert speech[0] == "Player, Rashid Shaheed"
    assert speech[3] == "Rashid Shaheed, Status, Questionable"
    assert speech[6] == "Rashid Shaheed, Return Date, 2026-11-08"


def test_a_cell_says_whose_row_it_is_from_the_first_column(app):
    assert cell_speech(make_table(app), 0) == ["Player, A", "A, Pos, G", "A, PTS, 10"]


def test_a_standings_cell_says_the_team_rather_than_its_position(app):
    table = StandingsTable(division_name="X", league="MLB")
    table.populate_data([["1", "Yankees", "90", "60", "0.600", "-", "W2"]], set_focus=False)
    speech = cell_speech(table, 0)
    assert speech[:3] == ["Yankees, Pos, 1", "Team, Yankees", "Yankees, W, 90"]


@pytest.mark.parametrize("league,division,conference,name", [
    ("NBA", "Central", "Eastern Conference", "Central, Eastern Conference, Standings"),
    ("NHL", "Central", "Western Conference", "Central, Western Conference, Standings"),
    ("NFL", "AFC East", "American Football Conference", "AFC East Standings"),
    ("MLB", "AL East", "American League", "AL East Standings"),
    ("NBA", "Eastern Conference", "Eastern Conference", "Eastern Conference Standings"),
    ("NBA", "Central", "", "Central Standings"),
])
def test_a_division_table_says_its_conference_where_the_name_does_not(app, league, division, conference, name):
    """The NBA's Central is in the East and the NHL's in the West; the tab says only "Central"."""
    table = StandingsTable(division_name=division, league=league, conference=conference)
    assert table.table_widget.accessibleName() == name
    assert table.division_name == division


def test_a_ranking_cell_says_the_name_rather_than_the_rank(app):
    table = RankingsTable(["Rank", "Team", "Value"])
    table.populate_data([[1, "Celtics", "120"]], set_focus=False)
    assert cell_speech(table, 0) == ["Celtics, Rank, 1", "Team, Celtics", "Celtics, Value, 120"]


class TestButtonKeys:
    """Enter presses the focused button, and a list's Enter presses no button."""

    @pytest.fixture
    def dialog(self, app):
        from PyQt6.QtWidgets import QDialog, QListWidget
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        dialog.items = QListWidget()
        dialog.items.addItem("row")
        dialog.items.setCurrentRow(0)
        dialog.button = QPushButton("Add to Favorites")
        dialog.clicks = []
        dialog.button.clicked.connect(lambda: dialog.clicks.append(1))
        layout.addWidget(dialog.button)
        layout.addWidget(dialog.items)
        keys = accessible_table.ButtonKeys(dialog)
        QApplication.instance().installEventFilter(keys)
        yield dialog
        QApplication.instance().removeEventFilter(keys)

    @staticmethod
    def enter(auto_repeat=False):
        return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier,
                         "", auto_repeat)

    def test_buttons_are_not_automatic_defaults(self, dialog):
        dialog.show()
        QApplication.processEvents()
        assert not dialog.button.autoDefault()
        dialog.close()

    def test_enter_on_a_list_row_presses_no_button(self, dialog):
        dialog.show()
        QApplication.processEvents()
        dialog.items.setFocus()
        QApplication.sendEvent(dialog.items, self.enter())
        assert dialog.clicks == []
        dialog.close()

    def test_enter_on_a_button_presses_it_once(self, dialog, monkeypatch):
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: dialog.button))
        QApplication.sendEvent(dialog.button, self.enter())
        assert dialog.clicks == [1]
        QApplication.sendEvent(dialog.button, self.enter(auto_repeat=True))
        assert dialog.clicks == [1]


class TestTabs:
    @pytest.fixture
    def tabs(self, app):
        tabs = QTabWidget()
        prepare_table_tabs(tabs)
        page = QWidget()
        layout = QVBoxLayout(page)
        tabs.table = make_table(app)
        layout.addWidget(tabs.table)
        tabs.addTab(page, "One")
        return tabs

    def test_bar_is_a_tab_stop_and_the_tab_widget_is_not_another(self, tabs):
        assert tabs.tabBar().focusPolicy() & Qt.FocusPolicy.TabFocus

    def test_f6_moves_between_the_tabs_and_the_table(self, tabs, app):
        tabs.show()
        QApplication.processEvents()
        tabs.activateWindow()
        tabs.tabBar().setFocus()
        f6 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F6, Qt.KeyboardModifier.NoModifier)
        calls = []
        tabs.table.setFocus = lambda: calls.append("table")
        bar = tabs.tabBar()
        bar.hasFocus = lambda: True
        QApplication.sendEvent(bar, f6)
        assert calls == ["table"]
        bar.hasFocus = lambda: False
        bar.setFocus = lambda: calls.append("bar")
        QApplication.sendEvent(tabs, f6)
        assert calls == ["table", "bar"]
        tabs.close()
