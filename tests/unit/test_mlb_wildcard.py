"""Tests for the MLB wild card standings (espn_api.get_mlb_wildcard_standings).

ESPN's responses are faked rather than fetched. These cover the parts where a
wrong answer misrepresents the playoff picture: which teams are shown as already
in, the order of the race, and the fact that ESPN's published `playoffSeed` is
preserved rather than re-derived from win percentage.

The source is ESPN's standings endpoint with `type=1`, which returns the 12
non-division-leaders per league. The three teams present in the default
standings but absent from that list are the division leaders.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import espn_api  # noqa: E402


def entry(team_id, name, abbr, wins, losses, pct, seed=None, gb="-", streak="W1"):
    stats = [
        {"name": "wins", "value": wins, "displayValue": str(wins)},
        {"name": "losses", "value": losses, "displayValue": str(losses)},
        {"name": "winPercent", "value": pct, "displayValue": f"{pct:.3f}".lstrip("0")},
        {"name": "streak", "value": 1, "displayValue": streak},
        {"name": "gamesBehind", "value": 0.0, "displayValue": gb},
        # divisionGamesBehind is a *different* race; it must never be shown here.
        {"name": "divisionGamesBehind", "value": 99.0, "displayValue": "99.0"},
    ]
    if seed is not None:
        stats.append({"name": "playoffSeed", "value": seed, "displayValue": str(seed)})
    return {
        "team": {"id": str(team_id), "displayName": name, "abbreviation": abbr},
        "stats": stats,
    }


# Three leaders + four in the race. Ranks 2 and 3 are tied on win percentage and
# listed out of order, so the test fails if the code re-sorts by record.
RACE = [
    entry(1, "Boston Red Sox", "BOS", 75, 63, 0.543, seed=3, gb="0.5"),
    entry(2, "New York Yankees", "NYY", 78, 60, 0.565, seed=1, gb="+8.5"),
    entry(3, "Seattle Mariners", "SEA", 75, 63, 0.543, seed=2, gb="-"),
    entry(4, "Detroit Tigers", "DET", 63, 74, 0.460, seed=4, gb="6.0"),
]
LEADERS = [
    entry(10, "Tampa Bay Rays", "TB", 82, 55, 0.599),
    entry(11, "Houston Astros", "HOU", 70, 68, 0.507),
    entry(12, "Chicago White Sox", "CHW", 72, 65, 0.526),
]


def league(name, entries):
    return {"name": name, "standings": {"entries": entries}}


RACE_PAYLOAD = {"children": [league("American League", RACE)]}
# The overall request is by division (level=3): each league holds its divisions, which hold the
# teams, so a leader's division is the group ESPN puts it in.
OVERALL_PAYLOAD = {"children": [{"name": "American League", "children": [
    league("American League East", [RACE[0], RACE[1], LEADERS[0]]),
    league("American League Central", [RACE[3], LEADERS[2]]),
    league("American League West", [RACE[2], LEADERS[1]]),
]}]}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def fetch(race=RACE_PAYLOAD, overall=OVERALL_PAYLOAD, status_code=200):
    """The code issues the type=1 request first, then the level=3 one."""
    responses = [FakeResponse(race, status_code), FakeResponse(overall, status_code)]
    with patch("espn_api.requests.get", side_effect=responses):
        return espn_api.get_mlb_wildcard_standings()


def test_division_leaders_are_whoever_the_wildcard_table_omits():
    al = fetch()["AL"]
    leaders = [t for t in al if t["wc_position"] == "-"]

    # Sorted by record, best first.
    assert [t["team_name"] for t in leaders] == [
        "Tampa Bay Rays", "Chicago White Sox", "Houston Astros",
    ]
    assert al[:3] == leaders, "leaders must sort ahead of the race"
    assert [t["wc_status"] for t in leaders] == [
        "AL East leader", "AL Central leader", "AL West leader",
    ]


def test_race_keeps_espn_seed_not_win_percentage():
    """Seeds 2 and 3 are tied on record; ESPN's order must survive."""
    race = [t for t in fetch()["AL"] if t["wc_position"] != "-"]

    assert [t["wc_position"] for t in race] == ["1", "2", "3", "4"]
    assert [t["team_name"] for t in race] == [
        "New York Yankees", "Seattle Mariners", "Boston Red Sox", "Detroit Tigers",
    ]


def test_only_the_top_three_are_marked_as_holding_a_spot():
    race = [t for t in fetch()["AL"] if t["wc_position"] != "-"]

    assert [t["wc_status"] for t in race[:3]] == ["Wild card 1", "Wild card 2", "Wild card 3"]
    assert race[3]["wc_status"] == "", "4th place must not read as being in"


def test_games_back_is_the_wildcard_race_not_the_division_race():
    al = fetch()["AL"]
    race = {t["team_name"]: t for t in al if t["wc_position"] != "-"}

    assert race["New York Yankees"]["games_back"] == "+8.5"
    assert race["Seattle Mariners"]["games_back"] == "-"
    # divisionGamesBehind is 99.0 in every fixture row; it must never leak through.
    assert all(t["games_back"] != "99.0" for t in al)
    # Division leaders have no wild card deficit to show.
    assert all(t["games_back"] == "-" for t in al if t["wc_position"] == "-")


def test_row_carries_the_fields_the_standings_table_reads():
    row = fetch()["AL"][0]

    for key in ("team_name", "wins", "losses", "win_percentage", "games_back",
                "streak", "division", "wc_position", "wc_status"):
        assert key in row, f"missing {key}"
    assert row["wins"] == 82 and row["losses"] == 55
    assert row["division"] == "AL East"
    assert row["streak"] == "W1"


def test_the_overall_request_is_by_division_and_labels_the_race_too():
    responses = [FakeResponse(RACE_PAYLOAD), FakeResponse(OVERALL_PAYLOAD)]
    with patch("espn_api.requests.get", side_effect=responses) as get:
        al = espn_api.get_mlb_wildcard_standings()["AL"]
    assert get.call_args_list[1].kwargs["params"] == {"level": 3}
    divisions = {t["team_name"]: t["division"] for t in al}
    assert divisions["Seattle Mariners"] == "AL West"
    assert divisions["Detroit Tigers"] == "AL Central"


def test_a_leader_espn_puts_in_no_division_reads_as_a_division_leader():
    overall = {"children": [league("American League", RACE + LEADERS)]}
    leaders = [t for t in fetch(overall=overall)["AL"] if t["wc_position"] == "-"]
    assert [t["wc_status"] for t in leaders] == ["American League leader"] * 3


def test_league_with_no_race_entries_is_omitted():
    result = fetch()
    assert "AL" in result
    assert "NL" not in result, "an empty league should not produce an empty tab"


@pytest.mark.parametrize("payload,status", [
    ({"children": []}, 200),
    ({}, 200),
    ({"children": []}, 500),
])
def test_failures_return_empty_rather_than_raising(payload, status):
    assert fetch(race=payload, overall=payload, status_code=status) == {}


def test_network_error_returns_empty():
    with patch("espn_api.requests.get", side_effect=OSError("no network")):
        assert espn_api.get_mlb_wildcard_standings() == {}


def test_missing_leaders_still_produces_the_race():
    """If the default standings call returns nothing usable, show the race alone
    rather than dropping the tab entirely."""
    al = fetch(overall={"children": [league("American League", [])]})["AL"]
    assert len(al) == 4
    assert all(t["wc_position"] != "-" for t in al)
