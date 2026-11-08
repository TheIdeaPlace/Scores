"""The Windows on-ice controls: the row in a live NHL game's details, Enter on it, and the
dialog it opens, built from a real live summary. Builds Qt objects."""
import copy
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget  # noqa: E402

import scores  # noqa: E402

LIVE = json.loads((Path(__file__).parent.parent / "fixtures" / "espn" / "summary_live_NHL_401892664.json")
                  .read_text(encoding="utf-8"))
LINE = ("On the ice: Rangers: Zibanejad, Lafreniere, Perreault, Gavrikov, Morrow, Korpisalo; "
        "Kraken: Kakko, Samoskevich, Catton, Mahura, Ottavainen, Daccord")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def spoken(monkeypatch):
    said = []
    monkeypatch.setattr(scores, "announce", lambda text, *a, **k: said.append(text))
    return said


def _finished(summary):
    done = copy.deepcopy(summary)
    done["header"]["competitions"][0]["status"]["type"]["state"] = "post"
    return done


class DetailsHost(scores.GameDetailsView):
    """The real row building and Enter handling. GameDetailsView's own constructor starts
    loading a game, so only BaseView's runs."""

    def __init__(self, league):
        scores.BaseView.__init__(self)
        self.league = league
        self.game_id = "401892664"
        self.original_game_data = None
        self._game_title = ""
        self.details_list = QListWidget(self)
        self.layout.addWidget(self.details_list)
        self.details_list.itemActivated.connect(self._on_detail_item_selected)

    def rows(self):
        return [self.details_list.item(i).text() for i in range(self.details_list.count())]


def _details(summary):
    return scores.ApiService.extract_meaningful_game_info(summary)


def test_a_live_nhl_game_has_the_row(app):
    host = DetailsHost("NHL")
    host._add_basic_game_info(_details(LIVE), LIVE)
    assert LINE in host.rows()
    assert host._game_title == "New York Rangers at Seattle Kraken"
    row = host.rows().index(LINE)
    data = host.details_list.item(row).data(Qt.ItemDataRole.UserRole)
    assert data["field"] == "on_ice" and data["data"] == LIVE
    # It follows the clock, where the game's state is.
    assert host.rows()[row - 1].startswith("Game Time:")


def test_no_row_when_the_game_is_over_or_not_nhl(app):
    host = DetailsHost("NHL")
    done = _finished(LIVE)
    host._add_basic_game_info(_details(done), done)
    assert not any(r.startswith("On the ice") for r in host.rows())
    other = DetailsHost("NCAAH")
    other._add_basic_game_info(_details(LIVE), LIVE)
    assert not any(r.startswith("On the ice") for r in other.rows())


def test_enter_on_the_row_opens_the_dialog(app, monkeypatch):
    opened = []

    class FakeDialog:
        def __init__(self, league, game_id, title, summary, parent):
            opened.append((league, game_id, title, summary))

        def exec(self):
            return 0

    monkeypatch.setattr(scores, "OnIceDialog", FakeDialog)
    host = DetailsHost("NHL")
    host._add_basic_game_info(_details(LIVE), LIVE)
    host.show()
    host.details_list.setCurrentRow(host.rows().index(LINE))
    host.details_list.hasFocus = lambda: True
    QTest.keyClick(host.details_list, Qt.Key.Key_Return)
    assert opened == [("NHL", "401892664", "New York Rangers at Seattle Kraken", LIVE)]
    host.close()


def _dialog_rows(dialog):
    return [dialog.players_list.item(i).text() for i in range(dialog.players_list.count())]


@pytest.fixture
def requests(monkeypatch):
    """Each refresh the dialog starts, as its loader, with no request made."""
    started = []
    monkeypatch.setattr(scores, "_start_detached_thread", started.append)
    return started


def _pulled_goalie(summary):
    """The Rangers' goalie off: everyone after him moves up a row."""
    pulled = copy.deepcopy(summary)
    pulled["onIce"][1]["entries"] = [e for e in pulled["onIce"][1]["entries"] if e["athleteid"] != "3069266"]
    return pulled


def test_dialog_lists_each_team_then_its_players(app, requests):
    dialog = scores.OnIceDialog("NHL", "401892664", "New York Rangers at Seattle Kraken", LIVE)
    assert dialog.windowTitle() == "On the Ice - New York Rangers at Seattle Kraken - NHL - Sports Scores"
    rows = _dialog_rows(dialog)
    assert len(rows) == 14
    assert rows[0] == "New York Rangers, 6 on the ice"
    assert rows[1] == "Mika Zibanejad, number 93, Center"
    assert rows[6] == "Joonas Korpisalo, number 70, Goaltender"
    assert rows[7] == "Seattle Kraken, 6 on the ice"
    assert rows[13] == "Joey Daccord, number 35, Goaltender"
    assert dialog.players_list.currentRow() == 0
    assert dialog.players_list.accessibleName() == "On the Ice"
    dialog.close()


def test_opening_asks_again_quietly(app, spoken, requests):
    """The row's summary can be minutes old, so the dialog asks again as it opens. That
    says nothing unless the list changed, and nothing at all if it fails."""
    dialog = scores.OnIceDialog("NHL", "401892664", "", LIVE)
    assert len(requests) == 1 and dialog._quiet
    dialog.show()
    dialog._on_loaded(dialog._generation, LIVE, {})
    assert not spoken
    dialog._on_error(dialog._generation, "ESPN didn't answer. Try again.")
    assert not spoken
    dialog._on_loaded(dialog._generation, _pulled_goalie(LIVE), {})
    assert spoken == ["On the ice changed"]
    dialog.close()


def test_f5_asks_again_and_says_so(app, spoken, requests):
    dialog = scores.OnIceDialog("NHL", "401892664", "", LIVE)
    assert dialog.windowTitle() == "On the Ice - NHL - Sports Scores"
    dialog.show()
    QTest.keyClick(dialog.players_list, Qt.Key.Key_F5)
    assert len(requests) == 2 and not dialog._quiet
    dialog.players_list.setCurrentRow(9)
    dialog._on_loaded(dialog._generation - 1, _finished(LIVE), {})  # an older request: dropped
    assert len(_dialog_rows(dialog)) == 14 and not spoken
    dialog._on_loaded(dialog._generation, LIVE, {})
    assert dialog.players_list.currentRow() == 9
    assert spoken == ["On the ice updated"]
    dialog._on_error(dialog._generation, "ESPN didn't answer. Try again.")
    assert spoken[-1] == "ESPN didn't answer. Try again."
    dialog.close()
    dialog._on_loaded(dialog._generation, LIVE, {})
    assert spoken[-1] == "ESPN didn't answer. Try again.", "a closed dialog says nothing"


def test_refresh_stays_on_the_same_player(app, spoken, requests):
    dialog = scores.OnIceDialog("NHL", "401892664", "", LIVE)
    dialog.show()
    dialog.refresh()
    dialog.players_list.setCurrentRow(9)  # Mackie Samoskevich, a Kraken
    dialog._on_loaded(dialog._generation, _pulled_goalie(LIVE), {})
    assert dialog.players_list.currentItem().text() == "Mackie Samoskevich, number 11, Right Wing"
    assert dialog.players_list.currentRow() == 8
    dialog.players_list.setCurrentRow(0)
    dialog._on_loaded(dialog._generation, _finished(LIVE), {})
    assert _dialog_rows(dialog) == ["ESPN isn't saying who is on the ice right now."]
    assert dialog.players_list.currentRow() == 0
    dialog.close()
