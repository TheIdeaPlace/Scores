"""Alt+D in the statistics dialog: ESPN's definitions of the statistics on screen (#193).
Builds Qt objects: CI or the VM only."""
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import espn_api  # noqa: E402
import scores  # noqa: E402
import stat_glossary  # noqa: E402
from exceptions import ApiError  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


MLB_GLOSSARY = stat_glossary.glossary(load("byteam_MLB.json"))


def mlb_leaders():
    """Real MLB leaders, with a pitchers' strikeout list as /leaders sends one."""
    data = load("leaders_v3_MLB.json")
    era = next(c for c in data["leaders"]["categories"] if c["name"] == "ERA")
    data["leaders"]["categories"].append({**era, "name": "strikeouts", "displayName": "Strikeouts",
                                          "leaders": [{**leader, "value": 200 - i, "displayValue": str(200 - i)}
                                                      for i, leader in enumerate(era["leaders"])]})
    return espn_api._parse_leaders(data)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def open_dialog(app):
    made = []

    def build(league, stat_type, data):
        with patch.object(scores, "_start_detached_thread"):
            view = scores.StatisticsViewDialog(league, stat_type)
        made.append(view)
        view.show()
        app.processEvents()
        if data is not None:
            view._on_statistics_loaded(data)
            app.processEvents()
        return view

    yield build
    for view in made:
        view.close()
        view.deleteLater()
    app.processEvents()


def definitions_of(view):
    """The definitions dialog Alt+D opens, built but not run."""
    shown = []
    with patch.object(scores.StatDefinitionsDialog, "exec", lambda self: shown.append(self)):
        view._show_stat_definitions()
    dialog = shown[0]
    items = [dialog.definitions_list.item(i).text() for i in range(dialog.definitions_list.count())]
    return dialog, items


def test_player_leaders_get_their_own_categorys_definition(open_dialog):
    view = open_dialog("MLB", "player", {**mlb_leaders(), "glossary": MLB_GLOSSARY})
    dialog, items = definitions_of(view)
    assert dialog.windowTitle() == "MLB Player Statistics Definitions"
    assert "Strikeouts: The number of times the pitcher struck out a batter." in items
    assert any(item.startswith("Earned Run Average: The average number of runs a pitcher yields") for item in items)
    assert len(items) == len(view._stat_infos)
    assert dialog.definitions_list.currentRow() == 0
    assert dialog.definitions_list.accessibleName() == "Statistics Definitions"


def test_team_statistics_use_the_glossary_they_came_with(open_dialog):
    data = load("byteam_MLB.json")
    stats = espn_api._parse_team_stats("MLB", "baseball/mlb", data)
    view = open_dialog("MLB", "team", stats)
    dialog, items = definitions_of(view)
    assert dialog.windowTitle() == "MLB Team Statistics Definitions"
    batting = next(item for item in items if item.startswith("Strikeouts (Batting)"))
    pitching = next(item for item in items if item.startswith("Strikeouts (Pitching)"))
    assert batting.endswith("The number of times a player strikes out.")
    assert pitching.endswith("The number of times the pitcher struck out a batter.")


def test_definitions_that_couldnt_be_had_say_so(open_dialog):
    view = open_dialog("MLB", "player", {**mlb_leaders(), "glossary": None})
    assert definitions_of(view)[1] == [stat_glossary.NOT_LOADED]


def test_before_anything_has_loaded_there_is_nothing_to_define(open_dialog):
    view = open_dialog("MLB", "player", None)
    assert definitions_of(view)[1] == [stat_glossary.NOTHING_SHOWN]


def test_soccer_says_espn_has_none_for_each(open_dialog):
    data = {"player_stats": [{"category": "Goals", "stats": [
        {"player_name": "A", "team": "B", "value": "3", "stat_name": "Goals"}]}], "team_stats": [], "glossary": {}}
    view = open_dialog("EPL", "player", data)
    assert definitions_of(view)[1] == ["Goals: No definition from ESPN."]


class TestTheLoader:
    def run(self, app, stat_type, **services):
        loader = scores.StatisticsLoader("MLB", stat_type)
        got = []
        loader.data_loaded.connect(got.append)
        loader.error_occurred.connect(lambda message: got.append(("error", message)))
        with patch.multiple(scores.ApiService, **services):
            loader.run()
        return got

    def test_player_leaders_come_with_the_glossary(self, app):
        got = self.run(app, "player", get_player_statistics=lambda league: mlb_leaders(),
                       get_stat_glossary=lambda league: MLB_GLOSSARY)
        assert got[0]["glossary"] == MLB_GLOSSARY
        assert got[0]["player_stats"]

    def test_the_glossary_failing_leaves_the_leaders(self, app):
        def fail(league):
            raise ApiError("ESPN isn't providing these right now. Try again in a minute.")

        got = self.run(app, "player", get_player_statistics=lambda league: mlb_leaders(), get_stat_glossary=fail)
        assert got[0]["player_stats"] and got[0]["glossary"] is None

    def test_no_leaders_asks_for_no_glossary(self, app):
        asked = []
        got = self.run(app, "player", get_player_statistics=lambda league: {"player_stats": [], "team_stats": []},
                       get_stat_glossary=lambda league: asked.append(league) or {})
        assert asked == [] and "glossary" not in got[0]
