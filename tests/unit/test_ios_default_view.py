"""Every iPhone table screen starts in the "Default view" setting (issue 90: 13 of 18 didn't).

A screen with a view mode menu keeps its mode in `@State`; that state has to start from
`ViewMode.savedDefault()`, never a fixed mode. Swift only builds on a Mac, so this reads
the source; SportsScoresTests/ViewModeDefaultTests.swift checks savedDefault itself.
"""
import re
from pathlib import Path

APP = Path(__file__).parent.parent.parent / "iOS" / "SportsScoresApp" / "SportsScores"
# `@State [any modifiers] var name: ViewMode ...`, at the start of a line, so not a comment.
TYPED = re.compile(r"^[ \t]*@State\b[^\n]*?\bvar\s+(\w+)\s*:\s*ViewMode\b([^\n]*)", re.MULTILINE)
# `@State ... var name = ViewMode.quickList` or `= .quickList` with no type written.
UNTYPED = re.compile(r"^[ \t]*@State\b[^\n]*?\bvar\s+(\w+)\s*=\s*(?:ViewMode)?\.(table|quickList|fullList)\b",
                     re.MULTILINE)


def view_mode_states():
    for path in sorted(APP.rglob("*.swift")):
        text = path.read_text(encoding="utf-8")
        for name, rest in TYPED.findall(text):
            yield path, name, rest.strip()
        for name, mode in UNTYPED.findall(text):
            yield path, name, f"= .{mode}"


def test_there_are_screens_to_check():
    assert len(list(view_mode_states())) >= 18


def test_every_screen_starts_in_the_default_view():
    fixed = [(path.name, name, rest) for path, name, rest in view_mode_states()
             # A state with no initial value is set in init, from the screen that opened it.
             if rest and rest != "= .savedDefault()"]
    assert not fixed, f"screens that ignore the Default view setting: {fixed}"


def test_a_screen_set_in_init_is_handed_a_mode():
    for path, name, rest in view_mode_states():
        if not rest:
            assert f"self._{name} = State(initialValue:" in path.read_text(encoding="utf-8"), path.name


def test_the_scan_catches_a_fixed_mode():
    for line in ("    @State fileprivate var viewMode: ViewMode = .quickList",
                 "    @State private var viewMode = ViewMode.table",
                 "    @State var mode = .fullList"):
        assert TYPED.findall(line) or UNTYPED.findall(line), line
    assert not TYPED.findall("    /// `@State private var viewMode: ViewMode = .savedDefault()`")
