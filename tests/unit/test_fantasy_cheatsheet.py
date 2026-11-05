"""Tests for the fantasy cheatsheet data layer (espn_api.get_fantasy_cheatsheet).

The feed is faked rather than fetched. These cover the parts where a wrong
answer silently produces a plausible-looking but useless draft board: picking
the wrong season's projections, scoring the projected stat line, dropping
non-fantasy positions, and the draftable-pool cutoff.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import espn_api  # noqa: E402


def projected_set(season, stats):
    """A projected full-season stat set as the fantasy feed shapes it."""
    return {
        "statSourceId": 1,
        "statSplitTypeId": 0,
        "scoringPeriodId": 0,
        "seasonId": season,
        "stats": stats,
    }


def raw_player(**overrides):
    player = {
        "id": 4429795,
        "fullName": "Jahmyr Gibbs",
        "defaultPositionId": 2,          # RB
        "proTeamId": 8,                  # DET
        "injuryStatus": "ACTIVE",
        "ownership": {"averageDraftPosition": 1.75, "auctionValueAverage": 63.76},
        "draftRanksByRankType": {"PPR": {"rank": 1}, "STANDARD": {"rank": 1}},
        "stats": [projected_set(2026, {"24": 1000.0, "25": 10.0, "42": 500.0,
                                       "43": 4.0, "53": 60.0, "72": 1.0})],
    }
    player.update(overrides)
    return player


class TestProjection:
    def test_scores_the_projected_stat_line(self):
        # 1000 rush yds (100) + 10 rush TD (60) + 500 rec yds (50)
        # + 4 rec TD (24) - 1 fumble lost (2) = 232, receptions carried separately.
        base, receptions = espn_api._fantasy_projection(raw_player(), 2026)
        assert base == pytest.approx(232.0)
        assert receptions == pytest.approx(60.0)

    def test_passing_stats_score_at_espn_default_rates(self):
        player = raw_player(stats=[projected_set(2026, {"3": 5000.0, "4": 40.0, "20": 15.0})])
        # 5000 pass yds (200) + 40 pass TD (160) - 15 INT (30) = 330
        base, receptions = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(330.0)
        assert receptions == 0

    def test_matches_the_requested_season_not_the_first_set(self):
        # The feed carries a projected set for the prior season too, and the
        # order is not stable. Taking the first match returns last year's board.
        player = raw_player(stats=[
            projected_set(2025, {"24": 100.0}),
            projected_set(2026, {"24": 1000.0}),
        ])
        base, _ = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(100.0)  # 1000 rushing yards, from the 2026 set

    def test_no_projection_for_the_season_returns_none(self):
        player = raw_player(stats=[projected_set(2024, {"24": 1000.0})])
        assert espn_api._fantasy_projection(player, 2026) == (None, 0)

    def test_ignores_weekly_and_actual_stat_sets(self):
        player = raw_player(stats=[
            {"statSourceId": 0, "statSplitTypeId": 0, "scoringPeriodId": 0,
             "seasonId": 2026, "stats": {"24": 9999.0}},          # actuals, not projections
            {"statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 5,
             "seasonId": 2026, "stats": {"24": 9999.0}},          # a single week
            projected_set(2026, {"24": 1000.0}),
        ])
        base, _ = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(100.0)

    def test_empty_stat_dict_is_skipped(self):
        player = raw_player(stats=[
            projected_set(2026, {}),
            projected_set(2026, {"24": 1000.0}),
        ])
        base, _ = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(100.0)


class TestMapping:
    def test_maps_a_draftable_player(self):
        row = espn_api._map_fantasy_player(raw_player(), 2026, 800)
        assert row["id"] == "4429795"
        assert row["name"] == "Jahmyr Gibbs"
        assert row["position"] == "RB"
        assert row["team"] == "DET"
        assert row["ppr_rank"] == 1
        assert row["adp"] == pytest.approx(1.75)
        assert row["auction"] == pytest.approx(63.76)
        assert row["injury"] == ""

    def test_drops_non_fantasy_positions(self):
        # 9 is a defensive end: ranked in ESPN's overall board, not draftable here.
        assert espn_api._map_fantasy_player(raw_player(defaultPositionId=9), 2026, 800) is None

    def test_drops_players_outside_an_explicit_cap(self):
        deep = raw_player(draftRanksByRankType={"PPR": {"rank": 900}, "STANDARD": {"rank": 950}})
        assert espn_api._map_fantasy_player(deep, 2026, 800) is None

    def test_no_cap_by_default(self):
        # ESPN's overall rank is not an ordering of draft relevance: Ricky
        # Pearsall sits at 1507 and Tyreek Hill at 1899, both rostered in real
        # leagues. Any cutoff silently hides players people are drafting.
        deep = raw_player(fullName="Ricky Pearsall",
                          draftRanksByRankType={"PPR": {"rank": 1507}})
        row = espn_api._map_fantasy_player(deep, 2026)
        assert row is not None
        assert row["ppr_rank"] == 1507

    def test_inactive_players_are_dropped(self):
        # ESPN keeps ranking retirees; all of them are owned in 0.0% of leagues.
        retired = raw_player(fullName="Matthew Slater", active=False)
        assert espn_api._map_fantasy_player(retired, 2026) is None

    def test_a_player_without_an_active_flag_is_kept(self):
        player = raw_player()
        player.pop("active", None)
        assert espn_api._map_fantasy_player(player, 2026) is not None

    def test_keeps_a_player_ranked_in_either_format(self):
        # Ranked deep in PPR but early in Standard — a Standard league still drafts them.
        row = espn_api._map_fantasy_player(
            raw_player(draftRanksByRankType={"PPR": {"rank": 900}, "STANDARD": {"rank": 40}}),
            2026, 800)
        assert row is not None
        assert row["ppr_rank"] == 900
        assert row["standard_rank"] == 40

    def test_unranked_player_is_dropped(self):
        assert espn_api._map_fantasy_player(raw_player(draftRanksByRankType={}), 2026, 800) is None

    def test_zero_rank_counts_as_unranked(self):
        unranked = raw_player(draftRanksByRankType={"PPR": {"rank": 0}, "STANDARD": {"rank": 0}})
        assert espn_api._map_fantasy_player(unranked, 2026, 800) is None

    def test_defense_gets_a_synthetic_id_and_no_projection(self):
        # A defense's raw stat line uses points/yards-allowed tiers the offensive
        # scoring table cannot price, so it is left unscored rather than wrong.
        dst = raw_player(defaultPositionId=16, proTeamId=7, fullName="Broncos D/ST",
                         stats=[projected_set(2026, {"89": 1.0, "127": 5000.0})])
        row = espn_api._map_fantasy_player(dst, 2026, 800)
        assert row["id"] == "dst-7"
        assert row["position"] == "D/ST"
        assert row["team"] == "DEN"
        assert row["proj_base"] is None

    def test_kicker_is_left_unscored(self):
        kicker = raw_player(defaultPositionId=5,
                            stats=[projected_set(2026, {"83": 35.0, "86": 46.0})])
        assert espn_api._map_fantasy_player(kicker, 2026, 800)["proj_base"] is None

    def test_rookie_has_no_prior_season(self):
        rookie = raw_player(stats=[projected_set(2026, {"24": 500.0})])
        assert espn_api._map_fantasy_player(rookie, 2026, 800)["rookie"] is True

    def test_veteran_carries_a_prior_season(self):
        # raw_player's default stat line is 2026-only, so add last year's.
        veteran = raw_player(stats=[
            projected_set(2025, {"24": 900.0}),
            projected_set(2026, {"24": 1000.0}),
        ])
        assert espn_api._map_fantasy_player(veteran, 2026, 800)["rookie"] is False

    def test_no_stats_at_all_is_not_called_a_rookie(self):
        # Nothing to judge on. Guessing here would flag every player the feed
        # happens to carry no stat block for.
        assert espn_api._map_fantasy_player(raw_player(stats=[]), 2026, 800)["rookie"] is False

    def test_defense_is_never_a_rookie(self):
        dst = raw_player(defaultPositionId=16, proTeamId=7, fullName="Broncos D/ST",
                         stats=[projected_set(2026, {"89": 1.0})])
        assert espn_api._map_fantasy_player(dst, 2026, 800)["rookie"] is False

    def test_prior_season_from_a_weekly_split_still_counts(self):
        # Rookie detection looks at every stat set, not just projected ones.
        veteran = raw_player(stats=[
            {"statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": 5,
             "seasonId": 2025, "stats": {"24": 60.0}},
            projected_set(2026, {"24": 1000.0}),
        ])
        assert espn_api._map_fantasy_player(veteran, 2026, 800)["rookie"] is False

    def test_free_agent_team_id(self):
        assert espn_api._map_fantasy_player(raw_player(proTeamId=0), 2026, 800)["team"] == "FA"

    def test_injury_designations_are_title_cased(self):
        row = espn_api._map_fantasy_player(raw_player(injuryStatus="INJURY_RESERVE"), 2026, 800)
        assert row["injury"] == "Injury Reserve"

    def test_active_is_not_an_injury(self):
        assert espn_api._normalize_fantasy_injury("ACTIVE") == ""
        assert espn_api._normalize_fantasy_injury(None) == ""
        assert espn_api._normalize_fantasy_injury("QUESTIONABLE") == "Questionable"


class TestCheatsheetLoad:
    def test_sorts_by_ppr_rank(self):
        feed = [
            raw_player(id=2, fullName="Second", draftRanksByRankType={"PPR": {"rank": 5}}),
            raw_player(id=1, fullName="First", draftRanksByRankType={"PPR": {"rank": 2}}),
        ]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            board = espn_api.get_fantasy_cheatsheet(season=2026)
        assert [p["name"] for p in board["players"]] == ["First", "Second"]
        assert board["season"] == 2026

    def test_falls_back_to_the_prior_season_when_empty(self):
        # In the deep offseason ESPN has not populated the new season yet.
        prior = [raw_player(id=n, draftRanksByRankType={"PPR": {"rank": n}})
                 for n in range(1, 61)]
        responses = [[], prior]

        def fake_get(*_args, **_kwargs):
            response = type("R", (), {"status_code": 200})()
            response.json = lambda payload=responses.pop(0): payload
            return response

        with patch.object(espn_api.requests, "get", side_effect=fake_get):
            board = espn_api.get_fantasy_cheatsheet(season=2026)
        assert board["season"] == 2025
        assert len(board["players"]) == 60

    def test_deeply_ranked_players_survive_the_whole_pipeline(self):
        # The regression this guards: a rank cutoff reintroduced anywhere between
        # the feed and the board would silently hide Ricky Pearsall (rank 1507,
        # rostered in a third of ESPN leagues) all over again. The other tests
        # call _map_fantasy_player directly and would not notice.
        feed = [
            raw_player(id=1, fullName="Jahmyr Gibbs", draftRanksByRankType={"PPR": {"rank": 1}}),
            raw_player(id=2, fullName="Ricky Pearsall",
                       draftRanksByRankType={"PPR": {"rank": 1507}}),
            raw_player(id=3, fullName="Tyreek Hill",
                       draftRanksByRankType={"PPR": {"rank": 1899}}),
        ]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            board = espn_api.get_fantasy_cheatsheet(season=2026)
        assert [p["name"] for p in board["players"]] == [
            "Jahmyr Gibbs", "Ricky Pearsall", "Tyreek Hill"]

    def test_board_ranks_are_dense(self):
        # ESPN's published rank orders a far larger pool — IDP players, punters,
        # the 32 Team QB slots — so raw it runs 1..2565 with 1,539 holes and
        # jumps like 36 -> 69. The board numbers itself 1, 2, 3 with no gaps
        # while keeping ESPN's order and their published rank.
        feed = [
            raw_player(id=1, fullName="First", draftRanksByRankType={"PPR": {"rank": 36}}),
            raw_player(id=2, fullName="Second", draftRanksByRankType={"PPR": {"rank": 69}}),
            raw_player(id=3, fullName="Third", draftRanksByRankType={"PPR": {"rank": 978}}),
        ]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            players = espn_api.get_fantasy_cheatsheet(season=2026)["players"]

        assert [p["ppr_board_rank"] for p in players] == [1, 2, 3]
        assert [p["ppr_rank"] for p in players] == [36, 69, 978]

    def test_board_ranks_are_numbered_per_format(self):
        # A player can sit higher on one board than the other, so the two dense
        # numberings are computed independently.
        feed = [
            raw_player(id=1, fullName="PPR favourite",
                       draftRanksByRankType={"PPR": {"rank": 10}, "STANDARD": {"rank": 90}}),
            raw_player(id=2, fullName="Standard favourite",
                       draftRanksByRankType={"PPR": {"rank": 20}, "STANDARD": {"rank": 30}}),
        ]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            by_name = {p["name"]: p for p in
                       espn_api.get_fantasy_cheatsheet(season=2026)["players"]}

        assert by_name["PPR favourite"]["ppr_board_rank"] == 1
        assert by_name["PPR favourite"]["standard_board_rank"] == 2
        assert by_name["Standard favourite"]["standard_board_rank"] == 1

    def test_a_player_ranked_in_one_format_only(self):
        feed = [raw_player(id=1, draftRanksByRankType={"PPR": {"rank": 5}})]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            player = espn_api.get_fantasy_cheatsheet(season=2026)["players"][0]
        assert player["ppr_board_rank"] == 1
        assert player["standard_board_rank"] is None

    def test_placeholder_adp_is_cleared(self):
        # ESPN gives undrafted players an ADP just past the end of a real draft
        # rather than omitting it. Left in place it reads as a real draft slot,
        # and the sub-decimal jitter defeats the rank tiebreak when sorting.
        feed = [raw_player(id=n, fullName=f"Real {n}",
                           draftRanksByRankType={"PPR": {"rank": n}},
                           ownership={"averageDraftPosition": float(n),
                                      "auctionValueAverage": 1.0})
                for n in range(1, 11)]
        feed += [raw_player(id=100 + n, fullName=f"Undrafted {n}",
                            draftRanksByRankType={"PPR": {"rank": 500 + n}},
                            ownership={"averageDraftPosition": 170.0 + n / 100.0,
                                       "auctionValueAverage": 0.0})
                 for n in range(60)]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            board = espn_api.get_fantasy_cheatsheet(season=2026)

        by_name = {p["name"]: p for p in board["players"]}
        assert by_name["Real 5"]["adp"] == pytest.approx(5.0)
        assert all(by_name[f"Undrafted {n}"]["adp"] is None for n in range(60))

    def test_a_pool_with_no_placeholder_is_left_alone(self):
        # Nothing is shared by a large slice of the pool, so nothing is stripped.
        feed = [raw_player(id=n, fullName=f"P{n}",
                           draftRanksByRankType={"PPR": {"rank": n}},
                           ownership={"averageDraftPosition": float(n) * 3,
                                      "auctionValueAverage": 1.0})
                for n in range(1, 61)]
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 200
            fake_requests.get.return_value.json.return_value = feed
            board = espn_api.get_fantasy_cheatsheet(season=2026)
        assert all(p["adp"] is not None for p in board["players"])

    def test_server_failure_propagates(self):
        # Both the season and the fallback fail: the dialog must say the feed is
        # down, not "ESPN has not published this season yet".
        with patch.object(espn_api, "requests") as fake_requests:
            fake_requests.get.return_value.status_code = 503
            with pytest.raises(espn_api.ApiError, match="Try again"):
                espn_api.get_fantasy_cheatsheet(season=2026)

    def test_missing_upcoming_season_falls_back(self):
        # ESPN 404s the new season's URL until it creates it.
        prior = [raw_player(id=n, draftRanksByRankType={"PPR": {"rank": n}})
                 for n in range(1, 61)]
        statuses = [404, 200]

        def fake_get(*_args, **_kwargs):
            response = type("R", (), {"status_code": statuses.pop(0)})()
            response.json = lambda: prior
            return response

        with patch.object(espn_api.requests, "get", side_effect=fake_get):
            board = espn_api.get_fantasy_cheatsheet(season=2026)
        assert board["season"] == 2025
        assert len(board["players"]) == 60

    def test_two_point_conversions_are_scored(self):
        player = raw_player(stats=[projected_set(2026, {"19": 2.0, "26": 3.0, "44": 1.0})])
        base, _ = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(12.0)

    def test_null_stat_value_does_not_raise(self):
        player = raw_player(stats=[projected_set(2026, {"24": None, "25": 2.0, "53": None})])
        base, receptions = espn_api._fantasy_projection(player, 2026)
        assert base == pytest.approx(12.0)
        assert receptions == 0
