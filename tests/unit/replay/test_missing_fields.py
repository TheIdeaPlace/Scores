"""One bad field at a time: every data function against its real payload with each
field in turn missing, null, or an empty list. None may raise, none may put the word
None in its text, and none may hand a screen a None for a field it shows. ESPN does
send nulls, and a field's absence shouldn't cost the user the rest of the screen.
`.get(key, default)` is no help: with the key present and null, it returns None.
"""
import datetime
import re

import pytest

import espn_api
from services.venue_service import VenueService, venue_summary

from .support import HTTP_404, load, mutations


def case(name, call, fixture, route, others=None):
    return pytest.param(call, fixture, route, others or {}, id=name)


NONE_WORD = re.compile(r"\bNone\b")

# None on purpose: the screens test these for "not set", or never show them.
MAY_BE_NONE = {"position", "playoff_seed", "clinch_status", "magic_number", "number"}

# ESPN's own data handed on untouched: the screen reading it has to cope, not this.
RAW_FIELDS = {"competitions", "polls"}


def none_problems(value, path=""):
    """Every string with the word None in it, and every None a screen might show."""
    if isinstance(value, str):
        if NONE_WORD.search(value):
            yield f"{path}: {value!r}"
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in RAW_FIELDS:
                if item is None and key not in MAY_BE_NONE:
                    yield f"{path}.{key}: None"
                yield from none_problems(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from none_problems(item, f"{path}[{index}]")


def summary_lines():
    """What format_complex_data makes of each field of a game summary."""
    details = espn_api.get_game_details("NFL", "1")
    return [espn_api.format_complex_data(key, details.get(source))
            for key, source in (("gameInfo", "gameInfo"), ("odds", "pickcenter"), ("broadcasts", "broadcasts"), ("injuries", "injuries"))]


def venue_facts():
    """A venue list, and the details and facts of each venue on it."""
    service = VenueService()
    venues = service.get_venues_for_league("mlb").values()
    return [service.venue_details(venue, "mlb") for venue in venues] + [venue_summary(venue) for venue in venues]


def scoreboard_with_one_team():
    """A real NWSL board with the same team in both games, as the last-resort schedule
    path reads it, a month at a time."""
    data = load("scoreboard_NWSL.json")
    for event in data["events"]:
        event["competitions"][0]["competitors"][0]["team"]["id"] = "TEAM"
    return data


def scoreboard_schedule():
    return espn_api.parse_schedule_from_api(f"{espn_api.BASE_URL}/soccer/usa.nwsl/scoreboard", "TEAM", datetime.datetime(2026, 10, 3))


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
    case("get_team_schedule WNBA", lambda: espn_api.get_team_schedule("WNBA", "8"), "schedule_WNBA_8_post.json", "/schedule"),
    case("get_team_schedule postseason", lambda: espn_api.get_team_schedule("NFL", "26"), "schedule_NFL_26_post.json", "/schedule"),
    case("get_team_schedule preseason", lambda: espn_api.get_team_schedule("NFL", "26"), "schedule_NFL_26_pre.json", "/schedule"),
    case("get_team_schedule soccer", lambda: espn_api.get_team_schedule("EPL", "359"), "schedule_EPL_359_results.json", "/schedule"),
    case("get_team_schedule soccer cup", lambda: espn_api.get_team_schedule("UCL", "359"), "schedule_UCL_359_2025.json", "/schedule"),
    case("parse_schedule_from_api", scoreboard_schedule, scoreboard_with_one_team, "/scoreboard"),
    case("game details NFL", lambda: espn_api.extract_meaningful_game_info(espn_api.get_game_details("NFL", "1")),
         "details_NFL_pieces.json", "/summary"),
    case("game details NCAAH", lambda: espn_api.extract_meaningful_game_info(espn_api.get_game_details("NCAAH", "1")),
         "details_NCAAH_pieces.json", "/summary"),
    case("format_complex_data", summary_lines, "details_NFL_pieces.json", "/summary"),
    case("venues", venue_facts, "scoreboard_NFL_202611.json", "/scoreboard"),
    case("get_live_golf_tournament", lambda: espn_api.get_live_golf_tournament("PGA"), live_golf, "/scoreboard"),
    case("get_golf_leaderboard", lambda: espn_api.get_golf_leaderboard("PGA"), "golf_scoreboard_PGA.json", "/scoreboard"),
    case("get_golf_schedule", lambda: espn_api.get_golf_schedule("PGA"), "golf_schedule_PGA.json", "/scoreboard"),
    case("get_draft_round", lambda: espn_api.get_draft_round(2026, 1), "draft_site_NFL_2026.json", "/draft"),
    case("get_draft", lambda: espn_api.get_draft(2026), "draft_site_NFL_2026.json", "/draft"),
    case("get_team_info NFL", lambda: espn_api.get_team_info("NFL", "9"), "team_NFL_9.json", "/teams/9",
         {"/season$": "season_NFL.json"}),
    case("get_team_info NHL", lambda: espn_api.get_team_info("NHL", "129764"), "team_NHL_utah.json", "/teams/129764",
         {"/season$": "season_NBA.json"}),
    case("get_team_info season", lambda: espn_api.get_team_info("WNBA", "8", home_venue=False), "season_WNBA.json", "/season$",
         {"/teams/8": "team_WNBA_8.json"}),
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
    case("get_standings WNBA", lambda: espn_api.get_standings("WNBA"), "standings_WNBA.json", "/standings"),
    case("get_standings soccer", lambda: espn_api.get_standings("EPL"), "standings_EPL.json", "/standings"),
    case("get_soccer_teams", lambda: espn_api.get_soccer_teams("CONCACAF"), "teams_CONCACAF.json", "/teams",
         {"/standings": "standings_CONCACAF.json"}),
    case("get_player_statistics soccer", lambda: espn_api.get_player_statistics("EPL")["player_stats"],
         "leaders_core_EPL.json", "/leaders",
         {"/season$": "season_EPL.json", "/athletes/": "core_athlete_EPL_253989.json",
          r"/seasons/\d+/teams/": "core_team_EPL_382.json"}),
    case("get_player_statistics",lambda: espn_api.get_player_statistics("NBA")["player_stats"], "leaders_v3_NBA.json", "/leaders",
         {"/season$": "season_NBA.json"}),
    case("get_team_statistics", lambda: espn_api.get_team_statistics("NBA")["team_stats"], "byteam_NBA.json", "/byteam",
         {"/season$": "season_NBA.json"}),
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
        espn_api._CORE_SEASON_CACHE.clear()
        espn_api._DRAFT_CACHE.clear()
        try:
            result = call()
        except Exception as e:
            failures.append(f"{description}: raised {type(e).__name__}: {e}")
            continue
        problems = list(none_problems(result))
        if problems:
            failures.append(f"{description}: {problems[:3]}")
    assert not failures, "\n".join(failures[:40])


def test_a_bad_game_on_the_scoreboard_schedule_path_keeps_the_next_one(espn):
    """Everything here runs inside one try, so anything that raises loses this game and
    every later one in the month, and comes back as [] with no sign of why."""
    served = {}
    espn.on("/scoreboard", lambda url: served["payload"])
    real = scoreboard_with_one_team()
    second_game = real["events"][1]["id"]
    served["payload"] = real
    assert second_game in {game["game_id"] for game in scoreboard_schedule()}

    lost = []
    for description, changed in mutations(real):
        if description.startswith("events.0"):
            served["payload"] = changed
            if second_game not in {game["game_id"] for game in scoreboard_schedule()}:
                lost.append(description)
    assert not lost, lost
