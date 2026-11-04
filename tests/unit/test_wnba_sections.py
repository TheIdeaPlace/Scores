"""The WNBA's league view has the same sections as other pro leagues, and its own flags (#132)."""
import ast
import os
import re
import sys
from types import SimpleNamespace
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


def test_the_standings_list_names_the_wnba_once():
    names = re.search(r'if has_divisions and self\.league in \[("MLB", "NFL", "NBA".*?)\]', source("scores.py")).group(1)
    assert names.count('"WNBA"') == 1


def stat_definitions(league):
    """The real method, read out of scores.py so that nothing here needs Qt."""
    tree = ast.parse(source("scores.py"))
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_get_stat_definitions")
    namespace = {}
    exec(compile(ast.Module([method], []), "scores.py", "exec"), namespace)
    return namespace["_get_stat_definitions"](SimpleNamespace(league=league))


@pytest.mark.parametrize("league", ["NBA", "WNBA", "NCAAM", "NCAAWB"])
def test_basketball_stat_definitions_are_basketball(league):
    definitions = stat_definitions(league)
    assert "PPG (Points Per Game)" in definitions
    assert "Goals" not in definitions


def test_another_league_keeps_the_general_list():
    assert "Goals" in stat_definitions("NCAAH")


def test_nothing_calls_a_conference_a_division():
    """A screen reader heard "Division Standings" and "Teams in Eastern Conference division"."""
    text = source("scores.py")
    for wording in ('"Division Standings"', "between divisions", "{division_name} division"):
        assert wording not in text


@pytest.mark.parametrize("flag,action", [("--wnba", "league"), ("--wnba-teams", "teams"), ("--wnba-standings", "standings")])
def test_the_flags_go_to_the_wnba(flag, action):
    import main
    with patch.object(sys, "argv", ["scores", flag]):
        assert main.determine_startup_params(main.parse_command_line()) == {"action": action, "league": "WNBA"}


def test_both_flag_lists_have_them():
    text = source("main.py")
    for flag in ("--wnba", "--wnba-teams", "--wnba-standings"):
        assert text.count(f"'{flag}'") == 2, flag
