"""A blank row looks like spacing, and sounds like a stop that says "blank" (NVDA: "list item,
blank"), which also shows up in a refresh and at the end of the list. Lists have no blank rows."""
import os
import re

SCORES = os.path.join(os.path.dirname(__file__), "..", "..", "scores.py")
BLANK_ROW = re.compile(r'''addItem\(\s*(QListWidgetItem\(\s*)?("\s*"|'\s*')\s*\)''')


def test_no_list_gets_a_blank_row():
    with open(SCORES, encoding="utf-8") as f:
        found = [f"line {n}: {line.strip()}" for n, line in enumerate(f, 1) if BLANK_ROW.search(line)]
    assert not found, found


def test_the_check_can_see_them():
    for line in ('self.a.addItem("")', "self.a.addItem(QListWidgetItem(''))", 'b.addItem(" ")'):
        assert BLANK_ROW.search(line), line
    assert not BLANK_ROW.search('self.a.addItem("Venue")')
    assert not BLANK_ROW.search('self.a.addItem("  ".join(parts))')
