"""College football's Standings and Teams dialogs, and the cache behind Standings, on ESPN's real
group=90 answer. Builds Qt objects: CI or the VM only."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QToolButton  # noqa: E402

import espn_api  # noqa: E402
import scores  # noqa: E402
import settings  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn", "standings_NCAAF_group90.json")


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    """No real %APPDATA% settings, and nothing left in the cache, which is a singleton."""
    monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
    monkeypatch.setattr(settings, "_cache", None)
    monkeypatch.setattr(scores.DataCache(), "standings_cache", {})


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rows():
    with open(FIXTURE, encoding="utf-8") as f:
        return espn_api.parse_college_standings(json.load(f))


def tab_names(dialog):
    return [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]


class TestTabs:
    def test_standings_and_teams_list_the_conferences_in_the_same_order(self, app, rows):
        standings_dialog = scores.StandingsDialog(rows, "NCAAF")
        teams_dialog = scores.SimpleTeamsDialog(rows, "NCAAF")
        standings = tab_names(standings_dialog)
        assert standings == tab_names(teams_dialog)
        assert len(standings) == 25
        assert standings[0] == "Southeastern Conference"
        assert standings[10] == "FBS Independents"
        assert standings[11] == "Big Sky Conference"
        assert standings[11:] == sorted(standings[11:])

    def test_the_teams_tabs_keep_their_scroll_buttons(self, app, rows):
        """Without them, Qt's tab bar asks for the width of every tab, and 25 run off the screen."""
        dialog = scores.SimpleTeamsDialog(rows, "NCAAF")
        assert dialog.tab_widget.usesScrollButtons()

    def test_the_teams_tabs_are_one_tab_stop(self, app, rows):
        dialog = scores.SimpleTeamsDialog(rows, "NCAAF")
        tabs = dialog.tab_widget
        assert tabs.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tabs.tabBar().focusPolicy() == Qt.FocusPolicy.TabFocus
        buttons = tabs.tabBar().findChildren(QToolButton)
        assert buttons and all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in buttons)


class TestCache:
    def test_changing_the_setting_doesnt_read_the_other_coverages_standings(self, rows):
        settings.set("ncaaf_coverage", "all_d1")
        cache = scores.DataCache()
        cache.set_standings(espn_api.standings_cache_key("NCAAF"), rows)
        assert cache.get_standings("NCAAF") == rows
        settings.set("ncaaf_coverage", "fbs")
        assert cache.get_standings("NCAAF") is None
        settings.set("ncaaf_coverage", "all_d1")
        assert cache.get_standings("NCAAF") == rows

    def test_the_key_is_taken_when_the_fetch_starts(self, app, rows):
        """All of Division I asked for, FBS only chosen while it loads: that answer isn't FBS's."""
        settings.set("ncaaf_coverage", "all_d1")
        started = scores.StandingsLoader("NCAAF").cache_key
        settings.set("ncaaf_coverage", "fbs")
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "StandingsDialog"):
            scores.LeagueView._on_standings_data_loaded(view, started, rows)
        assert scores.DataCache().get_standings("NCAAF") is None
        settings.set("ncaaf_coverage", "all_d1")
        assert scores.DataCache().get_standings("NCAAF") == rows

    def test_the_view_hands_on_the_key_from_when_it_asked(self, app, rows):
        settings.set("ncaaf_coverage", "all_d1")
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "_start_detached_thread"):  # no loading from ESPN
            scores.LeagueView._show_standings_dialog(view)
        settings.set("ncaaf_coverage", "fbs")
        view.standings_loader.data_loaded.emit(rows)
        view._on_standings_data_loaded.assert_called_once_with("standings_NCAAF_group90", rows)

    def test_a_new_answer_opens_the_dialog_with_it(self, app, rows):
        view = MagicMock(league="NCAAF")
        with patch.object(scores, "StandingsDialog") as dialog:
            scores.LeagueView._on_standings_data_loaded(view, "standings_NCAAF_group90", rows)
        dialog.assert_called_once_with(rows, "NCAAF", view)
        dialog.return_value.exec.assert_called_once()
