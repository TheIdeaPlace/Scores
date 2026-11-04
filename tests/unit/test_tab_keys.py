"""Which tab a key goes to, and that every tab widget gets those keys. No Qt: safe anywhere."""
import ast
from pathlib import Path

import pytest

from tab_keys import TabTypeAhead, first_tab, last_tab, tab_label, wrapped_tab

REPO = Path(__file__).resolve().parents[2]
WINDOW_MS = 1000
CONFERENCES = [
    "Southeastern Conference", "Big Ten Conference", "Big 12 Conference", "Sun Belt Conference",
    "Big Sky Conference", "Mountain West Conference", "Southland Conference",
]
BOX = ["Ohio Bobcats Passing", "Ohio Bobcats Receiving", "Ohio Bobcats Defense", "Akron Zips Passing"]


class Clock:
    now = 100.0

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms / 1000


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def search(clock):
    return TabTypeAhead(clock=clock)


def type_keys(search, keys, labels, current=0, window_ms=WINDOW_MS):
    """Each key's result, moving as the bar does when there is one."""
    seen = []
    for key in keys:
        target = search.press(key, labels, current, window_ms)
        seen.append(target)
        if target is not None:
            current = target
    return seen


class TestLabels:
    @pytest.mark.parametrize("text,heard", [
        ("Roster", "Roster"), ("R&oster", "Roster"), ("&Info", "Info"), ("A&&M", "A&M"), ("End&", "End"), ("", ""),
    ])
    def test_a_mnemonic_is_not_part_of_the_name(self, text, heard):
        assert tab_label(text) == heard


class TestMoves:
    @pytest.mark.parametrize("current,step,expected", [
        (0, 1, 1), (1, -1, 0), (2, 1, 0), (0, -1, 2),
    ])
    def test_arrows_go_round_past_both_ends(self, current, step, expected):
        assert wrapped_tab(["a", "b", "c"], current, step) == expected

    def test_arrows_skip_unusable_tabs_going_round(self):
        labels = [None, "b", None, "d", None]
        assert wrapped_tab(labels, 3, 1) == 1
        assert wrapped_tab(labels, 1, -1) == 3
        assert wrapped_tab(labels, 1, 1) == 3

    def test_arrows_stay_on_the_only_usable_tab(self):
        assert wrapped_tab([None, "b", None], 1, 1) == 1

    def test_arrows_have_nowhere_to_go_with_no_usable_tab(self):
        assert wrapped_tab([None, None], 0, 1) is None
        assert wrapped_tab([], 0, 1) is None

    def test_arrows_start_from_a_bar_with_no_current_tab(self):
        assert wrapped_tab(["a", "b"], -1, 1) == 0

    def test_first_and_last_skip_unusable_tabs(self):
        labels = [None, "b", "c", None]
        assert first_tab(labels) == 1
        assert last_tab(labels) == 2

    def test_first_and_last_of_nothing(self):
        assert first_tab([None]) is None
        assert last_tab([]) is None


class TestTypeAhead:
    def test_a_letter_goes_to_the_next_tab_after_the_current_one(self, search):
        assert search.press("s", CONFERENCES, 1, WINDOW_MS) == 3

    def test_a_letter_goes_round_past_the_end(self, search):
        assert search.press("s", CONFERENCES, 6, WINDOW_MS) == 0

    def test_the_same_letter_cycles_through_the_tabs_starting_with_it(self, search):
        assert type_keys(search, "bbbbb", CONFERENCES) == [1, 2, 4, 1, 2]

    def test_different_letters_build_a_prefix(self, search):
        assert type_keys(search, "su", CONFERENCES) == [3, 3]
        search.reset()
        assert type_keys(search, "sun", CONFERENCES, current=3) == [6, 3, 3]

    def test_a_prefix_can_stay_on_the_tab_it_is_on(self, search):
        assert type_keys(search, "so", CONFERENCES, current=6) == [0, 0]

    def test_a_shared_first_word_needs_the_prefix_and_its_space(self, search):
        assert type_keys(search, "ohio bobcats r", BOX, current=3)[-1] == 1

    def test_digits_and_punctuation_carry_a_prefix(self, search):
        assert type_keys(search, "big 1", CONFERENCES)[-1] == 2

    def test_case_does_not_matter(self, search):
        assert search.press("B", CONFERENCES, 0, WINDOW_MS) == 1
        assert search.press("I", CONFERENCES, 1, WINDOW_MS) == 1

    def test_the_only_tab_with_that_letter_stays_put(self, search):
        assert search.press("m", CONFERENCES, 5, WINDOW_MS) == 5

    def test_no_match_does_nothing_and_starts_over(self, search):
        assert search.press("s", CONFERENCES, 0, WINDOW_MS) == 3
        assert search.press("x", CONFERENCES, 3, WINDOW_MS) is None
        # Fresh: this is "m", not "sxm".
        assert search.press("m", CONFERENCES, 3, WINDOW_MS) == 5

    def test_a_pause_starts_a_new_search(self, search, clock):
        assert search.press("s", CONFERENCES, 0, WINDOW_MS) == 3
        clock.advance(WINDOW_MS + 1)
        assert search.press("u", CONFERENCES, 3, WINDOW_MS) is None

    def test_a_pause_right_at_the_limit_keeps_the_search(self, search, clock):
        assert search.press("s", CONFERENCES, 0, WINDOW_MS) == 3
        clock.advance(WINDOW_MS)
        assert search.press("u", CONFERENCES, 3, WINDOW_MS) == 3

    def test_the_limit_is_between_keys_not_for_the_whole_search(self, search, clock):
        for key in "big":
            assert search.press(key, CONFERENCES, 0, WINDOW_MS) == 1
            clock.advance(WINDOW_MS - 1)
        assert search.press(" ", CONFERENCES, 1, WINDOW_MS) == 1

    def test_after_a_pause_the_same_letter_moves_on(self, search, clock):
        assert search.press("b", CONFERENCES, 0, WINDOW_MS) == 1
        clock.advance(WINDOW_MS + 1)
        assert search.press("b", CONFERENCES, 1, WINDOW_MS) == 2

    def test_unusable_tabs_never_match(self, search):
        labels = ["Big Ten", None, "Big Sky", None]
        assert type_keys(search, "bb", labels) == [2, 0]

    def test_no_usable_tab_is_no_match(self, search):
        assert search.press("b", [None, None], 0, WINDOW_MS) is None

    def test_no_tabs_at_all_is_no_match(self, search):
        assert search.press("b", [], -1, WINDOW_MS) is None

    def test_reset_starts_over(self, search):
        search.press("s", CONFERENCES, 0, WINDOW_MS)
        search.reset()
        assert search.press("b", CONFERENCES, 3, WINDOW_MS) == 4

    def test_a_search_starts_on_a_letter_or_digit(self, search):
        assert search.accepts("s", WINDOW_MS)
        assert search.accepts("1", WINDOW_MS)
        assert not search.accepts(" ", WINDOW_MS)
        assert not search.accepts("-", WINDOW_MS)

    def test_control_characters_are_never_part_of_a_search(self, search):
        search.press("s", CONFERENCES, 0, WINDOW_MS)
        assert search.accepts(" ", WINDOW_MS)
        assert not search.accepts("\r", WINDOW_MS)
        assert not search.accepts("\x1b", WINDOW_MS)

    def test_a_space_after_a_pause_is_not_part_of_a_search(self, search, clock):
        search.press("s", CONFERENCES, 0, WINDOW_MS)
        clock.advance(WINDOW_MS + 1)
        assert not search.accepts(" ", WINDOW_MS)

    def test_the_default_clock_is_a_real_one(self):
        assert TabTypeAhead().press("b", CONFERENCES, 0, WINDOW_MS) == 1


class TestEveryTabWidgetGetsTheKeys:
    @staticmethod
    def _bodies(tree):
        """Every statement list in the file, wherever it's nested."""
        for node in ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                statements = getattr(node, field, None)
                if isinstance(statements, list):
                    yield statements

    @staticmethod
    def _is_tab_widget_made(statement):
        value = getattr(statement, "value", None)
        return (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "QTabWidget")

    @staticmethod
    def _prepares(statement, target):
        value = getattr(statement, "value", None)
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "prepare_table_tabs"):
            return False
        return ast.dump(value.args[0], annotate_fields=False) == target

    @pytest.mark.parametrize("path", sorted(REPO.glob("*.py")), ids=lambda p: p.name)
    def test_each_tab_widget_is_prepared_right_after_it_is_made(self, path):
        source = path.read_text(encoding="utf-8")
        if "QTabWidget(" not in source:
            return
        tree = ast.parse(source)
        for statements in self._bodies(tree):
            for position, statement in enumerate(statements):
                if not self._is_tab_widget_made(statement):
                    continue
                target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
                name = ast.dump(target, annotate_fields=False).replace("Store()", "Load()")
                assert self._prepares(statements[position + 1], name), (
                    f"{path.name}:{statement.lineno} makes a QTabWidget without calling prepare_table_tabs "
                    "on the next line, so its bar has none of the app's keys")

    def test_the_scan_finds_the_tab_widgets_in_scores(self):
        tree = ast.parse((REPO / "scores.py").read_text(encoding="utf-8"))
        made = sum(self._is_tab_widget_made(s) for body in self._bodies(tree) for s in body)
        assert made >= 15

    def test_nothing_builds_a_bare_tab_bar(self):
        for path in REPO.glob("*.py"):
            assert "QTabBar(" not in path.read_text(encoding="utf-8"), path.name
