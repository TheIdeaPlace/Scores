"""Team Hub's Stats tab and the golf dialog's News tab on Windows (#196). Builds Qt objects with
stand-in loaders, so nothing reaches ESPN; the one test that needs key presses shows the dialog."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent, QKeySequence  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

import espn_api  # noqa: E402
import scores  # noqa: E402
import settings  # noqa: E402
from accessible_table import AccessibleTable  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
FAILED = "ESPN isn't providing these right now. Try again in a minute."


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
    monkeypatch.setattr(settings, "_cache", None)


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class FakeStatsLoader:
    made = []

    def __init__(self, team_id, league, kind):
        self.team_id, self.league, self.kind = team_id, league, kind
        self.data_loaded = FakeSignal()
        self.error_occurred = FakeSignal()
        FakeStatsLoader.made.append(self)

    def start(self):
        pass

    def answer(self, data):
        self.data_loaded.emit(self.kind, data)

    def fail(self, message=FAILED):
        self.error_occurred.emit(self.kind, message)


PLAYERS = espn_api._parse_leaders(load("leaders_v3_team_NBA_14.json"), one_team=True)
RANKINGS = {"rankings": [
    {"section": "Offensive", "category": "Points Per Game", "value": "123.0", "rank": 1, "rank_display": "1st",
     "league_size": 30},
    {"section": "Defensive", "category": "Blocks", "value": "41", "rank": 9, "rank_display": "Tied-9th",
     "league_size": 30},
], "season": "2026-27 Regular Season"}


def quick_rows(table):
    return [table.quick_list.item(i).text() for i in range(table.quick_list.count())]


def full_rows(table):
    return [table.full_list.item(i).text() for i in range(table.full_list.count())]


class TestTeamHubStats:
    @pytest.fixture
    def hub(self, app):
        FakeStatsLoader.made = []
        quiet = {scores.TeamHubDialog.INFO_TAB, scores.TeamHubDialog.ROSTER_TAB, scores.TeamHubDialog.SCHEDULE_TAB,
                 scores.TeamHubDialog.NEWS_TAB, scores.TeamHubDialog.TRANSACTIONS_TAB}
        original = scores.TeamHubDialog._on_tab_changed

        def only_stats(dialog, index):
            # The other tabs' loaders aren't stood in for, so they mustn't start.
            if index in quiet:
                dialog._tabs_loaded.add(index)
                return
            original(dialog, index)

        with patch.object(scores, "TeamStatsLoader", FakeStatsLoader), \
                patch.object(scores.TeamHubDialog, "_on_tab_changed", only_stats):
            dialog = scores.TeamHubDialog({"team_name": "Miami Heat", "team_id": "14"}, "NBA")
            yield dialog
            dialog.deleteLater()

    def open_stats(self, hub):
        hub.tab_widget.setCurrentIndex(hub.STATS_TAB)
        return {loader.kind: loader for loader in FakeStatsLoader.made}

    def test_six_tabs_with_stats_after_roster_as_on_the_iphone(self, hub):
        tabs = hub.tab_widget
        assert [tabs.tabText(i) for i in range(tabs.count())] == [
            "&Info", "R&oster", "St&ats", "&Schedule", "&News", "T&ransactions"]

    def test_its_mnemonic_is_its_own(self, hub):
        """Alt+T, Alt+Q, Alt+F and Alt+V are the view keys, and S is Schedule's."""
        tabs = hub.tab_widget
        keys = [QKeySequence.mnemonic(tabs.tabText(i)).toString() for i in range(tabs.count())]
        keys += [QKeySequence.mnemonic(b.text()).toString() for b in hub.findChildren(QPushButton) if b.text()]
        keys += [QKeySequence.mnemonic("Sho&w:").toString()]
        assert QKeySequence.mnemonic("St&ats").toString() == "Alt+A"
        named = [key for key in keys if key]
        assert len(named) == len(set(named)), named
        assert not {"Alt+T", "Alt+Q", "Alt+F", "Alt+V"} & set(named)

    def test_nothing_is_asked_until_the_tab_is_opened(self, hub):
        assert FakeStatsLoader.made == []
        loaders = self.open_stats(hub)
        assert set(loaders) == {"players", "team"}
        assert all((l.team_id, l.league) == ("14", "NBA") for l in loaders.values())

    def test_it_says_it_is_loading(self, hub):
        self.open_stats(hub)
        assert quick_rows(hub.stats_table) == ["Loading player stats..."]
        assert full_rows(hub.stats_table) == ["Player Stats: Loading player stats..."]

    def test_the_players_in_all_three_views(self, hub):
        self.open_stats(hub)["players"].answer(PLAYERS)
        table = hub.stats_table
        assert table._headers == ["Category", "Rank", "Player", "Value"]
        assert quick_rows(table)[0] == "Points Per Game, 1, Norman Powell, 21.7"
        assert full_rows(table)[0] == "Category: Points Per Game; Rank: 1; Player: Norman Powell; Value: 21.7"
        assert table.table_widget.rowCount() == len(quick_rows(table))
        assert table.table_widget.item(0, 2).text() == "Norman Powell"
        season = "2025-26 Regular Season, ranked within this team, qualified players first"
        assert hub.stats_season.text() == season
        assert table.accessibleName() == f"Miami Heat Player Stats, {season}"

    def test_a_cell_names_its_player(self, hub):
        """Down the Value column, each number says whose it is."""
        self.open_stats(hub)["players"].answer(PLAYERS)
        cells = hub.stats_table.table_widget
        assert cells.item(0, 3).data(Qt.ItemDataRole.AccessibleTextRole) == "Norman Powell, Value, 21.7"
        assert cells.item(0, 0).data(Qt.ItemDataRole.AccessibleTextRole) == "Norman Powell, Category, Points Per Game"

    def test_show_team_switches_to_the_ranks(self, hub):
        loaders = self.open_stats(hub)
        loaders["players"].answer(PLAYERS)
        loaders["team"].answer(RANKINGS)
        hub.stats_choice.setCurrentIndex(1)
        table = hub.stats_table
        assert table._headers == ["Section", "Category", "Value", "Rank"]
        assert quick_rows(table) == ["Offensive, Points Per Game, 123.0, 1st", "Defensive, Blocks, 41, Tied-9th"]
        assert table.table_widget.item(1, 3).data(Qt.ItemDataRole.AccessibleTextRole) == "Blocks, Rank, Tied-9th"
        assert table.accessibleName() == "Miami Heat Team Rankings, 2026-27 Regular Season"
        hub.stats_choice.setCurrentIndex(0)
        assert quick_rows(table)[0].startswith("Points Per Game, 1, ")

    def test_the_other_lists_answer_does_not_redraw_this_one(self, hub):
        loaders = self.open_stats(hub)
        loaders["players"].answer(PLAYERS)
        hub.stats_table.table_widget.setCurrentCell(3, 2)
        loaders["team"].answer(RANKINGS)
        assert hub.stats_table.table_widget.currentRow() == 3

    def test_nothing_to_show_says_so(self, hub):
        loaders = self.open_stats(hub)
        loaders["players"].answer({"player_stats": [], "team_stats": []})
        loaders["team"].answer({"rankings": [], "season": ""})
        assert quick_rows(hub.stats_table) == ["No player statistics available."]
        hub.stats_choice.setCurrentIndex(1)
        assert quick_rows(hub.stats_table) == ["No team statistics available."]
        assert hub.stats_table.accessibleName() == "Miami Heat Team Rankings"

    def test_a_failure_says_so_and_coming_back_asks_again_for_that_list_only(self, hub):
        loaders = self.open_stats(hub)
        loaders["players"].answer(PLAYERS)
        loaders["team"].fail()
        hub.stats_choice.setCurrentIndex(1)
        assert quick_rows(hub.stats_table) == [f"{FAILED} Press F5 to try again."]
        hub.tab_widget.setCurrentIndex(hub.ROSTER_TAB)
        hub.tab_widget.setCurrentIndex(hub.STATS_TAB)
        again = FakeStatsLoader.made[2:]
        assert [l.kind for l in again] == ["team"]
        assert quick_rows(hub.stats_table) == ["Loading team stats..."]
        again[0].answer(RANKINGS)
        assert len(quick_rows(hub.stats_table)) == 2

    def test_f5_asks_again_for_a_failed_list_only(self, hub):
        loaders = self.open_stats(hub)
        loaders["players"].answer(PLAYERS)
        loaders["team"].fail()
        hub.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))
        assert [l.kind for l in FakeStatsLoader.made] == ["players", "team", "team"]
        hub.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))
        assert len(FakeStatsLoader.made) == 3, "nothing has failed now; it's loading"

    def test_a_list_still_coming_is_not_asked_for_twice(self, hub):
        loaders = self.open_stats(hub)
        loaders["team"].fail()
        hub.tab_widget.setCurrentIndex(hub.ROSTER_TAB)
        hub.tab_widget.setCurrentIndex(hub.STATS_TAB)
        assert [l.kind for l in FakeStatsLoader.made] == ["players", "team", "team"]

    @pytest.mark.parametrize("league", ["EPL", "NCAAH"])
    def test_a_league_windows_has_no_players_for_says_so_and_opens_on_team(self, app, league):
        FakeStatsLoader.made = []
        with patch.object(scores, "TeamStatsLoader", FakeStatsLoader), \
                patch.object(scores.TeamHubDialog, "_load_info"):
            hub = scores.TeamHubDialog({"team_name": "Manchester City", "team_id": "382"}, league)
            hub.tab_widget.setCurrentIndex(hub.STATS_TAB)
            assert [l.kind for l in FakeStatsLoader.made] == ["team"]
            assert hub.stats_choice.currentData() == "team"
            hub.stats_choice.setCurrentIndex(0)
            assert quick_rows(hub.stats_table) == ["Player leaders for one team aren't on Windows yet for this league."]
            hub.deleteLater()

    def test_the_tabs_view_keys_find_the_table(self, hub):
        self.open_stats(hub)
        page = hub.tab_widget.widget(hub.STATS_TAB)
        assert page.findChildren(AccessibleTable) == [hub.stats_table]

    def test_the_other_tabs_still_load_by_their_own_index(self, app):
        with patch.object(scores.TeamHubDialog, "_load_info"), \
                patch.object(scores.TeamHubDialog, "_load_schedule") as schedule, \
                patch.object(scores.TeamHubDialog, "_load_news") as news, \
                patch.object(scores.TeamHubDialog, "_load_transactions") as transactions:
            hub = scores.TeamHubDialog({"team_name": "Miami Heat", "team_id": "14"}, "NBA")
            for index in (hub.SCHEDULE_TAB, hub.NEWS_TAB, hub.TRANSACTIONS_TAB):
                hub.tab_widget.setCurrentIndex(index)
            assert (schedule.call_count, news.call_count, transactions.call_count) == (1, 1, 1)
            assert hub.tab_widget.tabText(hub.NEWS_TAB) == "&News"
            hub.deleteLater()


class TestStatsLoader:
    def test_it_asks_for_the_list_it_is_for(self, app):
        with patch.object(scores.ApiService, "get_team_player_leaders", return_value=PLAYERS) as players, \
                patch.object(scores.ApiService, "get_team_stat_rankings", return_value=RANKINGS) as ranks:
            got = []
            for kind in ("players", "team"):
                loader = scores.TeamStatsLoader("14", "NBA", kind)
                loader.data_loaded.connect(lambda k, d: got.append((k, d)))
                loader.run()
        players.assert_called_once_with("NBA", "14")
        ranks.assert_called_once_with("NBA", "14")
        assert got == [("players", PLAYERS), ("team", RANKINGS)]

    def test_a_failure_says_which_list_and_what_happened(self, app):
        from exceptions import ApiError
        with patch.object(scores.ApiService, "get_team_stat_rankings", side_effect=ApiError(FAILED)):
            got = []
            loader = scores.TeamStatsLoader("14", "NBA", "team")
            loader.error_occurred.connect(lambda k, m: got.append((k, m)))
            loader.run()
        assert got == [("team", FAILED)]


# ---------------------------------------------------------------------------------- golf news

class FakeNewsLoader:
    made = []

    def __init__(self, tour):
        self.tour = tour
        self.data_loaded = FakeSignal()
        self.error_occurred = FakeSignal()
        FakeNewsLoader.made.append(self)

    def start(self):
        pass


class FakeQuiet:
    def __init__(self, *args, **kwargs):
        self.data_loaded = FakeSignal()
        self.error_occurred = FakeSignal()

    def start(self):
        pass


NEWS = [
    {"headline": "Ben James takes a one-shot lead", "description": "A 64 in Los Cabos.",
     "web_url": "https://www.espn.com/golf/story/_/id/1/ben-james"},
    {"headline": "No link here", "description": "", "web_url": ""},
]


class TestGolfNews:
    @pytest.fixture
    def golf(self, app):
        FakeNewsLoader.made = []
        with patch.object(scores, "GolfNewsLoader", FakeNewsLoader), \
                patch.object(scores, "GolfLeaderboardLoader", FakeQuiet), \
                patch.object(scores, "GolfScheduleLoader", FakeQuiet):
            dialog = scores.GolfTournamentDialog("LPGA")
            yield dialog
            dialog.deleteLater()

    @staticmethod
    def rows(lst):
        return [lst.item(i).text() for i in range(lst.count())]

    def test_a_news_tab_after_schedule(self, golf):
        tabs = golf.tab_widget
        assert [tabs.tabText(i) for i in range(tabs.count())] == ["Leaderboard", "Schedule", "News"]
        assert golf.news_list.accessibleName() == "LPGA Tour News"

    def test_asked_for_once_the_first_time_the_tab_opens(self, golf):
        assert FakeNewsLoader.made == []
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        golf.tab_widget.setCurrentIndex(0)
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        assert [loader.tour for loader in FakeNewsLoader.made] == ["LPGA"]
        assert self.rows(golf.news_list) == ["Loading news…"]

    def test_the_stories(self, golf):
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        FakeNewsLoader.made[0].data_loaded.emit(NEWS)
        assert self.rows(golf.news_list) == ["Ben James takes a one-shot lead\nA 64 in Los Cabos.", "No link here"]
        assert golf.news_list.currentRow() == 0

    def test_enter_opens_the_story_in_the_browser(self, golf):
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        FakeNewsLoader.made[0].data_loaded.emit(NEWS)
        with patch.object(scores.webbrowser, "open") as opened:
            golf.news_list.itemActivated.emit(golf.news_list.item(0))
            golf.news_list.itemActivated.emit(golf.news_list.item(1))
        opened.assert_called_once_with("https://www.espn.com/golf/story/_/id/1/ben-james")

    def test_no_news_says_so(self, golf):
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        FakeNewsLoader.made[0].data_loaded.emit([])
        assert self.rows(golf.news_list) == ["No news available."]
        with patch.object(scores.webbrowser, "open") as opened:
            golf.news_list.itemActivated.emit(golf.news_list.item(0))
        opened.assert_not_called()

    def test_a_failure_says_so_and_f5_asks_again(self, golf):
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        FakeNewsLoader.made[0].error_occurred.emit("ESPN isn't providing the news right now. Try again in a minute.")
        assert self.rows(golf.news_list) == ["ESPN isn't providing the news right now. Try again in a minute."]
        golf.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))
        assert len(FakeNewsLoader.made) == 2
        assert self.rows(golf.news_list) == ["Loading news…"]
        FakeNewsLoader.made[1].data_loaded.emit(NEWS)
        assert len(self.rows(golf.news_list)) == 2

    def test_enter_on_a_story_does_not_close_the_dialog(self, golf, app):
        from PyQt6.QtTest import QTest
        golf.show()
        golf.tab_widget.setCurrentIndex(golf.NEWS_TAB)
        FakeNewsLoader.made[0].data_loaded.emit(NEWS)
        golf.news_list.setFocus()
        app.processEvents()
        with patch.object(scores.webbrowser, "open") as opened:
            QTest.keyClick(golf.news_list, Qt.Key.Key_Return)
        assert golf.isVisible()
        opened.assert_called_once()
