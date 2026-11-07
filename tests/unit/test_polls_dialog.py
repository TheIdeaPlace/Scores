"""The Polls dialog on ESPN's real college football rankings: every poll, in ESPN's order, as
tabs. CollegePollsTests.swift holds the iPhone to the same fixture and the same list. Builds Qt
objects: CI or the VM only."""
import json
import os

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from accessible_table import ListPages  # noqa: E402
import scores  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn")

FOOTBALL_POLLS = ["CFP Rankings", "AP Poll", "AFCA Coaches Poll", "FCS Coaches Poll", "AFCA Div II", "AFCA Div III"]


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def polls_data(fixture):
    with open(os.path.join(FIXTURES, fixture), encoding="utf-8") as f:
        return {"polls": json.load(f)["rankings"]}


def tab_names(dialog):
    return [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]


def cells(table, column):
    widget = table.table_widget
    return [widget.item(row, column).text() for row in range(widget.rowCount())]


@pytest.fixture
def football(app):
    dialog = scores.PollsDialog(polls_data("rankings_NCAAF.json"), "NCAAF")
    yield dialog
    dialog.deleteLater()


def test_every_football_poll_is_a_tab_in_espns_order(football):
    # Six is under the eight that make a list.
    assert isinstance(football.tab_widget, QTabWidget)
    assert not isinstance(football.tab_widget, ListPages)
    assert tab_names(football) == FOOTBALL_POLLS


def test_each_tab_has_its_own_poll(football):
    tops = [football.tab_widget.widget(i).table for i in range(football.tab_widget.count())]
    assert [cells(t, 1)[0] for t in tops] == [
        "Miami Hurricanes", "Miami Hurricanes", "Miami Hurricanes",
        "Tarleton State Texans", "Ferris State Bulldogs", "Wheaton (IL) Thunder"]
    assert tops[4].accessibleName() == "AFCA Div II Rankings"


def headers(table):
    widget = table.table_widget
    return [widget.horizontalHeaderItem(col).text() for col in range(widget.columnCount())]


def speech(table, row):
    widget = table.table_widget
    return [widget.item(row, col).data(Qt.ItemDataRole.AccessibleTextRole) for col in range(widget.columnCount())]


def list_rows(widget):
    return [widget.item(row).data(Qt.ItemDataRole.AccessibleTextRole) for row in range(widget.count())]


def test_a_voted_poll_has_points(football):
    ap = football.tab_widget.widget(1).table
    assert headers(ap) == ["Rank", "Team", "Record", "Points", "Previous"]
    assert cells(ap, 3) == ["1740", "1648", "1540"]


def test_the_playoff_committee_has_no_points_column(football):
    """It doesn't vote: ESPN sends 0.0 for everyone, which read as blanks (NVDA bug bash, finding 8)."""
    cfp = football.tab_widget.widget(0).table
    assert headers(cfp) == ["Rank", "Team", "Record", "Previous"]
    assert cells(cfp, 3) == ["NR", "NR", "NR"]
    assert list_rows(cfp.quick_list)[2] == "3, Utah Utes, 8-0, NR"
    assert list_rows(cfp.full_list)[0] == "Rank: 1; Team: Miami Hurricanes; Record: 8-0; Previous: NR"


def test_a_cell_says_the_team_rather_than_the_rank(football):
    """NVDA heard "2, Previous, NR" (bug bash, finding 8): the row's team, not its rank."""
    cfp = football.tab_widget.widget(0).table
    assert speech(cfp, 1) == ["Georgia Bulldogs, Rank, 2", "Team, Georgia Bulldogs",
                              "Georgia Bulldogs, Record, 7-1", "Georgia Bulldogs, Previous, NR"]
    ap = football.tab_widget.widget(1).table
    assert speech(ap, 0)[3] == "Miami Hurricanes, Points, 1740"
    assert list_rows(ap.quick_list)[0] == "1, Miami Hurricanes, 8-0, 1740, 1 —"


@pytest.mark.parametrize("fixture,league,top", [
    ("rankings_NCAAH.json", "NCAAH", "Wisconsin Badgers"),
    ("rankings_NCAAWH.json", "NCAAWH", "Ohio State Buckeyes"),
])
def test_one_poll_is_one_table_without_points(app, fixture, league, top):
    dialog = scores.PollsDialog(polls_data(fixture), league)
    assert dialog.tab_widget is None
    table = dialog.findChild(scores.PollsTable)
    assert headers(table) == ["Rank", "Team", "Record (W-L-T)", "Previous"]
    assert speech(table, 0)[2].startswith(f"{top}, Record (W-L-T), ")
    dialog.deleteLater()


def test_a_rank_with_nothing_but_its_number(app):
    table = scores.PollsTable(poll_name="Poll")
    table.populate_poll([{"current": 4, "previous": None, "points": None, "team": None}], set_focus=False)
    assert cells(table, 1) == ["Unknown"]
    assert headers(table) == ["Rank", "Team", "Record", "Previous"]
    assert cells(table, 3) == ["NR"]
