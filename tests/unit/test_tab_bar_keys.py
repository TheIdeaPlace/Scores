"""Home, End, arrows that go round and type-ahead find on a real tab bar. Builds Qt objects: CI or
the VM only. Which tab each key picks is in test_tab_keys.py; this is that it reaches the bar."""
import gc
import json
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6 import sip  # noqa: E402
from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QFocusEvent, QKeyEvent, QKeySequence  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QPushButton, QTabWidget, QVBoxLayout, QWidget  # noqa: E402

import accessible_table  # noqa: E402
from accessible_table import (  # noqa: E402
    AccessibleTable, ButtonKeys, ListPages, _TabBarViewKeys, is_tab_bar, make_tab_area, prepare_table_tabs, tab_labels)
import espn_api  # noqa: E402
import scores  # noqa: E402
import settings  # noqa: E402

NAMES = ["Southeastern", "Big Ten", "Big 12", "Sun Belt", "Big Sky", "Mountain West"]
PLAIN = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
KEYPAD = Qt.KeyboardModifier.KeypadModifier

LETTER_KEYS = {
    " ": Qt.Key.Key_Space,
    "1": Qt.Key.Key_1,
    **{c: Qt.Key(Qt.Key.Key_A.value + ord(c) - ord("a")) for c in "abcdefghijklmnopqrstuvwxyz"},
}


class Clock:
    now = 50.0

    def __call__(self):
        return self.now


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def clock():
    return Clock()


def make_tabs(names=NAMES, clock=None):
    tabs = QTabWidget()
    prepare_table_tabs(tabs)
    for name in names:
        tabs.addTab(QLabel(name), name)
    if clock is not None:
        tabs.findChild(_TabBarViewKeys).search.clock = clock
    return tabs


@pytest.fixture
def tabs(app, clock):
    return make_tabs(clock=clock)


def press(target, key, modifiers=PLAIN, text=""):
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
    QApplication.sendEvent(target, event)
    return event


def type_text(tabs, text):
    for char in text:
        lower = char.lower()
        modifiers = SHIFT if char != lower else PLAIN
        press(tabs.tabBar(), LETTER_KEYS[lower], modifiers, char)


class TestHomeAndEnd:
    def test_home_goes_to_the_first_tab(self, tabs):
        tabs.setCurrentIndex(3)
        press(tabs.tabBar(), Qt.Key.Key_Home)
        assert tabs.currentIndex() == 0

    def test_end_goes_to_the_last_tab(self, tabs):
        press(tabs.tabBar(), Qt.Key.Key_End)
        assert tabs.currentIndex() == len(NAMES) - 1

    def test_the_numeric_keypad_counts(self, tabs):
        press(tabs.tabBar(), Qt.Key.Key_End, KEYPAD)
        assert tabs.currentIndex() == len(NAMES) - 1

    def test_they_skip_disabled_and_hidden_tabs(self, tabs):
        tabs.setCurrentIndex(2)
        tabs.setTabEnabled(0, False)
        tabs.setTabVisible(5, False)
        press(tabs.tabBar(), Qt.Key.Key_Home)
        assert tabs.currentIndex() == 1
        press(tabs.tabBar(), Qt.Key.Key_End)
        assert tabs.currentIndex() == 4

    def test_with_a_modifier_they_are_left_alone(self, tabs):
        tabs.setCurrentIndex(3)
        press(tabs.tabBar(), Qt.Key.Key_Home, CTRL)
        press(tabs.tabBar(), Qt.Key.Key_End, SHIFT)
        assert tabs.currentIndex() == 3


class TestArrows:
    def test_left_and_right_still_move_one_tab(self, tabs):
        tabs.setCurrentIndex(2)
        press(tabs.tabBar(), Qt.Key.Key_Right)
        assert tabs.currentIndex() == 3
        press(tabs.tabBar(), Qt.Key.Key_Left)
        assert tabs.currentIndex() == 2

    def test_right_on_the_last_tab_goes_to_the_first(self, tabs):
        tabs.setCurrentIndex(len(NAMES) - 1)
        press(tabs.tabBar(), Qt.Key.Key_Right)
        assert tabs.currentIndex() == 0

    def test_left_on_the_first_tab_goes_to_the_last(self, tabs):
        press(tabs.tabBar(), Qt.Key.Key_Left)
        assert tabs.currentIndex() == len(NAMES) - 1

    def test_going_round_skips_disabled_and_hidden_tabs(self, tabs):
        tabs.setCurrentIndex(3)
        tabs.setTabEnabled(0, False)
        tabs.setTabVisible(4, False)
        tabs.setTabEnabled(5, False)
        press(tabs.tabBar(), Qt.Key.Key_Right)
        assert tabs.currentIndex() == 1

    def test_right_to_left_flips_the_arrows_as_qt_does(self, tabs):
        tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        press(tabs.tabBar(), Qt.Key.Key_Left)
        assert tabs.currentIndex() == 1
        press(tabs.tabBar(), Qt.Key.Key_Right)
        assert tabs.currentIndex() == 0
        press(tabs.tabBar(), Qt.Key.Key_Right)
        assert tabs.currentIndex() == len(NAMES) - 1

    def test_a_bar_with_no_tabs_passes_the_key_on(self, app):
        tabs = make_tabs([])
        press(tabs.tabBar(), Qt.Key.Key_Right)
        press(tabs.tabBar(), Qt.Key.Key_Home)
        assert tabs.currentIndex() == -1


class TestTypeAhead:
    def test_a_first_letter_goes_to_that_tab(self, tabs):
        type_text(tabs, "m")
        assert tabs.currentIndex() == 5

    def test_the_same_letter_cycles(self, tabs):
        seen = []
        for _ in range(4):
            type_text(tabs, "b")
            seen.append(tabs.currentIndex())
        assert seen == [1, 2, 4, 1]

    def test_different_letters_build_a_prefix(self, tabs):
        type_text(tabs, "sun")
        assert tabs.currentIndex() == 3

    def test_a_space_carries_the_prefix(self, tabs):
        type_text(tabs, "big s")
        assert tabs.currentIndex() == 4

    def test_a_digit_carries_the_prefix(self, tabs):
        type_text(tabs, "big 1")
        assert tabs.currentIndex() == 2

    def test_capitals_match(self, tabs):
        type_text(tabs, "S")
        assert tabs.currentIndex() == 3

    def test_a_pause_past_the_window_starts_over(self, tabs, clock):
        type_text(tabs, "s")
        assert tabs.currentIndex() == 3
        clock.now += (2 * QApplication.doubleClickInterval() + 1) / 1000
        type_text(tabs, "u")
        assert tabs.currentIndex() == 3
        type_text(tabs, "m")
        assert tabs.currentIndex() == 5

    def test_the_window_follows_the_system_double_click_time(self, tabs, clock):
        saved = QApplication.doubleClickInterval()
        QApplication.setDoubleClickInterval(2000)
        try:
            type_text(tabs, "s")
            assert tabs.currentIndex() == 3
            clock.now += 3.9  # Inside 2 x 2000 ms, so this is "so", which is Southeastern.
            type_text(tabs, "o")
            assert tabs.currentIndex() == 0
            clock.now += 4.1  # Outside it, so this is a new search for "m", not "som".
            type_text(tabs, "m")
            assert tabs.currentIndex() == 5
        finally:
            QApplication.setDoubleClickInterval(saved)

    def test_no_match_stays_put_and_starts_over(self, tabs):
        type_text(tabs, "x")
        assert tabs.currentIndex() == 0
        type_text(tabs, "m")
        assert tabs.currentIndex() == 5

    def test_a_key_that_matches_nothing_is_still_used_up(self, tabs):
        assert press(tabs.tabBar(), Qt.Key.Key_X, PLAIN, "x").isAccepted()

    def test_disabled_and_hidden_tabs_are_skipped(self, tabs):
        tabs.setTabEnabled(1, False)
        tabs.setTabVisible(2, False)
        type_text(tabs, "b")
        assert tabs.currentIndex() == 4
        type_text(tabs, "b")
        assert tabs.currentIndex() == 4

    def test_a_mnemonic_in_the_name_is_ignored(self, app, clock):
        tabs = make_tabs(["&Info", "R&oster", "T&ransactions"], clock)
        type_text(tabs, "ro")
        assert tabs.currentIndex() == 1

    def test_tab_labels_are_what_is_heard(self, app):
        tabs = make_tabs(["&Info", "R&oster", "Gone"])
        tabs.setTabEnabled(2, False)
        assert tab_labels(tabs) == ["Info", "Roster", None]

    def test_moving_away_with_an_arrow_or_home_ends_the_search(self, tabs):
        type_text(tabs, "s")
        press(tabs.tabBar(), Qt.Key.Key_Left)
        type_text(tabs, "m")
        assert tabs.currentIndex() == 5

    def test_leaving_the_bar_ends_the_search(self, tabs):
        type_text(tabs, "s")
        QApplication.sendEvent(tabs.tabBar(), QFocusEvent(QEvent.Type.FocusOut))
        type_text(tabs, "m")
        assert tabs.currentIndex() == 5

    def test_a_tab_widget_page_changes_with_the_bar(self, tabs):
        type_text(tabs, "sun")
        assert tabs.currentWidget().text() == "Sun Belt"


class TestAnAmpersandInAName:
    NAME = "Texas A&M Players"

    def test_qt_takes_a_plain_ampersand_as_a_mnemonic(self, app):
        """What the escaping is for. complexwidgets.cpp strips it from the exposed name too."""
        assert QKeySequence.mnemonic(self.NAME).toString() == "Alt+M"

    def test_a_tab_keeps_it_rather_than_making_a_mnemonic(self, app):
        tabs = make_tab_area(2)
        tabs.addTab(QLabel("One"), "Ohio Players")
        tabs.addTab(QLabel("Two"), self.NAME)
        assert tabs.tabText(1) == "Texas A&&M Players"
        assert QKeySequence.mnemonic(tabs.tabText(1)).isEmpty()

    def test_a_list_keeps_it_once(self, app):
        pages = make_tab_area(9)
        pages.addTab(QLabel("One"), self.NAME)
        assert pages.tabText(0) == self.NAME
        assert pages.tabBar().item(0).text() == self.NAME

    @pytest.mark.parametrize("count", [2, 9], ids=["tabs", "list"])
    def test_type_ahead_finds_it_with_the_ampersand(self, app, clock, count):
        area = make_tab_area(count)
        area.addTab(QLabel("One"), "Ohio Players")
        area.addTab(QLabel("Two"), "Texas Tech Players")
        area.addTab(QLabel("Three"), self.NAME)
        area.findChild(_TabBarViewKeys).search.clock = clock
        assert tab_labels(area)[2] == self.NAME
        type_text(area, "texas a")
        press(area.tabBar(), Qt.Key.Key_Ampersand, SHIFT, "&")
        press(area.tabBar(), Qt.Key.Key_M, SHIFT, "M")
        assert area.currentIndex() == 2

    def test_team_hub_asks_for_its_mnemonics(self, app):
        tabs = make_tab_area(5, mnemonics=True)
        tabs.addTab(QLabel("Roster"), "R&oster")
        assert tabs.tabText(0) == "R&oster"
        assert not QKeySequence.mnemonic(tabs.tabText(0)).isEmpty()


class TestLeftAlone:
    @pytest.mark.parametrize("modifiers", [CTRL, ALT, CTRL | ALT, Qt.KeyboardModifier.MetaModifier])
    def test_a_letter_with_a_modifier_is_not_typed(self, tabs, modifiers):
        event = press(tabs.tabBar(), Qt.Key.Key_M, modifiers, "m")
        assert tabs.currentIndex() == 0
        assert not event.isAccepted()

    def test_a_space_with_no_search_going_is_not_used_up(self, tabs):
        assert not press(tabs.tabBar(), Qt.Key.Key_Space, PLAIN, " ").isAccepted()

    @pytest.mark.parametrize("key,text", [(Qt.Key.Key_Return, "\r"), (Qt.Key.Key_Escape, "\x1b")])
    def test_enter_and_escape_pass_through_during_a_search(self, tabs, key, text):
        type_text(tabs, "s")
        assert not press(tabs.tabBar(), key, PLAIN, text).isAccepted()
        assert tabs.currentIndex() == 3

    def test_tab_is_not_part_of_a_search(self, tabs):
        type_text(tabs, "s")
        press(tabs.tabBar(), Qt.Key.Key_Tab, PLAIN, "\t")
        assert tabs.currentIndex() == 3

    def test_ctrl_tab_still_moves_a_tab(self, tabs):
        press(tabs.tabBar(), Qt.Key.Key_Tab, CTRL)
        assert tabs.currentIndex() == 1

    def test_ctrl_shift_tab_still_moves_back_a_tab(self, tabs):
        tabs.setCurrentIndex(2)
        press(tabs.tabBar(), Qt.Key.Key_Backtab, CTRL | SHIFT)
        assert tabs.currentIndex() == 1

    def test_f6_is_not_a_search(self, tabs):
        calls = []
        bar = tabs.tabBar()  # Held: Python attributes on it would otherwise go with the wrapper.
        bar.setFocus = lambda: calls.append("bar")
        press(tabs, Qt.Key.Key_F6)
        assert calls == ["bar"]
        assert tabs.currentIndex() == 0

    def test_the_bar_is_still_one_tab_stop(self, tabs):
        assert tabs.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tabs.tabBar().focusPolicy() == Qt.FocusPolicy.TabFocus


class TestPagesKeepTheirKeys:
    @pytest.fixture
    def tabs_with_table(self, app, monkeypatch):
        saved = {"default_view_mode": 0}
        monkeypatch.setattr(accessible_table.settings, "get", lambda k, d=None: saved.get(k, d))
        monkeypatch.setattr(accessible_table.settings, "set", saved.__setitem__)
        tabs = QTabWidget()
        prepare_table_tabs(tabs)
        for name in ("Passing", "Rushing"):
            page = QWidget()
            layout = QVBoxLayout(page)
            table = AccessibleTable(accessible_name=name, accessible_description=name)
            table.setup_columns(["Player", "YDS"])
            table.populate_data([["Avery", "10"], ["Rushing Rob", "4"]], set_focus=False)
            layout.addWidget(table)
            tabs.addTab(page, name)
        tabs.table = tabs.widget(0).findChildren(AccessibleTable)[0]
        return tabs

    def test_a_table_gets_its_own_letters(self, tabs_with_table):
        tabs = tabs_with_table
        press(tabs.table.table_widget, Qt.Key.Key_R, PLAIN, "r")
        assert tabs.currentIndex() == 0
        assert tabs.table.table_widget.currentRow() == 1

    def test_a_list_view_gets_its_own_home_and_end(self, tabs_with_table):
        tabs = tabs_with_table
        tabs.table.handle_view_key(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q, ALT))
        press(tabs.table.quick_list, Qt.Key.Key_End)
        assert tabs.currentIndex() == 0

    def test_a_key_coming_up_through_the_tab_widget_does_not_change_the_tab(self, tabs_with_table):
        tabs = tabs_with_table
        press(tabs, Qt.Key.Key_R, PLAIN, "r")
        press(tabs, Qt.Key.Key_End)
        press(tabs, Qt.Key.Key_Right)
        assert tabs.currentIndex() == 0

    def test_a_list_page_gets_its_own_letters(self, app):
        tabs = make_tabs([])
        page = QListWidget()
        page.addItems(["Apple", "Pear"])
        page.setCurrentRow(0)
        tabs.addTab(page, "Fruit")
        tabs.addTab(QLabel("Pasta"), "Pasta")
        press(page, Qt.Key.Key_P, PLAIN, "p")
        assert tabs.currentIndex() == 0
        assert page.currentRow() == 1


class TestRealDialogs:
    @pytest.fixture(autouse=True)
    def no_real_settings(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
        monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
        monkeypatch.setattr(settings, "_cache", None)

    @pytest.fixture
    def rows(self):
        fixture = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn", "standings_NCAAF_group90.json")
        with open(fixture, encoding="utf-8") as f:
            return espn_api.parse_college_standings(json.load(f))

    @staticmethod
    def rows_in_groups(rows, names):
        return [dict(row, division=names[i % len(names)]) for i, row in enumerate(rows)]

    @pytest.mark.parametrize("dialog_class", ["StandingsDialog", "SimpleTeamsDialog"])
    def test_the_college_football_conferences_are_a_list(self, app, rows, dialog_class):
        dialog = getattr(scores, dialog_class)(rows, "NCAAF")
        tabs = dialog.tab_widget
        assert isinstance(tabs, ListPages)
        assert tabs.tabBar().accessibleName() == "Conferences"
        bar = tabs.tabBar()
        press(bar, Qt.Key.Key_End)
        assert tabs.currentIndex() == tabs.count() - 1
        press(bar, Qt.Key.Key_Down)
        assert tabs.currentIndex() == 0
        type_text(tabs, "sun")
        assert tabs.tabText(tabs.currentIndex()) == "Sun Belt Conference"
        press(bar, Qt.Key.Key_Home)
        assert tabs.currentIndex() == 0
        assert tabs.currentWidget() is tabs.widget(0)

    @pytest.mark.parametrize("dialog_class", ["StandingsDialog", "SimpleTeamsDialog"])
    def test_eight_groups_stay_tabs_and_nine_are_a_list(self, app, rows, dialog_class):
        names = [f"Group {i} Conference" for i in range(9)]
        eight = getattr(scores, dialog_class)(self.rows_in_groups(rows, names[:8]), "NCAAM")
        nine = getattr(scores, dialog_class)(self.rows_in_groups(rows, names), "NCAAM")
        assert isinstance(eight.tab_widget, QTabWidget)
        assert eight.tab_widget.count() == 8
        assert isinstance(nine.tab_widget, ListPages)
        assert nine.tab_widget.count() == 9

    def test_enter_on_the_list_goes_to_the_table_and_leaves_the_dialog_open(self, app, rows):
        """Inside a dialog Qt would carry Enter on up to the dialog, which would press Close."""
        keys = ButtonKeys()
        app.installEventFilter(keys)
        dialog = scores.StandingsDialog(rows, "NCAAF")
        try:
            close = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Close")
            clicks = []
            close.clicked.connect(lambda: clicks.append(1))
            dialog.show()
            dialog.activateWindow()
            QApplication.processEvents()
            bar = dialog.tab_widget.tabBar()
            bar.setFocus()
            QApplication.processEvents()
            press(bar, Qt.Key.Key_Return, PLAIN, "\r")
            QApplication.processEvents()
            assert clicks == []
            assert dialog.isVisible()
            table = dialog.tab_widget.currentWidget().findChildren(AccessibleTable)[0]
            assert table.isAncestorOf(QApplication.focusWidget())
        finally:
            app.removeEventFilter(keys)
            dialog.close()

    @staticmethod
    def first_tab_stop_after(bar, dialog):
        widget = bar.nextInFocusChain()
        while not (widget.focusPolicy() & Qt.FocusPolicy.TabFocus and widget.isVisibleTo(dialog)):
            widget = widget.nextInFocusChain()
        return widget

    @pytest.mark.parametrize("names,wildcard", [
        (["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"],
         {"AL": [{"team_name": "Yankees", "wins": 9, "losses": 4}]}),
        (["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West", "League"],
         {"AL": [{"team_name": "Yankees", "wins": 9, "losses": 4}]}),
        (["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"], {}),
    ], ids=["tabs", "list", "unavailable"])
    def test_tab_from_a_wild_card_goes_to_it_and_not_to_close(self, app, rows, monkeypatch, names, wildcard):
        monkeypatch.setattr(scores.DataCache(), "get_mlb_wildcard", lambda: wildcard)
        dialog = scores.StandingsDialog(self.rows_in_groups(rows, names), "MLB")
        tabs = dialog.tab_widget
        index = next(i for i in range(tabs.count()) if tabs.tabText(i) == "AL Wild Card")
        with patch.object(scores, "announce"), patch.object(scores, "_start_detached_thread"):
            tabs.setCurrentIndex(index)
        stop =self.first_tab_stop_after(tabs.tabBar(), dialog)
        assert tabs.currentWidget().isAncestorOf(stop)

    def test_tab_from_a_draft_round_goes_to_its_picks_and_not_to_close(self, app):
        with patch.object(scores.NFLDraftDialog, "_load_year"), patch.object(scores.NFLDraftDialog, "_load_round"):
            dialog = scores.NFLDraftDialog()
            dialog._on_meta_loaded({"status": "post", "rounds": [
                {"number": 1, "short_name": "Round 1"}, {"number": 2, "short_name": "Round 2"}]})
            tabs = dialog.tab_widget
            assert self.first_tab_stop_after(tabs.tabBar(), dialog) is tabs.widget(0)
            tabs.setCurrentIndex(1)
            assert self.first_tab_stop_after(tabs.tabBar(), dialog) is tabs.widget(1)

    def test_nfl_divisions_stay_tabs(self, app, rows):
        names = ["AFC East", "AFC North", "AFC South", "AFC West", "NFC East", "NFC North", "NFC South", "NFC West"]
        dialog = scores.StandingsDialog(self.rows_in_groups(rows, names), "NFL")
        assert isinstance(dialog.tab_widget, QTabWidget)
        assert dialog.tab_widget.tabText(0) == "AFC East"

    def test_mlb_with_its_wild_cards_is_eight_tabs(self, app, rows):
        names = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]
        dialog = scores.StandingsDialog(self.rows_in_groups(rows, names), "MLB")
        tabs = dialog.tab_widget
        assert isinstance(tabs, QTabWidget)
        assert [tabs.tabText(i) for i in (6, 7)] == ["AL Wild Card", "NL Wild Card"]

    def test_wild_cards_on_a_list_are_reachable_and_load(self, app, rows, monkeypatch):
        names = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West", "League"]
        monkeypatch.setattr(scores.DataCache(), "get_mlb_wildcard", lambda: None)
        dialog = scores.StandingsDialog(self.rows_in_groups(rows, names), "MLB")
        tabs = dialog.tab_widget
        assert isinstance(tabs, ListPages)
        assert tabs.tabBar().accessibleName() == "Divisions and Wild Cards"
        assert tabs.tabText(7) == "AL Wild Card"
        with patch.object(scores, "_start_detached_thread") as started, patch.object(scores, "announce") as said:
            type_text(tabs, "al wi")
        assert tabs.currentIndex() == 7
        started.assert_called_once()
        said.assert_called_once_with("Loading AL Wild Card standings")

    def test_the_noun_comes_from_the_names(self, app, rows):
        names = [f"Area {i}" for i in range(9)]
        dialog = scores.SimpleTeamsDialog(self.rows_in_groups(rows, names), "NHL")
        assert dialog.tab_widget.tabBar().accessibleName() == "Divisions"

    @pytest.mark.parametrize("dialog_class", ["StandingsDialog", "SimpleTeamsDialog"])
    def test_a_dialog_still_opens_on_the_first_table(self, app, rows, dialog_class):
        dialog = getattr(scores, dialog_class)(rows, "NCAAF")
        table = dialog.tab_widget.widget(0).findChildren(AccessibleTable)[0]
        calls = []
        table.setFocus = lambda: calls.append("table")
        scores._focus_first_table(dialog)
        assert calls == ["table"]

    def test_tab_from_the_list_goes_to_the_table_on_show(self, app, rows):
        dialog = scores.StandingsDialog(rows, "NCAAF")
        table = dialog.tab_widget.currentWidget().findChildren(AccessibleTable)[0]
        widget = dialog.tab_widget.tabBar().nextInFocusChain()
        while not (widget.focusPolicy() & Qt.FocusPolicy.TabFocus and widget.isVisibleTo(dialog)):
            widget = widget.nextInFocusChain()
        assert table.isAncestorOf(widget)

    @pytest.mark.parametrize("box,area,count,name", [
        ("box_NFL_401873035.json", ListPages, 20, "Boxscore Tables"),
        ("box_NCAAF_401860924.json", ListPages, 19, "Boxscore Tables"),
        ("box_MLB_401817091.json", QTabWidget, 7, "Boxscore Tabs"),
        ("box_NHL_401892628.json", QTabWidget, 7, "Boxscore Tabs"),
        ("box_NBA_401909906.json", QTabWidget, 3, "Boxscore Tabs"),
    ])
    def test_a_box_score_picks_by_how_many_tables_it_has(self, app, box, area, count, name):
        path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn", box)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        host = QWidget()
        layout = QVBoxLayout(host)
        scores.GameDetailsView._add_boxscore_data_to_layout(None, layout, data.get("boxscore", data))
        made = layout.itemAt(0).widget()
        assert isinstance(made, area)
        assert made.count() == count
        named = made.tabBar() if area is ListPages else made
        assert named.accessibleName() == name

    def test_team_hub_keeps_its_mnemonics_out_of_the_search(self, app):
        # No loading from ESPN when a tab opens.
        with patch.object(scores.TeamHubDialog, "_on_tab_changed"):
            hub = scores.TeamHubDialog({"team_name": "Green Bay Packers", "team_id": "9"}, "NFL")
        tabs = hub.tab_widget
        type_text(tabs, "ro")
        assert tabs.tabText(tabs.currentIndex()) == "R&oster"


class TestListPages:
    NAMES = ["Southeastern", "Big Ten", "Big 12", "Sun Belt", "Big Sky", "Mountain West", "Ivy", "Patriot", "A&M Group"]

    @pytest.fixture
    def pages(self, app, clock):
        pages = make_tab_area(len(self.NAMES), "Tabs name", "Tabs text", list_name="Conferences", list_description="Help")
        for name in self.NAMES:
            pages.addTab(QLabel(name), name)
        pages.findChild(_TabBarViewKeys).search.clock = clock
        return pages

    @pytest.fixture
    def pages_with_tables(self, app, monkeypatch):
        saved = {"default_view_mode": 0}
        monkeypatch.setattr(accessible_table.settings, "get", lambda k, d=None: saved.get(k, d))
        monkeypatch.setattr(accessible_table.settings, "set", saved.__setitem__)
        pages = ListPages()
        for name in ("Passing", "Rushing", "Kicking"):
            page = QWidget()
            layout = QVBoxLayout(page)
            table = AccessibleTable(accessible_name=name, accessible_description=name)
            table.setup_columns(["Player", "YDS"])
            table.populate_data([["Avery", "10"], ["Rushing Rob", "4"]], set_focus=False)
            layout.addWidget(table)
            pages.addTab(page, name)
        return pages

    @staticmethod
    def table_on(pages, index):
        return pages.widget(index).findChildren(AccessibleTable)[0]

    def test_make_tab_area_names_the_list_and_leaves_the_rest_unnamed(self, pages):
        assert isinstance(pages, ListPages)
        assert pages.tabBar().accessibleName() == "Conferences"
        assert pages.tabBar().accessibleDescription() == "Help"
        assert pages.accessibleName() == ""
        assert pages.accessibleDescription() == ""

    def test_make_tab_area_gives_tabs_their_keys_and_names(self, app):
        tabs = make_tab_area(8, "Tabs name", "Tabs text", list_name="Conferences")
        assert isinstance(tabs, QTabWidget)
        assert tabs.accessibleName() == "Tabs name"
        assert tabs.accessibleDescription() == "Tabs text"
        assert tabs.findChild(_TabBarViewKeys) is not None
        assert tabs.focusPolicy() == Qt.FocusPolicy.NoFocus

    def test_it_answers_as_a_tab_widget_does(self, pages):
        assert pages.count() == len(self.NAMES)
        assert pages.tabText(3) == "Sun Belt"
        assert pages.currentIndex() == 0
        assert pages.currentWidget().text() == "Southeastern"
        assert pages.widget(3).text() == "Sun Belt"
        assert pages.widget(99) is None

    def test_the_first_row_is_chosen_from_the_start(self, pages):
        assert pages.tabBar().currentRow() == 0
        assert pages.tabBar().currentItem().isSelected()

    def test_the_page_follows_the_list(self, pages):
        seen = []
        pages.currentChanged.connect(seen.append)
        pages.tabBar().setCurrentRow(3)
        assert pages.currentWidget().text() == "Sun Belt"
        assert seen == [3]
        pages.setCurrentIndex(5)
        assert pages.tabBar().currentRow() == 5
        assert pages.currentWidget().text() == "Mountain West"
        assert seen == [3, 5]

    def test_the_list_is_the_only_tab_stop_of_its_own(self, pages):
        assert pages.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert pages.tabBar().focusPolicy() & Qt.FocusPolicy.TabFocus
        assert pages.focusProxy() is pages.tabBar()

    def test_the_list_fits_its_longest_name(self, pages):
        width = pages.tabBar().width()
        assert width <= ListPages._WIDEST_LIST
        assert pages.tabBar().minimumWidth() == pages.tabBar().maximumWidth()

    def test_down_and_up_go_round_the_ends(self, pages):
        press(pages.tabBar(), Qt.Key.Key_Up)
        assert pages.currentIndex() == len(self.NAMES) - 1
        press(pages.tabBar(), Qt.Key.Key_Down)
        assert pages.currentIndex() == 0
        press(pages.tabBar(), Qt.Key.Key_Down)
        assert pages.currentIndex() == 1

    def test_left_and_right_are_not_list_moves(self, pages):
        pages.resize(400, 300)
        pages.show()
        try:
            QApplication.processEvents()
            pages.setCurrentIndex(3)
            press(pages.tabBar(), Qt.Key.Key_Left)
            press(pages.tabBar(), Qt.Key.Key_Right)
            assert pages.currentIndex() == 3
        finally:
            pages.close()

    def test_home_and_end(self, pages):
        press(pages.tabBar(), Qt.Key.Key_End)
        assert pages.currentIndex() == len(self.NAMES) - 1
        press(pages.tabBar(), Qt.Key.Key_Home)
        assert pages.currentIndex() == 0

    def test_type_ahead_cycles_and_builds_a_prefix(self, pages):
        seen = []
        for _ in range(4):
            type_text(pages, "b")
            seen.append(pages.currentIndex())
        assert seen == [1, 2, 4, 1]
        pages.findChild(_TabBarViewKeys).search.reset()
        type_text(pages, "sun")
        assert pages.currentIndex() == 3

    def test_type_ahead_uses_the_system_window_not_qts_400_ms(self, pages, clock):
        saved = QApplication.doubleClickInterval()
        QApplication.setDoubleClickInterval(500)
        try:
            type_text(pages, "s")
            assert pages.currentIndex() == 3
            clock.now += 0.9  # Past Qt's fixed 400 ms, inside 2 x 500.
            type_text(pages, "o")
            assert pages.currentIndex() == 0
        finally:
            QApplication.setDoubleClickInterval(saved)

    def test_an_ampersand_in_a_name_is_just_that(self, pages):
        assert tab_labels(pages)[-1] == "A&M Group"
        type_text(pages, "a")
        assert pages.currentIndex() == len(self.NAMES) - 1

    def test_a_modified_letter_is_left_alone(self, pages):
        press(pages.tabBar(), Qt.Key.Key_M, CTRL, "m")
        assert pages.currentIndex() == 0

    def test_focus_stays_on_the_list_as_it_moves_and_tab_goes_to_the_table(self, pages_with_tables):
        pages = pages_with_tables
        bar = pages.tabBar()
        pages.resize(600, 400)
        pages.show()
        try:
            pages.activateWindow()
            QApplication.processEvents()
            bar.setFocus()
            QApplication.processEvents()
            assert QApplication.focusWidget() is bar
            for row in (1, 2):
                press(bar, Qt.Key.Key_Down)
                QApplication.processEvents()
                assert pages.currentIndex() == row
                assert QApplication.focusWidget() is bar

            press(bar, Qt.Key.Key_Tab, PLAIN, "\t")
            QApplication.processEvents()
            view = QApplication.focusWidget()
            assert self.table_on(pages, 2).isAncestorOf(view)
            assert pages.currentIndex() == 2

            press(view, Qt.Key.Key_Backtab, SHIFT)
            QApplication.processEvents()
            assert QApplication.focusWidget() is bar
            assert pages.currentIndex() == 2
        finally:
            pages.close()

    def test_ctrl_tab_from_a_table_lands_in_the_next_table(self, pages_with_tables, monkeypatch):
        pages = pages_with_tables
        here = self.table_on(pages, 0).table_widget
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: here))
        table = self.table_on(pages, 1)
        calls = []
        table.setFocus = lambda: calls.append("table")
        press(here, Qt.Key.Key_Tab, CTRL)
        QApplication.processEvents()
        assert pages.currentIndex() == 1
        assert calls == ["table"]

    def test_ctrl_tab_and_ctrl_shift_tab_go_round_from_the_list(self, pages):
        press(pages.tabBar(), Qt.Key.Key_Backtab, CTRL | SHIFT)
        assert pages.currentIndex() == len(self.NAMES) - 1
        press(pages.tabBar(), Qt.Key.Key_Tab, CTRL)
        assert pages.currentIndex() == 0

    def test_f6_moves_between_the_list_and_the_table(self, pages_with_tables):
        pages = pages_with_tables
        bar = pages.tabBar()
        table = self.table_on(pages, 0)
        calls = []
        table.setFocus = lambda: calls.append("table")
        bar.setFocus = lambda: calls.append("list")
        bar.hasFocus = lambda: True
        press(bar, Qt.Key.Key_F6)
        bar.hasFocus = lambda: False
        press(table.table_widget, Qt.Key.Key_F6)
        assert calls == ["table", "list"]

    def test_f6_lands_on_a_page_that_is_itself_a_list(self, app):
        pages = ListPages()
        page = QListWidget()  # Empty, which PyQt makes false, and it's still the page.
        pages.addTab(page, "Fruit")
        pages.resize(400, 300)
        pages.show()
        try:
            QApplication.processEvents()
            calls = []
            page.setFocus = lambda: calls.append("page")
            bar = pages.tabBar()
            bar.hasFocus = lambda: True
            press(bar, Qt.Key.Key_F6)
            assert calls == ["page"]
        finally:
            pages.close()

    @pytest.mark.parametrize("make", [lambda: make_tab_area(9), lambda: make_tab_area(2)], ids=["list", "tabs"])
    def test_destroying_an_area_with_focus_on_its_bar_is_safe(self, app, make):
        """The bar gets FocusOut during the destructor. An exception there would end the process."""
        area = make()
        area.addTab(QLabel("One"), "One")
        area.addTab(QLabel("Two"), "Two")
        area.show()
        area.activateWindow()
        QApplication.processEvents()
        area.tabBar().setFocus()
        QApplication.processEvents()
        assert area.tabBar().hasFocus()
        sip.delete(area)
        QApplication.processEvents()
        assert sip.isdeleted(area)

    @pytest.mark.parametrize("make", [lambda: make_tab_area(9), lambda: make_tab_area(2)], ids=["list", "tabs"])
    def test_an_area_left_open_for_the_garbage_collector_is_safe(self, app, make):
        """CI once stopped dead after a failing test left a ListPages open like this. The destroy
        test above doesn't reproduce that for a list, since calling its tabBar can't raise."""
        area = make()
        area.addTab(QLabel("One"), "One")
        area.addTab(QLabel("Two"), "Two")
        area.show()
        area.activateWindow()
        QApplication.processEvents()
        area.tabBar().setFocus()
        QApplication.processEvents()
        assert area.tabBar().hasFocus()
        del area
        gc.collect()
        QApplication.processEvents()
        for leftover in QApplication.topLevelWidgets():  # In case it wasn't collected after all.
            leftover.close()

    def test_view_keys_on_the_list_act_on_the_table(self, pages_with_tables):
        pages = pages_with_tables
        table = self.table_on(pages, 0)
        press(pages.tabBar(), Qt.Key.Key_Q, ALT)
        assert table._current_view == table.VIEW_QUICK_LIST

    def test_is_tab_bar_knows_the_list_from_any_other(self, pages, app):
        tabs = QTabWidget()
        assert is_tab_bar(pages.tabBar())
        assert is_tab_bar(tabs.tabBar())
        assert not is_tab_bar(QListWidget())
        assert not is_tab_bar(None)

    def test_a_load_doesnt_pull_someone_off_the_list(self, pages, monkeypatch):
        calls = []
        target = QListWidget()
        target.setFocus = lambda: calls.append("target")
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: pages.tabBar()))
        scores._take_focus_after_load(target)
        assert calls == []
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: None))
        scores._take_focus_after_load(target)
        assert calls == ["target"]

    def test_a_tables_own_letters_and_arrows_stay_with_it(self, pages_with_tables):
        pages = pages_with_tables
        view = self.table_on(pages, 0).table_widget
        press(view, Qt.Key.Key_R, PLAIN, "r")
        press(pages, Qt.Key.Key_R, PLAIN, "r")
        press(pages, Qt.Key.Key_Down)
        assert pages.currentIndex() == 0
