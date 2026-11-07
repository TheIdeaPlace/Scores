"""stat_glossary: ESPN's definitions keyed by category and name (#193), held to the grid the iPhone's
StatGlossary.swift is held to, and to what tools/stat_categories.py found (docs/stat-categories.csv)."""
import csv
import json
import os

import pytest

import stat_glossary as sg
from team_stats import parse_team_stats, team_stat_lists

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
GRID_PATH = os.path.join(FIXTURES, "stat_glossary_grid.json")


def load(name):
    with open(os.path.join(FIXTURES, "espn", name), encoding="utf-8") as f:
        return json.load(f)


with open(GRID_PATH, encoding="utf-8") as _f:
    GRID = json.load(_f)


# --- The shared grid ------------------------------------------------------------------------------

def test_the_leader_table_is_the_grids():
    assert {sport: {key: list(stat) for key, stat in table.items()} for sport, table in sg.LEADER_STATS.items()} \
        == GRID["leader_stats"]


@pytest.mark.parametrize("fixture", sorted(GRID["glossaries"]))
def test_the_glossary_of_a_real_payload_is_the_grids(fixture):
    assert sg.glossary(load(fixture)) == GRID["glossaries"][fixture]


@pytest.mark.parametrize("case", GRID["cases"], ids=[case["name"] for case in GRID["cases"]])
def test_each_lookup_gives_the_grids_answer(case):
    found = sg.glossary(load(case["fixture"]))
    assert sg.definition(found, case["sport"], case["key"], case["kind"] == "team") == case["definition"]


def test_the_grid_covers_every_fixture_it_names():
    assert {case["fixture"] for case in GRID["cases"]} == set(GRID["glossaries"])


# --- The Strikeouts mix-up, and the other names two categories share --------------------------------

def test_pitchers_strikeout_leaders_get_the_pitchers_definition():
    found = sg.glossary(load("byteam_MLB.json"))
    leaders = sg.definition(found, "baseball", "strikeouts", team=False)
    assert "pitcher" in leaders
    assert leaders == sg.definition(found, "baseball", "pitching.strikeouts", team=True)
    assert leaders != sg.definition(found, "baseball", "batting.strikeouts", team=True)


def test_interception_leaders_are_a_defenses():
    found = sg.glossary(load("byteam_NFL.json"))
    assert "thrown" not in sg.definition(found, "football", "interceptions", team=False)
    assert "thrown" in sg.definition(found, "football", "passing.interceptions", team=True)


def test_sack_leaders_dont_get_the_sacks_a_passer_took():
    """byteam's only sacks are passing's, the ones a team took. A defense's leaders have none."""
    found = sg.glossary(load("byteam_NFL.json"))
    assert sg.definition(found, "football", "passing.sacks", team=True)
    assert sg.definition(found, "football", "sacks", team=False) is None


@pytest.mark.parametrize("fixture", ["byteam_MLB.json", "byteam_NFL.json", "byteam_NCAAF.json", "byteam_NBA.json",
                                     "byteam_NHL.json", "byteam_WNBA.json", "byteam_NCAAM.json", "byteam_NCAAWB.json"])
def test_a_name_in_two_categories_keeps_each_ones_definition(fixture):
    """Every stat name byteam has in more than one category, with different text, is told apart."""
    data = load(fixture)
    found = sg.glossary(data)
    by_name = {}
    for key, text in found.items():
        category, name = key.split(".", 1)
        by_name.setdefault(name, {})[category] = text
    for name, texts in by_name.items():
        for category, text in texts.items():
            assert sg.definition(found, "", f"{category}.{name}", team=True) == text


def test_the_names_shared_with_different_definitions_are_the_known_ones():
    """What #193 found. A new one is worth a look: a leader of that name may need its category."""
    shared = {}
    for fixture in ("byteam_MLB.json", "byteam_NFL.json", "byteam_NBA.json", "byteam_NHL.json"):
        by_name = {}
        for key, text in sg.glossary(load(fixture)).items():
            category, name = key.split(".", 1)
            by_name.setdefault(name, {})[category] = text
        shared[fixture] = sorted(name for name, texts in by_name.items() if len(set(texts.values())) > 1)
    assert shared == {
        "byteam_MLB.json": ["hits", "homeRuns", "strikeouts", "walks"],
        "byteam_NFL.json": ["interceptions", "puntReturnYards", "puntReturns"],
        "byteam_NBA.json": [],
        "byteam_NHL.json": [],
    }


# --- The leader table against what tools/stat_categories.py found ----------------------------------

def leader_rows():
    with open(os.path.join(ROOT, "docs", "stat-categories.csv"), encoding="utf-8-sig") as f:
        return [row for row in csv.DictReader(f)
                if row["kind"] == "player_leader" and row["source"].split("; ")[0] == "leaders"]


SPORTS = {"MLB": "baseball", "NFL": "football", "NCAAF": "football", "NBA": "basketball", "WNBA": "basketball",
          "NCAAM": "basketball", "NCAAWB": "basketball", "NHL": "hockey"}


def test_every_leader_category_the_apps_read_is_in_the_table():
    missing = sorted({(row["league"], row["key"]) for row in leader_rows()
                      if row["key"] not in sg.LEADER_STATS[SPORTS[row["league"]]]})
    assert missing == []


def test_each_leader_is_in_the_category_stat_categories_found():
    """Its `group` is where a leading player's own statistics have the stat. WNBA PER had no leader
    with a number, so the tool couldn't tell; basketball's other leagues say general."""
    wrong = []
    for row in leader_rows():
        if row["group"] == "leaders":
            continue
        category, _ = sg.LEADER_STATS[SPORTS[row["league"]]][row["key"]]
        if category.lower() != row["group"].lower():
            wrong.append((row["league"], row["key"], row["group"], category))
    assert wrong == []


# --- The glossary from odd payloads ----------------------------------------------------------------

@pytest.mark.parametrize("payload", [None, [], "text", {}, {"categories": None}, {"categories": "x"},
                                     {"categories": [None, "x", {"name": None}]},
                                     {"categories": [{"name": "batting", "names": ["a"]}]},
                                     {"categories": [{"name": "batting", "names": None, "descriptions": ["x"]}]}])
def test_a_payload_with_no_glossary_is_empty(payload):
    assert sg.glossary(payload) == {}


def test_only_text_that_says_something_is_a_definition():
    payload = {"categories": [
        {"name": "Batting", "names": ["a", "b", "c", None, "e", "f"],
         "descriptions": ["  The   first.\n", "", None, "orphan", 5, "  "]},
        {"name": "batting", "names": ["a", "b"], "descriptions": ["Later.", "The second."]},
    ]}
    assert sg.glossary(payload) == {"batting.a": "The first.", "batting.b": "The second."}


def test_a_category_is_found_in_either_case():
    found = sg.glossary({"categories": [{"name": "defensiveinterceptions", "names": ["interceptions"],
                                         "descriptions": ["Picks."]}]})
    assert sg.definition(found, "football", "interceptions", team=False) == "Picks."
    assert sg.definition(found, "football", "defensiveInterceptions.interceptions", team=True) == "Picks."


@pytest.mark.parametrize("key", [None, "", ".", "batting", "batting.", ".strikeouts", "opponent.batting",
                                 "x.batting.strikeouts", "opponent.batting.strikeouts.extra"])
def test_a_team_key_that_isnt_one_has_no_definition(key):
    found = {"batting.strikeouts": "K.", "opponent.batting": "No."}
    assert sg.definition(found, "baseball", key, team=True) is None


# --- What the Windows dialog says ------------------------------------------------------------------

def test_the_dialog_lines_for_player_leaders():
    found = sg.glossary(load("byteam_MLB.json"))
    stats = [{"name": "Strikeouts", "key": "strikeouts", "type": "player"},
             {"name": "Wins Above Replacement", "key": "WARBR", "type": "player"},
             {"name": "Something", "key": None, "type": "player"}]
    assert sg.definition_lines(stats, found, "baseball") == [
        "Strikeouts: The number of times the pitcher struck out a batter.",
        "Wins Above Replacement: No definition from ESPN.",
        "Something: No definition from ESPN.",
    ]


def test_the_dialog_lines_for_team_statistics_from_the_real_parser():
    data = load("byteam_NFL.json")
    found = sg.glossary(data)
    lists = team_stat_lists(parse_team_stats(data, "football"))
    lines = dict(zip([item["name"] for item in lists], sg.definition_lines(lists, found, "football")))
    sacks = next(name for name in lines if name.startswith("Sacks Taken (Passing)"))
    assert lines[sacks].endswith(": The total number of sacks.")
    opponent = next(name for name in lines if name.startswith("Passing Yards (Opponent"))
    assert lines[opponent] == f"{opponent}: {sg.OPPONENT_NOTE}The total passing yards."
    assert all(line.startswith(f"{name}: ") for name, line in lines.items())


def test_every_team_statistic_on_screen_has_its_key():
    for fixture, sport in (("byteam_MLB.json", "baseball"), ("byteam_NBA.json", "basketball"),
                           ("byteam_NFL.json", "football"), ("byteam_NHL.json", "hockey")):
        data = load(fixture)
        found = sg.glossary(data)
        lists = team_stat_lists(parse_team_stats(data, sport))
        assert lists and all(item["key"] for item in lists), fixture
        defined = [item for item in lists if sg.definition(found, sport, item["key"], team=True)]
        # Nearly all have one: a column with a name and no definition is rare.
        assert len(defined) * 10 >= len(lists) * 9, fixture


def test_the_mlb_team_lists_tell_the_two_strikeouts_apart():
    data = load("byteam_MLB.json")
    found = sg.glossary(data)
    lists = {item["name"]: item for item in team_stat_lists(parse_team_stats(data, "baseball"))}
    batting = next(item for name, item in lists.items() if name.startswith("Strikeouts (Batting"))
    pitching = next(item for name, item in lists.items() if name.startswith("Strikeouts (Pitching"))
    assert (batting["key"], pitching["key"]) == ("batting.strikeouts", "pitching.strikeouts")
    assert "pitcher" in sg.definition(found, "baseball", pitching["key"], team=True)
    assert "pitcher" not in sg.definition(found, "baseball", batting["key"], team=True)


def test_still_loading_says_so_before_anything_else():
    stats = [{"name": "Strikeouts", "key": "strikeouts", "type": "player"}]
    assert sg.definition_lines(stats, None, "baseball", still_loading=True) == [sg.STILL_LOADING]
    assert sg.definition_lines([], None, "baseball", still_loading=True) == [sg.STILL_LOADING]


def test_nothing_on_screen_says_so():
    assert sg.definition_lines([], {"a.b": "c"}, "baseball") == [sg.NOTHING_SHOWN]


def test_definitions_that_couldnt_be_had_say_so_once():
    stats = [{"name": "Strikeouts", "key": "strikeouts", "type": "player"}] * 3
    assert sg.definition_lines(stats, None, "baseball") == [sg.NOT_LOADED]


def test_a_league_espn_has_no_definitions_for_says_none_for_each():
    stats = [{"name": "Goals", "key": "goalsLeaders", "type": "player"},
             {"name": "Assists", "key": "assistsLeaders", "type": "player"}]
    assert sg.definition_lines(stats, {}, "soccer") == ["Goals: No definition from ESPN.",
                                                       "Assists: No definition from ESPN."]
