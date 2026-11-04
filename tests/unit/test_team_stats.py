"""ESPN's statistics/byteam to ranked lists, on real payloads. Pure: no Qt, no network.

`tests/fixtures/team_stat_directions.json` is the shared reference for which way a stat ranks and
how ties read. This holds team_stats.py to it, and TeamStatsTests.swift holds the iPhone to it.
"""
import json
import os
from pathlib import Path

import pytest

import espn_api
import team_stats
from team_stats import (
    RANKING_HEADERS,
    low_is_good,
    needs_team_list,
    parse_team_stats,
    qualified_teams,
    rank_teams,
    ranking_rows,
    team_stat_lists,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
DIRECTIONS = json.loads((FIXTURES / "team_stat_directions.json").read_text(encoding="utf-8"))


def load(name):
    with open(os.path.join(FIXTURES, "espn", name), encoding="utf-8") as f:
        return json.load(f)


def the_list(payload, sport, name, team_list=None):
    lists = team_stat_lists(parse_team_stats(payload, sport, team_list))
    return next(item for item in lists if item["name"] == name)["data"]


def team_ids(teams):
    return {team["team"]["id"] for team in teams}


class TestTheSharedDirections:
    def test_the_table_matches(self):
        assert {sport: sorted(stats) for sport, stats in team_stats.LOW_IS_GOOD.items()} == DIRECTIONS["lowIsGood"]

    def test_the_counts_of_tries_match(self):
        assert {sport: sorted(stats) for sport, stats in team_stats.COUNTS_OF_TRIES.items()} == DIRECTIONS["countsOfTries"]

    @pytest.mark.parametrize("table", [team_stats.LOW_IS_GOOD, team_stats.COUNTS_OF_TRIES, team_stats.STAT_TITLES],
                             ids=["low_is_good", "counts_of_tries", "titles"])
    def test_every_stat_the_tables_name_is_a_real_column(self, table):
        """A typo here would quietly rank the real column the wrong way."""
        for sport, stats in table.items():
            known = DIRECTIONS["knownStats"][sport]
            for key in stats:
                section, stat = key.split(".")
                assert stat in known.get(section, ()), f"{sport} {key}"

    @pytest.mark.parametrize("fixture,sport", [
        ("byteam_NFL.json", "football"), ("byteam_NCAAF.json", "football"), ("byteam_NCAAF_2025.json", "football"),
        ("byteam_NBA.json", "basketball"), ("byteam_WNBA.json", "basketball"), ("byteam_NCAAM.json", "basketball"),
        ("byteam_NCAAWB.json", "basketball"), ("byteam_NHL.json", "hockey"), ("byteam_MLB.json", "baseball"),
    ])
    def test_every_real_column_is_known(self, fixture, sport):
        known = DIRECTIONS["knownStats"][sport]
        for meta in load(fixture)["categories"]:
            for name in meta.get("names") or []:
                assert name in known[meta["name"]], f"{meta['name']}.{name}"

    @pytest.mark.parametrize("sport", sorted(DIRECTIONS["catalog"]))
    def test_every_stat_the_iphone_lists_goes_the_same_way(self, sport):
        rows = DIRECTIONS["catalog"][sport]
        assert rows
        for row in rows:
            opponent = row["split"] == "opponent"
            assert low_is_good(sport, row["section"], row["stat"], opponent) is not row["higherIsBetter"], row

    @pytest.mark.parametrize("row", DIRECTIONS["beyondTheCatalog"], ids=lambda r: f"{r['split']}.{r['section']}.{r['stat']}")
    def test_the_rest(self, row):
        assert low_is_good(row["sport"], row["section"], row["stat"], row["split"] == "opponent") is not row["higherIsBetter"]

    @pytest.mark.parametrize("case", DIRECTIONS["rankGrid"], ids=lambda c: c["why"])
    def test_the_rank_grid(self, case):
        rows = [{"name": f"Team {i:02d}", "value": value} for i, value in enumerate(case["values"])]
        ranked = rank_teams(rows, low_first=not case["higherIsBetter"])
        assert [row["rank"] for row in sorted(ranked, key=lambda row: row["name"])] == case["ranks"]
        assert [row["rank"] for row in ranked] == sorted(case["ranks"])


class TestColumns:
    """The real shape of each sport, including what the old per-team endpoint never had."""

    def test_own_numbers_then_opponents(self):
        titles = [c["category"] for c in parse_team_stats(load("byteam_NBA.json"), "basketball")]
        assert titles == ["General", "Defensive", "Offensive", "Differential",
                          "Opponent General", "Opponent Defensive", "Opponent Offensive"]

    def test_a_team_row_has_what_to_show_and_what_to_rank_by(self):
        categories = parse_team_stats(load("byteam_NBA.json"), "basketball")
        offensive = next(c for c in categories if c["category"] == "Offensive")
        row = next(t for t in offensive["stats"] if t["team_name"] == "Memphis Grizzlies")
        assert row["team_id"] == "29"
        assert row["stats"]["Points Per Game"] == "123.0"
        assert row["values"]["Points Per Game"] == 123.0
        assert len(offensive["stats"]) == 30

    def test_every_column_espn_gives_is_kept(self):
        data = load("byteam_NFL.json")
        names = {meta["name"]: meta for meta in data["categories"] if meta.get("names")}
        categories = {c["category"]: c for c in parse_team_stats(data, "football")}
        titles = team_stats.STAT_TITLES["football"]
        for section, title in (("passing", "Passing"), ("kicking", "Kicking"), ("punting", "Punting")):
            expected = {titles.get(f"{section}.{name}", shown)
                        for name, shown in zip(names[section]["names"], names[section]["displayNames"])}
            assert set(categories[title]["stats"][0]["stats"]) == expected
        assert categories["Opponent Passing"]["stats"][0]["stats"]

    def test_hockey_and_baseball_have_no_opponents_section(self):
        assert [c["category"] for c in parse_team_stats(load("byteam_NHL.json"), "hockey")] == [
            "General", "Offensive", "Defensive", "Penalties"]
        assert [c["category"] for c in parse_team_stats(load("byteam_MLB.json"), "baseball")] == [
            "Batting", "Pitching", "Fielding"]

    def test_a_repeated_name_reads_as_the_later_stat(self):
        """27.4 is teamAssistTurnoverRatio, and 1.8 is the ratio anyone means."""
        categories = parse_team_stats(load("byteam_NBA.json"), "basketball")
        general = next(c for c in categories if c["category"] == "General")
        grizzlies = next(t for t in general["stats"] if t["team_id"] == "29")
        assert grizzlies["stats"]["Assist To Turnover Ratio"] == "1.8"

    @pytest.mark.parametrize("name,kept", [
        ("Shootout Attempts (Offensive)", True), ("Shootout Goals (Offensive)", True), ("Shootout Saves (Defensive)", True),
    ])
    def test_a_null_showing_zero_ranks_as_zero(self, name, kept):
        """An NHL team yet to go to a shootout has "0" with a null. Three lists had 18 of 32."""
        data = load("byteam_NHL.json")
        rows = the_list(data, "hockey", name)
        assert len(rows) == len(data["teams"])
        assert any(row["value"] == 0 and row["displayValue"] == "0" for row in rows)

    def test_a_null_showing_anything_else_is_still_left_out(self):
        data = load("byteam_NHL.json")
        block = next(c for c in data["teams"][0]["categories"] if c["name"] == "general")
        block["values"] = [None] * len(block["values"])
        general = next(c for c in parse_team_stats(data, "hockey") if c["category"] == "General")
        assert data["teams"][0]["team"]["displayName"] not in {t["team_name"] for t in general["stats"]}

    @pytest.mark.parametrize("name", ["Sacks Taken (Passing)", "Interceptions Thrown (Passing)",
                                      "Total Yards Per Game (Passing)", "Fourth Down Attempts (Miscellaneous)",
                                      "Turnover Differential (Miscellaneous)", "Punt Returns Allowed (Punting)",
                                      "Sacks Taken (Opponent Passing)"])
    def test_a_name_that_would_mislead_is_put_right(self, name):
        assert the_list(load("byteam_NFL.json"), "football", name)

    @pytest.mark.parametrize("name", ["First Downs Attempts (Miscellaneous)", "Total Sacks (Passing)"])
    def test_espns_words_for_them_are_gone(self, name):
        names = [item["name"] for item in team_stat_lists(parse_team_stats(load("byteam_NFL.json"), "football"))]
        assert name not in names

    def test_a_section_with_nothing_for_a_team_leaves_the_team_out_of_it(self):
        """ESPN's differential section is all "-" and nulls for a school with one Division I game."""
        data = load("byteam_NCAAM_2026.json")
        uccs = next(t for t in data["teams"] if t["team"]["id"] == "2145")
        block = next(c for c in uccs["categories"] if c["name"] == "differential")
        assert set(block["totals"]) == {"-"} and set(block["values"]) == {None}
        differential = next(c for c in parse_team_stats(data, "basketball") if c["category"] == "Differential")
        assert "2145" not in {t["team_id"] for t in differential["stats"]}


class TestRankingOnRealPayloads:
    def test_highest_first_where_high_is_good(self):
        rows = the_list(load("byteam_NBA.json"), "basketball", "Points Per Game (Offensive)")
        values = [row["value"] for row in rows]
        assert values == sorted(values, reverse=True) and rows[0]["rank"] == 1 and len(rows) == 30

    @pytest.mark.parametrize("fixture,sport,name", [
        ("byteam_NBA.json", "basketball", "Turnovers Per Game (Offensive)"),
        ("byteam_NBA.json", "basketball", "Points Per Game (Opponent Offensive)"),
        ("byteam_NFL.json", "football", "Total Giveaways (Miscellaneous)"),
        ("byteam_NFL.json", "football", "Total Points Per Game (Opponent Passing)"),
        ("byteam_NHL.json", "hockey", "Goals Against Average (Defensive)"),
        ("byteam_NHL.json", "hockey", "Penalty Minutes (Penalties)"),
        ("byteam_MLB.json", "baseball", "Earned Run Average (Pitching)"),
        ("byteam_MLB.json", "baseball", "Errors (Fielding)"),
    ])
    def test_lowest_first_where_low_is_good(self, fixture, sport, name):
        values = [row["value"] for row in the_list(load(fixture), sport, name)]
        assert len(values) > 1 and values == sorted(values) and values[0] < values[-1]

    @pytest.mark.parametrize("fixture,sport,name", [
        ("byteam_NFL.json", "football", "Punts (Punting)"),
        ("byteam_NFL.json", "football", "Punts (Opponent Punting)"),
        ("byteam_NFL.json", "football", "Passing Attempts (Opponent Passing)"),
        ("byteam_NBA.json", "basketball", "Field Goals Attempted (Opponent Offensive)"),
    ])
    def test_a_count_of_tries_reads_highest_first_for_opponents_too(self, fixture, sport, name):
        """A defense wants to force punts: the most forced comes first, not the fewest."""
        values = [row["value"] for row in the_list(load(fixture), sport, name)]
        assert len(values) > 1 and values == sorted(values, reverse=True)

    def test_the_most_giveaways_is_not_first_as_espn_has_it(self):
        data = load("byteam_NFL.json")
        rows = the_list(data, "football", "Total Giveaways (Miscellaneous)")
        names = next(m["names"] for m in data["categories"] if m["name"] == "miscellaneous")
        index = names.index("totalGiveaways")
        espn_first = next(c["values"][index] for t in data["teams"] for c in t["categories"]
                          if c["name"] == "miscellaneous" and c["splitId"] == "0" and c["ranks"][index] == "1")
        assert espn_first == max(row["value"] for row in rows), "the fixture should show ESPN's rank the wrong way"
        assert rows[0]["value"] == min(row["value"] for row in rows)

    def test_teams_level_share_a_rank_and_the_next_rank_counts_them(self):
        rows = the_list(load("byteam_NFL.json"), "football", "Total Giveaways (Miscellaneous)")
        by_value = {}
        for row in rows:
            by_value.setdefault(row["value"], []).append(row)
        tied = [group for group in by_value.values() if len(group) > 1]
        assert tied, "the fixture should have a tie"
        for position, row in enumerate(rows, 1):
            assert row["rank"] == 1 + sum(1 for other in rows if other["value"] < row["value"]), position
        assert all(len({row["rank"] for row in group}) == 1 for group in tied)

    def test_a_tie_reads_in_name_order_so_the_list_doesnt_reshuffle(self):
        rows = rank_teams([{"name": "B", "value": 1}, {"name": "A", "value": 1}, {"name": "C", "value": 2}], low_first=True)
        assert [row["name"] for row in rows] == ["A", "B", "C"]

    def test_the_list_keeps_what_espn_shows(self):
        rows = the_list(load("byteam_MLB.json"), "baseball", "Earned Run Average (Pitching)")
        assert all(row["displayValue"].replace(".", "").isdigit() for row in rows)

    def test_a_stat_only_some_teams_have_is_offered_and_lists_those(self):
        stats = [{"team_name": "A", "stats": {"Saves": "1"}, "values": {"Saves": 1}},
                 {"team_name": "B", "stats": {"Saves": "2", "Holds": "9"}, "values": {"Saves": 2, "Holds": 9}}]
        lists = {item["stat_name"]: item for item in team_stat_lists([{"category": "Pitching", "stats": stats}])}
        assert [row["name"] for row in lists["Saves"]["data"]] == ["B", "A"]
        assert [row["name"] for row in lists["Holds"]["data"]] == ["B"]
        assert lists["Holds"]["name"] == "Holds (Pitching)" and lists["Holds"]["type"] == "team"

    def test_no_categories_is_no_lists(self):
        assert team_stat_lists([]) == []


class TestDivisionOne:
    def on_the_list(self, name):
        return {str(entry["team"]["id"]) for entry in load(name)["sports"][0]["leagues"][0]["teams"]}

    def test_a_school_with_one_game_is_dropped_late_in_a_season(self):
        data = load("byteam_NCAAM_2026.json")
        assert "2145" in team_ids(data["teams"]), "the fixture should have UCCS, with one game"
        assert team_ids(qualified_teams(data, self.on_the_list("teams_NCAAM.json"))) == team_ids(data["teams"]) - {"2145"}

    def test_it_can_top_a_stat_otherwise(self):
        data = load("byteam_NCAAM_2026.json")
        name = "Points Per Game (Offensive)"
        assert the_list(data, "basketball", name)[0]["name"].startswith("Colorado Colorado Springs")
        ranked = the_list(data, "basketball", name, self.on_the_list("teams_NCAAM.json"))
        assert not ranked[0]["name"].startswith("Colorado Colorado Springs")

    def test_opening_week_tells_them_apart_though_everyone_has_played_once(self):
        data = load("byteam_NCAAM.json")
        kept = qualified_teams(data, self.on_the_list("teams_NCAAM.json"))
        assert 0 < len(kept) < len(data["teams"]), "the fixture should have a non-Division I school"
        assert "150" in team_ids(kept), "Duke"
        assert not {"2358", "2650"} & team_ids(kept), "Lyon and Tougaloo"

    def test_a_school_moving_up_stays_with_no_opponents_numbers(self):
        """East Texas A&M and Southern Indiana are Division I, on ESPN's team list. It's the only
        thing that says so: they've played one game, as have the schools that aren't."""
        data = load("byteam_NCAAWB.json")
        no_opponents = [t for t in data["teams"] if not any(c.get("splitId") == "900" for c in t["categories"])]
        assert len(no_opponents) == 4, "the fixture should have 2 of each"
        kept = {t["team"]["displayName"] for t in qualified_teams(data, self.on_the_list("teams_NCAAWB.json"))}
        assert {"East Texas A&M Lions", "Southern Indiana Screaming Eagles"} <= kept
        assert len(kept) == len(data["teams"]) - 2

    def test_an_empty_team_list_only_keeps_those_with_opponents_numbers(self):
        data = load("byteam_NCAAWB.json")
        assert len(qualified_teams(data, set())) == 4

    def test_it_only_needs_the_list_when_someone_has_no_opponents_numbers(self):
        assert needs_team_list(load("byteam_NCAAWB.json"))
        assert not needs_team_list(load("byteam_NFL.json"))
        assert not needs_team_list({"teams": []})

    def test_no_list_means_no_filter(self):
        """Pro leagues and college football, whose list is only FBS."""
        data = load("byteam_NHL.json")
        general = next(c for c in parse_team_stats(data, "hockey") if c["category"] == "General")
        assert len(general["stats"]) == len(data["teams"])


class TestBadShapes:
    @pytest.mark.parametrize("data", [None, [], {}, {"teams": None}, {"teams": [None]}, {"categories": None, "teams": [{}]}])
    def test_nothing_usable_is_nothing(self, data):
        assert parse_team_stats(data, "basketball") == []
        assert parse_team_stats(data, "basketball", team_list=set()) == []

    def real(self):
        return load("byteam_NHL.json")

    def test_a_team_with_no_name_is_left_out(self):
        data = self.real()
        count = len(data["teams"])
        del data["teams"][0]["team"]["displayName"]
        del data["teams"][0]["team"]["name"]
        assert len(parse_team_stats(data, "hockey")[0]["stats"]) == count - 1

    def test_short_or_missing_columns_dont_raise(self):
        data = self.real()
        for block in data["teams"][0]["categories"]:
            block["totals"] = block["totals"][:1]
            block["values"] = None
        data["teams"][1]["categories"][0]["values"] = "nonsense"
        assert parse_team_stats(data, "hockey")

    def test_a_number_that_isnt_one_is_left_out(self):
        data = self.real()
        block = next(c for c in data["teams"][0]["categories"] if c["name"] == "general")
        block["values"] = [True] * len(block["values"])
        general = next(c for c in parse_team_stats(data, "hockey") if c["category"] == "General")
        assert data["teams"][0]["team"]["displayName"] not in {t["team_name"] for t in general["stats"]}

    def test_a_section_without_a_display_name_is_named_for_its_key(self):
        data = load("byteam_NBA.json")
        for team in data["teams"]:
            for block in team["categories"]:
                del block["displayName"]
        titles = [c["category"] for c in parse_team_stats(data, "basketball")]
        assert "General" in titles and "Opponent General" in titles


class TestRankingRows:
    def test_each_row_lines_up_with_its_headers(self):
        player = ranking_rows("player", [{"player_name": "A", "team": "X", "value": "9"}])
        team = ranking_rows("team", [{"name": "B", "rank": 1, "displayValue": "9", "value": 9.0}])
        assert len(player[0]) == len(RANKING_HEADERS["player"])
        assert len(team[0]) == len(RANKING_HEADERS["team"])

    def test_a_players_rank_is_their_place_in_the_list(self):
        rows = ranking_rows("player", [{"player_name": "Luka Doncic", "team": "LAL", "value": "38.3"},
                                       {"player_name": "Shai", "team": "OKC", "value": "31.0"}])
        assert rows == [[1, "Luka Doncic", "LAL", "38.3"], [2, "Shai", "OKC", "31.0"]]

    def test_real_leaders_become_rows(self):
        categories = espn_api._parse_leaders(load("leaders_v3_NBA.json"))["player_stats"]
        points = next(c for c in categories if c["category"] == "Points Per Game")
        assert ranking_rows("player", points["stats"])[0] == [1, "Luka Doncic", "LAL", "38.3"]

    def test_the_shape_the_dialog_makes_of_mlb_leaders(self):
        rows = ranking_rows("player", [{"player_name": "Pete Crow-Armstrong", "stat_value": "45", "value": "45",
                                        "team": "Chicago Cubs", "position": None}])
        assert rows == [[1, "Pete Crow-Armstrong", "Chicago Cubs", "45"]]

    def test_teams_keep_the_rank_they_share(self):
        lists = team_stat_lists(parse_team_stats(load("byteam_NBA.json"), "basketball"))
        ranked = lists[0]["data"]
        rows = ranking_rows("team", ranked)
        assert [row[0] for row in rows] == [team["rank"] for team in ranked]
        assert [row[1] for row in rows] == [team["name"] for team in ranked]
        assert [row[2] for row in rows] == [team["displayValue"] for team in ranked]
        level = ranking_rows("team", rank_teams([{"name": "B", "value": 5.0, "displayValue": "5"},
                                                 {"name": "A", "value": 5.0, "displayValue": "5"},
                                                 {"name": "C", "value": 1.0, "displayValue": "1"}], False))
        assert level == [[1, "A", "5"], [1, "B", "5"], [3, "C", "1"]]

    @pytest.mark.parametrize("team", ["", None])
    def test_a_player_with_no_team_reads_na_rather_than_a_silent_cell(self, team):
        assert ranking_rows("player", [{"player_name": "A", "team": team, "value": "1"}])[0][2] == "N/A"

    def test_missing_names_and_numbers(self):
        assert ranking_rows("player", [{}]) == [[1, "Unknown", "N/A", ""]]
        assert ranking_rows("team", [{"rank": 2}]) == [[2, "Unknown", ""]]

    def test_a_zero_is_a_number_and_not_a_gap(self):
        assert ranking_rows("player", [{"player_name": "A", "team": "X", "value": 0}])[0][3] == 0

    def test_no_rows(self):
        assert ranking_rows("player", []) == [] and ranking_rows("team", []) == []
