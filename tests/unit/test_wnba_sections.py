"""The WNBA's league view has the same sections as other pro leagues, and its own flags (#132)."""
import os
import re
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)


def source(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_the_league_view_offers_its_sections():
    block = re.search(r"def _add_common_sections.*?if self\.league in \[(.*?)\]", source("scores.py"), re.S)
    assert '"WNBA"' in block.group(1)


def test_standings_get_conference_tabs():
    line = re.search(r"if has_divisions and self\.league in \[(.*?)\]", source("scores.py"))
    assert '"WNBA"' in line.group(1)


@pytest.mark.parametrize("flag,action", [("--wnba", "league"), ("--wnba-teams", "teams"), ("--wnba-standings", "standings")])
def test_the_flags_go_to_the_wnba(flag, action):
    pytest.importorskip("PyQt6")
    import main
    with patch.object(sys, "argv", ["scores", flag]):
        assert main.parse_command_line() == {"action": action, "league": "WNBA"}


def test_both_flag_lists_have_them():
    text = source("main.py")
    for flag in ("--wnba", "--wnba-teams", "--wnba-standings"):
        assert text.count(f"'{flag}'") == 2, flag
