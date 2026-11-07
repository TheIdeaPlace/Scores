"""The Windows listen controls: Live Scores rows carry what opening and listening need, the
Game Radio dialog stays open on Enter, the listen row opens one menu, and the context menu
offers only what applies. Menus are captured rather than shown. Builds Qt objects."""
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QMenu  # noqa: E402

import scores  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def menus(monkeypatch):
    """Every menu opened, as (title, [item texts]); choosing nothing, as Escape does."""
    shown = []

    def exec_(self, *args, **kwargs):
        shown.append((self.title() or self.accessibleName(), [a.text() for a in self.actions()]))
        return None

    monkeypatch.setattr(QMenu, "exec", exec_)
    return shown


@pytest.fixture
def spoken(monkeypatch):
    said = []
    monkeypatch.setattr(scores, "announce", lambda text, *a, **k: said.append(text))
    return said


def test_live_scores_rows_carry_id_and_league():
    raw = {"id": "401", "name": "A at B", "teams": [], "competitions": [{}]}
    row = scores.LiveScoresView._row_data({"game_id": "401", "league": "NFL", "raw_data": raw})
    assert (row["id"], row["league"]) == ("401", "NFL")
    assert "league" not in raw, "the scoreboard entry itself is left alone"


def test_game_radio_dialog_stays_open_on_enter(app, menus, monkeypatch):
    opened = []
    monkeypatch.setattr(scores.webbrowser, "open", lambda url: opened.append(url) or True)
    dialog = scores.RadioDialog("NFL")
    dialog.show()
    dialog.radio_list.setFocus()
    dialog.radio_list.setCurrentRow(0)
    QTest.keyClick(dialog.radio_list, Qt.Key.Key_Return)
    assert opened and dialog.isVisible()
    dialog.radio_list.setCurrentRow(dialog.radio_list.count() - 1)
    QTest.keyClick(dialog.radio_list, Qt.Key.Key_Return)
    assert menus and menus[-1][0].startswith("Listen to the ")
    assert dialog.isVisible()
    assert dialog.windowTitle() == "Game Radio - NFL - Sports Scores"
    dialog.close()


class DetailsHost(scores.GameDetailsView):
    """The real Enter handling. GameDetailsView's own constructor starts loading a game, so
    only BaseView's runs."""

    def __init__(self):
        scores.BaseView.__init__(self)
        self.listened = 0
        self.details_list = QListWidget(self)
        self.layout.addWidget(self.details_list)
        item = QListWidgetItem("Listen to the Game (Alt+L)")
        item.setData(Qt.ItemDataRole.UserRole, {"field": "listen", "data": True})
        self.details_list.addItem(item)
        self.details_list.itemActivated.connect(self._on_detail_item_selected)

    def _listen_to_game(self):
        self.listened += 1


def test_enter_on_the_listen_row_opens_one_menu(app):
    host = DetailsHost()
    host.show()
    host.details_list.setCurrentRow(0)
    # A key handler that also activates on Enter would open it a second time, and only with
    # focus on the list. Which window is active depends on the tests before this one, so
    # say so rather than rely on it.
    host.details_list.hasFocus = lambda: True
    QTest.keyClick(host.details_list, Qt.Key.Key_Return)
    assert host.listened == 1
    host.close()


def _list_with_keys(can_listen, is_game=True):
    calls = []
    widget = QListWidget()
    widget.addItem("a game")
    widget.setCurrentRow(0)
    scores._add_listen_keys(widget, lambda: calls.append("listen"), lambda: calls.append("open"),
                            lambda: is_game, lambda: can_listen)
    return widget, calls


def test_context_menu_offers_listen_only_where_there_are_links(app, menus):
    widget, calls = _list_with_keys(can_listen=True)
    widget.customContextMenuRequested.emit(widget.rect().center())
    assert menus[-1] == ("Game Options", ["Game Details\tEnter", "Listen to the Game\tAlt+L"])
    assert calls == [], "Escape chooses nothing"
    widget, _ = _list_with_keys(can_listen=False)
    widget.customContextMenuRequested.emit(widget.rect().center())
    assert menus[-1] == ("Game Options", ["Game Details\tEnter"])


def test_context_menu_on_a_row_that_is_not_a_game_says_so(app, menus, spoken):
    widget, _ = _list_with_keys(can_listen=True, is_game=False)
    widget.customContextMenuRequested.emit(widget.rect().center())
    assert not menus and spoken == ["No options for this row"]


def test_listen_menu_for_a_real_game(app, menus, spoken):
    board = json.loads((FIXTURES / "scoreboard_NFL_202611.json").read_text(encoding="utf-8"))
    comp = board["events"][0]["competitions"][0]
    widget = QListWidget()
    scores._show_game_listen_menu(widget, "NFL", comp, widget.mapToGlobal(widget.rect().center()))
    title, items = menus[-1]
    assert title.startswith("Listen to ") and " at " in title
    assert any("SiriusXM" in item for item in items)
    scores._show_game_listen_menu(widget, "MLB", comp, widget.mapToGlobal(widget.rect().center()))
    assert spoken[-1] == "No radio links for MLB yet"
