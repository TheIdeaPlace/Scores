"""What replaced the decoration a screen reader read aloud: words where a symbol meant
something, bold where a row was set apart by characters. Builds Qt objects: CI or the VM only."""
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QTreeWidgetItem, QVBoxLayout, QWidget  # noqa: E402

from accessible_table import AccessibleTable  # noqa: E402
import scores  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_a_scoring_at_bat_still_names_its_batter_when_its_pitches_play(app):
    """The row starts "Scoring play: " now; the batter's name is still what comes before the colon."""
    at_bat = QTreeWidgetItem([f"{scores.SCORING_PLAY_PREFIX}Juan Soto: Juan Soto homered to right  (NYM 2 - ATL 1)"])
    at_bat.addChild(QTreeWidgetItem(["Pitch 1"]))
    view = MagicMock(audio_mapper=object())
    view._is_at_bat_item.side_effect = lambda item: item is at_bat
    view._is_pitch_item.side_effect = lambda item: item is not at_bat
    view._pitch_has_location.return_value = True
    scores.GameDetailsView._play_pitch_sequence(view, at_bat)
    view._on_audio_feedback.assert_called_once_with("Playing pitch sequence for Juan Soto (1 pitches)")


def test_a_world_cup_group_says_who_advances_in_words(app):
    team = {"games_played": 3, "wins": 3, "draws": 0, "losses": 0, "goal_difference": 6, "points": 9}
    view = MagicMock(_GROUP_HEADERS=scores.WorldCupDialog._GROUP_HEADERS, current_groups=[{
        "name": "Group A",
        "teams": [{"abbreviation": "USA", "advancement_note": "Advance to Round of 32", **team},
                  {"abbreviation": "MEX", "advancement_note": "", **team}],
    }])
    container = QWidget()
    layout = QVBoxLayout(container)
    scores.WorldCupDialog._rebuild_groups_widget(view, layout, container)
    table = container.findChild(AccessibleTable)
    cells = [table.table_widget.item(row, 0).text() for row in range(table.table_widget.rowCount())]
    assert cells == ["USA (Advance to Round of 32)", "MEX"]


def test_venue_details_headings_are_bold_words_and_facts_have_no_bullets(app):
    dialog = scores.VenueDetailsDialog({
        "basic_info": {"name": "Wrigley Field", "location": "Chicago, IL", "league": "MLB"},
        "characteristics": {"indoor": False},
        "home_teams": [{"name": "Chicago Cubs", "abbreviation": "CHC"}],
        "interesting_facts": ["Ivy on the outfield walls"],
    })
    lst = dialog.details_list
    rows = [lst.item(i) for i in range(lst.count())]
    bold = [row.text() for row in rows if row.font().bold()]
    assert bold == ["Wrigley Field", "Basic Information", "Stadium Characteristics", "Home Teams",
                    "Interesting Facts"]
    assert "Ivy on the outfield walls" in [row.text() for row in rows]
    dialog.deleteLater()
