"""The Windows listen controls: Live Scores rows carry what opening and listening need, the
Game Radio dialog stays open on Enter, the listen row opens one menu, and the context menu
offers only what applies. Menus are captured rather than shown. Builds Qt objects."""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QMenu, QPushButton  # noqa: E402

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
    scores._show_game_listen_menu(widget, "WNBA", comp, widget.mapToGlobal(widget.rect().center()))
    assert spoken[-1] == "No radio links for WNBA yet"


# MLB: everywhere the other covered leagues have radio.

def _mlb_summary():
    return json.loads((FIXTURES / "summary_final_MLB_401817091.json").read_text(encoding="utf-8"))


def test_mlb_scores_list_listens_on_alt_l(app, menus, spoken):
    with patch.object(scores, "_start_detached_thread"):
        view = scores.LeagueView(None, "MLB")
    assert "Alt+L" in view.scores_list.accessibleDescription()
    board = json.loads((FIXTURES / "scoreboard_MLB_202606.json").read_text(encoding="utf-8"))
    game = board["events"][0]
    view._games_by_id = {game["id"]: game}
    item = QListWidgetItem("a game")
    item.setData(Qt.ItemDataRole.UserRole, game["id"])
    view.scores_list.addItem(item)
    view.scores_list.setCurrentItem(item)
    # The Alt+L action itself: a widget shortcut needs a shown, focused window to fire.
    listen = [a for a in view.scores_list.actions() if a.shortcut().toString() == "Alt+L"]
    assert len(listen) == 1
    listen[0].trigger()
    title, items = menus[-1]
    away_id, away_name, home_id, home_name = scores.radio_links.competitors(game["competitions"][0])
    assert title.startswith("Listen to ") and away_name in title and home_name in title
    assert items[0].startswith(f"{away_name}: ")
    assert any(item.startswith(f"{home_name}: ") for item in items)
    assert any(item.startswith("MLB Media Center") for item in items)


def test_mlb_league_list_has_game_radio(app):
    view = MagicMock(league="MLB", scores_list=QListWidget())
    view._add_section_row = lambda title, role: scores.LeagueView._add_section_row(view, title, role)
    scores.LeagueView._add_common_sections(view)
    roles = [view.scores_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(view.scores_list.count())]
    assert "__radio__" in roles


def test_mlb_game_radio_lists_the_league_then_every_team(app):
    dialog = scores.RadioDialog("MLB")
    rows = [dialog.radio_list.item(i).text() for i in range(dialog.radio_list.count())]
    assert dialog.windowTitle() == "Game Radio - MLB - Sports Scores"
    assert rows[0].startswith("Every game: MLB Media Center")
    teams = [row for row in rows if not row.startswith("Every game: ")]
    assert len(teams) == 30 and not any(row.endswith("no link yet") for row in teams)
    dialog.close()


def test_mlb_game_details_has_the_listen_row(app, menus, spoken):
    with patch.object(scores, "_start_detached_thread"):
        view = scores.GameDetailsView(None, "MLB", "401817091")
    summary = _mlb_summary()
    view._on_game_details_loaded(view._details_generation, summary, {})
    rows = [view.details_list.item(i).text() for i in range(view.details_list.count())]
    assert "Listen to the Game (Alt+L)" in rows
    view._listen_to_game()
    title, items = menus[-1]
    assert title == "Listen to New York Mets at Washington Nationals"
    assert items[0].startswith("New York Mets: ")


def test_mlb_team_hub_has_listen_on_the_radio(app):
    with patch.object(scores.TeamHubDialog, "_on_tab_changed"):
        hub = scores.TeamHubDialog({"team_name": "New York Yankees", "team_id": "10"}, "MLB")
    assert "&Listen on the Radio" in [button.text() for button in hub.findChildren(QPushButton)]
    hub.close()
