"""ESPN's statistics/byteam to ranked lists, on real payloads. Pure: no Qt, no network.

`tests/fixtures/team_stat_directions.json` is the shared reference for which way a stat ranks and
how ties read. This holds team_stats.py to it, and TeamStatsTests.swift holds the iPhone to it.
"""
import json
import os
from pathlib import Path

import pytest

import team_stats
from team_stats import low_is_good, parse_team_stats, qualified_teams, rank_teams, team_stat_lists

FIXTURES = Path(__file__).parent.parent / "fixtures"
DIRECTIONS = json.loads((FIXTURES / "team_stat_directions.json").read_text(encoding="utf-8"))


def load(name):
    with open(os.path.join(FIXTURES, "espn", name), encoding="utf-8") as f:
        return json.load(f)


def the_list(payload, sport, name, college=False):
    lists = team_stat_lists(parse_team_stats(payload, sport, college))
    return next(item for item in lists if item["name"] == name)["data"]


def team_ids(teams):
    return {team["team"]["id"] for team in teams}


class TestTheSharedDirections:
    def test_the_table_matches(self):
        assert {sport: sorted(stats) for sport, stats in team_stats.LOW_IS_GOOD.items()} == DIRECTIONS["lowIsGood"]

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
        for section, title in (("passing", "Passing"), ("kicking", "Kicking"), ("punting", "Punting")):
            assert set(categories[title]["stats"][0]["stats"]) == set(names[section]["displayNames"])
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
    def test_a_school_with_one_game_is_dropped_late_in_a_season(self):
        data = load("byteam_NCAAM_2026.json")
        assert "2145" in team_ids(data["teams"]), "the fixture should have UCCS, with one game"
        assert team_ids(qualified_teams(data)) == team_ids(data["teams"]) - {"2145"}

    def test_it_can_top_a_stat_otherwise(self):
        data = load("byteam_NCAAM_2026.json")
        assert the_list(data, "basketball", "Points Per Game (Offensive)")[0]["name"].startswith("Colorado Colorado Springs")
        assert not the_list(data, "basketball", "Points Per Game (Offensive)", college=True)[0]["name"].startswith("Colorado Colorado Springs")

    def test_opening_week_tells_them_apart_though_everyone_has_played_once(self):
        data = load("byteam_NCAAM.json")
        kept = qualified_teams(data)
        assert 0 < len(kept) < len(data["teams"]), "the fixture should have a non-Division I school"
        assert "150" in team_ids(kept), "Duke"
        for team in data["teams"]:
            has_opponents = any(c.get("splitId") == "900" for c in team["categories"])
            assert (team in kept) is has_opponents, team["team"]["displayName"]

    def game_counts(self, *teams):
        """(games played, whether ESPN has its opponents' numbers), by team. Team 0, 1, ..."""
        data = load("byteam_NCAAM_2026.json")
        names = next(m["names"] for m in data["categories"] if m["name"] == "general")
        values = [None] * len(names)
        built = []
        for i, (games, opponents) in enumerate(teams):
            row = list(values)
            row[names.index("gamesPlayed")] = games
            blocks = [{"name": "general", "splitId": "0", "values": row, "totals": []}]
            if opponents:
                blocks.append({"name": "general", "splitId": "900", "values": row, "totals": []})
            built.append({"team": {"id": str(i), "displayName": f"T{i}"}, "categories": blocks})
        return {**data, "teams": built}

    def test_a_school_moving_up_stays_once_the_season_is_under_way(self):
        """Lindenwood played 33 games in 2025-26 with no opponents' numbers."""
        data = self.game_counts((33, True), (33, False), (1, False))
        assert team_ids(qualified_teams(data)) == {"0", "1"}

    def test_a_school_moving_up_is_out_for_the_first_few_games(self):
        data = self.game_counts((3, True), (3, False))
        assert team_ids(qualified_teams(data)) == {"0"}

    def test_a_division_one_team_with_few_games_stays(self):
        data = self.game_counts((30, True), (3, True))
        assert team_ids(qualified_teams(data)) == {"0", "1"}

    def test_a_list_with_no_opponents_numbers_falls_back_to_games(self):
        data = self.game_counts((4, False), (2, False), (1, False))
        assert team_ids(qualified_teams(data)) == {"0", "1"}

    def test_a_team_with_no_games_column_stays_rather_than_vanishing(self):
        data = self.game_counts((4, False), (None, False))
        assert team_ids(qualified_teams(data)) == {"0", "1"}

    def test_a_team_missing_the_section_with_the_games_stays_rather_than_vanishing(self):
        data = self.game_counts((4, False), (2, False))
        data["teams"].append({"team": {"id": "9", "displayName": "T9"}, "categories": []})
        assert team_ids(qualified_teams(data)) == {"0", "1", "9"}

    def test_no_column_for_games_keeps_everyone(self):
        data = {"categories": [{"name": "x", "names": ["a"], "displayNames": ["A"]}],
                "teams": [{"team": {"id": "1"}, "categories": []}, {"team": {"id": "2"}, "categories": []}]}
        assert team_ids(qualified_teams(data)) == {"1", "2"}

    def test_a_pro_league_is_never_filtered(self):
        """In a season's first days a team with one game can sit behind one with three."""
        data = load("byteam_NHL.json")
        names = next(m["names"] for m in data["categories"] if m["name"] == "general")
        block = next(c for c in data["teams"][0]["categories"] if c["name"] == "general")
        block["values"][names.index("games")] = 1
        count = len(data["teams"])
        general = next(c for c in parse_team_stats(data, "hockey") if c["category"] == "General")
        assert len(general["stats"]) == count
        general = next(c for c in parse_team_stats(data, "hockey", college=True) if c["category"] == "General")
        assert len(general["stats"]) == count - 1


class TestBadShapes:
    @pytest.mark.parametrize("data", [None, [], {}, {"teams": None}, {"teams": [None]}, {"categories": None, "teams": [{}]}])
    def test_nothing_usable_is_nothing(self, data):
        assert parse_team_stats(data, "basketball") == []
        assert parse_team_stats(data, "basketball", college=True) == []

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

    def test_the_games_column_can_be_short(self):
        data = load("byteam_NCAAM_2026.json")
        for block in data["teams"][0]["categories"]:
            block["values"] = []
        assert qualified_teams(data)
