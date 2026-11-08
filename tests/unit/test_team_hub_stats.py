"""Team Hub's Stats tab on Windows: one team's leaders from /leaders with team=, and where the team
ranks from the core API's statistics for it, ranked against the league's byteam list, as the iPhone
does (TeamStatsViewModel). tests/fixtures/team_hub_stats_grid.json holds both apps to the same rows."""
import json
from pathlib import Path

import pytest

import espn_api
import team_stats
from team_stats import HUB_HEADERS, LeagueRanks, hub_player_rows, hub_rankings, hub_team_rows, ordinal, rank_display

FIXTURES = Path(__file__).parent.parent / "fixtures"
GRID = json.loads((FIXTURES / "team_hub_stats_grid.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FIXTURES / "espn" / name).read_text(encoding="utf-8"))


def team_list(name):
    listed = load(name)
    return {str(e["team"]["id"]) for e in listed["sports"][0]["leagues"][0]["teams"]}


def ranks_for(byteam, sport, teams=None):
    """The league list as get_team_stat_rankings would use it, or None if it's another season type."""
    answer = load(byteam)
    if answer["requestedSeason"]["type"]["type"] != espn_api.REGULAR_SEASON:
        return None
    listed = team_list(teams) if teams and team_stats.needs_team_list(answer) else None
    return LeagueRanks(answer, sport, listed)


# ------------------------------------------------------------------------------- the shared grid

def test_the_grid_has_the_cases_that_matter():
    assert {case["fixture"] for case in GRID["players"]} == {
        "leaders_v3_team_NBA_14.json", "leaders_v3_team_MLB_30.json", "leaders_v3_team_NFL_3.json"}
    cores = {case["core"] for case in GRID["team"]}
    assert {"core_team_stats_NCAAF_333_2025.json", "core_team_stats_NCAAF_149.json"} <= cores
    shown = [row["rank"] for case in GRID["team"] for row in case["rows"]]
    assert any(rank.startswith("Tied-") for rank in shown)
    assert any(" of " in rank for rank in shown), "a college rank says what it's out of"


@pytest.mark.parametrize("case", GRID["players"], ids=lambda case: case["fixture"])
def test_one_teams_players_read_as_the_grid_says(case):
    parsed = espn_api._parse_leaders(load(case["fixture"]), one_team=True)
    assert parsed["season"] == case["season"]
    assert [c["category"] for c in parsed["player_stats"]] == [c["title"] for c in case["categories"]]
    rows = hub_player_rows(parsed["player_stats"])
    expected = [[c["title"], r["rank"], r["player"], r["value"]] for c in case["categories"] for r in c["rows"]]
    assert rows == expected


@pytest.mark.parametrize("case", GRID["team"], ids=lambda case: case["core"])
def test_one_teams_ranks_read_as_the_grid_says(case):
    sport = espn_api.LEAGUES[case["sport"]].split("/")[0]
    teams = "teams_NCAAM.json" if case["sport"] == "NCAAM" else None
    rankings = hub_rankings(load(case["core"]), case["teamId"], case["sport"].startswith("NCAA"),
                            ranks_for(case["byteam"], sport, teams))
    assert hub_team_rows(rankings) == [[r["section"], r["category"], r["value"], r["rank"]] for r in case["rows"]]


# ------------------------------------------------------------------------- one team's leaders

def one_team(fixture):
    return {c["category"]: c["stats"] for c in espn_api._parse_leaders(load(fixture), one_team=True)["player_stats"]}


def test_one_team_keeps_the_players_behind_its_qualified_ones():
    points = one_team("leaders_v3_team_NBA_14.json")["Points Per Game"]
    assert "Tyler Herro" in [p["player_name"] for p in points]
    assert len(points) == 13


def test_the_league_rule_would_have_lost_them():
    league = {c["category"]: c["stats"] for c in espn_api._parse_leaders(load("leaders_v3_team_NBA_14.json"))["player_stats"]}
    assert "Tyler Herro" not in [p["player_name"] for p in league["Points Per Game"]]


def test_one_team_does_not_repeat_its_yards_lists():
    assert list(one_team("leaders_v3_team_NFL_3.json")) == ["Passing Yards", "Sacks"]


def test_one_teams_ranks_share_a_tie_below_the_top():
    rows = hub_player_rows([{"category": "Sacks", "stats": one_team("leaders_v3_team_NFL_3.json")["Sacks"]}])
    assert [row[1] for row in rows][:6] == [1, 2, 3, 4, 5, 5]


def test_one_teams_on_base_percentage_reads_as_one():
    assert one_team("leaders_v3_team_MLB_30.json")["On Base Percentage"][0]["value"] == ".360"


def test_one_teams_season_says_what_its_ranks_are():
    parsed = espn_api._parse_leaders(load("leaders_v3_team_NFL_3.json"), one_team=True)
    assert parsed["season"] == "2025 Regular Season, ranked within this team, qualified players first"


def test_with_no_season_named_it_still_says_what_its_ranks_are():
    data = load("leaders_v3_team_NFL_3.json")
    del data["requestedSeason"]
    assert espn_api._parse_leaders(data, one_team=True)["season"] == "Ranked within this team, qualified players first"


def test_a_preseason_is_nothing_for_one_team_too():
    data = load("leaders_v3_team_NFL_3.json")
    data["requestedSeason"]["type"]["type"] = espn_api.PRESEASON
    assert espn_api._parse_leaders(data, one_team=True)["player_stats"] == []


def test_the_rows_carry_category_rank_player_and_value():
    assert HUB_HEADERS["players"] == ["Category", "Rank", "Player", "Value"]
    rows = hub_player_rows([{"category": "Goals", "stats": [{"player_name": "", "team": "", "value": "3"}]}])
    assert rows == [["Goals", 1, "Unknown", "3"]], "no cell is silent"


# ---------------------------------------------------------------------------- one team's ranks

def nba(core=None, league=True):
    return hub_rankings(core or load("core_team_stats_NBA_29.json"), "29", False,
                        ranks_for("byteam_NBA.json", "basketball") if league else None)


def by_category(rankings):
    return {row["category"]: row for row in rankings}


def test_a_total_reads_its_own_rank_not_espns_per_game_one():
    """The core API has the Grizzlies' 192 assists Tied-5th. They're 11th in the league's list."""
    assists = by_category(nba())["Assists"]
    assert (assists["rank"], assists["value"]) == (11, "192")
    assert assists["rank"] == LeagueRanks(load("byteam_NBA.json"), "basketball").standing("29", "offensive", "assists")[0]


def test_a_per_game_stat_espn_has_no_rank_for_now_has_one():
    assert "Points Per Game" in by_category(nba())
    assert "Points Per Game" not in by_category(nba(league=False)), "ESPN has no rank for it"


def test_a_pro_rank_has_no_out_of():
    rankings = nba()
    assert rankings and not any(" of " in row["rank_display"] for row in rankings)
    assert {row["league_size"] for row in rankings} == {30}


def test_a_college_rank_says_what_its_out_of():
    rankings = hub_rankings(load("core_team_stats_NCAAM_150.json"), "150", True,
                            ranks_for("byteam_NCAAM.json", "basketball", "teams_NCAAM.json"))
    size = rankings[0]["league_size"]
    assert size == 6, "the fixture's Division I teams"
    assert all(row["rank_display"].endswith(f" of {size}") for row in rankings)


def test_college_ranks_past_thirty_four_are_kept_with_no_list():
    points = by_category(hub_rankings(load("core_team_stats_NCAAM_150.json"), "150", True))["Points"]
    assert points["rank_display"] == "Tied-118th"
    assert points["league_size"] is None


def test_a_pro_rank_past_the_end_of_the_league_is_hidden():
    """Kick return fair catch percentage reads 200th in the NFL's core payload."""
    rankings = hub_rankings(load("core_team_stats_NFL_22.json"), "22", False)
    assert rankings and max(row["rank"] for row in rankings) <= team_stats.HUB_MOST_PRO_TEAMS


def test_a_rank_past_the_leagues_size_is_hidden_with_the_list_too():
    rankings = hub_rankings(load("core_team_stats_NFL_22.json"), "22", False, ranks_for("byteam_NFL.json", "football"))
    assert all(row["rank"] <= row["league_size"] for row in rankings)


def test_a_type_3_list_is_not_ranked_against():
    """Alabama's 3,551 passing yards in 2025 are the regular season's, 11th. The list runs through
    the bowls, where it has 3,953: read against that, 3,551 was 6th of 136."""
    assert ranks_for("byteam_NCAAF_2025.json", "football") is None
    passing = [row for row in hub_rankings(load("core_team_stats_NCAAF_333_2025.json"), "333", True)
               if row["category"] == "Passing Yards" and row["value"] == "3,551"]
    assert [(row["rank_display"], row["league_size"]) for row in passing] == [("11th", None)]


def test_a_team_not_on_the_list_does_not_read_out_of_its_size():
    """Montana is in FCS, and college football's list is FBS."""
    rankings = hub_rankings(load("core_team_stats_NCAAF_149.json"), "149", True, ranks_for("byteam_NCAAF.json", "football"))
    assert rankings and not any(" of " in row["rank_display"] for row in rankings)
    assert by_category(rankings)["Total Tackles"]["rank_display"] == "Tied-363rd"


def core_with(*stats, section="offensive", title="Offensive"):
    return {"splits": {"categories": [{"name": section, "displayName": title, "stats": list(stats)}]}}


def stat(name, value="5", rank=3, shown="3rd", title=None):
    return {"name": name, "displayName": title or name, "displayValue": value, "rank": rank, "rankDisplayValue": shown}


@pytest.mark.parametrize("left_out", [
    stat("gamesPlayed"),
    stat("points", value="0"),
    stat("points", value="0.0"),
    stat("points", shown="Tied-1st", rank=1),
    stat("points", shown="?"),
    stat("points", shown=""),
    stat("points", rank=None),
    stat("points", rank=35, shown="35th"),
    {"name": "points", "displayValue": "5", "rank": 3, "rankDisplayValue": "3rd"},
], ids=["excluded", "zero", "zero_point_zero", "tied_first", "question_mark", "no_rank_text", "no_rank",
        "past_the_league", "no_title"])
def test_what_is_left_out(left_out):
    assert hub_rankings(core_with(left_out), "1", False) == []


def test_fielding_is_left_out():
    assert hub_rankings(core_with(stat("errors"), section="fielding", title="Fielding"), "1", False) == []


def test_a_float_rank_still_reads():
    assert hub_rankings(core_with(stat("points", rank=3.0)), "1", False)[0]["rank"] == 3


def test_sections_stay_together_in_the_order_they_first_come():
    core = {"splits": {"categories": [
        {"name": "a", "displayName": "Offense", "stats": [stat("one")]},
        {"name": "b", "displayName": "Defense", "stats": [stat("two")]},
        {"name": "c", "displayName": "Offense", "stats": [stat("three")]},
    ]}}
    assert [row["category"] for row in hub_rankings(core, "1", False)] == ["one", "three", "two"]


@pytest.mark.parametrize("core", [None, [], {}, {"splits": None}, {"splits": {"categories": [None, {"stats": None}]}}])
def test_an_odd_answer_is_no_rankings(core):
    assert hub_rankings(core, "1", False) == []


def test_the_team_rows():
    assert HUB_HEADERS["team"] == ["Section", "Category", "Value", "Rank"]
    assert hub_team_rows(nba())[0] == ["Defensive", "Blocks", "41", "Tied-9th"]


def test_the_names_left_out_are_the_iphones():
    """Read from buildTeamStatRankings in ESPNAPIService.swift, as tools/stat_categories.py reads it."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
    import stat_categories
    assert stat_categories.swift_team_hub_excluded() == team_stats.HUB_EXCLUDED


# ------------------------------------------------------------------------------- words for ranks

@pytest.mark.parametrize("number,text", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"),
                                         (13, "13th"), (21, "21st"), (22, "22nd"), (101, "101st"), (111, "111th"),
                                         (113, "113th"), (118, "118th"), (123, "123rd"), (302, "302nd")])
def test_ordinals(number, text):
    assert ordinal(number) == text


def test_how_a_rank_reads():
    assert rank_display(9, False) == "9th"
    assert rank_display(9, True) == "Tied-9th"
    assert rank_display(118, False, 302) == "118th of 302"
    assert rank_display(118, True, 302) == "Tied-118th of 302"


def test_league_ranks_go_the_way_the_table_says():
    """Turnovers: fewest first."""
    league = LeagueRanks(load("byteam_NBA.json"), "basketball")
    values = league._values("offensive", "avgTurnovers")
    fewest = min(values, key=values.get)
    assert league.standing(fewest, "offensive", "avgTurnovers")[0] == 1


def test_a_stat_the_list_does_not_have_has_no_standing():
    league = LeagueRanks(load("byteam_NBA.json"), "basketball")
    assert league.standing("29", "offensive", "noSuchStat") is None
    assert league.standing("no such team", "offensive", "assists") is None
    assert LeagueRanks(None, "basketball").standing("29", "offensive", "assists") is None
