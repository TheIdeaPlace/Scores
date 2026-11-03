"""build_box_tables against real ESPN payloads (tests/fixtures/espn)."""
import glob
import json
import os

import pytest

from box_score import DID_NOT_PLAY, TOTALS, build_box_tables

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "espn")


def load(prefix):
    path = glob.glob(os.path.join(FIXTURES, f"box_{prefix}_*.json"))[0]
    with open(path, encoding="utf-8") as f:
        return json.load(f)["boxscore"]


def by_title(tables):
    return {t.title: t for t in tables}


@pytest.mark.parametrize("league", ["NBA", "WNBA", "NCAAM", "NCAAWB", "NFL", "NCAAF", "NHL", "MLB"])
def test_every_table_has_rows_and_no_unknown_tab(league):
    tables = build_box_tables(load(league))
    assert len(tables) >= 3
    for table in tables:
        assert table.rows, table.title
        assert "Unknown" not in table.title
        assert all(len(row) <= len(table.headers) for row in table.rows), table.title


@pytest.mark.parametrize("league", ["NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "NFL", "NCAAF", "MLB"])
def test_every_player_espn_lists_is_shown(league):
    box = load(league)
    tables = by_title(build_box_tables(box))
    for team in box["players"]:
        name = team["team"]["displayName"]
        shown = {row[0] for title, t in tables.items() if title.startswith(name) for row in t.rows}
        for group in team["statistics"]:
            for athlete in group.get("athletes", []):
                info = athlete["athlete"]
                assert (info.get("displayName") or info.get("shortName")).strip() in shown


def test_inactive_basketball_players_who_played_are_kept():
    """`active` means on the floor at the end. It hid about half of those who played."""
    box = load("NBA")
    group = box["players"][0]["statistics"][0]
    dropped_before = [a for a in group["athletes"] if not a.get("active", True) and a.get("stats")]
    assert dropped_before, "fixture should exercise the old filter"
    table = build_box_tables(box)[0]
    names = [row[0] for row in table.rows]
    for athlete in dropped_before:
        assert athlete["athlete"]["displayName"] in names


def test_basketball_table_shape():
    box = load("NCAAM")
    team = box["players"][0]["team"]["displayName"]
    table = by_title(build_box_tables(box))[f"{team} Players"]
    assert table.headers[:4] == ["Player", "Pos", "MIN", "PTS"]
    assert table.rows[-1][0] == TOTALS
    assert table.rows[-1][1] == ""
    assert table.rows[-1][3] == box["players"][0]["statistics"][0]["totals"][1]


def test_did_not_play_row_is_short_not_blank():
    box = {"players": [{"team": {"displayName": "A"}, "statistics": [{
        "names": ["MIN", "PTS"],
        "athletes": [
            {"active": False, "stats": ["10", "2"], "athlete": {"displayName": "Plays", "position": {"abbreviation": "G"}}},
            {"active": False, "stats": [], "didNotPlay": True, "athlete": {"shortName": "J. Loubens"}},
        ]}]}]}
    table = build_box_tables(box)[0]
    assert table.rows == [["Plays", "G", "10", "2"], ["J. Loubens", "", DID_NOT_PLAY]]


def test_football_groups_use_labels_and_have_names():
    box = load("NFL")
    team = box["players"][0]["team"]["displayName"]
    tables = by_title(build_box_tables(box))
    passing = tables[f"{team} Passing"]
    assert passing.headers[0] == "Player"
    assert "Pos" not in passing.headers  # football payloads carry no positions
    assert passing.headers[1] == box["players"][0]["statistics"][0]["labels"][0]
    assert f"{team} Kick Returns" in tables or f"{team} Punting" in tables
    assert f"{team} Defense" in tables


def test_hockey_groups():
    box = load("NHL")
    team = box["players"][0]["team"]["displayName"]
    tables = by_title(build_box_tables(box))
    assert f"{team} Forwards" in tables
    assert f"{team} Goalies" in tables
    assert f"{team} Skaters" not in tables  # ESPN sends this group empty


def test_team_stats_compare_both_teams_flat():
    box = load("NFL")
    tables = by_title(build_box_tables(box))
    team_stats = tables["Team Stats"]
    assert team_stats.headers == ["Statistic"] + [t["team"]["displayName"] for t in box["teams"]]
    first = box["teams"][0]["statistics"][0]
    row = next(r for r in team_stats.rows if r[0] == first["label"])
    assert row[1] == first["displayValue"]
    labels = [r[0] for r in team_stats.rows]
    assert len(labels) == len(set(labels)), "ESPN repeats NFL interceptions; show it once"


def test_baseball_keeps_categories():
    box = load("MLB")
    titles = [t.title for t in build_box_tables(box)]
    assert any("Batting" in t for t in titles)
    assert any(t.startswith("Team ") for t in titles)


@pytest.mark.parametrize("league", ["NCAAH", "NCAAWH"])
def test_college_hockey_has_nothing_to_show(league):
    assert build_box_tables(load(league)) == []


@pytest.mark.parametrize("junk", [None, [], {}, "x", {"teams": [], "players": []}])
def test_empty_or_bad_input(junk):
    assert build_box_tables(junk) == []
