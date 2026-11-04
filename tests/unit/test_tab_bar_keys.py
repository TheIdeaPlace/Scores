"""Home, End, arrows that go round and type-ahead find on a real tab bar. Builds Qt objects: CI or
the VM only. Which tab each key picks is in test_tab_keys.py; this is that it reaches the bar."""
import json
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QFocusEvent, QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget, QTabWidget, QVBoxLayout, QWidget  # noqa: E402

import accessible_table  # noqa: E402
from accessible_table import AccessibleTable, _TabBarViewKeys, prepare_table_tabs, tab_labels  # noqa: E402
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
        assert tab_labels(tabs.tabBar()) == ["Info", "Roster", None]

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

    @pytest.mark.parametrize("dialog_class", ["StandingsDialog", "SimpleTeamsDialog"])
    def test_the_college_football_conferences(self, app, rows, dialog_class):
        dialog = getattr(scores, dialog_class)(rows, "NCAAF")
        tabs = dialog.tab_widget
        bar = tabs.tabBar()
        press(bar, Qt.Key.Key_End)
        assert tabs.currentIndex() == tabs.count() - 1
        press(bar, Qt.Key.Key_Right)
        assert tabs.currentIndex() == 0
        type_text(tabs, "sun")
        assert tabs.tabText(tabs.currentIndex()) == "Sun Belt Conference"
        press(bar, Qt.Key.Key_Home)
        assert tabs.currentIndex() == 0

    def test_team_hub_keeps_its_mnemonics_out_of_the_search(self, app):
        # No loading from ESPN when a tab opens.
        with patch.object(scores.TeamHubDialog, "_on_tab_changed"):
            hub = scores.TeamHubDialog({"team_name": "Green Bay Packers", "team_id": "9"}, "NFL")
        tabs = hub.tab_widget
        type_text(tabs, "ro")
        assert tabs.tabText(tabs.currentIndex()) == "R&oster"
