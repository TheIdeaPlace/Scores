"""One bad field at a time: every data function against its real payload with each
field in turn missing, null, or an empty list. None may raise, and none may turn
the gap into the text "None". ESPN does send nulls, and a field's absence shouldn't
cost the user the rest of the screen.
"""
import datetime

import pytest

import espn_api

from .support import HTTP_404, load, mutations


def case(name, call, fixture, route, others=None):
    return pytest.param(call, fixture, route, others or {}, id=name)


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_in(item)


def live_golf():
    """The saved tournament hadn't started; get_live_golf_tournament only reads one in progress."""
    data = load("golf_scoreboard_PGA.json")
    data["events"][0]["competitions"][0]["status"]["type"]["state"] = "in"
    return data


CASES = [
    case("get_scores", lambda: espn_api.get_scores("NBA"), "scoreboard_events_by_status.json", "/scoreboard"),
    case("get_world_cup_scores_range",
         lambda: espn_api.get_world_cup_scores_range("WC2026", datetime.date(2026, 6, 20), datetime.date(2026, 6, 20)),
         "worldcup_scoreboard_20260620.json", "/scoreboard"),
    case("get_news", lambda: espn_api.get_news("NFL"), "news_NFL.json", "/news"),
    case("get_team_news", lambda: espn_api.get_team_news("NFL", "9"), "team_news_NFL_9.json", "/news"),
    case("get_team_schedule NFL", lambda: espn_api.get_team_schedule("NFL", "9"), "schedule_NFL_9.json", "/schedule"),
    case("get_team_schedule NBA", lambda: espn_api.get_team_schedule("NBA", "15"), "schedule_NBA_15.json", "/schedule"),
    case("get_team_schedule MLB", lambda: espn_api.get_team_schedule("MLB", "10"), "schedule_MLB_10.json", "/schedule"),
    case("get_team_schedule NCAAM", lambda: espn_api.get_team_schedule("NCAAM", "275"), "schedule_NCAAM_275.json", "/schedule"),
    case("game details NFL", lambda: espn_api.extract_meaningful_game_info(espn_api.get_game_details("NFL", "1")),
         "details_NFL_pieces.json", "/summary"),
    case("game details NCAAH", lambda: espn_api.extract_meaningful_game_info(espn_api.get_game_details("NCAAH", "1")),
         "details_NCAAH_pieces.json", "/summary"),
    case("get_live_golf_tournament", lambda: espn_api.get_live_golf_tournament("PGA"), live_golf, "/scoreboard"),
    case("get_golf_leaderboard", lambda: espn_api.get_golf_leaderboard("PGA"), "golf_scoreboard_PGA.json", "/scoreboard"),
    case("get_golf_schedule", lambda: espn_api.get_golf_schedule("PGA"), "golf_schedule_PGA.json", "/scoreboard"),
    case("get_draft_round", lambda: espn_api.get_draft_round(2026, 1), "draft_NFL_2026.json:rounds", "/draft/rounds",
         {"/teams": "teams_NFL.json"}),
    case("get_draft", lambda: espn_api.get_draft(2026), "draft_NFL_2026.json:draft", "/draft$",
         {"/draft/rounds": "draft_NFL_2026.json:rounds", "/draft/status": "draft_NFL_2026.json:status"}),
    case("get_team_info NFL", lambda: espn_api.get_team_info("NFL", "9"), "team_NFL_9.json", "/teams/9"),
    case("get_team_info NHL", lambda: espn_api.get_team_info("NHL", "129764"), "team_NHL_utah.json", "/teams/129764"),
    case("get_team_roster", lambda: espn_api.get_team_roster("NFL", "9"), "roster_NFL_9.json", "/roster"),
    case("get_team_roster flat", lambda: espn_api.get_team_roster("NBA", "15"), "roster_NBA_15.json", "/roster"),
    case("get_transactions", lambda: espn_api.get_transactions("NFL"), "transactions_NFL.json", "/transactions"),
    case("get_team_transactions", lambda: espn_api.get_team_transactions("NFL", "9"), "transactions_NFL_9.json", "/transactions"),
    case("get_rankings", lambda: espn_api.get_rankings("NCAAF"), "rankings_NCAAF.json", "/rankings"),
    case("get_world_cup_standings", lambda: espn_api.get_world_cup_standings("WC2026"), "worldcup_standings_WC2026.json", "/standings"),
    case("get_standings MLB", lambda: espn_api.get_standings("MLB"), "standings_MLB.json", "/standings"),
    case("get_standings NFL", lambda: espn_api.get_standings("NFL"), "standings_NFL.json", "/standings"),
    case("get_standings NHL", lambda: espn_api.get_standings("NHL"), "standings_NHL.json", "/standings"),
    case("get_standings NCAAH", lambda: espn_api.get_standings("NCAAH"), "standings_NCAAH.json", "/standings"),
    case("get_standings soccer", lambda: espn_api.get_standings("EPL"), "team_EPL_359.json", r"/teams/\d+$",
         {"/teams$": "teams_EPL.json"}),
    case("get_player_statistics", lambda: espn_api.get_player_statistics("NCAAM"), "statistics_NCAAM.json", "/statistics"),
    case("get_statistics", lambda: espn_api.get_statistics("NFL"), "statistics_NFL.json", "/statistics"),
    case("get_team_statistics", lambda: espn_api.get_team_statistics("NBA"), "team_stats_NBA_15.json", r"/statistics",
         {"/teams$": "teams_NBA.json"}),
]


def payload(spec):
    """A function, "file.json", or "file.json:key" for one piece of a bundle."""
    if callable(spec):
        return spec()
    name, _, key = spec.partition(":")
    data = load(name)
    return data[key] if key else data


@pytest.mark.parametrize("call,fixture,route,others", CASES)
def test_no_single_bad_field_raises_or_reads_none(espn, call, fixture, route, others):
    espn.on(".*", HTTP_404)
    for pattern, spec in others.items():
        espn.on(pattern, payload(spec))
    served = {"payload": payload(fixture)}
    espn.on(route, lambda url: served["payload"])
    # The sweep proves nothing if the real payload already comes back empty.
    assert call(), "the unmodified payload should produce a result"

    failures = []
    for description, changed in mutations(served["payload"]):
        served["payload"] = changed
        try:
            result = call()
        except Exception as e:
            failures.append(f"{description}: raised {type(e).__name__}: {e}")
            continue
        if "None" in strings_in(result):
            failures.append(f"{description}: the text None in {result}")
    assert not failures, "\n".join(failures[:20])
