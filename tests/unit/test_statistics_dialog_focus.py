"""The statistics dialog's rows have to take focus at the moment they replace the loading row,
so UI Automation reports them rather than the window. Builds Qt objects: CI or the VM only."""
from unittest.mock import patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import scores  # noqa: E402


@pytest.fixture
def dialog():
    app = QApplication.instance() or QApplication([])
    with patch.object(scores, "_start_detached_thread"):  # no loading from ESPN
        view = scores.StatisticsViewDialog("NBA", "player")
    view.show()
    app.processEvents()
    yield view
    view.close()
    view.deleteLater()
    app.processEvents()


def assert_row_has_focus(view, text):
    # Before the event loop runs: this is the moment setFocus has to work.
    assert view.stats_list.isVisible()
    assert view.focusWidget() is view.stats_list
    QApplication.instance().processEvents()
    assert view.focusWidget() is view.stats_list
    assert text in view.stats_list.item(0).text()
    assert view.stats_list.currentRow() == 0


def test_the_failure_row_takes_focus(dialog):
    dialog._on_statistics_error("ESPN isn't providing these right now.")
    assert_row_has_focus(dialog, "Unable to load statistics: ESPN isn't providing these")


def test_the_nothing_available_row_takes_focus(dialog):
    dialog._on_statistics_loaded({"player_stats": [], "team_stats": []})
    assert_row_has_focus(dialog, "No player statistics are available for NBA")


def test_real_statistics_take_focus(dialog):
    leaders = [{"name": "Goals", "stats": [{"player_name": "A Player", "team": "X", "value": "9"}]}]
    dialog._on_statistics_loaded({"player_stats": leaders, "team_stats": []})
    assert dialog.stats_list.isVisible()
    assert dialog.focusWidget() is dialog.stats_list
