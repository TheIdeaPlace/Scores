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


def method(name, **names):
    """A real method, read out of scores.py so that nothing here needs Qt."""
    tree = ast.parse(source("scores.py"))
    node = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = dict(names)
    exec(compile(ast.Module([node], []), "scores.py", "exec"), namespace)
    return namespace[name]


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


class InfoList:
    def __init__(self):
        self.rows = []

    def clear(self):
        self.rows = []

    def addItem(self, text):
        self.rows.append(text)

    def setCurrentRow(self, row):
        pass


def info_rows(info):
    dialog = SimpleNamespace(info_list=InfoList())
    method("_on_info_loaded")(dialog, info)
    return dialog.info_list.rows


def test_a_record_reads_overall():
    assert "Record (Overall): 33-11" in info_rows({"name": "Lynx", "record_overall": "33-11"})


def test_a_college_record_with_its_postseason_left_out_says_so():
    rows = info_rows({"name": "Michigan", "record_overall": "31-3", "record_regular_season_only": True})
    assert "Record (Regular Season): 31-3" in rows
    assert not any("Overall" in row for row in rows)


def test_a_failure_says_the_record_is_not_available():
    assert "Record not available right now" in info_rows({"name": "Lynx", "record_unavailable": True})


def test_a_team_with_no_record_says_nothing_about_it():
    assert info_rows({"name": "Lynx", "record_unavailable": False}) == ["Team: Lynx"]


def test_a_standings_error_puts_the_window_title_back():
    titles = []
    warnings = []
    dialog = SimpleNamespace(parent_app=SimpleNamespace(update_window_title=titles.append),
                             _title_items=lambda: ["WNBA"])
    box = SimpleNamespace(warning=lambda *args: warnings.append(args))
    method("_on_standings_data_error", QMessageBox=box)(dialog, "Try again")
    assert titles == [["WNBA"]]
    assert warnings == [(dialog, "Standings", "Try again")]
