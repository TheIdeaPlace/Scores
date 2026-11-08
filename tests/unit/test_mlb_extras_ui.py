"""The Windows win probability and season series controls: the two rows in an MLB game's
details, Enter on them, and the dialogs they open, built from a real MLB summary.
Builds Qt objects."""
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

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
FINAL = json.loads((FIXTURES / "summary_final_MLB_401817091.json").read_text(encoding="utf-8"))
WP_LINE = "Win probability: Mets 100%"
SERIES_LINE = "Regular Season Series: Mets lead 7-5"  # as of this game, the 12th of 13
TITLE = "New York Mets at Washington Nationals"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def spoken(monkeypatch):
    said = []
    monkeypatch.setattr(scores, "announce", lambda text, *a, **k: said.append(text))
    return said


@pytest.fixture
def requests(monkeypatch):
    started = []
    monkeypatch.setattr(scores, "_start_detached_thread", started.append)
    return started


class DetailsHost(scores.GameDetailsView):
    """The real row building and Enter handling, without loading a game."""

    def __init__(self, league):
        scores.BaseView.__init__(self)
        self.league = league
        self.game_id = "401817091"
        self.original_game_data = None
        self._game_title = ""
        self.details_list = QListWidget(self)
        self.layout.addWidget(self.details_list)
        self.details_list.itemActivated.connect(self._on_detail_item_selected)

    def rows(self):
        return [self.details_list.item(i).text() for i in range(self.details_list.count())]


def _details(summary):
    return scores.ApiService.extract_meaningful_game_info(summary)


def test_an_mlb_game_has_both_rows_after_the_game_time(app):
    host = DetailsHost("MLB")
    host._add_basic_game_info(_details(FINAL), FINAL)
    rows = host.rows()
    assert host._game_title == TITLE
    wp_row, series_row = rows.index(WP_LINE), rows.index(SERIES_LINE)
    assert series_row == wp_row + 1
    for row, field in ((wp_row, "win_probability"), (series_row, "season_series")):
        data = host.details_list.item(row).data(Qt.ItemDataRole.UserRole)
        assert data == {"field": field, "data": FINAL}


def test_no_rows_outside_mlb_or_without_the_blocks(app):
    other = DetailsHost("NFL")
    other._add_basic_game_info(_details(FINAL), FINAL)
    assert WP_LINE not in other.rows() and SERIES_LINE not in other.rows()
    bare = copy.deepcopy(FINAL)
    bare.pop("winprobability")
    bare.pop("seasonseries")
    host = DetailsHost("MLB")
    host._add_basic_game_info(_details(bare), bare)
    assert not any(r.startswith(("Win probability", "Regular Season Series")) for r in host.rows())


@pytest.mark.parametrize("line,name", [(WP_LINE, "WinProbabilityDialog"), (SERIES_LINE, "SeasonSeriesDialog")])
def test_enter_on_a_row_opens_its_dialog(app, monkeypatch, line, name):
    opened = []

    class FakeDialog:
        def __init__(self, league, game_id, title, summary, parent):
            opened.append((league, game_id, title, summary))

        def exec(self):
            return 0

    monkeypatch.setattr(scores, name, FakeDialog)
    host = DetailsHost("MLB")
    host._add_basic_game_info(_details(FINAL), FINAL)
    host.show()
    host.details_list.setCurrentRow(host.rows().index(line))
    host.details_list.hasFocus = lambda: True
    QTest.keyClick(host.details_list, Qt.Key.Key_Return)
    assert opened == [("MLB", "401817091", TITLE, FINAL)]
    host.close()


def _cells(table):
    return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]


def test_win_probability_dialog(app):
    dialog = scores.WinProbabilityDialog("MLB", "401817091", TITLE, FINAL)
    assert dialog.windowTitle() == f"Win Probability - {TITLE} - MLB - Sports Scores"
    assert dialog.overview.text().startswith("Mets 100%, Nationals 0% after the last play. Biggest swing: Mets +50")
    assert dialog.accessibleDescription() == dialog.overview.text()
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == list(dialog.TABS)
    innings, plays, swings = (_cells(t) for t in dialog.tables)
    assert len(innings) == 18 and len(plays) == 74 and len(swings) == 5
    assert dialog.tables[0].horizontalHeaderItem(3).text() == "Mets chance"
    assert plays[0] == ["Top 1st", "Lindor popped out to shortstop.", "Mets 0, Nationals 0", "30%", "70%", ""]
    assert swings[0][0] == "Top 7th" and swings[0][5] == "Mets +50"
    assert innings[-1][0] == "Bottom 9th"
    dialog.close()


def test_win_probability_dialog_f5_keeps_the_row(app, spoken, requests):
    dialog = scores.WinProbabilityDialog("MLB", "401817091", "", FINAL)
    assert dialog.windowTitle() == "Win Probability - MLB - Sports Scores"
    dialog.show()
    dialog.tables[1].setCurrentCell(40, 0)
    QTest.keyClick(dialog, Qt.Key.Key_F5)
    assert len(requests) == 1
    dialog._on_loaded(dialog._generation - 1, {}, {})  # an older request: dropped
    assert dialog.tables[1].rowCount() == 74 and not spoken
    dialog.tables[1].setCurrentCell(40, 5)
    dialog._on_loaded(dialog._generation, FINAL, {})
    assert (dialog.tables[1].currentRow(), dialog.tables[1].table_widget.currentColumn()) == (40, 5)
    assert spoken == ["Updated. Mets 100%, Nationals 0%"]
    dialog._on_error(dialog._generation, "ESPN didn't answer. Try again.")
    assert spoken[-1] == "ESPN didn't answer. Try again."
    # The game's block gone: each tab says so, in the first cell, where focus lands.
    dialog._on_loaded(dialog._generation, {}, {})
    assert _cells(dialog.tables[1])[0][0] == "ESPN has no win probability for this game."
    assert _cells(dialog.tables[2])[0][0] == "No play has changed the chances yet."
    assert dialog.tables[1].currentRow() == 0
    assert spoken[-1] == "Updated. ESPN has no win probability for this game."
    dialog.close()


def test_season_series_dialog(app):
    dialog = scores.SeasonSeriesDialog("MLB", "401817091", TITLE, FINAL)
    assert dialog.windowTitle() == f"Season Series - {TITLE} - MLB - Sports Scores"
    tabs = dialog.findChildren(scores.QTabWidget)[0]
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Regular Season Series: Mets lead 7-5", "Current Series: Tied 1-1",
        "Preseason Series: Nationals won 4-1"]
    tables = dialog.findChildren(scores.AccessibleTable)
    assert sorted(t.accessible_name for t in tables) == [
        "Current Series: Tied 1-1, 3 games", "Preseason Series: Nationals won 4-1, 5 games",
        "Regular Season Series: Mets lead 7-5, 13 games"]
    regular = next(t for t in tables if t.accessible_name.startswith("Regular Season Series"))
    rows = _cells(regular)
    assert len(rows) == 13
    assert regular.horizontalHeaderItem(1).text() == "Game"
    # It starts on the game being looked at.
    assert rows[regular.currentRow()][1:] == ["Mets 7 at Nationals 1", "Mets", "Final, this game"]
    dialog.close()


def test_season_series_dialog_with_nothing(app):
    dialog = scores.SeasonSeriesDialog("MLB", "1", "", {})
    assert dialog.windowTitle() == "Season Series - MLB - Sports Scores"
    lists = dialog.findChildren(QListWidget)
    assert lists and lists[0].item(0).text() == "ESPN has no season series for this game."
    dialog.close()


def test_kitchen_sink_is_gone():
    assert not hasattr(scores, "KitchenSinkDialog")
