"""Pure: which tab a key press on a tab bar goes to. No Qt, so it's tested on any platform.

Every function takes the tabs as a list of labels, one per tab, with None for a tab that's
disabled or hidden. Those are skipped everywhere. `tab_labels` in accessible_table.py builds
the list from a real tab bar.
"""
import re
import time
from typing import Callable, List, Optional

# How long type-ahead waits for the next key, in double-click times. Windows ties its own list
# searches to the double-click time, and that's the setting Kelly remembered. Microsoft's WPF
# TextSearch.cs records what the system list box does, 4 times the double-click time, then says
# "4 * DoubleClickSpeed seems too slow for the search" and uses 2. At the Windows default of
# 500 ms that's a second, and someone who slows their double-click down gets longer here too.
# Qt's own keyboardInputInterval isn't an alternative: its Windows plugin doesn't implement the
# hint (qwindowsintegration.cpp), so it's a fixed 400 ms whatever Windows is set to.
TYPE_AHEAD_DOUBLE_CLICK_TIMES = 2

# Kelly's rule: "if an area has say more than seven or eight tabs, it is probably better as a
# list." A long row of tabs is slow to go through and has no sense of where you are in it.
MAX_TABS = 8

Labels = List[Optional[str]]


def use_list(count: int) -> bool:
    """Whether a tab area of this many pages should be a list rather than tabs."""
    return count > MAX_TABS


def group_noun(names: List[str]) -> str:
    """What to call a list of a league's groups, from their names: "Conferences" if any is one.

    ESPN's names say so: "Big Ten Conference" and "Eastern Conference" are, and the NBA's
    "Eastern Conference Atlantic" is a division inside one. Some conferences don't say, such as
    Patriot League and Hockey East, but a league has at least one that does.
    """
    return "Conferences" if any(name.endswith("Conference") for name in names) else "Divisions"


def tab_label(text: str) -> str:
    """A tab's text as it's heard: "R&oster" is Roster, and "A&&M" is A&M."""
    return re.sub(r"&(.?)", r"\1", text)


def wrapped_tab(labels: Labels, current: int, step: int) -> Optional[int]:
    """The next usable tab `step` (1 or -1) away, going round past either end.

    Comes back to `current` if it's the only usable one, and None if there are none.
    """
    count = len(labels)
    for distance in range(1, count + 1):
        index = (current + step * distance) % count
        if labels[index] is not None:
            return index
    return None


def first_tab(labels: Labels) -> Optional[int]:
    """The first usable tab, or None."""
    return next((i for i, label in enumerate(labels) if label is not None), None)


def last_tab(labels: Labels) -> Optional[int]:
    """The last usable tab, or None."""
    return next((i for i in range(len(labels) - 1, -1, -1) if labels[i] is not None), None)


class TabTypeAhead:
    """Type-ahead find, the way a Windows list does it.

    One letter goes to the next tab starting with it, after the current one and round past the
    end. The same letter again goes on to the next such tab. Different letters typed quickly
    build a prefix, which can carry on through spaces and punctuation: "sun" reaches Sun Belt,
    and "ohio bobcats r" reaches Ohio Bobcats Receiving. No match does nothing, and starts over.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._typed = ""
        self._last_key = 0.0

    def reset(self) -> None:
        self._typed = ""

    def _drop_if_stale(self, window_ms: int) -> None:
        if self._typed and (self.clock() - self._last_key) * 1000 > window_ms:
            self.reset()

    def accepts(self, char: str, window_ms: int) -> bool:
        """A search starts on a letter or a digit, and anything printable continues one."""
        self._drop_if_stale(window_ms)
        return char.isalnum() or (bool(self._typed) and char.isprintable())

    def press(self, char: str, labels: Labels, current: int, window_ms: int) -> Optional[int]:
        """The tab this key moves to, which may be the current one, or None for no match."""
        self._drop_if_stale(window_ms)
        typed = self._typed + char.casefold()
        repeating = len(set(typed)) == 1
        prefix = typed[0] if repeating else typed
        # A growing prefix can still be the tab we're on. A new letter or a repeat moves on,
        # and only ends up back here if this is the only tab starting with it.
        start = current + 1 if repeating else current
        count = len(labels)
        for distance in range(count):
            index = (start + distance) % count
            label = labels[index]
            if label is not None and label.casefold().startswith(prefix):
                self._typed = typed
                self._last_key = self.clock()
                return index
        self.reset()
        return None
