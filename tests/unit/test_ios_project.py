"""The iPhone project file, which two branches can each add to with hand-picked ids.

Git merges them without complaint if both pick the same id, and one file silently becomes
another: test code ended up in the app target that way, which only a Mac build shows.
"""
import re
from pathlib import Path

PROJECT = Path(__file__).parent.parent.parent / "iOS" / "SportsScoresApp" / "SportsScores.xcodeproj" / "project.pbxproj"


def ids_and_names(text):
    """Each `ID /* name */` in the file, as (id, name)."""
    return re.findall(r"\b([0-9A-F]{24}) /\* ([^*]+?) \*/", text)


def test_an_id_means_one_thing():
    names = {}
    for identifier, name in ids_and_names(PROJECT.read_text(encoding="utf-8")):
        names.setdefault(identifier, set()).add(name)
    shared = {identifier: sorted(found) for identifier, found in names.items() if len(found) > 1}
    assert not shared, f"the same id for different things: {shared}"


def test_it_finds_a_collision():
    text = "7E57A0000000000000000050 /* A.swift */\n7E57A0000000000000000050 /* B.swift */"
    assert {name for _, name in ids_and_names(text)} == {"A.swift", "B.swift"}


def test_the_real_file_has_ids_to_check():
    assert len(ids_and_names(PROJECT.read_text(encoding="utf-8"))) > 100
