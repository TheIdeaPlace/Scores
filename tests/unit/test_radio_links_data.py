"""radio_links.json itself: the iPhone's copy matches, and every entry is usable."""

import json
import re
from pathlib import Path

import pytest

import radio_links

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "radio_links.json"
IPHONE = ROOT / "iOS" / "SportsScoresApp" / "SportsScores" / "radio_links.json"
DATA = json.loads(WINDOWS.read_text(encoding="utf-8"))

# Every team in the league, so a team can't drop out of the list unnoticed.
TEAM_COUNTS = {"NFL": 32, "NBA": 30, "NHL": 32}


def test_iphone_copy_matches():
    assert IPHONE.read_bytes() == WINDOWS.read_bytes(), (
        "Copy radio_links.json to iOS/SportsScoresApp/SportsScores/radio_links.json")


def test_build_bundles_it():
    assert '"radio_links.json"' in (ROOT / "build.py").read_text(encoding="utf-8")


def test_every_table_a_league_reads_exists():
    assert set(radio_links.LEAGUE_TABLES.values()) <= set(DATA["tables"])


@pytest.mark.parametrize("table", sorted(TEAM_COUNTS))
def test_pro_tables_have_every_team(table):
    assert len(DATA["tables"][table]["teams"]) == TEAM_COUNTS[table]


@pytest.mark.parametrize("table", sorted(DATA["tables"]))
def test_entries_are_usable(table):
    entry = DATA["tables"][table]
    assert radio_links._links(entry), f"{table} has no league-wide link"
    names = set()
    for team_id, team in entry["teams"].items():
        assert re.fullmatch(r"\d+", team_id), f"{table} {team_id} isn't an ESPN team id"
        assert team.get("name"), f"{table} {team_id} has no name"
        assert team["name"] not in names, f"{table} lists {team['name']} twice"
        names.add(team["name"])
        for link in team.get("links", []):
            assert link["label"].strip(), f"{team['name']} has a link with no label"
            assert link["url"].startswith("https://"), f"{team['name']}: {link['url']}"
        assert len(radio_links._links(team)) == len(team.get("links", []))


@pytest.mark.parametrize("league, fixture", [
    ("NFL", "scoreboard_NFL_202611.json"), ("NBA", "scoreboard_NBA_202611.json"),
    ("NHL", "box_NHL_401892628.json")])
def test_real_game_teams_are_found(league, fixture):
    """The file's ids are ESPN's: every team in a real game has radio. A game summary's
    competition is in its header, as game details read it."""
    payload = json.loads((ROOT / "tests" / "fixtures" / "espn" / fixture).read_text(encoding="utf-8"))
    events = payload.get("events") or [payload["header"]]
    comps = [event["competitions"][0] for event in events]
    assert comps
    for comp in comps:
        away_id, away_name, home_id, home_name = radio_links.competitors(comp)
        for team_id, name in ((away_id, away_name), (home_id, home_name)):
            assert radio_links.team_entry(DATA, league, team_id), f"{league} {name} ({team_id})"


def test_college_ids_are_espns():
    """Clemson at Syracuse, on a real scoreboard, finds both schools."""
    board = json.loads((ROOT / "tests" / "fixtures" / "espn" / "scoreboard_NCAAF_202611.json")
                       .read_text(encoding="utf-8"))
    for event in board["events"]:
        away_id, _, home_id, _ = radio_links.competitors(event["competitions"][0])
        if {away_id, home_id} == {"228", "183"}:
            assert radio_links.team_entry(DATA, "NCAAF", "228")["name"].startswith("Clemson")
            assert radio_links.team_entry(DATA, "NCAAM", "183")["name"].startswith("Syracuse")
            return
    pytest.fail("the fixture no longer has Clemson and Syracuse")


@pytest.mark.parametrize("league", sorted(radio_links.LEAGUE_TABLES))
def test_each_league_is_covered(league):
    assert radio_links.covers(DATA, league)
