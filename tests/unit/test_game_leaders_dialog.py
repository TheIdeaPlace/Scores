"""A game's Leaders dialog, built from real summaries. _show_detail_dialog catches whatever goes
wrong while it builds the table and shows a message instead, so an error raises nothing here:
these tests look for the table itself. Builds Qt objects: CI or the VM only."""
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QTabWidget, QWidget  # noqa: E402

import accessible_table  # noqa: E402
import scores  # noqa: E402
from accessible_table import AccessibleTable, LeadersTable  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
TABLE, QUICK, FULL = AccessibleTable.VIEW_TABLE, AccessibleTable.VIEW_QUICK_LIST, AccessibleTable.VIEW_FULL_LIST


def leaders_of(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["leaders"]


NBA = leaders_of("summary_leaders_NBA_401909906.json")
NFL = leaders_of("summary_leaders_NFL_401873035.json")


class Host(QWidget):
    """What the two methods touch. GameDetailsView's constructor starts loading a game, so they're
    borrowed from the real class, as tests/integration/test_play_audio_wiring.py does."""

    _show_detail_dialog = scores.GameDetailsView._show_detail_dialog
    _add_leaders_data_to_layout = scores.GameDetailsView._add_leaders_data_to_layout
    league = "NBA"
    game_id = "401909906"
    play_audio_mapper = None


@pytest.fixture(autouse=True)
def saved_view(monkeypatch):
    saved = {"default_view_mode": TABLE}
    monkeypatch.setattr(accessible_table.settings, "get", lambda k, d=None: saved.get(k, d))
    monkeypatch.setattr(accessible_table.settings, "set", saved.__setitem__)
    return saved


@pytest.fixture
def open_leaders(monkeypatch):
    app = QApplication.instance() or QApplication([])
    hosts, opened = [], []

    def run_without_blocking(dialog):
        opened.append(dialog)
        dialog.show()
        # Long enough for _focus_once_active's timer to have fired.
        QTest.qWait(scores.DIALOG_FOCUS_DELAY_MS + 200)
        return 0

    monkeypatch.setattr(scores.QDialog, "exec", run_without_blocking)

    def build(leaders):
        host = Host()
        hosts.append(host)
        host._show_detail_dialog("leaders", leaders)
        return opened[-1]

    yield build
    for dialog in opened:
        dialog.close()
    for host in hosts:
        host.deleteLater()
    app.processEvents()


def tables_of(dialog):
    tabs = dialog.findChildren(QTabWidget)
    words = [label.text() for label in dialog.findChildren(QLabel)]
    assert tabs, f"no tabs of leaders; the dialog says {words}"
    return tabs[0], [tabs[0].widget(i).findChildren(LeadersTable)[0] for i in range(tabs[0].count())]


def row_cells(table, row):
    return [table.table_widget.item(row, col).text() for col in range(table.columnCount())]


@pytest.mark.parametrize("leaders,first_team,first_row", [
    (NBA, "Los Angeles Lakers", ["Points", "Luka Doncic", "45"]),
    (NFL, "Washington Commanders", ["Passing Yards", "Jayden Daniels", "16/29, 217 YDS, 1 TD"]),
])
def test_each_team_has_a_tab_with_a_table_of_its_leaders(open_leaders, leaders, first_team, first_row):
    tabs, tables = tables_of(open_leaders(leaders))
    assert [tabs.tabText(i) for i in range(tabs.count())] == [team["team"]["displayName"] for team in leaders]
    assert tabs.tabText(0) == first_team
    assert row_cells(tables[0], 0) == first_row
    for team, table in zip(leaders, tables):
        assert table.rowCount() == len(team["leaders"])
        assert table.quick_list.count() == table.full_list.count() == table.rowCount()
        assert [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())] == [
            "Category", "Player", "Value"]


def test_all_three_views_read_the_row(open_leaders):
    _, tables = tables_of(open_leaders(NBA))
    table = tables[0]
    assert table.quick_list.item(0).text() == "Points, Luka Doncic, 45"
    assert table.full_list.item(0).text() == "Category: Points; Player: Luka Doncic; Value: 45"
    spoken = [table.table_widget.item(0, col).data(Qt.ItemDataRole.AccessibleTextRole) for col in range(3)]
    assert spoken == ["Category, Points", "Points, Player, Luka Doncic", "Points, Value, 45"]


def test_each_table_is_named_for_its_team_in_every_view(open_leaders):
    _, tables = tables_of(open_leaders(NBA))
    name = "Los Angeles Lakers Statistical Leaders"
    assert tables[0].accessibleName() == tables[0].table_widget.accessibleName() == name
    assert tables[0].quick_list.accessibleName() == f"{name} - Quick List"
    assert tables[0].full_list.accessibleName() == f"{name} - Full List"
    assert "Toronto Raptors" in tables[1].table_widget.accessibleName()


@pytest.mark.parametrize("mode", [TABLE, QUICK, FULL])
def test_focus_lands_on_the_first_row_of_the_first_table_on_opening(open_leaders, saved_view, mode):
    saved_view["default_view_mode"] = mode
    dialog = open_leaders(NBA)
    _, tables = tables_of(dialog)
    shown = tables[0].stacked_widget.currentWidget()
    assert shown is [tables[0].table_widget, tables[0].quick_list, tables[0].full_list][mode]
    assert shown.isVisible()
    assert dialog.focusWidget() is shown
    assert tables[0].currentRow() == 0


def test_the_view_keys_work(open_leaders, saved_view):
    dialog = open_leaders(NBA)
    _, tables = tables_of(dialog)
    QApplication.sendEvent(tables[0].table_widget,
                           QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.AltModifier))
    assert dialog.focusWidget() is tables[0].quick_list
    assert saved_view["default_view_mode"] == QUICK


def test_a_team_with_no_rows_gets_its_message_and_no_stray_table(open_leaders):
    empty = {"team": {"displayName": "Nobody FC"}, "leaders": [{"displayName": "Points", "leaders": []}]}
    leaders = [empty, NBA[0]]
    dialog = open_leaders(leaders)
    tabs = dialog.findChildren(QTabWidget)[0]
    assert tabs.widget(0).findChildren(LeadersTable) == []
    assert "No statistical leaders available for Nobody FC." in [
        label.text() for label in tabs.widget(0).findChildren(QLabel)]
    assert tabs.widget(1).findChildren(LeadersTable)[0].rowCount() == len(NBA[0]["leaders"])
    assert dialog.parent().findChildren(LeadersTable, options=Qt.FindChildOption.FindDirectChildrenOnly) == []


def test_a_failure_is_a_plain_sentence_on_a_row_with_focus(open_leaders, monkeypatch, tmp_path):
    def fail(self, layout, data):
        raise AttributeError("'LeadersTable' object has no attribute 'setEditTriggers'")

    log = tmp_path / "errors.log"
    monkeypatch.setattr(scores.error_log, "log_path", lambda: str(log))
    monkeypatch.setattr(Host, "_add_leaders_data_to_layout", fail)
    dialog = open_leaders(NBA)
    assert "setEditTriggers" in log.read_text(encoding="utf-8")  # the build has no console
    rows = dialog.findChildren(QListWidget)
    assert len(rows) == 1
    assert rows[0].item(0).text() == "Leaders can't be shown for this game."
    assert rows[0].currentRow() == 0
    assert rows[0].isVisible()
    assert dialog.focusWidget() is rows[0]
    assert not any("setEditTriggers" in label.text() for label in dialog.findChildren(QLabel))
