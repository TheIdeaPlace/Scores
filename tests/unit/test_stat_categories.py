"""tools/stat_categories.py, the stat category reference, on real saved payloads. Nothing here
touches the network: every request the tool would make is replaced by a fixture or nothing."""
import csv
import json
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import espn_api  # noqa: E402
import stat_categories as sc  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "espn")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def offline(monkeypatch):
    """No request reaches the network: anything not given a fixture answers nothing."""
    monkeypatch.setattr(sc, "get_json", lambda url, params=None, tries=3: None)
    monkeypatch.setattr(espn_api, "core_season", lambda path: {"year": 2026, "type": {"type": 2}})


def by_key(rows):
    return {row["key"]: row for row in rows.all()}


def test_the_iphone_hides_the_same_leaders_as_windows():
    # Read from ESPNAPIService.swift: if the pattern stops matching, the CSV would guess.
    assert sc.swift_string_set("leadersNotShown") == espn_api.LEADERS_NOT_SHOWN


def test_the_team_hub_exclusions_are_read_from_the_iphone():
    excluded = sc.swift_team_hub_excluded()
    assert {"gamesPlayed", "MLBRating", "WAR"} <= excluded


def test_the_iphone_catalog_is_its_league_list_only():
    catalog = sc.iphone_catalog()
    assert ("own", "batting", "runs") in catalog["baseball"]
    # beyondTheCatalog is more direction checks, not more stats on the iPhone.
    assert ("own", "general", "gamesPlayed") not in catalog["football"]
    assert "cricket" not in catalog


def test_mlb_leaders(offline, monkeypatch):
    data = load("leaders_v3_MLB.json")
    # The saved answer predates Opponent Batting Average: add it, as ESPN sends it now.
    era = next(c for c in data["leaders"]["categories"] if c["name"] == "ERA")
    data["leaders"]["categories"].append({**era, "name": "opponentAvg", "displayName": "Opponent Batting Average"})
    monkeypatch.setattr(espn_api, "_fetch_leaders", lambda path, year: data)
    rows = sc.Rows()
    result = sc.leaders_rows(rows, "MLB", espn_api.LEADERS_NOT_SHOWN)
    assert not isinstance(result, str)
    found = by_key(rows)
    assert found["opponentAvg"]["shown_windows"] is False
    assert found["opponentAvg"]["shown_iphone"] is False
    assert "no qualifying minimum" in found["opponentAvg"]["notes"][0]
    assert found["ERA"]["shown_windows"] and found["ERA"]["low_is_good"] is True
    assert found["homeRuns"]["low_is_good"] is False
    assert all(row["available_in_current_source"] and row["sources"] == ["leaders"] for row in found.values())


def test_soccer_repeats_are_marked_hidden(offline, monkeypatch):
    data = load("leaders_v3_EPL.json")
    asked = []
    monkeypatch.setattr(espn_api, "_fetch_leaders", lambda path, year, season_type=2: asked.append(
        (path, year, season_type)) or data)
    rows = sc.Rows()
    sc.soccer_leaders_rows(rows, "EPL")
    assert asked == [("soccer/eng.1", 2026, 1)], "the season and type the apps ask for"
    found = by_key(rows)
    assert found["goalsLeaders"]["shown_windows"] and found["goalsLeaders"]["shown_iphone"]
    assert not found["goals"]["shown_windows"] and not found["goals"]["shown_iphone"]
    assert "repeats an earlier list" in found["goals"]["notes"][0]
    assert all(row["sources"] == ["leaders"] for row in found.values())


def test_soccer_leaders_not_answering_is_a_problem_to_report(offline, monkeypatch):
    def failing(path, year, season_type=2):
        raise espn_api.ApiError(espn_api.STATISTICS_UNAVAILABLE)

    monkeypatch.setattr(espn_api, "_fetch_leaders", failing)
    assert sc.soccer_leaders_rows(sc.Rows(), "EPL") == "EPL: /leaders didn't answer"


def test_nfl_team_stats(offline, monkeypatch):
    monkeypatch.setattr(espn_api, "_fetch_team_stats", lambda path, year, sort=None: load("byteam_NFL.json"))
    rows = sc.Rows()
    sc.byteam_rows(rows, "NFL", 2026, sc.iphone_catalog())
    found = by_key(rows)
    sacks = found["passing.sacks"]
    assert sacks["shown_windows"] and not sacks["shown_iphone"] and sacks["low_is_good"] is True
    assert "Windows calls it Sacks Taken" in sacks["notes"]
    opponent = found["opponent.passing.sacks"]
    assert opponent["group"] == "opponent passing" and opponent["low_is_good"] is False
    assert opponent["shown_iphone"] and "iPhone: league list" in opponent["notes"]
    assert not found["general.gamesPlayed"]["shown_iphone"]
    assert all(row["available_in_current_source"] for row in found.values())


def test_a_repeated_team_stat_name_is_hidden_on_windows(offline, monkeypatch):
    monkeypatch.setattr(espn_api, "_fetch_team_stats", lambda path, year, sort=None: load("byteam_NBA.json"))
    rows = sc.Rows()
    sc.byteam_rows(rows, "NBA", 2026, sc.iphone_catalog())
    hidden = [row for row in rows.all() if "has the same name and is shown instead" in "; ".join(row["notes"])]
    assert hidden and not any(row["shown_windows"] for row in hidden)
    ratio = by_key(rows)["general.teamAssistTurnoverRatio"]
    assert "general.assistTurnoverRatio has the same name" in "; ".join(ratio["notes"])
    assert by_key(rows)["general.assistTurnoverRatio"]["shown_windows"]
    # The same stat listed twice is one row, shown.
    assert by_key(rows)["general.avgRebounds"]["shown_windows"]


def test_a_dropped_team_stat_says_where_it_went(offline, monkeypatch):
    monkeypatch.setattr(espn_api, "_fetch_team_stats", lambda path, year, sort=None: load("byteam_NFL.json"))
    rows = sc.Rows()
    sc.byteam_rows(rows, "NFL", 2026, sc.iphone_catalog())
    old = {"results": {"stats": {"categories": [{"name": "defensive", "stats": [
        {"name": "totalTackles", "displayName": "Total Tackles", "description": "Tackles made."}]},
        {"name": "passing", "stats": [{"name": "passingYards", "displayName": "Passing Yards"}]}]}}}
    monkeypatch.setattr(sc, "get_json", lambda url, params=None, tries=3: old)
    sc.site_team_rows(rows, "NFL", "22")
    found = by_key(rows)
    assert "dropped in #152" in found["defensive.totalTackles"]["notes"][0]
    assert not found["defensive.totalTackles"]["available_in_current_source"]
    assert found["passing.passingYards"]["sources"] == ["byteam", "site_team_stats"]
    assert not any("dropped" in note for note in found["passing.passingYards"]["notes"])


def core_nba_team_rows(monkeypatch, byteam):
    core = load("core_team_stats_NBA_29.json")
    monkeypatch.setattr(sc, "get_json", lambda url, params=None, tries=3: core if "/teams/29/" in url else None)
    rows = sc.Rows()
    if byteam:
        monkeypatch.setattr(espn_api, "_fetch_team_stats", lambda path, year, sort=None: byteam)
        sc.byteam_rows(rows, "NBA", 2027, sc.iphone_catalog())
    excluded = sc.swift_team_hub_excluded()
    assert sc.core_team_rows(rows, "NBA", ["29"], 2027, excluded, byteam)
    return by_key(rows), core


def test_the_team_hub_is_held_to_the_iphones_filter(offline, monkeypatch):
    found, core = core_nba_team_rows(monkeypatch, load("byteam_NBA.json"))
    stats = {(c["name"], s["name"]): s for c in core["splits"]["categories"] for s in c["stats"]}
    # The league list ranks blocks, so the Team Hub shows it whatever ESPN's own rank says.
    assert found["defensive.blocks"]["shown_iphone"]
    # Excluded on the iPhone, though the core API has it.
    assert ("general", "gamesPlayed") in stats and not found["general.gamesPlayed"]["shown_iphone"]
    # A core-only stat with no usable rank of ESPN's is left out, and says so.
    left_out = [row for key, row in found.items() if row["sources"] == ["core_team_stats"] and not row["shown_iphone"]]
    assert left_out and all("Team Hub leaves it out" in "; ".join(row["notes"]) for row in left_out)
    shown_core_only = [key for key, row in found.items() if row["sources"] == ["core_team_stats"] and row["shown_iphone"]]
    for key in shown_core_only:
        section, name = key.split(".", 1)
        stat = stats[(section, name)]
        assert stat["rank"] <= 30 and stat["rankDisplayValue"] not in ("", "?", "Tied-1st")


def test_without_a_league_list_the_team_hub_needs_espns_rank(offline, monkeypatch):
    found, core = core_nba_team_rows(monkeypatch, None)
    for category in core["splits"]["categories"]:
        for stat in category["stats"]:
            if stat.get("rank") is None and stat["name"] not in sc.swift_team_hub_excluded():
                assert not found[f"{category['name']}.{stat['name']}"]["shown_iphone"]


def test_a_player_stat_joins_the_leader_category_it_is(offline):
    rows = sc.Rows()
    row = rows.add("MLB", sc.PLAYER, "strikeouts", key="strikeouts", group="pitching", display_name="Strikeouts",
                   source="leaders", available=True, shown_windows=True, shown_iphone=True)
    row["_matches"] = {"pitching.strikeouts"}
    sc.add_player_stat(rows, "MLB", "pitching", "strikeouts", "byathlete", "Strikeouts", "K", "Batters struck out.")
    sc.add_player_stat(rows, "MLB", "batting", "strikeouts", "byathlete", "Strikeouts", "K", "Times struck out.")
    found = by_key(rows)
    assert found["strikeouts"]["sources"] == ["leaders", "byathlete"]
    assert found["strikeouts"]["definition"] == "Batters struck out."
    assert found["batting.strikeouts"]["sources"] == ["byathlete"]


def test_find_stat_takes_the_group_with_the_leaders_number():
    answers = [{"splits": {"categories": [
        {"name": "batting", "stats": [{"name": "strikeouts", "value": 3.0}]},
        {"name": "pitching", "stats": [{"name": "strikeouts", "value": 252.0}]}]}}]
    assert sc.find_stat(answers, "strikeouts", 252.0)[0] == "pitching"
    assert sc.find_stat(answers, "strikeouts")[0] == "batting"
    assert sc.find_stat(answers, "saves") == (None, None)


def test_mlb_statsapi_categories_say_whether_they_were_dropped(offline):
    rows = sc.Rows()
    hr = rows.add("MLB", sc.PLAYER, "homeRuns", key="homeRuns", group="batting", display_name="Home Runs",
                  source="leaders", available=True)
    hr["_matches"] = {"batting.homeruns"}
    sc.add_player_stat(rows, "MLB", "batting", "doubles", "byathlete", "Doubles", "2B", "Two-base hits.")
    rows.add("MLB", sc.TEAM, "fielding.catcherCaughtStealing", key="fielding.catcherCaughtStealing",
             group="fielding", display_name="Caught Stealing", definition="Runners thrown out stealing.",
             source="core_team_stats")
    sc.mlb_statsapi_rows(rows)
    sc.finish(rows)
    found = by_key(rows)
    assert "also an MLB Stats API category (homeRuns)" in found["homeRuns"]["notes"]
    doubles = found["batting.doubles"]
    assert doubles["sources"] == ["byathlete", "mlb_statsapi"]
    assert doubles["notes"][0] == "not a leader category; byathlete can rank every player by it"
    assert "dropped in #166" in doubles["notes"][1]
    caught = found["fielding.catcherCaughtStealing"]
    assert caught["definition"] == "Runners thrown out stealing." and caught["sources"] == ["mlb_statsapi"]
    dropped = [row for row in found.values() if any("dropped in #166" in note for note in row["notes"])]
    assert len(dropped) == len(sc.MLB_STATSAPI_CATEGORIES) - 1


def test_the_csv_opens_in_excel(tmp_path):
    rows = sc.Rows()
    rows.add("NFL", sc.TEAM, "passing.sacks", key="passing.sacks", group="passing", display_name="Total Sacks",
             definition="Sacks, \"taken\".", source="byteam", available=True, low_is_good=True)
    rows.add("MLB", sc.PLAYER, "WARBR", key="WARBR", group="batting", display_name="Wins Above Replacement",
             source="leaders", available=True, shown_windows=True, shown_iphone=True, low_is_good=False)
    sc.finish(rows)
    out = sc.csv_rows(rows)
    path = tmp_path / "out.csv"
    sc.write_csv(str(path), out)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").splitlines()[0] == ",".join(f'"{c}"' for c in sc.COLUMNS)
    with open(path, encoding="utf-8-sig", newline="") as f:
        read = list(csv.DictReader(f))
    assert [r["league"] for r in read] == ["MLB", "NFL"]
    assert read[0]["definition_source"] == "written" and read[0]["definition"]
    assert read[1]["definition"] == 'Sacks, "taken".' and read[1]["low_is_good"] == "yes"
    assert read[1]["shown_windows"] == "no"
