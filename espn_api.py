import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from exceptions import ApiError
from itertools import islice
import racing
import favorite_card
from game_labels import (best_odds, broadcast_names, format_height, format_weight,
                         injured_player_count, leader_display_value, local_schedule_datetime,
                         schedule_game_label)
import golf
from soccer import (SOCCER_LEAGUES, TORNEO_LEAGUES, _stat_number, leaders_season_types, parse_soccer_standings,
                    soccer_leader_lists, soccer_leaders_season)
import stat_glossary
from team_list import STANDINGS as TEAM_LIST_FROM_STANDINGS, parse_team_list, with_standings
from team_list import source as team_list_source
import team_stats
from team_stats import needs_team_list, parse_team_stats
from timezone_utils import convert_espn_time_to_local

# Every ESPN request gets a timeout. requests has none by default, so one
# stalled response would block its caller forever; several screens fetch on
# the UI thread, where that is a frozen window. Callers that need longer pass
# their own timeout=.
DEFAULT_TIMEOUT = 15


def _http_get(url, session=None, **kwargs):
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return (session or requests).get(url, **kwargs)


# ESPN sometimes sends null, or an empty list, where a dict or list belongs. A
# `.get(key, {})` default doesn't help when the key is there with a null in it.
def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    """The dicts in a list of them: nothing if it isn't a list, and no null elements."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


# A failed request says so, in a sentence a screen can read out: a timeout, a 5xx or a body that
# isn't JSON raises ApiError with one of these, so it can't read as there being nothing to show.
def _unavailable(what):
    return f"ESPN isn't providing {what} right now. Try again in a minute."


SCORES_UNAVAILABLE = _unavailable("scores")
NEWS_UNAVAILABLE = _unavailable("news")
GAME_UNAVAILABLE = _unavailable("this game")
POLLS_UNAVAILABLE = _unavailable("polls")
SCHEDULE_UNAVAILABLE = _unavailable("the schedule")
TEAM_UNAVAILABLE = _unavailable("this team")
ROSTER_UNAVAILABLE = _unavailable("the roster")
TRANSACTIONS_UNAVAILABLE = _unavailable("transactions")
DRAFT_UNAVAILABLE = _unavailable("the draft")
LEADERBOARD_UNAVAILABLE = _unavailable("the leaderboard")
FANTASY_UNAVAILABLE = _unavailable("the draft board")
RACE_UNAVAILABLE = _unavailable("this race")


def _espn_answer(unavailable, url, **kwargs):
    """ESPN's JSON object, or None for a 400 or 404, which say it has nothing there. Anything else
    that isn't an answer raises ApiError(unavailable), and that includes a 200 whose body is null or
    not an object: None here means ESPN said it has nothing. The iPhone tells them apart the same way."""
    try:
        resp = _http_get(url, **kwargs)
        answer = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        print(f"{url}: {e}")
        raise ApiError(unavailable) from e
    if resp.status_code in (400, 404):
        return None
    if resp.status_code != 200 or not isinstance(answer, dict):
        print(f"{url}: {resp.status_code}, not an answer")
        raise ApiError(unavailable)
    return answer


def _listed(body, key, unavailable):
    """The dicts in a body's list. Not there, or empty, is ESPN having none. A null where the
    list belongs, or a body that isn't an object at all, isn't an answer, so it says the same as a
    request that failed."""
    if not isinstance(body, dict) or (key in body and body[key] is None):
        raise ApiError(unavailable)
    return _dicts(body.get(key))


BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

LEAGUES = {
    "NFL": "football/nfl",
    "NBA": "basketball/nba",
    "MLB": "baseball/mlb",
    "NHL": "hockey/nhl",
    "WNBA": "basketball/wnba",
    "NCAAF": "football/college-football",
    "NCAAM": "basketball/mens-college-basketball",
    "NCAAWB": "basketball/womens-college-basketball",
    "NCAAH": "hockey/mens-college-hockey",
    "NCAAWH": "hockey/womens-college-hockey",
    "EPL":        "soccer/eng.1",
    "MLS":        "soccer/usa.1",
    "NWSL":       "soccer/usa.nwsl",
    "La Liga":    "soccer/esp.1",
    "Bundesliga": "soccer/ger.1",
    "Serie A":    "soccer/ita.1",
    "Ligue 1":    "soccer/fra.1",
    "UCL":        "soccer/uefa.champions",
    "UEL":        "soccer/uefa.europa",
    "Liga MX":    "soccer/mex.1",
    "CONCACAF":   "soccer/concacaf.champions",
    "PGA":        "golf/pga",
    "LPGA":       "golf/lpga",
    "WC2026":     "soccer/fifa.world",
    "WWC2027":    "soccer/fifa.wwc",
}

# ESPN's college football division id, per coverage setting. 80 is the Football Bowl
# Subdivision; 90 is all of Division I, FBS plus FCS. The scoreboard takes it as
# `groups=` and standings as singular `group=`; each ignores the other's spelling.
NCAAF_COVERAGE_GROUPS = {
    "fbs": "80",
    "all_d1": "90",
}


def _ncaaf_coverage_group():
    """The division id for the user's college football coverage setting."""
    import settings
    coverage = settings.get('ncaaf_coverage', 'all_d1')
    return NCAAF_COVERAGE_GROUPS.get(coverage, NCAAF_COVERAGE_GROUPS['all_d1'])


# Which college football conferences come first in Standings and Teams, under ESPN's names.
# All of FBS is here, and the FCS conferences follow alphabetically. ESPN splits the Sun
# Belt into East and West only when asked for FBS alone.
NCAAF_CONFERENCE_ORDER = (
    "Southeastern Conference", "Big Ten Conference", "Big 12 Conference",
    "Atlantic Coast Conference", "Pac-12 Conference", "American Conference",
    "Conference USA", "Mid-American Conference", "Mountain West Conference",
    "Sun Belt Conference", "Sun Belt - East", "Sun Belt - West",
    "FBS Independents",
)


# ESPN's college football scoreboard *doubles* `limit` internally on any query
# that is not a `dates=A-B` range: limit=5 returns 10 events, limit=50 returns
# 100. The effective (post-doubling) value must stay at or below 1000 — past
# that the page size collapses to 25, so limit=501 is worse than limit=250.
# 400 clears a 209-game Division I week on range queries while leaving the
# doubled shapes at 800, comfortably inside the ceiling.
NCAAF_SCOREBOARD_LIMIT = 400


# ESPN's "NCAA Division I" group for college basketball. Unlike football there is
# no FBS/FCS-style split to choose between — 52 is the root, 50 is Division I and
# 51 is everything that is not — so this needs no user setting, just the
# parameter. Without it a day returns roughly a seventh of the slate: 145 men's
# games become 21, and 122 women's become 4.
NCAAB_GROUP = "50"

# Basketball does not double `limit` the way college football does, and honours
# it exactly, so this is a straight ceiling on a day's games.
NCAAB_SCOREBOARD_LIMIT = 400

def college_scoreboard_params(league_key):
    """Extra scoreboard query parameters that give a college league its full slate.

    Returns [] for every other league, which ESPN already returns in full.

    `groups=` picks the division. Leave it off and a college football scoreboard
    collapses to 25 featured games when undated and to FBS-only when dated, and
    college basketball returns only a handful of featured games. `limit=` then
    lifts the page size far enough to hold the result.

    Football follows the user's coverage setting. Basketball has only the one division.
    """
    if league_key == "NCAAF":
        return [f"groups={_ncaaf_coverage_group()}", f"limit={NCAAF_SCOREBOARD_LIMIT}"]
    if league_key in ("NCAAM", "NCAAWB"):
        return [f"groups={NCAAB_GROUP}", f"limit={NCAAB_SCOREBOARD_LIMIT}"]
    return []


# Kept as the old name so nothing that imported it breaks.
ncaaf_scoreboard_params = college_scoreboard_params


def ncaaf_needs_fbs_retry(league_key, events):
    """True when an empty NCAAF response should be retried as FBS.

    ESPN returns *zero* events for a week-indexed postseason query under
    `groups=90` — `seasontype=3&groups=90` is empty where `groups=80` has all 46
    bowl games. That would blank the Bowls & Playoffs view, and the main
    scoreboard too once ESPN rolls the current week into the postseason.

    Since groups=90 is otherwise a strict superset of groups=80, an empty
    all-Division-I response is never legitimately better than the FBS one, so
    retrying costs nothing when the slate really is empty.
    """
    if league_key != "NCAAF" or events:
        return False
    import settings
    return settings.get('ncaaf_coverage', 'all_d1') != 'fbs'


# The sections of a scores list, in the order they're shown. Matches the iOS
# app: what is on now, what is on next, what finished, then games that did not
# take place. ESPN orders a scoreboard by kickoff, which on a college football
# Saturday interleaves all of these.
SCORE_SECTIONS = [
    ("in_progress", "In Progress"),
    ("upcoming", "Upcoming"),
    ("completed", "Completed"),
    ("postponed", "Postponed / Cancelled"),
]
_SECTION_RANK = {key: rank for rank, (key, _) in enumerate(SCORE_SECTIONS)}


def game_section(game):
    """Which SCORE_SECTIONS key a get_scores game belongs under.

    Postponed and cancelled are checked by status name before state, because
    ESPN reports them as "pre" or "post". Suspended games count as in
    progress: they are unfinished, not abandoned, and the partial score is
    worth reading.
    """
    name = game.get("status_name", "")
    if name in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"):
        return "postponed"
    if name == "STATUS_SUSPENDED":
        return "in_progress"
    state = game.get("state")
    if state == "in":
        return "in_progress"
    if state == "post":
        return "completed"
    return "upcoming"


def sort_games_by_section(games):
    """Order games by section, and by start date within each section.

    The sort is stable, so games with the same section and start keep
    ESPN's order.
    """
    return sorted(games, key=lambda g: (_SECTION_RANK[game_section(g)],
                                        g.get("date") or ""))


def _swap_to_fbs(url):
    """Rewrite an NCAAF scoreboard URL to ask for FBS instead of all Division I."""
    return url.replace(f"groups={NCAAF_COVERAGE_GROUPS['all_d1']}",
                       f"groups={NCAAF_COVERAGE_GROUPS['fbs']}")

# ESPN's standings endpoint takes a `type=` parameter that selects which table
# it returns. type=1 is the wild card view: the 12 non-division-leaders per
# league, with `playoffSeed` as the wild card rank and `gamesBehind` as games
# back of the last spot. The three teams present in the default (type=0)
# standings but absent from type=1 are exactly the division leaders.
MLB_STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings"
MLB_STANDINGS_TYPE_WILDCARD = 1

# Number of wild card berths per league.
MLB_WILDCARD_SPOTS = 3


def _mlb_stat(entry, name, default=""):
    """Display value of a named stat on an ESPN standings entry."""
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            return stat.get("displayValue") or default
    return default


def _mlb_stat_value(entry, name, default=0.0):
    for stat in entry.get("stats", []):
        if stat.get("name") == name:
            try:
                return float(stat.get("value", default))
            except (TypeError, ValueError):
                return default
    return default


def _mlb_wildcard_team(entry, status, position, games_back):
    """Normalise one ESPN standings entry into the dict the standings table wants."""
    team = entry.get("team", {}) or {}
    abbreviation = team.get("abbreviation") or ""
    league_name = "American" if abbreviation in _MLB_AL_ABBREVIATIONS else "National"
    return {
        "team_name": team.get("displayName") or "Unknown",
        "team_id": str(team.get("id") or ""),
        "abbreviation": abbreviation,
        "wins": int(_mlb_stat_value(entry, "wins")),
        "losses": int(_mlb_stat_value(entry, "losses")),
        "win_percentage": _mlb_stat(entry, "winPercent", "0.000"),
        "games_back": games_back,
        "streak": _mlb_stat(entry, "streak", "-"),
        "division": _get_team_division(abbreviation, league_name),
        "wc_position": position,
        "wc_status": status,
    }


_MLB_AL_ABBREVIATIONS = {
    "BAL", "BOS", "NYY", "TB", "TOR", "CHW", "CLE", "DET", "KC", "MIN",
    "HOU", "LAA", "OAK", "ATH", "SEA", "TEX",
}


def get_mlb_wildcard_standings():
    """Current MLB wild card picture, as {"AL": [...], "NL": [...]}.

    Each league's list is in display order: the three division leaders first
    (already holding a playoff spot), then the 12-team wild card race in ESPN's
    published `playoffSeed` order. The top three of that race hold the wild card
    berths; each team carries a `wc_status` saying which of those it is, so the
    playoff cut line is spoken rather than drawn.

    Returns {} on any failure, which the caller renders as "unavailable".
    """
    try:
        race_resp = _http_get(
            MLB_STANDINGS_URL,
            params={"type": MLB_STANDINGS_TYPE_WILDCARD},
            timeout=15,
        )
        overall_resp = _http_get(MLB_STANDINGS_URL, timeout=15)
        if race_resp.status_code != 200 or overall_resp.status_code != 200:
            return {}
        race_leagues = race_resp.json().get("children", [])
        overall_leagues = overall_resp.json().get("children", [])
    except Exception as e:
        print(f"[WARNING] MLB wild card standings unavailable: {e}")
        return {}

    overall_by_league = {
        lg.get("name", ""): (lg.get("standings", {}) or {}).get("entries", [])
        for lg in overall_leagues
    }

    result = {}
    for league in race_leagues:
        league_name = league.get("name", "")
        key = "AL" if league_name.startswith("American") else "NL"
        race_entries = (league.get("standings", {}) or {}).get("entries", [])
        if not race_entries:
            continue

        # Division leaders are whoever the wild card table leaves out.
        race_ids = {e.get("team", {}).get("id") for e in race_entries}
        leaders = [e for e in overall_by_league.get(league_name, [])
                   if e.get("team", {}).get("id") not in race_ids]

        ordered_leaders = []
        for entry in sorted(leaders,
                            key=lambda e: _mlb_stat_value(e, "winPercent"),
                            reverse=True):
            division = _get_team_division(
                entry.get("team", {}).get("abbreviation", ""),
                "American" if key == "AL" else "National")
            ordered_leaders.append(_mlb_wildcard_team(
                entry,
                status=f"{division} leader" if division else "Division leader",
                position="-",
                games_back="-",
            ))

        ordered_race = []
        for entry in sorted(race_entries,
                            key=lambda e: _mlb_stat_value(e, "playoffSeed", 99)):
            rank = int(_mlb_stat_value(entry, "playoffSeed"))
            status = f"Wild card {rank}" if 0 < rank <= MLB_WILDCARD_SPOTS else ""
            ordered_race.append(_mlb_wildcard_team(
                entry,
                status=status,
                position=str(rank) if rank else "-",
                games_back=_mlb_stat(entry, "gamesBehind", "-"),
            ))

        if ordered_leaders or ordered_race:
            result[key] = ordered_leaders + ordered_race
    return result

# Leagues whose ESPN season year is the year the season ends in: season=2027
# means the 2026-27 season. WNBA is deliberately not in this list — its ESPN
# season year is the calendar year it is played in.
YEAR_PLUS_ONE_LEAGUES = ("NBA", "NHL", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH")

def get_current_season_year(league_key):
    """The ESPN season year for the season that is current right now.

    ESPN labels the winter sports by the year the season *ends* in, so the
    2026-27 NHL season is season=2027, and it rolls the year over as soon as
    the previous season is finished rather than when the first game is played
    (the 2026-27 schedule was already published in July 2026). Football keeps
    the year the season starts in, so January and February still belong to the
    previous season year.
    """
    from datetime import datetime
    now = datetime.now()
    year, month = now.year, now.month

    if league_key in YEAR_PLUS_ONE_LEAGUES:
        # Previous season is over by June; the new schedule lands in July.
        return year + 1 if month >= 7 else year
    if league_key in ("NFL", "NCAAF"):
        # Season ends with the Super Bowl / bowl games in January-February.
        return year - 1 if month < 3 else year
    # MLB, WNBA and everything else run inside a single calendar year.
    return year


def scoreboard_months(start, end):
    """The YYYYMM values covering start..end, for scoreboard dates= queries.

    ESPN's scoreboard accepts a day (YYYYMMDD), a month (YYYYMM) or a year, but
    stopped accepting YYYYMMDD-YYYYMMDD ranges in September 2026 — every sport
    now answers a range with 400 "Failed to get events endpoint".
    """
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


# Leagues whose schedule comes one season type at a time. WNBA is here: ESPN's scoreboard,
# which it used to read, only reached 30 days either side of today and had no past seasons.
SEASON_TYPE_SCHEDULE_LEAGUES = ("NFL", "NCAAF", "MLB", "NBA", "NHL", "WNBA", "NCAAH", "NCAAWH", "NCAAM", "NCAAWB")


def _schedule_answer(url):
    """ESPN's answer to one team schedule request, or None for a 400 or 404, which say it
    has nothing there. Anything else, a timeout, a 5xx, a 403 or a 429, reaches the caller,
    and the dialog reports it: a schedule missing its playoffs or its games to come would
    look complete, and one missing everything would look like an off-season. The iPhone
    has the same rule, in ESPNAPIService.fetchTeamSchedulePage."""
    answer = _espn_answer(SCHEDULE_UNAVAILABLE, url)
    if answer is None:
        return None
    _listed(answer, "events", SCHEDULE_UNAVAILABLE)
    return answer


def _season_type_schedule_events(base_url, season_year, lenient=False):
    """Preseason, regular season and postseason, or None if ESPN has no regular season here.

    FCS playoffs are type 2, and a team that missed the postseason gets an empty list
    for type 3, not an error. The regular season comes first so a failure costs one request.

    `lenient` is for a caller that can use whatever part loaded, a favorite's card. The three
    are asked for at once, as on the iPhone. A part that fails is left out, but if no part
    has any games and one failed, it raises: an empty answer then may only be the failure,
    and mustn't read as a season not yet published. None means ESPN answered 400 or 404 for
    all three. The iPhone throws then too (ESPNAPIService.fetchTeamSeasonSchedule), so its
    card shows no games where this one falls back to last season.
    """
    if lenient:
        def ask(season_type):
            try:
                return _schedule_answer(f"{base_url}?season={season_year}&seasontype={season_type}"), None
            except ApiError as e:
                return None, e

        with ThreadPoolExecutor(max_workers=3) as pool:
            replies = list(pool.map(ask, (2, 1, 3)))  # in this order, so a repeat keeps the regular season's
        events, answered = [], False
        failure = next((error for _, error in replies if error is not None), None)
        for answer, _ in replies:
            if answer is not None:
                answered = True
                events.extend(_dicts(answer.get("events")))
        if not events and failure is not None:
            raise failure
        return events if answered else None

    answer = _schedule_answer(f"{base_url}?season={season_year}&seasontype=2")
    if answer is None:
        return None
    events = _dicts(answer.get("events"))
    for season_type in (1, 3):
        answer = _schedule_answer(f"{base_url}?season={season_year}&seasontype={season_type}")
        if answer is not None:
            events.extend(_dicts(answer.get("events")))
    return events


def _soccer_schedule_events(base_url, season_year, current_season, lenient=False):
    """Results, plus the games to come if this is the current season, or None if ESPN has
    no results here.

    Soccer has no seasontype: 2 and 3 answer with nothing. `season=Y` gives the
    games played and `fixture=true` the games to come, whatever season is asked
    for, so a past season must not ask for it.

    Each league's seasons cross the new year on their own calendar, so the year
    ESPN calls current can be behind ours: in February 2027 `season=2027` is empty
    for the Premier League, whose 2026-27 season ESPN reports as `season.year` 2026.
    Its results are then the ones to show. Only the year before counts: the Women's
    World Cup's `season.year` stays at 2023 until the next one, and 2023 isn't current.

    `lenient`, for a favorite's card, leaves out a list that fails, and raises when a list
    failed and none had any games, so a failure can't read as a season not yet published.
    The iPhone's does the same.
    """
    failure = None
    try:
        answer = _schedule_answer(f"{base_url}?season={season_year}")
    except ApiError as e:
        if not lenient:
            raise
        failure, answer = e, {}
    if answer is None:
        return None
    events = _dicts(answer.get("events"))
    espn_season = _as_dict(answer.get("season")).get("year")
    if season_year not in (current_season, espn_season):
        if failure is not None:
            raise failure
        return events

    queries = ["fixture=true"]
    if espn_season == season_year - 1:
        queries.insert(0, f"season={espn_season}")
    for query in queries:
        try:
            answer = _schedule_answer(f"{base_url}?{query}")
        except ApiError as e:
            if not lenient:
                raise
            failure, answer = failure or e, None
        if answer is not None:
            events.extend(_dicts(answer.get("events")))
    if failure is not None and not events:
        raise failure
    return events


def _unique_events(events):
    """Without repeats, the first of each kept. A result comes before a fixture, so a game
    just played that ESPN still lists as to come keeps its score."""
    seen, unique = set(), []
    for event in events:
        event_id = event.get("id")
        key = str(event_id) if event_id else None
        if key is None or key not in seen:
            unique.append(event)
        if key is not None:
            seen.add(key)
    return unique


def _schedule_row_facts(event, comp, status_type):
    """What a row needs beyond teams and times, on either path."""
    return {
        "label": schedule_game_label(event),
        "completed": bool(status_type.get("completed")),
        "neutral_site": bool(comp.get("neutralSite")),
    }


def get_team_schedule(league_key, team_id, days_ahead=30, days_behind=30, season=None):
    """A team's schedule for one season. See get_team_schedule_and_season."""
    return get_team_schedule_and_season(league_key, team_id, days_ahead, days_behind, season)[0]


def get_team_schedule_and_season(league_key, team_id, days_ahead=30, days_behind=30, season=None):
    """(a team's schedule, the season it is from), from ESPN's team schedule endpoint.

    A past season asked for is that season or nothing, never another year's games. The
    current season can fall back to the last one (below), and those rows show their year.
    Team Hub always asks for a season, the top of its list being the current one, and moves
    that list to the season that comes back, so it doesn't name a season with no games.
    """
    from datetime import timedelta

    league_path = LEAGUES.get(league_key)
    if not league_path:
        return [], season

    # Determine if we're viewing a historical season (not the current one)
    current_season = get_current_season_year(league_key)
    is_historical_season = season is not None and season != current_season
    season_year = season if season else current_season
    base_url = f"{BASE_URL}/{league_path}/teams/{team_id}/schedule"

    if league_key in SEASON_TYPE_SCHEDULE_LEAGUES:
        events = _season_type_schedule_events(base_url, season_year)
    elif league_path.startswith("soccer/"):
        events = _soccer_schedule_events(base_url, season_year, current_season)
    else:
        # The last resort, for a league with no team schedule: the scoreboard, filtered
        # to this team. It knows only the days around today, so it has no past seasons.
        if is_historical_season:
            return [], season_year
        today = datetime.now()
        start_date = today - timedelta(days=days_behind)
        end_date = today + timedelta(days=days_ahead)
        # ESPN rejects dates=START-END ranges (400 since September 2026), so
        # fetch each month the window touches and trim to the window afterwards.
        # A month is far bigger than a day, so lift the page size to the 1000
        # ceiling (past it ESPN collapses to 25).
        schedule = []
        for month in scoreboard_months(start_date, end_date):
            url = f"{BASE_URL}/{league_path}/scoreboard?dates={month}&limit=1000"
            schedule.extend(parse_schedule_from_api(url, team_id, datetime.now(), season))
        first, last = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        schedule = [g for g in schedule if first <= g['date'] <= last]
        schedule.sort(key=lambda g: g['date'])
        return schedule, season_year

    # A request ESPN refused is no sign of an off-season.
    if events is None:
        return [], season_year

    # Offseason fallback: ESPN publishes a new season's schedule some weeks
    # after the previous one ends, so in that gap the current season year comes
    # back empty. Fall back to the season that just finished.
    if not events and season in (None, current_season):
        schedule, used = get_team_schedule_and_season(league_key, team_id, days_ahead, days_behind,
                                                      season=current_season - 1)
        return (schedule, used) if schedule else ([], season_year)

    # ESPN's dates all read the same way, so as text they sort in time order. That
    # keeps a doubleheader in order within its day, after the sort by day below.
    events = sorted(_unique_events(events), key=lambda e: str(e.get("date") or ""))

    schedule = []
    today = datetime.now()
    
    for event in events:
        # Parse event date
        event_date_str = event.get('date', '')
        if event_date_str:
            try:
                event_date = local_schedule_datetime(event_date_str, event.get('timeValid', True))
            except:
                continue
        else:
            continue
            
        # Get competition data
        competitions = _dicts(event.get('competitions'))
        if not competitions:
            continue
            
        comp = competitions[0]
        competitors = _dicts(comp.get('competitors'))
        
        # Find home and away teams
        home_team = away_team = None
        home_score = away_score = ''
        
        for competitor in competitors:
            team_info = _as_dict(competitor.get('team'))
            if competitor.get('homeAway') == 'home':
                home_team = team_info.get('displayName') or 'Unknown'
                score_data = competitor.get('score', '')
                if isinstance(score_data, dict):
                    home_score = score_data.get('displayValue') or ''
                else:
                    home_score = str(score_data) if score_data else ''
            else:
                away_team = team_info.get('displayName') or 'Unknown'
                score_data = competitor.get('score', '')
                if isinstance(score_data, dict):
                    away_score = score_data.get('displayValue') or ''
                else:
                    away_score = str(score_data) if score_data else ''
        
        # Determine if this is home or away for our team
        team_name = None
        is_home = False
        for competitor in competitors:
            team_info = _as_dict(competitor.get('team'))
            if team_info.get('id') == team_id:
                team_name = team_info.get('displayName') or 'Unknown'
                is_home = competitor.get('homeAway') == 'home'
                break
                
        if not team_name:
            continue
            
        opponent = (away_team if is_home else home_team) or 'Unknown'
        home_away = 'vs' if is_home else '@'
        
        # Get game status
        status = _as_dict(comp.get('status'))
        status_type = _as_dict(status.get('type'))
        game_status = status_type.get('description') or 'Unknown'
        
        # Get start time
        start_time = status_type.get('shortDetail') or status_type.get('detail') or 'TBD'
        
        # Convert timezone to user's local time
        start_time = convert_espn_time_to_local(start_time)
        
        # Get venue
        venue = _as_dict(comp.get('venue'))
        venue_name = venue.get('fullName') or 'TBD'
        
        # Include the year for a past season, or a game outside this year: a current
        # season can cross new year, and MLS's lists 2027's games beside 2026's.
        if is_historical_season or event_date.year != today.year:
            date_display = event_date.strftime('%a, %b %d, %Y')
        else:
            date_display = event_date.strftime('%a, %b %d')
        
        schedule.append({
            'date': event_date.strftime('%Y-%m-%d'),
            'date_display': date_display,
            'opponent': opponent,
            'home_away': home_away,
            'time': start_time,
            'status': game_status,
            'venue': venue_name,
            'home_score': home_score,
            'away_score': away_score,
            'game_id': event.get('id') or '',
            'is_today': event_date.date() == today.date(),
            **_schedule_row_facts(event, comp, status_type),
        })
        
    # Sort by date
    schedule.sort(key=lambda x: x['date'])
    return schedule, season_year


def get_favorite_card_schedule(league_key, team_id):
    """A favorite team's games for its card on Home, as favorite_card.card_games: the current
    season, or the last one in the weeks before ESPN publishes the next. The same requests as
    the iPhone's ESPNAPIService.fetchFavoriteCardSchedule, and as lenient: the card needs only
    the last and next games, so a preseason that fails doesn't cost it the regular season.

    Raises ApiError when nothing loaded, so the card can say so rather than look empty. A
    league with no team schedule (golf) has no card games.
    """
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    current_season = get_current_season_year(league_key)
    base_url = f"{BASE_URL}/{league_path}/teams/{team_id}/schedule"
    for season_year in (current_season, current_season - 1):
        if league_key in SEASON_TYPE_SCHEDULE_LEAGUES:
            events = _season_type_schedule_events(base_url, season_year, lenient=True)
        elif league_path.startswith("soccer/"):
            events = _soccer_schedule_events(base_url, season_year, current_season, lenient=True)
        else:
            return []
        if events:
            return favorite_card.card_games(events)
    return []


def parse_schedule_from_api(url, team_id, today, season=None):
    """Parse schedule data from ESPN API response"""
    from datetime import datetime
    
    # Determine if this is a historical season
    current_year = datetime.now().year
    is_historical_season = season is not None and season != current_year
    
    schedule = []
    
    try:
        resp = _http_get(url)
        if resp.status_code == 200:
            data = resp.json()
            events = _dicts(data.get("events"))
            
            for event in events:
                competitions = _dicts(event.get("competitions"))
                if not competitions:
                    continue
                
                comp = competitions[0]
                competitors = _dicts(comp.get("competitors"))
                
                # Check if this team is playing
                team_playing = False
                is_home = False
                home_team = away_team = None
                home_score = away_score = ""
                
                for competitor in competitors:
                    team_info = _as_dict(competitor.get("team"))
                    if team_info.get("id") == team_id:
                        team_playing = True
                        is_home = competitor.get("homeAway") == "home"
                    
                    if competitor.get("homeAway") == "home":
                        home_team = team_info.get("displayName") or "Unknown"
                        score_data = competitor.get("score", "")
                        if isinstance(score_data, dict):
                            home_score = score_data.get("displayValue") or ""
                        else:
                            home_score = str(score_data) if score_data else ""
                    else:
                        away_team = team_info.get("displayName") or "Unknown"
                        score_data = competitor.get("score", "")
                        if isinstance(score_data, dict):
                            away_score = score_data.get("displayValue") or ""
                        else:
                            away_score = str(score_data) if score_data else ""
                
                if team_playing:
                    # Parse event date
                    event_date_str = event.get("date", "")
                    if event_date_str:
                        try:
                            event_date = local_schedule_datetime(event_date_str, event.get('timeValid', True))
                        except:
                            event_date = today
                    else:
                        event_date = today
                    
                    # Get game details
                    status = _as_dict(comp.get("status"))
                    status_type = _as_dict(status.get("type"))
                    game_status = status_type.get("description") or "Unknown"
                    
                    # Get start time
                    start_time = status_type.get("shortDetail") or status_type.get("detail") or "TBD"
                    
                    # Convert timezone to user's local time
                    start_time = convert_espn_time_to_local(start_time)
                    
                    # Get venue
                    venue = _as_dict(comp.get("venue"))
                    venue_name = venue.get("fullName") or "TBD"
                    
                    # Include the year for a past season, or a game outside this year.
                    if is_historical_season or event_date.year != today.year:
                        date_display = event_date.strftime("%a, %b %d, %Y")
                    else:
                        date_display = event_date.strftime("%a, %b %d")
                    
                    schedule.append({
                        "date": event_date.strftime("%Y-%m-%d"),
                        "date_display": date_display,
                        "opponent": (away_team if is_home else home_team) or "Unknown",
                        "home_away": "vs" if is_home else "@",
                        "time": start_time,
                        "status": game_status,
                        "venue": venue_name,
                        "home_score": home_score,
                        "away_score": away_score,
                        "game_id": event.get("id") or "",
                        "is_today": event_date.date() == today.date(),
                        **_schedule_row_facts(event, comp, status_type),
                    })
        
    except Exception as e:
        print(f"Error fetching schedule from {url}: {e}")
    
    return schedule


# Requests in flight at once when Live Scores fetches every league. ESPN can
# take a second or more per request; one after another, 25 leagues plus a
# summary per live game was over a minute.
LIVE_FETCH_WORKERS = 8
# More leagues than this failing at once isn't worth a screen reader listing them.
LIVE_FAILURES_NAMED = 4


def with_failed_leagues_kept(fresh, last, failed, field="league"):
    """A refresh's rows, plus the rows last shown for the leagues that just failed, so one
    league not answering doesn't take its games off the list."""
    failed = set(failed)
    return list(fresh) + [row for row in last if row.get(field) in failed]


def live_scores_failure_text(failed, showing):
    """The Live Scores row for leagues that didn't answer. `showing` is whether any games are
    on the list: with none, and too many failures to name, there's only the one thing to say."""
    failed = sorted(failed)
    if len(failed) > LIVE_FAILURES_NAMED:
        if not showing:
            return SCORES_UNAVAILABLE
        who = "Some leagues' scores"
    else:
        who = "Scores for " + (" and ".join(failed) if len(failed) < 3
                               else f"{', '.join(failed[:-1])} and {failed[-1]}")
    return f"{who} may be missing or out of date. ESPN isn't providing them right now. Try again in a minute."


def scoreboard_live_detail(league_key, comp):
    """Latest-play text for a live game, from its scoreboard entry alone.

    The scoreboard already carries the situation (last play, down and
    distance, count, runners), so Live Scores doesn't need a full game summary
    per live game. That was one extra request per game; on a college football
    Saturday, 50 of them. Returns None when the scoreboard has nothing to add,
    and the caller shows the status instead.
    """
    try:
        if league_key == "MLB":
            return extract_baseball_enhanced_display({"competitions": [comp]})
        if league_key in ("NFL", "NCAAF"):
            return _football_scoreboard_display(comp)
        last_play = ((comp.get("situation") or {}).get("lastPlay") or {}).get("text")
        return last_play or None
    except Exception as e:
        print(f"Error building live detail for {league_key}: {e}")
        return None


def _started_unfinished_game_dates(games, now):
    """ESPN game dates (US Eastern) of games that have kicked off and not finished.

    A game counts once its start time has passed, not only once the board says
    "in": a stale board can still list a game that has kicked off as upcoming.
    ESPN's dates= board files a game under its Eastern date, so a 10:30 pm ET
    kickoff still live at 1 am is on the previous day's board.
    """
    import pytz
    from datetime import datetime
    eastern = pytz.timezone("US/Eastern")
    dates = set()
    for game in games:
        if game_section(game) in ("completed", "postponed"):
            continue
        start = None
        for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                start = datetime.strptime(game.get("date") or "", fmt)
                break
            except ValueError:
                pass
        if start is None:
            continue
        start = pytz.utc.localize(start)
        if start <= now:
            dates.add(start.astimezone(eastern).date())
    return dates


def freshen_live_games(league_key, games, now=None):
    """A football week's games, with ones under way taken from the daily board.

    The week-addressed scoreboard (dates=YEAR&week=N) a football league view
    reads runs behind the date-addressed one Live Scores reads: on 2026-10-09
    it showed Utah State 6 when the game was at 9, and the clock minutes back.
    For each ESPN date with a game that has started and not finished (almost
    always one), that day's board is fetched and its version of each game
    replaces the week's. This is an extra scoreboard request on every load
    of a week with a game under way, and none otherwise. Games not on a daily
    board keep the week's version, and a failure keeps the week's games.
    """
    if now is None:
        import pytz
        from datetime import datetime
        now = datetime.now(pytz.utc)
    try:
        days = sorted(_started_unfinished_game_dates(games, now))
    except Exception as e:
        # A bad start time mustn't cost the user the whole week.
        print(f"Couldn't work out live {league_key} game dates: {e}")
        return games
    fresh = {}
    for day in days:
        try:
            fresh.update((g.get("id"), g) for g in get_scores(league_key, date=day))
        except Exception as e:
            print(f"Couldn't refresh live {league_key} games for {day}: {e}")
    if not fresh:
        return games
    return sort_games_by_section([fresh.get(g.get("id"), g) for g in games])


def _football_scoreboard_display(comp):
    """Two lines from a scoreboard competition: teams, scores, red zone and last
    play; then clock, possession and down and distance."""
    situation = comp.get("situation") or {}
    if not situation:
        return None  # halftime, between quarters
    home = away = None
    for competitor in comp.get("competitors", []):
        if competitor.get("homeAway") == "home":
            home = competitor
        elif competitor.get("homeAway") == "away":
            away = competitor
    if not home or not away:
        return None

    def name(c):
        return c.get("team", {}).get("displayName", "")

    possession = situation.get("possession")
    red_zone = situation.get("isRedZone") and possession
    away_part = f"{name(away)} {away.get('score', '0')}"
    home_part = f"{name(home)} {home.get('score', '0')}"
    if red_zone and possession == away.get("team", {}).get("id"):
        away_part += " (RZ)"
    elif red_zone and possession == home.get("team", {}).get("id"):
        home_part += " (RZ)"
    line1 = f"{away_part} at {home_part}"
    last_play = (situation.get("lastPlay") or {}).get("text", "")
    if last_play:
        line1 += f" | {last_play[:60] + '...' if len(last_play) > 60 else last_play}"

    parts = []
    status = comp.get("status", {})
    clock, period = status.get("displayClock", ""), status.get("period")
    if clock and period:
        parts.append(f"{clock} {'Q' + str(period) if period <= 4 else 'OT'}")
    for c in (home, away):
        if possession and c.get("team", {}).get("id") == possession:
            parts.append(f"{c['team'].get('abbreviation', '')} ball")
    down = situation.get("downDistanceText") or situation.get("shortDownDistanceText")
    if down:
        parts.append(down)
    return f"{line1}\n{' | '.join(parts)}" if parts else line1


def golf_total_to_par(competitor):
    """A golfer's total to par, including the round in progress.

    ESPN's competitor `score` leaves out the current round while it is being
    played: a golfer at +1, -4 and -8 through 12 holes of round 3 shows -3, not
    -11, so mid-round leaderboards were wrong. Each linescore's displayValue is
    that round's score to par ("-8", "+1", "E", or "-" if not started), so the
    total is their sum. Falls back to `score` when no round has a value, and
    keeps a non-numeric `score` (CUT, WD, DQ) as it is.
    """
    score = str(competitor.get("score") or "").strip()
    if score and score not in ("E", "e") and not score.lstrip("+-").isdigit():
        return score
    total, counted = 0, False
    for line in _dicts(competitor.get("linescores")):
        value = str(line.get("displayValue", "")).strip()
        if value in ("E", "e"):
            counted = True
        elif value[:1] in "+-" and value[1:].isdigit():
            total += int(value)
            counted = True
    if not counted:
        return score
    return "E" if total == 0 else f"{total:+d}"


GOLF_TOURS = ("PGA", "LPGA")
GOLF_TOUR_NAMES = {"PGA": "PGA Tour", "LPGA": "LPGA Tour"}


def get_live_golf_tournament(tour_key, leaders=3):
    """The tour's tournament if it is in progress, else None.

    Golf scoreboards list golfers, not two teams, so they can't go through the
    team-game path: that read every tournament as "Unknown at Unknown". Returns
    {tour, tour_name, name, status, leaders: [(position, name, score)]}, with
    tied scores sharing a "T" position the way a leaderboard shows them.
    """
    league_path = LEAGUES.get(tour_key)
    if not league_path:
        return None
    answer = _espn_answer(LEADERBOARD_UNAVAILABLE, f"{BASE_URL}/{league_path}/scoreboard")
    if answer is None:
        return None
    # The first event in progress, by the rule both apps share (golf.py): between rounds
    # the event is still on though its competition says play is complete for the day.
    event = golf.pick_event(_listed(answer, "events", LEADERBOARD_UNAVAILABLE))
    if event is not None and golf.event_state(event) == "in":
        comp = (_dicts(event.get("competitions")) or [{}])[0]
        status = _as_dict(_as_dict(comp.get("status")).get("type"))
        players = golf.by_order(comp.get("competitors"))
        scores = [golf_total_to_par(p) for p in players]
        top = []
        for i, player in enumerate(players[:leaders]):
            score = scores[i]
            first = scores.index(score) + 1
            tied = scores.count(score) > 1
            top.append((f"T{first}" if tied else str(first), golf.competitor_name(player), score))
        return {
            "tour": tour_key,
            "tour_name": GOLF_TOUR_NAMES.get(tour_key, tour_key),
            "name": event.get("name") or "",
            "status": status.get("detail") or "In Progress",
            "leaders": top,
        }
    return None


def extract_baseball_enhanced_display(game_details):
    """Extract enhanced baseball display with base runners, count, and batter info"""
    try:
        # The game_details structure varies depending on the source
        # It could be a direct event from scoreboard, or detailed game data
        
        # Try to find competitions data
        competitions = None
        if 'competitions' in game_details:
            competitions = game_details['competitions']
        elif 'header' in game_details and 'competitions' in game_details['header']:
            competitions = game_details['header']['competitions']
        
        if not competitions or not isinstance(competitions, list) or len(competitions) == 0:
            return None
        
        competition = competitions[0]
        
        # Get competitors (teams)
        competitors = competition.get('competitors', [])
        if len(competitors) < 2:
            return None
            
        # Extract team information with scores and names
        home_team = None
        away_team = None
        
        for competitor in competitors:
            if competitor.get('homeAway') == 'home':
                home_team = competitor
            elif competitor.get('homeAway') == 'away':
                away_team = competitor
        
        if not home_team or not away_team:
            return None
        
        # Get team names and scores
        home_name = home_team.get('team', {}).get('displayName', 'HOME')
        away_name = away_team.get('team', {}).get('displayName', 'AWAY')
        home_score = home_team.get('score', '0')
        away_score = away_team.get('score', '0')
        
        # Get situation data from competition
        situation = competition.get('situation', {})
        if not situation:
            return None
            
        # Get base runner information
        on_first = situation.get('onFirst', False)
        on_second = situation.get('onSecond', False)
        on_third = situation.get('onThird', False)
        
        # Convert to English description
        runner_count = sum([on_first, on_second, on_third])
        
        if runner_count == 0:
            base_description = "Bases empty"
        elif runner_count == 3:
            base_description = "Bases loaded"
        elif runner_count == 1:
            if on_first:
                base_description = "Runner on 1st"
            elif on_second:
                base_description = "Runner on 2nd"
            elif on_third:
                base_description = "Runner on 3rd"
        elif runner_count == 2:
            if on_first and on_second:
                base_description = "Runners on 1st and 2nd"
            elif on_first and on_third:
                base_description = "Runners on 1st and 3rd"
            elif on_second and on_third:
                base_description = "Runners on 2nd and 3rd"
        else:
            base_description = "Unknown base situation"
        
        # Get count and outs
        balls = situation.get('balls', 0)
        strikes = situation.get('strikes', 0)
        outs = situation.get('outs', 0)
        count_description = f"{balls}-{strikes} count, {outs} out{'s' if outs != 1 else ''}"
        
        # Get current batter
        batter = situation.get('batter', {}).get('athlete', {})
        batter_name = batter.get('displayName', 'Unknown') if batter else 'Unknown'
        
        # Get last play
        last_play = situation.get('lastPlay', {})
        last_play_text = last_play.get('text', 'No recent play') if last_play else 'No recent play'
        
        # Build display format
        # Line 1: Team names with scores
        team_display = f"{away_name} {away_score} at {home_name} {home_score}"
        
        # Line 2: Base situation, count, batter
        line2 = f"{base_description} | {count_description} | At bat: {batter_name}"
        
        # Line 3: Last play (simplified for space)
        if len(last_play_text) > 50:
            last_play_text = last_play_text[:47] + "..."
        line3 = f"Last: {last_play_text}"
        
        return f"{team_display}\n{line2}\n{line3}"
            
    except Exception as e:
        print(f"Error extracting baseball details: {e}")
        
    return None

def get_leagues():
    return list(LEAGUES.keys())

def get_available_seasons(league_key):
    """Get available seasons for a league, newest first.
    
    Each entry is (espn_season_year, display_label). The newest entry is the
    season currently in progress, so NHL in September 2026 leads with
    (2027, "2026-27 Season").
    
    Based on ESPN API historical data availability:
    - MLB: Comprehensive data from 2001 onward
    - NFL: Comprehensive data from 2001 onward  
    - NBA/NHL: Comprehensive data from 2000-01 onward
    - NCAAF: Comprehensive data from 2005 onward
    - NCAA hockey: Comprehensive data from 2012-13 onward
    """
    current_season = get_current_season_year(league_key)
    
    if league_key in YEAR_PLUS_ONE_LEAGUES:
        # Season year is the year the season ends in: 2027 = the 2026-27 season
        earliest = 2012 if league_key in ("NCAAH", "NCAAWH") else 2001
        return [(year, f"{year-1}-{str(year)[2:]} Season")
                for year in range(current_season, earliest - 1, -1)]
    elif league_key == "NCAAF":
        # NCAAF seasons are by year
        # ESPN has comprehensive data from 2005 onward
        return [(year, f"{year} Season") for year in range(current_season, 2004, -1)]
    elif league_key in ("NFL", "MLB"):
        # Seasons are by the year they start in
        # ESPN has comprehensive data from 2001 onward
        return [(year, f"{year} Season") for year in range(current_season, 2000, -1)]
    else:
        # For other leagues, return last 10 years as a reasonable default
        return [(year, f"{year} Season") for year in range(current_season, current_season - 10, -1)]

def get_scores(league_key, date=None, week=None, seasontype=None, season=None):
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []

    url = f"{BASE_URL}/{league_path}/scoreboard"
    params = []

    if date:
        # Non-football date navigation
        params.append(f"dates={date.strftime('%Y%m%d')}")
    elif week is not None and league_key in ("NFL", "NCAAF"):
        params.append(f"week={week}")
        if season is not None:
            # ESPN ignores season= when week= is also passed (known API quirk),
            # but a bare year in dates= does pick the season: dates=2025&week=5
            # serves the 2025 season's week 5, and dates=2026&week=18 serves the
            # January 2027 games. This replaced a dates=START-END range built
            # from the calendar, which ESPN began rejecting with a 400 in
            # September 2026 — for every sport, not just football.
            #
            # seasontype matters here: week numbers restart within each season
            # type, so week 1 is the Hall of Fame game in preseason and the
            # September opener in the regular season.
            from services.football_calendar import SEASON_TYPE_REGULAR
            params.append(f"dates={season}")
            if seasontype is None:
                seasontype = SEASON_TYPE_REGULAR
    elif season is not None and league_key in ("NFL", "NCAAF"):
        # Season-only: used for off-season default view (returns current/week-1)
        params.append(f"season={season}")

    # Add seasontype parameter (2=regular season, 3=postseason)
    if seasontype is not None:
        params.append(f"seasontype={seasontype}")
    params += college_scoreboard_params(league_key)
    if params:
        url += "?" + "&".join(params)

    answer = _espn_answer(SCORES_UNAVAILABLE, url)
    if answer is None:
        return []
    events = _listed(answer, "events", SCORES_UNAVAILABLE)

    if ncaaf_needs_fbs_retry(league_key, events):
        # The empty answer before this one is no sign of no games, so a failure here says so.
        retry = _espn_answer(SCORES_UNAVAILABLE, _swap_to_fbs(url))
        if retry is not None:
            events = _listed(retry, "events", SCORES_UNAVAILABLE)

    scores = []

    for event in events:
        name = event.get("name") or "Unknown Game"
        eid = event.get("id") or ""
        
        # Extract competition data
        competitions = _dicts(event.get("competitions"))
        if not competitions:
            continue
            
        comp = competitions[0]
        
        # Extract start time and status
        status = _as_dict(comp.get("status"))
        start_time = ""
        game_status = ""
        game_status_name = ""
        game_state = ""
        if status:
            type_info = _as_dict(status.get("type"))
            # The stable identifier, e.g. STATUS_SCHEDULED / STATUS_POSTPONED.
            # `description` below is display text and varies; this does not.
            game_status_name = type_info.get("name") or ""
            game_state = type_info.get("state") or ""
            start_time = type_info.get("shortDetail") or type_info.get("detail") or ""
            
            # Convert timezone to user's local time
            if start_time:
                start_time = convert_espn_time_to_local(start_time)
                
            game_status = type_info.get("description") or ""
        
        # Extract scores from competitors
        competitors = _dicts(comp.get("competitors"))
        team_scores = []
        for competitor in competitors:
            team = _as_dict(competitor.get("team"))
            score = competitor.get("score") or ""
            home_away = competitor.get("homeAway") or ""
            
            # For NCAA sports, use full team names (displayName) instead of nicknames
            # All of them: "Huskies 2 at Huskies 4" could be four different schools.
            if league_key in ["NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"]:
                team_name = team.get("displayName") or team.get("name") or team.get("abbreviation") or "Unknown"
                # ESPN uses 99 for unranked.
                rank = (competitor.get("curatedRank") or {}).get("current")
                if isinstance(rank, int) and 1 <= rank <= 25:
                    team_name = f"#{rank} {team_name}"
            else:
                team_name = team.get("name") or team.get("abbreviation") or "Unknown"

            # Overall record, so scheduled games have something to show instead of
            # ESPN's pre-game "0" scores. Matched on type rather than taken from
            # records[0] — the order of that list isn't guaranteed. A "0-0" record
            # (season opener, preseason) carries no information, so it's dropped
            # here and the team name stands alone.
            record_summary = ""
            for rec in _dicts(competitor.get("records")):
                if rec.get("type") == "total":
                    summary = rec.get("summary", "")
                    if summary and summary != "0-0":
                        record_summary = summary
                    break

            team_info = {
                "name": team_name,
                "abbreviation": team.get("abbreviation") or "",
                "score": score,
                "record": record_summary,
                "home_away": home_away
            }
            team_scores.append(team_info)
        
        scores.append({
            "id": eid,
            "name": name,
            "start_time": start_time,
            "status": game_status,
            "status_name": game_status_name,
            "state": game_state,
            "date": event.get("date") or "",
            "teams": team_scores,
            "competitions": [comp]  # Include raw competition data for bowl names
        })
    return sort_games_by_section(scores)

def _article_href(article, kind):
    """An article's web or mobile link, or "" when ESPN didn't send one."""
    return _as_dict(_as_dict(article.get("links")).get(kind)).get("href") or ""


def get_news(league_key, limit=10):
    """Get news headlines and links for a specific league
    
    Args:
        league_key: The league to get news for (e.g., 'MLB', 'NFL')
        limit: Maximum number of articles to retrieve (default: 10, ESPN default is 6)
    """
    league_path = LEAGUES.get(league_key) or racing.series_path(league_key)
    if not league_path:
        return []
    url = f"{BASE_URL}/{league_path}/news"
    params = {'limit': limit} if limit > 6 else {}
    answer = _espn_answer(NEWS_UNAVAILABLE, url, params=params)
    if answer is None:
        return []
    articles = _listed(answer, "articles", NEWS_UNAVAILABLE)
    news_items = []
    
    # Import text processor for cleaning descriptions
    try:
        from text_utils import text_processor
    except ImportError:
        text_processor = None
    
    for article in articles:
        raw_description = article.get("description") or ""
        
        # Clean description text if processor is available
        if text_processor:
            cleaned_description = text_processor.clean_description(raw_description, article)
        else:
            cleaned_description = raw_description
        
        news_item = {
            "headline": article.get("headline") or "No headline",
            "description": cleaned_description,
            "web_url": _article_href(article, "web"),
            "mobile_url": _article_href(article, "mobile"),
            "published": article.get("published") or "",
            "byline": article.get("byline") or ""
        }
        news_items.append(news_item)
    return news_items

def get_game_details(league_key, game_id):
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return {}
    url = f"{BASE_URL}/{league_path}/summary?event={game_id}"
    answer = _espn_answer(GAME_UNAVAILABLE, url)
    return {} if answer is None else answer


def extract_meaningful_game_info(details):
    """Extract meaningful information from game details for display"""
    if not details or not isinstance(details, dict):
        return {}
    
    info = {}
    
    # Basic game info
    competitions = _dicts(_as_dict(details.get('header')).get('competitions'))
    if competitions:
        comp = _as_dict(competitions[0])

        # Teams, records, and scores
        competitors = _dicts(comp.get('competitors'))
        teams = []
        scores = []
        for competitor in competitors:
            team = _as_dict(competitor.get('team'))
            record = _dicts(competitor.get('record'))
            score = competitor.get('score') or ''
            team_info = {
                'name': team.get('displayName') or 'Unknown',
                'team_id': team.get('id') or '',  # ADD THE TEAM ID!
                'abbreviation': team.get('abbreviation') or 'N/A',
                'record': (_as_dict(record[0]).get('summary') if record else None) or 'N/A',
                'home_away': competitor.get('homeAway') or 'unknown',
                'score': score
            }
            teams.append(team_info)
            if score:
                scores.append(f"{team.get('name') or team.get('abbreviation') or 'Unknown'}: {score}")
        info['teams'] = teams
        info['scores'] = scores

        # Game status and time
        status_type = _as_dict(_as_dict(comp.get('status')).get('type'))
        info['status'] = status_type.get('description') or 'Unknown'
        detailed_status = status_type.get('detail') or 'N/A'
        # Convert timezone to user's local time
        info['detailed_status'] = convert_espn_time_to_local(detailed_status)

        # Date
        info['date'] = comp.get('date') or 'N/A'

    game_info = _as_dict(details.get('gameInfo'))

    # Venue, when ESPN names one. scores.py adds the city to this name, so a venue
    # with a city but no name is left out rather than passed on as None.
    venue = _as_dict(game_info.get('venue'))
    venue_name = venue.get('fullName') or venue.get('displayName')
    if venue_name:
        info['venue'] = venue_name
        address = _as_dict(venue.get('address'))
        info['venue_city'] = address.get('city') or 'Unknown'
        info['venue_state'] = address.get('state') or ''

    # Weather, when ESPN has any
    weather = _as_dict(game_info.get('weather'))
    if weather.get('temperature') is not None:
        info['temperature'] = f"{weather['temperature']}°F"
    if weather.get('displayValue') or info.get('temperature'):
        info['weather'] = weather.get('displayValue') or info['temperature']

    # Odds (if available)
    odds = best_odds(details)
    if odds.get('details'):
        info['betting_line'] = odds['details']
    if odds.get('overUnder') is not None:
        info['over_under'] = f"O/U {odds['overUnder']}"
    
    # Broadcast information. The summary's list can be empty when its header has one.
    header_competition = _as_dict(competitions[0]) if competitions else {}
    networks = broadcast_names(details.get('broadcasts'), header_competition.get('broadcasts'))
    if networks:
        info['broadcast'] = ', '.join(networks)

    # Injuries summary
    if 'injuries' in details:
        injury_count = injured_player_count(details['injuries'])
        if injury_count > 0:
            info['injuries'] = f"{injury_count} {'player' if injury_count == 1 else 'players'} listed"
    
    # Game articles/recaps (if available)
    if 'article' in details and details['article']:
        article = details['article']
        if isinstance(article, dict) and article.get('headline'):
            info['article'] = {
                'headline': article['headline'],
                'description': article.get('description') or '',
                'story': article.get('story') or '',
                'type': article.get('type') or 'Article',
                'published': article.get('published') or '',
                'source': article.get('source') or ''
            }
    
    return info


def format_complex_data(key, value):
    """Format complex data structures for better display"""
    if not value:
        return "No data available"
    
    # Handle cases where value has a "header" key (common ESPN pattern)
    if isinstance(value, dict) and "header" in value:
        # Skip the header and process the actual content
        if len(value) == 1:
            return "No content data available"
        # Process other keys in the dict besides "header"
        content_keys = [k for k in value.keys() if k != "header"]
        # Use the first non-header key's data
        actual_value = value[content_keys[0]]
        return format_complex_data(key, actual_value)
    
    if key == "gameInfo" and isinstance(value, dict):
        info_parts = []
        # Show useful game information
        if "venue" in value:
            venue = value["venue"]
            if isinstance(venue, dict):
                venue_name = venue.get("fullName") or venue.get("displayName")
                if venue_name:
                    info_parts.append(f"Venue: {venue_name}")
        
        attendance = value.get("attendance")
        if attendance:
            # A number when ESPN has one, but don't let any other shape raise.
            shown = f"{attendance:,}" if isinstance(attendance, (int, float)) else attendance
            info_parts.append(f"Attendance: {shown}")
        
        # Skip officials here - they're handled interactively in the main game details
        # if "officials" in value and isinstance(value["officials"], list):
        #     officials_count = len(value["officials"])
        #     if officials_count > 0:
        #         info_parts.append(f"Officials: {officials_count} assigned")
        
        if "weather" in value:
            weather = value["weather"]
            if isinstance(weather, dict):
                weather_desc = weather.get("displayValue") or ""
                temp = weather.get("temperature")
                if weather_desc or temp is not None:
                    weather_info = weather_desc
                    if temp is not None:
                        weather_info += f" ({temp}°F)" if weather_desc else f"{temp}°F"
                    info_parts.append(f"Weather: {weather_info}")
        
        return "\n".join(info_parts) if info_parts else "No additional game info available"
    
    elif key == "news":
        if isinstance(value, list):
            headlines = []
            for item in value[:3]:  # Show first 3 items
                if isinstance(item, dict):
                    headline = item.get("headline", "")
                    if not headline:
                        headline = item.get("title", "")
                    if headline:
                        headlines.append(f"• {headline}")
            return "\n".join(headlines) if headlines else "No headlines available"
        elif isinstance(value, dict):
            if "articles" in value and isinstance(value["articles"], list):
                # Handle ESPN news format with articles array
                articles = value["articles"][:3]
                headlines = []
                for article in articles:
                    if isinstance(article, dict):
                        headline = article.get("headline", "")
                        if headline:
                            headlines.append(f"• {headline}")
                return "\n".join(headlines) if headlines else "No headlines found"
            else:
                return "News section available"
        else:
            return "News available"
    
    elif key == "leaders":
        if isinstance(value, list):
            leader_count = len(value)
            return f"Statistical leaders available ({leader_count} categories)"
        elif isinstance(value, dict):
            category_count = len(value.keys())
            return f"Statistical leaders available ({category_count} categories)"
        else:
            return "Leaders data available"
    
    elif key == "standings":
        if isinstance(value, list):
            team_count = len(value)
            return f"Standings available for {team_count} teams"
        elif isinstance(value, dict):
            if "entries" in value and isinstance(value["entries"], list):
                team_count = len(value["entries"])
                return f"Standings available for {team_count} teams"
            else:
                return "Standings data available"
        else:
            return "Standings available"
    
    elif key == "injuries" and isinstance(value, list):
        injury_count = injured_player_count(value)
        if not injury_count:
            return "No injuries reported"
        return f"Injury reports available ({injury_count} {'player' if injury_count == 1 else 'players'})"
    
    elif key == "broadcasts":
        if isinstance(value, list):
            networks = broadcast_names(value)
            return ", ".join(networks[:3]) if networks else "No networks listed"
        elif isinstance(value, dict):
            return "Broadcast data available"
        else:
            return "Broadcast section available"
    
    elif key == "odds":
        if isinstance(value, list):
            odds_info = []
            for odd in value[:2]:  # Show first 2
                if isinstance(odd, dict):
                    provider = _as_dict(odd.get("provider")).get("name") or "Unknown"
                    details = odd.get("details") or "No details"
                    over_under = odd.get("overUnder") or ""
                    info = f"• {provider}: {details}"
                    if over_under:
                        info += f" (O/U: {over_under})"
                    odds_info.append(info)
            return "\n".join(odds_info) if odds_info else "No odds details"
        elif isinstance(value, dict):
            return "Odds data available"
        else:
            return "Odds section available"
    
    elif key == "boxscore" and isinstance(value, dict):
        teams = value.get("teams", [])
        if teams:
            boxscore_info = []
            for team in teams[:2]:
                if isinstance(team, dict):
                    team_info = _as_dict(team.get("team"))
                    name = team_info.get("displayName") or "Unknown"
                    stats = team.get("statistics") or []
                    if stats:
                        # Show a few key stats
                        key_stats = []
                        for stat in stats[:3]:
                            if isinstance(stat, dict):
                                stat_name = stat.get("name", "")
                                stat_value = stat.get("displayValue", "")
                                if stat_name and stat_value:
                                    key_stats.append(f"{stat_name}: {stat_value}")
                        if key_stats:
                            boxscore_info.append(f"• {name}: {', '.join(key_stats)}")
            return "\n".join(boxscore_info) if boxscore_info else "No boxscore data"
        return "No team stats available"
    
    elif isinstance(value, list):
        return f"List with {len(value)} items" + (f": {', '.join(str(v)[:30] + '...' if len(str(v)) > 30 else str(v) for v in value[:3])}" if value and len(str(value[0])) < 50 else "")
    
    elif isinstance(value, dict):
        if len(value) <= 3:
            # For small dicts, show the key-value pairs
            items = []
            for k, v in list(value.items())[:3]:
                if isinstance(v, (str, int, float)):
                    items.append(f"{k}: {v}")
            return "; ".join(items) if items else f"Dict with {len(value)} items"
        return f"Dict with {len(value)} items: {', '.join(list(value.keys())[:5])}"
    
    return str(value)[:100] + ("..." if len(str(value)) > 100 else "")

def get_rankings(league_key):
    """Get current poll/ranking data for a specific league
    
    Returns a dict with structure:
    {
        'polls': [
            {
                'name': 'AP Top 25',
                'type': 'ap', 
                'shortName': 'AP Poll',
                'headline': 'Poll headline',
                'ranks': [
                    {
                        'current': 1,
                        'previous': 2,
                        'points': 1650,
                        'recordSummary': '13-0',
                        'team': {
                            'id': '84',
                            'location': 'Indiana',
                            'nickname': 'Hoosiers',
                            'displayName': 'Indiana Hoosiers',
                            'abbreviation': 'IND',
                            'logos': [...],
                            'color': '990000'
                        }
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return {'polls': []}
    
    url = f"{BASE_URL}/{league_path}/rankings"
    data = _espn_answer(POLLS_UNAVAILABLE, url)
    if data is None:
        return {'polls': []}

    polls = _listed(data, 'rankings', POLLS_UNAVAILABLE)

    return {'polls': polls}

def get_standings(league_key):
    """Get current standings for a specific league using optimized API endpoint"""
    if league_key == "MLB":
        return _get_mlb_standings_fast()
    elif league_key == "NFL":
        return _get_nfl_standings_fast()
    elif league_key == "NBA":
        return _get_nba_standings_fast()
    elif league_key == "NHL":
        return _get_nhl_standings_fast()
    elif league_key == "WNBA":
        # See _standings_or_nothing: the team list would read a team's playoff record, too.
        return _standings_or_nothing("WNBA", "basketball/wnba")
    elif league_key == "NCAAF":
        return _get_ncaaf_standings_fast()
    elif league_key == "NCAAM":
        return _get_ncaam_standings_fast()
    elif league_key == "NCAAWB":
        return _get_ncaawb_standings_fast()
    elif league_key == "NCAAH":
        return _get_ncaah_standings_fast()
    elif league_key == "NCAAWH":
        return _get_ncaawh_standings_fast()
    elif (LEAGUES.get(league_key) or "").startswith("soccer/"):
        return _standings_or_nothing(league_key, LEAGUES[league_key], parse=parse_soccer_standings)
    else:
        # Fallback to original method for other leagues
        return _get_standings_original(league_key)

def _get_mlb_standings_fast():
    """Fast MLB standings using dedicated endpoint (0.15s vs 7s)"""
    try:
        # Use the fast dedicated standings endpoint
        url = "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings"
        data = _espn_answer(STANDINGS_UNAVAILABLE, url)
        if data is None:
            return []
        _listed(data, "children", STANDINGS_UNAVAILABLE)

        standings = []
        
        # Division mapping for games back calculation
        division_teams = {}
        
        # Process each league (AL/NL)
        for league in data.get('children', []):
            league_name = league.get('name') or ''
            
            # Each league contains the standings entries
            league_standings = league.get('standings', {})
            entries = league_standings.get('entries', [])
            
            for entry in entries:
                team_info = entry.get('team', {})
                stats = entry.get('stats', [])
                
                # Create stats lookup
                stats_dict = {}
                for stat in stats:
                    stats_dict[stat.get('name', '')] = stat.get('value', 0)
                
                # Extract team data
                team_name = team_info.get('displayName') or 'Unknown'
                team_id = str(team_info.get('id') or '')
                abbreviation = team_info.get('abbreviation') or ''
                
                # Get wins/losses from stats
                wins = int(stats_dict.get('wins', 0))
                losses = int(stats_dict.get('losses', 0))
                win_pct = stats_dict.get('winPercent', 0.0)
                
                # Get division from team info or determine from abbreviation
                division = _get_team_division(abbreviation, league_name)
                
                # Get streak (look for streak stats)
                streak = ""
                streak_val = stats_dict.get('streak', 0)
                if streak_val != 0:
                    streak_type = "W" if streak_val > 0 else "L"
                    streak = f"{streak_type}{abs(int(streak_val))}"
                
                team_data = {
                    "team_name": team_name,
                    "team_id": team_id,
                    "abbreviation": abbreviation,
                    "wins": wins,
                    "losses": losses,
                    "win_percentage": f"{win_pct:.3f}",
                    "games_back": "0.0",  # Will calculate after grouping
                    "division": division,
                    "streak": streak,
                    "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else "",
                    # Expanded MLB data
                    "runs_for": int(stats_dict.get('pointsFor', 0)),
                    "runs_against": int(stats_dict.get('pointsAgainst', 0)),
                    "run_differential": int(stats_dict.get('pointDifferential', 0)),
                    "home_wins": int(stats_dict.get('homeWins', 0)),
                    "home_losses": int(stats_dict.get('homeLosses', 0)),
                    "road_wins": int(stats_dict.get('roadWins', 0)),
                    "road_losses": int(stats_dict.get('roadLosses', 0)),
                    "playoff_percent": float(stats_dict.get('playoffPercent', 0.0)),
                    "magic_number": int(stats_dict.get('magicNumberDivision', 0)) if stats_dict.get('magicNumberDivision', 0) > 0 else None
                }
                
                standings.append(team_data)

                if division not in division_teams:
                    division_teams[division] = []
                division_teams[division].append(team_data)
                
                # Group by division for games back calculation
        
        # Calculate games back for each division
        for division, teams in division_teams.items():
            # Sort by wins descending, then by win percentage
            teams.sort(key=lambda x: (-x["wins"], -float(x["win_percentage"])))
            
            if teams:
                leader = teams[0]
                leader_wins = leader["wins"]
                leader_losses = leader["losses"]
                
                for i, team in enumerate(teams):
                    if i == 0:
                        team["games_back"] = "—"  # Leader
                    else:
                        team_wins = team["wins"]
                        team_losses = team["losses"]
                        games_back = ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2
                        team["games_back"] = f"{games_back:.1f}" if games_back > 0 else "0.0"
        
        # Sort final standings by division, then by wins
        standings.sort(key=lambda x: (x["division"], -x["wins"], -float(x["win_percentage"])))
        
        return standings

    except ApiError:
        raise
    except Exception as e:
        print(f"Error in fast MLB standings: {e}")
        # Fallback to original method
        return _get_standings_original("MLB")

def _get_team_division(abbreviation, league_name):
    """Get team division from abbreviation and league"""
    # MLB Division mapping
    mlb_divisions = {
        # American League East
        "BAL": "AL East", "BOS": "AL East", "NYY": "AL East", "TB": "AL East", "TOR": "AL East",
        # American League Central  
        "CHW": "AL Central", "CLE": "AL Central", "DET": "AL Central", "KC": "AL Central", "MIN": "AL Central",
        # American League West
        "HOU": "AL West", "LAA": "AL West", "OAK": "AL West", "SEA": "AL West", "TEX": "AL West",
        # National League East
        "ATL": "NL East", "MIA": "NL East", "NYM": "NL East", "PHI": "NL East", "WSH": "NL East",
        # National League Central
        "CHC": "NL Central", "CIN": "NL Central", "MIL": "NL Central", "PIT": "NL Central", "STL": "NL Central",
        # National League West
        "ARI": "NL West", "COL": "NL West", "LAD": "NL West", "SD": "NL West", "SF": "NL West"
    }
    
    # Handle Oakland abbreviation
    if abbreviation == "ATH":
        abbreviation = "OAK"
    
    return mlb_divisions.get(abbreviation, f"{league_name} League")

def _get_nfl_standings_fast():
    """Fast NFL standings using dedicated endpoint"""
    try:
        url = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings"
        data = _espn_answer(STANDINGS_UNAVAILABLE, url)
        if data is None:
            return []
        _listed(data, "children", STANDINGS_UNAVAILABLE)

        standings = []
        
        # NFL divisions mapping
        nfl_divisions = {
            # AFC East
            "BUF": "AFC East", "MIA": "AFC East", "NE": "AFC East", "NYJ": "AFC East",
            # AFC North  
            "BAL": "AFC North", "CIN": "AFC North", "CLE": "AFC North", "PIT": "AFC North",
            # AFC South
            "HOU": "AFC South", "IND": "AFC South", "JAX": "AFC South", "TEN": "AFC South",
            # AFC West
            "DEN": "AFC West", "KC": "AFC West", "LV": "AFC West", "LAC": "AFC West",
            # NFC East
            "DAL": "NFC East", "NYG": "NFC East", "PHI": "NFC East", "WSH": "NFC East",
            # NFC North
            "CHI": "NFC North", "DET": "NFC North", "GB": "NFC North", "MIN": "NFC North",
            # NFC South
            "ATL": "NFC South", "CAR": "NFC South", "NO": "NFC South", "TB": "NFC South",
            # NFC West
            "ARI": "NFC West", "LAR": "NFC West", "SF": "NFC West", "SEA": "NFC West"
        }
        
        # Process each conference
        division_teams = {}
        for conference in data.get('children', []):
            conf_standings = conference.get('standings', {})
            entries = conf_standings.get('entries', [])
            
            for entry in entries:
                team_info = entry.get('team', {})
                stats = entry.get('stats', [])
                
                # Create stats lookup
                stats_dict = {}
                for stat in stats:
                    stats_dict[stat.get('name', '')] = stat.get('value', 0)
                
                # Extract team data
                team_name = team_info.get('displayName') or 'Unknown'
                team_id = str(team_info.get('id') or '')
                abbreviation = team_info.get('abbreviation') or ''
                
                # Get wins/losses from stats
                wins = int(stats_dict.get('wins', 0))
                losses = int(stats_dict.get('losses', 0))
                ties = int(stats_dict.get('ties', 0))
                win_pct = stats_dict.get('winPercent', 0.0)
                
                # Get division
                division = nfl_divisions.get(abbreviation, "Unknown Division")
                
                # NFL record format includes ties
                record_display = f"{wins}-{losses}"
                if ties > 0:
                    record_display += f"-{ties}"
                
                team_data = {
                    "team_name": team_name,
                    "team_id": team_id,
                    "abbreviation": abbreviation,
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "win_percentage": f"{win_pct:.3f}",
                    "games_back": "0.0",
                    "division": division,
                    "streak": _standing_stat(stats, "streak").get("displayValue") or "",  # Can be enhanced later
                    "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else "",
                    "record_display": record_display,
                    # Expanded NFL data
                    "points_for": int(stats_dict.get('pointsFor', 0)),
                    "points_against": int(stats_dict.get('pointsAgainst', 0)),
                    "point_differential": int(stats_dict.get('pointDifferential', 0)),
                    "division_wins": int(stats_dict.get('divisionWins', 0)),
                    "division_losses": int(stats_dict.get('divisionLosses', 0)),
                    "playoff_seed": int(stats_dict.get('playoffSeed', 0)) if stats_dict.get('playoffSeed', 0) > 0 else None
                }
                
                standings.append(team_data)

                if division not in division_teams:
                    division_teams[division] = []
                division_teams[division].append(team_data)
                
        
        # Calculate games back for each division
        for division, teams in division_teams.items():
            teams.sort(key=lambda x: (-x["wins"], x["losses"]))
            
            if teams:
                leader = teams[0]
                leader_wins = leader["wins"]
                leader_losses = leader["losses"]
                
                for i, team in enumerate(teams):
                    if i == 0:
                        team["games_back"] = "—"
                    else:
                        team_wins = team["wins"]
                        team_losses = team["losses"]
                        games_back = ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2
                        team["games_back"] = f"{games_back:.1f}" if games_back > 0 else "0.0"
        
        # Sort by division, then by wins
        standings.sort(key=lambda x: (x["division"], -x["wins"], x["losses"]))
        
        return standings

    except ApiError:
        raise
    except Exception as e:
        print(f"Error in fast NFL standings: {e}")
        return _get_standings_original("NFL")

def _get_nba_standings_fast():
    """Fast NBA standings using dedicated endpoint"""
    try:
        # The season ESPN calls current, as on the iPhone. A season from the calendar could be one
        # with no games yet, which read 0-0 for everyone from July.
        url = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
        data = _espn_answer(STANDINGS_UNAVAILABLE, url)
        if data is None:
            return []
        _listed(data, "children", STANDINGS_UNAVAILABLE)

        standings = []
        
        # NBA divisions mapping
        nba_divisions = {
            # Eastern Conference - Atlantic
            "BOS": "Atlantic", "BKN": "Atlantic", "NYK": "Atlantic", "NY": "Atlantic", "PHI": "Atlantic", "TOR": "Atlantic",
            # Eastern Conference - Central
            "CHI": "Central", "CLE": "Central", "DET": "Central", "IND": "Central", "MIL": "Central",
            # Eastern Conference - Southeast
            "ATL": "Southeast", "CHA": "Southeast", "MIA": "Southeast", "ORL": "Southeast", "WSH": "Southeast",
            # Western Conference - Northwest
            "DEN": "Northwest", "MIN": "Northwest", "OKC": "Northwest", "POR": "Northwest", "UTA": "Northwest", "UTAH": "Northwest",
            # Western Conference - Pacific
            "GSW": "Pacific", "GS": "Pacific", "LAC": "Pacific", "LAL": "Pacific", "PHX": "Pacific", "SAC": "Pacific",
            # Western Conference - Southwest
            "DAL": "Southwest", "HOU": "Southwest", "MEM": "Southwest", "NO": "Southwest", "SA": "Southwest"
        }
        
        # Process each conference
        division_teams = {}
        has_entries = False
        
        # Check if any conference has entries
        for conference in data.get('children', []):
            conf_standings = conference.get('standings', {})
            if conf_standings.get('entries', []):
                has_entries = True
                break
        
        # If no entries (early season), create fresh 0-0 standings from teams endpoint
        if not has_entries:
            return _get_nba_fresh_standings()
        
        for conference in data.get('children', []):
            conf_name = conference.get('name') or ''
            conf_standings = conference.get('standings', {})
            entries = conf_standings.get('entries', [])
            
            for entry in entries:
                team_info = entry.get('team', {})
                stats = entry.get('stats', [])
                
                # Create stats lookup
                stats_dict = {}
                for stat in stats:
                    stats_dict[stat.get('name', '')] = stat.get('value', 0)
                
                # Extract team data
                team_name = team_info.get('displayName') or 'Unknown'
                team_id = str(team_info.get('id') or '')
                abbreviation = team_info.get('abbreviation') or ''
                
                # Get wins/losses from stats
                wins = int(stats_dict.get('wins', 0))
                losses = int(stats_dict.get('losses', 0))
                win_pct = stats_dict.get('winPercent', 0.0)
                
                # Get division with conference prefix
                base_division = nba_divisions.get(abbreviation, "Unknown")
                division = f"{conf_name} {base_division}".strip() if base_division != "Unknown" else conf_name
                
                team_data = {
                    "team_name": team_name,
                    "team_id": team_id,
                    "abbreviation": abbreviation,
                    "wins": wins,
                    "losses": losses,
                    "win_percentage": f"{win_pct:.3f}",
                    "games_back": "0.0",
                    "division": division,
                    "streak": _standing_stat(stats, "streak").get("displayValue") or "",
                    "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else "",
                    # Expanded NBA data
                    "avg_points_for": float(stats_dict.get('avgPointsFor', 0.0)),
                    "avg_points_against": float(stats_dict.get('avgPointsAgainst', 0.0)),
                    "point_differential": int(stats_dict.get('pointDifferential', 0)),
                    "division_win_percent": float(stats_dict.get('divisionWinPercent', 0.0)),
                    "playoff_seed": int(stats_dict.get('playoffSeed', 0)) if stats_dict.get('playoffSeed', 0) > 0 else None,
                    "clinch_status": int(stats_dict.get('clincher', 0)) if stats_dict.get('clincher', 0) > 0 else None
                }
                
                standings.append(team_data)

                if division not in division_teams:
                    division_teams[division] = []
                division_teams[division].append(team_data)
                
        
        # Calculate games back for each division
        for division, teams in division_teams.items():
            teams.sort(key=lambda x: (-x["wins"], x["losses"]))
            
            if teams:
                leader = teams[0]
                leader_wins = leader["wins"]
                leader_losses = leader["losses"]
                
                for i, team in enumerate(teams):
                    if i == 0:
                        team["games_back"] = "—"
                    else:
                        team_wins = team["wins"]
                        team_losses = team["losses"]
                        games_back = ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2
                        team["games_back"] = f"{games_back:.1f}" if games_back > 0 else "0.0"
        
        # Sort by division, then by wins
        standings.sort(key=lambda x: (x["division"], -x["wins"], x["losses"]))
        
        return standings

    except ApiError:
        raise
    except Exception as e:
        print(f"Error in fast NBA standings: {e}")
        return _get_standings_original("NBA")

def _get_nba_fresh_standings():
    """Create fresh NBA standings with all teams at 0-0 for new season"""
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
        data = _espn_answer(STANDINGS_UNAVAILABLE, url)
        if data is None:
            return []
        _listed(data, "sports", STANDINGS_UNAVAILABLE)

        standings = []
        
        # NBA divisions mapping (same as main function)
        nba_divisions = {
            # Eastern Conference - Atlantic
            "BOS": "Atlantic", "BKN": "Atlantic", "NYK": "Atlantic", "NY": "Atlantic", "PHI": "Atlantic", "TOR": "Atlantic",
            # Eastern Conference - Central
            "CHI": "Central", "CLE": "Central", "DET": "Central", "IND": "Central", "MIL": "Central",
            # Eastern Conference - Southeast
            "ATL": "Southeast", "CHA": "Southeast", "MIA": "Southeast", "ORL": "Southeast", "WSH": "Southeast",
            # Western Conference - Northwest
            "DEN": "Northwest", "MIN": "Northwest", "OKC": "Northwest", "POR": "Northwest", "UTA": "Northwest", "UTAH": "Northwest",
            # Western Conference - Pacific
            "GSW": "Pacific", "GS": "Pacific", "LAC": "Pacific", "LAL": "Pacific", "PHX": "Pacific", "SAC": "Pacific",
            # Western Conference - Southwest
            "DAL": "Southwest", "HOU": "Southwest", "MEM": "Southwest", "NO": "Southwest", "SA": "Southwest"
        }
        
        # Conference mapping based on divisions
        eastern_divisions = ["Atlantic", "Central", "Southeast"]
        western_divisions = ["Northwest", "Pacific", "Southwest"]
        
        # Get teams from API
        if 'sports' in data and data['sports']:
            leagues = data['sports'][0].get('leagues', [])
            if leagues:
                teams = leagues[0].get('teams', [])
                
                for team in teams:
                    team_info = team.get('team', {})
                    
                    team_name = team_info.get('displayName') or 'Unknown'
                    team_id = str(team_info.get('id') or '')
                    abbreviation = team_info.get('abbreviation') or ''
                    
                    # Get division
                    base_division = nba_divisions.get(abbreviation, "Unknown")
                    
                    # Determine conference
                    if base_division in eastern_divisions:
                        conference = "Eastern Conference"
                    elif base_division in western_divisions:
                        conference = "Western Conference"
                    else:
                        conference = "Unknown Conference"
                    
                    division = f"{conference} {base_division}" if base_division != "Unknown" else conference
                    
                    # Create fresh team data with 0-0 record
                    team_data = {
                        "team_name": team_name,
                        "team_id": team_id,
                        "abbreviation": abbreviation,
                        "wins": 0,
                        "losses": 0,
                        "win_percentage": "0.000",
                        "games_back": "—",
                        "division": division,
                        "streak": "",
                        "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else ""
                    }
                    
                    standings.append(team_data)
        
        # Sort by division, then by team name (since all records are 0-0)
        standings.sort(key=lambda x: (x["division"], x["team_name"]))
        
        return standings

    except ApiError:
        raise
    except Exception as e:
        print(f"Error in fresh NBA standings: {e}")
        return []

def _get_nhl_standings_fast():
    """Fast NHL standings using dedicated endpoint"""
    try:
        url = "https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings"
        data = _espn_answer(STANDINGS_UNAVAILABLE, url)
        if data is None:
            return []
        _listed(data, "children", STANDINGS_UNAVAILABLE)

        standings = []
        
        # NHL divisions mapping
        nhl_divisions = {
            # Eastern Conference - Atlantic
            "BOS": "Atlantic", "BUF": "Atlantic", "DET": "Atlantic", "FLA": "Atlantic", 
            "MTL": "Atlantic", "OTT": "Atlantic", "TB": "Atlantic", "TOR": "Atlantic",
            # Eastern Conference - Metropolitan  
            "CAR": "Metropolitan", "CBJ": "Metropolitan", "NJ": "Metropolitan", "NYI": "Metropolitan",
            "NYR": "Metropolitan", "PHI": "Metropolitan", "PIT": "Metropolitan", "WSH": "Metropolitan",
            # Western Conference - Central
            "CHI": "Central", "COL": "Central", "DAL": "Central", "MIN": "Central",
            "NSH": "Central", "STL": "Central", "UTA": "Central", "UTAH": "Central", "WPG": "Central",
            # Western Conference - Pacific
            "ANA": "Pacific", "CGY": "Pacific", "EDM": "Pacific", "LA": "Pacific",
            "SJ": "Pacific", "SEA": "Pacific", "VAN": "Pacific", "VGK": "Pacific"
        }
        
        # Process each conference
        for conference in data.get('children', []):
            conf_name = conference.get('name') or ''
            conf_standings = conference.get('standings', {})
            entries = conf_standings.get('entries', [])
            
            for entry in entries:
                team_info = entry.get('team', {})
                stats = entry.get('stats', [])
                
                # Create stats lookup
                stats_dict = {}
                for stat in stats:
                    stats_dict[stat.get('name', '')] = stat.get('value', 0)
                
                # Extract team data
                team_name = team_info.get('displayName') or 'Unknown'
                team_id = str(team_info.get('id') or '')
                abbreviation = team_info.get('abbreviation') or ''
                
                # Get wins/losses from stats
                wins = int(stats_dict.get('wins', 0))
                losses = int(stats_dict.get('losses', 0))
                ot_losses = int(stats_dict.get('otLosses', 0))
                points = int(stats_dict.get('points', 0))
                
                # NHL uses points, not win percentage
                games_played = wins + losses + ot_losses
                point_pct = points / (games_played * 2) if games_played > 0 else 0.0
                
                # Get division with conference prefix
                base_division = nhl_divisions.get(abbreviation, "Unknown")
                division = f"{conf_name} {base_division}".strip() if base_division != "Unknown" else conf_name
                
                team_data = {
                    "team_name": team_name,
                    "team_id": team_id,
                    "abbreviation": abbreviation,
                    "wins": wins,
                    "losses": losses,
                    "win_percentage": f"{point_pct:.3f}",
                    "games_back": "",
                    "division": division,
                    "streak": _standing_stat(stats, "streak").get("displayValue") or "",
                    "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else "",
                    # Expanded NHL data
                    "points": points,
                    "ot_losses": ot_losses,
                    "goals_for": int(stats_dict.get('pointsFor', 0)),
                    "goals_against": int(stats_dict.get('pointsAgainst', 0)),
                    "goal_differential": int(stats_dict.get('pointDifferential', 0)),
                    "playoff_seed": int(stats_dict.get('playoffSeed', 0)) if stats_dict.get('playoffSeed', 0) > 0 else None
                }
                
                standings.append(team_data)
                
        
        # Sort final standings by division, then by points
        standings.sort(key=lambda x: (x["division"], -x["points"], -x["wins"]))
        
        return standings

    except ApiError:
        raise
    except Exception as e:
        print(f"Error in NHL standings: {e}")
        return _get_standings_original("NHL")

def _standing_stat(stats, stat_type):
    """The stat with this `type`. ESPN repeats `name` once per split (home, away,
    vs. conference...), so reading by name gets whichever split came last."""
    for stat in stats or []:
        if stat.get("type") == stat_type:
            return stat
    return {}


def _record_parts(summary):
    """"7-1" or "10-4-1" as a tuple of three ints; a missing part is 0."""
    parts = []
    for piece in str(summary or "").split("-")[:3]:
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    parts += [0] * (3 - len(parts))
    return tuple(parts)


def _games_back(stat):
    """ESPN's 0 and 2 read "-" and "2" there. These read as the NBA's do, "—" and "2.0"."""
    value = stat.get("value")
    return f"{value:.1f}" if isinstance(value, (int, float)) and value > 0 else "—"


def _college_standing_row(entry, conference):
    team_info = _as_dict(entry.get("team"))
    stats = _dicts(entry.get("stats"))
    overall = _standing_stat(stats, "total")
    wins, losses, ties = _record_parts(overall.get("summary") or overall.get("displayValue"))
    games = wins + losses + ties
    conf = _standing_stat(stats, "vsconf")
    return {
        "team_name": team_info.get("displayName") or "Unknown",
        "team_id": str(team_info.get("id") or ""),
        "abbreviation": team_info.get("abbreviation") or "",
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_percentage": f"{(wins + ties / 2) / games:.3f}" if games else "0.000",
        "games_back": _games_back(_standing_stat(stats, "gamesbehind")),
        "conference_record": conf.get("summary") or conf.get("displayValue") or "",
        "division": conference,
        "streak": _standing_stat(stats, "streak").get("displayValue") or "",
        "logo": next(iter(_dicts(team_info.get("logos"))), {}).get("href", ""),
    }


def parse_college_standings(data):
    """Every team in a college /standings response. Conferences can nest (the Sun
    Belt does) and a league can have no conferences at all, with its entries at
    the root (women's college hockey)."""
    rows = []

    def walk(node, conference):
        name = node.get("name") or conference
        for entry in _dicts(_as_dict(node.get("standings")).get("entries")):
            rows.append(_college_standing_row(entry, name))
        for child in _dicts(node.get("children")):
            walk(child, name)

    walk(_as_dict(data), "League")
    rows.sort(key=lambda r: (r["division"], -float(r["win_percentage"]), -r["wins"], r["losses"]))
    return rows


STANDINGS_UNAVAILABLE = "ESPN isn't providing standings right now. Try again in a minute."


def _standings_or_nothing(league, path, query="", parse=parse_college_standings):
    """A league's rows from /standings, [] if ESPN answered and has none, so that the screens say
    there's no data. A request that failed raises ApiError instead: it says nothing about what ESPN
    has. The WNBA, college and soccer leagues have no fallback to the team list: its rows have no
    division, which Teams leaves out, so it opened with no tabs and said nothing, college's are the
    first 50 teams of all of them, with one request each, and a soccer team whose record request
    failed read 0-0."""
    try:
        resp = _http_get(f"https://site.api.espn.com/apis/v2/sports/{path}/standings{query}")
        if resp.status_code != 200:
            raise ApiError(STANDINGS_UNAVAILABLE)
        data = resp.json()
        _listed(data, "children", STANDINGS_UNAVAILABLE)
        return parse(data)
    except (requests.RequestException, ValueError) as e:
        print(f"Error in {league} standings: {e}")
        raise ApiError(STANDINGS_UNAVAILABLE) from e


TEAMS_UNAVAILABLE = "ESPN isn't providing teams right now. Try again in a minute."


def _team_list(league_key):
    """A league's /teams?limit=1000 as rows, [] if ESPN answered with none. ESPN's list stops at
    50 unless told otherwise, and college leagues run past that."""
    try:
        resp = _http_get(f"{BASE_URL}/{LEAGUES[league_key]}/teams", params={"limit": 1000}, timeout=20)
        if resp.status_code != 200:
            raise ApiError(TEAMS_UNAVAILABLE)
        data = resp.json()
        _listed(data, "sports", TEAMS_UNAVAILABLE)
        return parse_team_list(data)
    except (requests.RequestException, ValueError) as e:
        print(f"Error in {league_key} teams: {e}")
        raise ApiError(TEAMS_UNAVAILABLE) from e


def get_teams(league_key):
    """Every team in a league, for the Teams screen and the Transactions team filter, as the
    iPhone lists them: see team_list for where each league's come from.

    A team in the standings is its standings row, with its division and record. The standings
    failing doesn't lose the list: its teams come back with no group or record, each marked
    `records_unavailable`, so the screen can say so rather than show them 0-0. The list failing,
    or the standings where they are the list, raises ApiError."""
    if team_list_source(LEAGUES[league_key]) == TEAM_LIST_FROM_STANDINGS:
        return get_standings(league_key)
    listed = _team_list(league_key)
    try:
        standings = get_standings(league_key)
    except ApiError:
        return [{**team, "records_unavailable": True} for team in listed]
    return with_standings(listed, standings)


def _get_ncaaf_standings_fast():
    """College football standings, every conference in the user's coverage setting.

    With no `group=`, ESPN returns FBS only, while the scoreboard shows FCS games too.
    """
    return _standings_or_nothing("NCAAF", "football/college-football",
                                 f"?group={_ncaaf_coverage_group()}")


def standings_cache_key(league_key):
    """What to cache a league's standings under. College football's depend on a setting."""
    key = f"standings_{league_key}"
    return f"{key}_group{_ncaaf_coverage_group()}" if league_key == "NCAAF" else key


def _get_ncaam_standings_fast():
    """Men's college basketball standings, every conference."""
    return _standings_or_nothing("NCAAM", "basketball/mens-college-basketball")


def _get_ncaawb_standings_fast():
    """Women's college basketball standings, every conference."""
    return _standings_or_nothing("NCAAWB", "basketball/womens-college-basketball")


def _get_ncaah_standings_fast():
    """Men's college hockey standings, every conference."""
    return _standings_or_nothing("NCAAH", "hockey/mens-college-hockey")


def _get_ncaawh_standings_fast():
    """Women's college hockey standings. ESPN sends these at the root, with no conferences."""
    return _standings_or_nothing("NCAAWH", "hockey/womens-college-hockey")


def _get_standings_original(league_key):
    """Original standings method (slower but works for all leagues)"""
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    
    # Use teams API to get all teams and their records
    teams_url = f"{BASE_URL}/{league_path}/teams"
    data = _espn_answer(STANDINGS_UNAVAILABLE, teams_url)
    if data is None:
        return []
    _listed(data, "sports", STANDINGS_UNAVAILABLE)

    return _parse_standings_from_teams_api(data, league_key)

def _parse_standings_from_teams_api(data, league_key):
    """Parse standings from the teams API with detailed team records"""
    standings = []
    
    # MLB Division mapping - Fixed Oakland abbreviation
    mlb_divisions = {
        # American League East
        "BAL": "AL East", "BOS": "AL East", "NYY": "AL East", "TB": "AL East", "TOR": "AL East",
        # American League Central  
        "CHW": "AL Central", "CLE": "AL Central", "DET": "AL Central", "KC": "AL Central", "MIN": "AL Central",
        # American League West
        "HOU": "AL West", "LAA": "AL West", "OAK": "AL West", "SEA": "AL West", "TEX": "AL West",
        # National League East
        "ATL": "NL East", "MIA": "NL East", "NYM": "NL East", "PHI": "NL East", "WSH": "NL East",
        # National League Central
        "CHC": "NL Central", "CIN": "NL Central", "MIL": "NL Central", "PIT": "NL Central", "STL": "NL Central",
        # National League West
        "ARI": "NL West", "COL": "NL West", "LAD": "NL West", "SD": "NL West", "SF": "NL West"
    }
    
    try:
        # Navigate through the teams structure
        sports = data.get("sports", [])
        if not sports:
            return []
            
        leagues = sports[0].get("leagues", [])
        if not leagues:
            return []
            
        teams = leagues[0].get("teams", [])
        
        for team_entry in teams:
            team = team_entry.get("team", {})
            
            # Get team info
            team_name = team.get("displayName") or "Unknown"
            abbreviation = team.get("abbreviation") or ""
            team_id = team.get("id") or ""
            
            # Get division from mapping (fix Oakland)
            if abbreviation == "ATH":  # ESPN uses ATH for Athletics
                abbreviation = "OAK"   # But our mapping uses OAK
            division = mlb_divisions.get(abbreviation, "League") if league_key == "MLB" else "League"
            
            # Get detailed team record by making individual API call
            wins, losses, win_pct, streak = _get_team_record(team_id, league_key)
            
            standings.append({
                "team_name": team_name,
                "team_id": team_id,
                "abbreviation": abbreviation,
                "wins": wins,
                "losses": losses,
                "win_percentage": win_pct,
                "games_back": "N/A",  # We'll calculate this after sorting by division
                "division": division,
                "streak": streak,  # Add streak information
                "logo": team.get("logos", [{}])[0].get("href", "") if team.get("logos") else ""
            })
        
        # Sort by division, then by wins (descending), then by win percentage
        standings.sort(key=lambda x: (x["division"], -int(x["wins"]), -float(x["win_percentage"])))
        
        # Calculate games back within each division
        if standings:
            # Group by division and calculate games back for each division
            divisions = {}
            for team in standings:
                div = team["division"]
                if div not in divisions:
                    divisions[div] = []
                divisions[div].append(team)
            
            # Calculate games back for each division
            for div_name, div_teams in divisions.items():
                if div_teams:
                    leader_wins = int(div_teams[0]["wins"])
                    leader_losses = int(div_teams[0]["losses"])
                    
                    for i, team in enumerate(div_teams):
                        if i == 0:
                            team["games_back"] = "—"  # Leader
                        else:
                            team_wins = int(team["wins"])
                            team_losses = int(team["losses"])
                            games_back = ((leader_wins - team_wins) + (team_losses - leader_losses)) / 2
                            team["games_back"] = f"{games_back:.1f}" if games_back > 0 else "0.0"
        
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error parsing teams API data: {e}")
        return []
    
    return standings

def _get_team_record(team_id, league_key):
    """Get individual team's win/loss record with streak information"""
    if not team_id:
        return 0, 0, "0.000", ""
        
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return 0, 0, "0.000", ""
    
    try:
        # Get detailed team information
        team_url = f"{BASE_URL}/{league_path}/teams/{team_id}"
        resp = _http_get(team_url)
        
        if resp.status_code != 200:
            return 0, 0, "0.000", ""
        
        data = resp.json()
        team = data.get("team", {})
        record = team.get("record", {})
        items = record.get("items", [])
        
        # Look for overall record
        for item in items:
            if item.get("type") == "total":
                summary = item.get("summary", "0-0")
                stats = item.get("stats", [])
                
                # The stats name each number. Football's summary can have a third part, its
                # ties: unpacking three parts into two used to fail, and the team read 0-0.
                by_name = {stat.get("name"): stat.get("value") for stat in stats}
                if all(isinstance(by_name.get(n), (int, float)) for n in ("wins", "losses")):
                    wins, losses = int(by_name["wins"]), int(by_name["losses"])
                else:
                    wins, losses, _ = _record_parts(summary)
                total_games = wins + losses
                win_pct = f"{wins/total_games:.3f}" if total_games > 0 else "0.000"

                # Extract streak information from stats
                streak = ""
                for stat in stats:
                    if stat.get("name") == "streak":
                        streak_value = stat.get("value", 0)
                        if isinstance(streak_value, (int, float)) and streak_value != 0:
                            if streak_value > 0:
                                streak = f"W{int(streak_value)}"
                            else:
                                streak = f"L{int(abs(streak_value))}"
                        break
                
                return wins, losses, win_pct, streak
        
        return 0, 0, "0.000", ""
        
    except Exception as e:
        print(f"Error getting team {team_id} record: {e}")
        return 0, 0, "0.000", ""

# Player leaders. ESPN has them here, with names and teams inside the response, for these
# leagues and soccer's (SOCCER_LEAGUES), which ask for their own season types. /leaders is a 404
# for college hockey, so asking would only look like a failure: that league has no leaders to show.
LEADERS_BASE_URL = "https://site.web.api.espn.com/apis/site/v3/sports"
CORE_BASE_URL = "https://sports.core.api.espn.com/v2/sports"
LEADER_LEAGUES = {"NFL", "NCAAF", "NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "MLB"}
LEADERS_LIMIT = 20
# /leaders answers 500 far more often the more it's asked for. It can be a retry away, or last
# for minutes at one limit while a smaller one works: on Nov 4, 2026, four leagues' 2025 season
# failed nine times in 90 seconds at 20, and every league answered at 5. A shorter list beats
# none. Leaving out region and lang makes the 500s much likelier, even at 20.
LEADERS_SMALLER_LIMITS = (10, 5)
STATISTICS_UNAVAILABLE = "ESPN isn't providing these right now. Try again in a minute."
PRESEASON = 1
REGULAR_SEASON = 2
POSTSEASON = 3
NEW_SEASON_DAYS = 3
CORE_SEASON_CACHE_SECONDS = 300
_CORE_SEASON_CACHE = {}  # league path: (when it was asked, ESPN's answer)
_CORE_SEASON_CACHE_LOCK = threading.Lock()
# /leaders lists these lowest first, and everything else highest first.
LOW_IS_GOOD_LEADERS = {"avgGoalsAgainst", "ERA", "WHIP", "opponentAvg"}
# No qualifying minimum in practice: 2026's list opens with 13 players on .000, catchers and
# outfielders among them. The iPhone leaves it out too.
LEADERS_NOT_SHOWN = {"opponentAvg"}
# A team's answer has these as well, repeating its yards lists with the same players.
REPEATED_FOR_ONE_TEAM = {"passingLeader", "rushingLeader", "receivingLeader"}
# What one team's ranks are, since the same season words on the league's list mean the league.
ONE_TEAM_RANKS = "ranked within this team, qualified players first"


def _no_leaders():
    return {"player_stats": [], "team_stats": []}


def core_season(league_path):
    """ESPN's own idea of a league's season now, with a whole number for its year. A good answer
    is kept for a few minutes, since Favorites asks once per team each time it rebuilds. Treat it
    as read-only: callers share it. Threads asking at once can each ask ESPN, which does no harm."""
    with _CORE_SEASON_CACHE_LOCK:
        cached = _CORE_SEASON_CACHE.get(league_path)
    if cached and time.monotonic() - cached[0] < CORE_SEASON_CACHE_SECONDS:
        return cached[1]
    sport, league = league_path.split("/", 1)
    try:
        resp = _http_get(f"{CORE_BASE_URL}/{sport}/leagues/{league}/season", timeout=10)
        season = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        raise ApiError(STATISTICS_UNAVAILABLE) from e
    season = _as_dict(season)
    if not isinstance(season.get("year"), int):
        raise ApiError(STATISTICS_UNAVAILABLE)
    with _CORE_SEASON_CACHE_LOCK:
        _CORE_SEASON_CACHE[league_path] = (time.monotonic(), season)
    return season


def latest_regular_season(season):
    """The year whose regular season to show, from core_season rather than the calendar: the NBA's
    2026-27 season is 2027. A season's playoffs and off-season come after its regular season
    and are filed under its year, so only a preseason means that the last one is the latest."""
    return season["year"] - 1 if _as_dict(season.get("type")).get("type") == PRESEASON else season["year"]


def _leaders_season(league_path):
    return latest_regular_season(core_season(league_path))


def regular_season_just_began(season):
    """Whether core_season says a regular season began in the last few days. ESPN's type turns over
    before the first game (college basketball at 07:00 UTC on Nov 1, its first game at 14:30), and
    until there are games, some of its feeds answer 500 for the new season."""
    season_type = _as_dict(season.get("type"))
    if season_type.get("type") != REGULAR_SEASON:
        return False
    try:
        began = datetime.fromisoformat(str(season_type.get("startDate")).replace("Z", "+00:00"))
        days = (datetime.now(began.tzinfo) - began).total_seconds() / 86400
    except (ValueError, TypeError):
        return False
    return 0 <= days <= NEW_SEASON_DAYS


def _fetch_leaders(league_path, year, season_type=REGULAR_SEASON, team_id=None):
    """A season's leaders from /leaders, the regular season's unless asked for another type, or
    None if ESPN has no such season. Without `seasontype`, a finished season's answer is its
    postseason; soccer's answer is the wrong season or a 500 without `season`, and a 404 or a
    playoff round's without `seasontype`. A second try at the full list gets a throwaway
    parameter, since ESPN can cache a 500 for up to 30 seconds.
    `team_id` asks for one team's players, up to 20 of them in every category it has anyone in."""
    attempts = [{"limit": LEADERS_LIMIT}, {"limit": LEADERS_LIMIT, "_": int(time.time() * 1000)}]
    attempts += [{"limit": limit} for limit in LEADERS_SMALLER_LIMITS]
    for attempt in attempts:
        if "_" in attempt:
            time.sleep(1)
        params = {"region": "us", "lang": "en", "season": year, "seasontype": season_type, **attempt}
        if team_id is not None:
            params["team"] = team_id
        try:
            resp = _http_get(f"{LEADERS_BASE_URL}/{league_path}/leaders", params=params, timeout=15)
            answer = resp.json() if resp.status_code == 200 else None
        except (requests.RequestException, ValueError) as e:
            raise ApiError(STATISTICS_UNAVAILABLE) from e
        if resp.status_code == 200:
            # None here means no such season, and a null body isn't ESPN saying that.
            if not isinstance(answer, dict):
                raise ApiError(STATISTICS_UNAVAILABLE)
            return answer
        if resp.status_code == 404:
            return None
        if resp.status_code < 500:
            break
    raise ApiError(STATISTICS_UNAVAILABLE)


def _leaders_in_order(key, leaders):
    """The leaders up to the first who breaks the category's direction. ESPN can follow its
    qualified players with everyone else: on Nov 4, 2026, NCAAM field goal percentage read
    71.4, 64.3, 55.6, 50.0, 46.2, 42.9, then 100.0 fourteen times. Those aren't the next best."""
    kept, last = [], None
    for leader in leaders:
        value = leader.get("value")
        if isinstance(value, (int, float)):
            if last is not None and (value > last if key not in LOW_IS_GOOD_LEADERS else value < last):
                break
            last = value
        kept.append(leader)
    return kept


def _parse_leaders(data, one_team=False):
    """/leaders to the rows the dialog shows, in ESPN's order, which is best first even for a
    stat where low is good. A league's ratings can be there with nobody rated, such as the WNBA's
    Player Efficiency Rating, where the leaders all read 0.0: that isn't a list of leaders.
    Asked for a past college football season's regular season, ESPN answers with type 3, and
    the numbers run through the bowl games, so "Season" says what they are and "Postseason"
    doesn't: 4379 passing yards for 2025, where the core API's type 2 says 4129.

    `one_team` is an answer for one team, for Team Hub. It has qualified players first and then
    everyone else, and Team Hub shows them all, so its lists aren't cut where the numbers turn
    back up: that would lose a real player, such as Tyler Herro on 20.5 points, listed after a
    teammate on 5.6. Its passing, rushing and receiving "leader" lists repeat its yards lists, and
    its season says the ranks are within the team. The iPhone: leaderCategories(oneTeam:)."""
    data = _as_dict(data)
    requested = _as_dict(data.get("requestedSeason"))
    season_type = _as_dict(requested.get("type"))
    if season_type.get("type") == PRESEASON:
        return _no_leaders()

    categories = []
    for category in _dicts(_as_dict(data.get("leaders")).get("categories")):
        key = category.get("name") or "unknown"
        if key in LEADERS_NOT_SHOWN or (one_team and key in REPEATED_FOR_ONE_TEAM):
            continue
        title = category.get("displayName") or key.title()
        leaders = _dicts(category.get("leaders"))
        if not one_team:
            leaders = _leaders_in_order(key, leaders)
        if all(not leader.get("value") for leader in leaders):
            continue
        stats = []
        for leader in leaders:
            athlete = _as_dict(leader.get("athlete"))
            team = _as_dict(leader.get("team"))
            name = athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName")
            if name:
                stats.append({
                    "player_name": name,
                    "team": team.get("abbreviation") or team.get("displayName") or "",
                    "value": leader_display_value(key, leader.get("value"), leader.get("displayValue")),
                    "stat_name": title,
                })
        if stats:
            # `key` is ESPN's name for the category, which stat_glossary finds its definition by.
            categories.append({"category": title, "key": key, "stats": stats})
    if not categories:
        return _no_leaders()
    name = "Season" if season_type.get("type") == POSTSEASON else season_type.get("name")
    season = _season_label(requested.get("displayName"), name)
    if one_team:
        season = f"{season}, {ONE_TEAM_RANKS}" if season else ONE_TEAM_RANKS[0].upper() + ONE_TEAM_RANKS[1:]
    return {"player_stats": categories, "team_stats": [], "season": season}


def _season_label(year_name, type_name):
    return " ".join(str(part) for part in (year_name, type_name) if part)


def get_team_player_leaders(league_key, team_id):
    """One team's players in each stat category, ranked among themselves, for Team Hub's Stats
    tab, as {player_stats, team_stats, season}: /leaders with team=, from the same season as
    get_player_statistics. The league's list wouldn't do: 20 rows of it had no Blackhawks in any
    category. Empty for a league without /leaders. A failed request raises ApiError.

    The iPhone also has soccer and college hockey, from the core API's whole league filtered to
    the team, which Windows doesn't read for a team yet."""
    key = league_key if league_key in LEAGUES else str(league_key).upper()
    if key not in LEADER_LEAGUES:
        return _no_leaders()
    league_path = LEAGUES[key]
    year = _leaders_season(league_path)
    answers = [_fetch_leaders(league_path, year, team_id=team_id)]
    result = _parse_leaders(answers[0], one_team=True)
    if not result["player_stats"]:
        answers.append(_fetch_leaders(league_path, year - 1, team_id=team_id))
        result = _parse_leaders(answers[1], one_team=True)
    if not any(answer is not None for answer in answers):
        raise ApiError(STATISTICS_UNAVAILABLE)
    return result


def get_player_statistics(league_key):
    """A league's player leaders, as {player_stats, team_stats, season}. `season` names what
    they're from, such as "2026-27 Regular Season". Empty means ESPN has no leaders for this
    league. A failed request raises ApiError instead, so the dialog can say so."""
    key = league_key if league_key in LEAGUES else league_key.upper()
    if key in SOCCER_LEAGUES:
        return _soccer_player_statistics(key)
    if key not in LEADER_LEAGUES:
        return _no_leaders()
    league_path = LEAGUES[key]
    year = _leaders_season(league_path)
    # A new regular season can start with nobody on the list yet, or be a 404 for now.
    answers = [_fetch_leaders(league_path, year)]
    result = _parse_leaders(answers[0])
    if not result["player_stats"]:
        answers.append(_fetch_leaders(league_path, year - 1))
        result = _parse_leaders(answers[1])
    if not any(answer is not None for answer in answers):
        raise ApiError(STATISTICS_UNAVAILABLE)
    return result


# Soccer's leaders, from /leaders as on the iPhone (fetchSoccerLeaders): one request, with names and
# teams inside, where the core API took one for each player and team, about 150. Its season comes from
# core_season, never the calendar, and its season type from soccer.leaders_season_types: type 1, or
# for Liga MX the torneo that's on. Asked for 20, soccer's /leaders answers 500 more than the other
# sports' do, and NWSL's and CONCACAF's never have at 20, so those step down to 10 as theirs do.
# A new season or torneo can have no list yet, which means the one before, and three are tried, as
# the core API's three seasons were.
SOCCER_LEADER_TRIES = 3


def _core_season_by_year(league_path, year):
    """The core API's answer for one season, with its types inside. Only Liga MX needs an earlier
    season's, to find its Clausura; failing means not knowing which torneo to show, so it says so."""
    sport, league = league_path.split("/", 1)
    try:
        resp = _http_get(f"{CORE_BASE_URL}/{sport}/leagues/{league}/seasons/{year}", timeout=10)
        season = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        raise ApiError(STATISTICS_UNAVAILABLE) from e
    if not isinstance(season, dict):
        raise ApiError(STATISTICS_UNAVAILABLE)
    return season


def _soccer_seasons_to_try(league_key, league_path, season, now):
    """(year, season type) to ask, latest first: ESPN's season and the two before it. An earlier
    season's types are only asked for by a league that needs them, and only once reached."""
    for year in range(season["year"], season["year"] - SOCCER_LEADER_TRIES, -1):
        if year == season["year"] or league_key not in TORNEO_LEAGUES:
            types_from = season
        else:
            types_from = _core_season_by_year(league_path, year)
        for season_type in leaders_season_types(league_key, types_from, now):
            yield year, season_type


def _soccer_player_statistics(league_key):
    """A soccer league's leaders, in the shape get_player_statistics returns. Nobody on a list yet
    means the season or torneo before; a failed request says so rather than showing that one."""
    league_path = LEAGUES[league_key]
    season = core_season(league_path)
    now = datetime.now(timezone.utc)
    seasons = _soccer_seasons_to_try(league_key, league_path, season, now)
    for year, season_type in islice(seasons, SOCCER_LEADER_TRIES):
        answer = _fetch_leaders(league_path, year, season_type)
        lists = soccer_leader_lists(answer)
        if lists:
            return {"player_stats": lists, "team_stats": [],
                    "season": soccer_leaders_season(answer, league_key, year)}
    return _no_leaders()


# Team statistics. One request has every team's whole stat line. ESPN has none for college hockey
# (an empty answer) or soccer (a 500), and the per-team endpoint has nothing there either, so those
# leagues have no team statistics to show.
TEAM_STATS_BASE_URL = "https://site.web.api.espn.com/apis/common/v3/sports"
TEAM_STAT_LEAGUES = {"NFL", "NCAAF", "NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "MLB"}
# Football collapses to 25 teams at limit=1000.
TEAM_STATS_LIMIT = 500
# ESPN returns at most 400 teams, and page 2 is empty or a 500. Late in a college basketball season
# it lists 722, half of them schools that played one Division I game, so the list is asked for
# again sorted each way by a column every team has: 400 from each end cover them all, up to 800.
# Only basketball says how many it has. The rest fit, so they never need it.
TEAM_STATS_SORT = {"basketball": "offensive.avgTurnovers"}
# Their lists have schools outside Division I. College football's is only FBS.
TEAM_STATS_NEEDS_TEAM_LIST = {"NCAAM", "NCAAWB"}
TEAMS_MISSING = "some teams missing"


class _TeamStatsServerError(ApiError):
    """ESPN answered with a 5xx, which is different from it not being reachable: see
    regular_season_just_began."""


def _no_team_stats():
    return {"team_stats": [], "player_stats": []}


def _fetch_team_stats(league_path, year, sort=None):
    """A season's regular season team statistics, or None if ESPN has no such season. Without
    `seasontype`, a finished season's answer is its postseason: the WNBA's 8 playoff teams, not its
    15. A season ESPN doesn't have yet can be an empty answer, or a 500 for basketball."""
    params = {"region": "us", "lang": "en", "season": year, "seasontype": 2, "limit": TEAM_STATS_LIMIT}
    if sort:
        params["sort"] = sort
    try:
        resp = _http_get(f"{TEAM_STATS_BASE_URL}/{league_path}/statistics/byteam", params=params, timeout=20)
        answer = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        raise ApiError(STATISTICS_UNAVAILABLE) from e
    if resp.status_code == 200:
        # An empty object is a season ESPN doesn't have yet. A null body isn't.
        if not isinstance(answer, dict):
            raise ApiError(STATISTICS_UNAVAILABLE)
        return answer
    if resp.status_code == 404:
        return None
    raise (_TeamStatsServerError if resp.status_code >= 500 else ApiError)(STATISTICS_UNAVAILABLE)


def _division_one_ids(league_path):
    """The ids on ESPN's team list, which for college basketball is Division I alone: 362 teams
    for the women, with none from outside it. A failure fails the list, since it would leave
    out real teams, and the ranks behind them would be wrong."""
    try:
        resp = _http_get(f"{BASE_URL}/{league_path}/teams", params={"limit": 1000}, timeout=20)
        data = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        raise ApiError(STATISTICS_UNAVAILABLE) from e
    if data is None:
        raise ApiError(STATISTICS_UNAVAILABLE)
    sports = _dicts(_as_dict(data).get("sports"))
    leagues = _dicts(sports[0].get("leagues")) if sports else []
    entries = _dicts(leagues[0].get("teams")) if leagues else []
    return {str(_as_dict(entry.get("team")).get("id")) for entry in entries}


def _with_every_team(league_path, year, data):
    """The answer with the teams it couldn't fit, if it says it has more than it gave. A list with
    some of them cut would still look whole, with every rank after the gap wrong, so a failure
    here fails the lot."""
    teams = _dicts(data.get("teams"))
    count = _as_dict(data.get("pagination")).get("count")
    column = TEAM_STATS_SORT.get(league_path.split("/")[0])
    if not (column and isinstance(count, int) and count > len(teams)):
        return data
    every = {str(_as_dict(team.get("team")).get("id")): team for team in teams}
    for direction in ("desc", "asc"):
        more = _fetch_team_stats(league_path, year, f"{column}:{direction}")
        if more is None:
            raise ApiError(STATISTICS_UNAVAILABLE)
        for team in _dicts(more.get("teams")):
            every.setdefault(str(_as_dict(team.get("team")).get("id")), team)
    return {**data, "teams": list(every.values())}


def _division_one_list(key, league_path, data):
    """ESPN's team list, for a college basketball answer that needs it to tell Division I teams
    apart (see team_stats.qualified_teams), or None."""
    if key not in TEAM_STATS_NEEDS_TEAM_LIST or not needs_team_list(data):
        return None
    return _division_one_ids(league_path)


def _parse_team_stats(key, league_path, data, team_list=None):
    """The result for one season's answer. Asked for a past college football season's regular
    season, ESPN answers with type 3, with the numbers running through the bowl games, so "Season"
    says what they are, as it does for the leaders. If there are still fewer teams than ESPN says it
    has, past the 800 that two sorted requests can reach, the season says so rather than the list
    looking whole, since every rank in it could be low."""
    requested = _as_dict(data.get("requestedSeason"))
    season_type = _as_dict(requested.get("type"))
    if season_type.get("type") == PRESEASON:
        return _no_team_stats()
    team_stats = parse_team_stats(data, league_path.split("/")[0], team_list)
    if not team_stats:
        return _no_team_stats()
    name = "Season" if season_type.get("type") == POSTSEASON else season_type.get("name")
    season = _season_label(requested.get("displayName"), name)
    count = _as_dict(data.get("pagination")).get("count")
    if isinstance(count, int) and count > len(_dicts(data.get("teams"))):
        season = f"{season}, {TEAMS_MISSING}"
    return {"team_stats": team_stats, "player_stats": [], "season": season,
            "glossary": stat_glossary.glossary(data)}


def get_team_statistics(league_key):
    """A league's team statistics, as {team_stats, player_stats, season}, for the same season as
    get_player_statistics, the one ESPN says is the latest. `season` names it, such as
    "2026-27 Regular Season". Empty means ESPN has none for this league. A failed request raises
    ApiError instead, so the dialog can say so."""
    key = league_key if league_key in LEAGUES else league_key.upper()
    if key not in TEAM_STAT_LEAGUES:
        return _no_team_stats()
    return _latest_team_stats(key, LEAGUES[key])[0]


def _latest_team_stats(key, league_path):
    """(get_team_statistics' result, the answer it came from with every team, its team list),
    with None for the answer when there's nothing to show."""
    season = core_season(league_path)
    year = latest_regular_season(season)
    # A new regular season can start with nobody on the list yet, or be a 404 or for its first days
    # a 500 for now. Any other 500 is a failure to report, not a reason to show last season's
    # numbers. What's shown says which season it is.
    answers = []
    for season_year in (year, year - 1):
        try:
            answer = _fetch_team_stats(league_path, season_year)
        except _TeamStatsServerError:
            if season_year != year or not regular_season_just_began(season):
                raise
            answer = None
        answers.append(answer)
        if answer is not None:
            answer = _with_every_team(league_path, season_year, answer)
            preseason = _as_dict(_as_dict(answer.get("requestedSeason")).get("type")).get("type") == PRESEASON
            team_list = None if preseason else _division_one_list(key, league_path, answer)
            result = _parse_team_stats(key, league_path, answer, team_list)
            if result["team_stats"]:
                return result, answer, team_list
    if not any(answer is not None for answer in answers):
        raise ApiError(STATISTICS_UNAVAILABLE)
    return _no_team_stats(), None, None


# Team Hub's ranks. The core API's statistics for one team, the regular season (soccer files its
# whole league season under type 1), this season's or the last.
HUB_SEASON_TYPE = 2
SOCCER_SEASON_TYPE = 1


def _core_season_name(league_path, year, season):
    """What ESPN calls a season, such as "2026-27" or "2025-26 English Premier League". `season` is
    the core API's current one, so only an earlier season takes a request. If that fails, the year
    still says it isn't this season's."""
    if season.get("year") == year and season.get("displayName"):
        return season["displayName"]
    sport, league = league_path.split("/", 1)
    try:
        resp = _http_get(f"{CORE_BASE_URL}/{sport}/leagues/{league}/seasons/{year}", timeout=10)
        name = _as_dict(resp.json()).get("displayName") if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        name = None
    return name or str(year)


def _network_failed(error):
    """Whether an ApiError was the network not getting through rather than ESPN answering badly."""
    return isinstance(error.__cause__, (requests.ConnectionError, requests.Timeout))


def get_team_stat_rankings(league_key, team_id):
    """Where one team ranks in each of its stats, for Team Hub's Stats tab, as {rankings, season}:
    team_stats.hub_rankings' rows and what season they're from. As on the iPhone
    (fetchTeamStatRankings), the stats come from the core API's statistics for the team, and a
    rank from the league's byteam list where it has the stat, if it's the same season's regular
    season. Not having that list only costs the ranks that come from it, unless the network didn't
    get through, which fails the lot. Empty rankings means ESPN has none to show. A failed request
    raises ApiError, which the iPhone treats as no rankings."""
    key = league_key if league_key in LEAGUES else str(league_key).upper()
    league_path = LEAGUES.get(key)
    if not league_path or key in GOLF_TOURS:
        return {"rankings": [], "season": ""}
    sport, league = league_path.split("/", 1)

    answer, team_list = None, None
    if key in TEAM_STAT_LEAGUES:
        try:
            _result, answer, team_list = _latest_team_stats(key, league_path)
        except ApiError as e:
            if _network_failed(e):
                raise

    season = core_season(league_path)
    soccer = key in SOCCER_LEAGUES
    year = season["year"] if soccer else latest_regular_season(season)
    season_type = SOCCER_SEASON_TYPE if soccer else HUB_SEASON_TYPE
    for season_year in (year, year - 1):
        url = (f"{CORE_BASE_URL}/{sport}/leagues/{league}/seasons/{season_year}"
               f"/types/{season_type}/teams/{team_id}/statistics")
        try:
            resp = _http_get(url, timeout=15)
            data = resp.json() if resp.status_code == 200 else None
        except (requests.RequestException, ValueError) as e:
            raise ApiError(STATISTICS_UNAVAILABLE) from e
        if resp.status_code == 404:
            continue  # No such season for this team.
        if resp.status_code != 200:
            # A new season's first days can be a 500 for now, as byteam's are.
            if resp.status_code >= 500 and season_year == year and regular_season_just_began(season):
                continue
            raise ApiError(STATISTICS_UNAVAILABLE)
        if not isinstance(data, dict):
            raise ApiError(STATISTICS_UNAVAILABLE)
        # Only if it's the same numbers, or the rank would be for others. A past college football
        # list is type 3 through the bowls, where these are type 2: Alabama's 3,551 passing yards in
        # 2025 are 11th, and that list has 3,953, 6th.
        requested = _as_dict((answer or {}).get("requestedSeason"))
        same = (answer is not None and requested.get("year") == season_year
                and _as_dict(requested.get("type")).get("type") == REGULAR_SEASON)
        ranks = team_stats.LeagueRanks(answer, sport, team_list) if same else None
        rankings = team_stats.hub_rankings(data, team_id, key.startswith("NCAA"), ranks)
        if rankings:
            name = _core_season_name(league_path, season_year, season)
            return {"rankings": rankings, "season": name if soccer else f"{name} Regular Season"}
    return {"rankings": [], "season": ""}


def league_sport(league_key):
    """The first part of a league's path, "baseball" for MLB, which stat_glossary and team_stats
    go by. "" for a league it doesn't know."""
    key = league_key if league_key in LEAGUES else str(league_key).upper()
    return LEAGUES.get(key, "").split("/")[0]


_GLOSSARY_CACHE = {}  # league key: ESPN's definitions, which don't change while the app is open
_GLOSSARY_CACHE_LOCK = threading.Lock()


def get_stat_glossary(league_key):
    """ESPN's definitions of a league's statistics, as stat_glossary.glossary has them, for the
    player leaders: the team statistics carry their own. They come with byteam, and one team's
    worth has them all, as the iPhone asks (TeamStatsStore.glossary). A league with no byteam has
    no definitions, which is {}. A failed request raises ApiError, so the definitions can say they
    couldn't be had rather than that ESPN has none."""
    key = league_key if league_key in LEAGUES else league_key.upper()
    if key not in TEAM_STAT_LEAGUES:
        return {}
    with _GLOSSARY_CACHE_LOCK:
        if key in _GLOSSARY_CACHE:
            return _GLOSSARY_CACHE[key]
    params = {"region": "us", "lang": "en", "limit": 1}
    try:
        resp = _http_get(f"{TEAM_STATS_BASE_URL}/{LEAGUES[key]}/statistics/byteam", params=params, timeout=15)
        answer = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        raise ApiError(STATISTICS_UNAVAILABLE) from e
    if not isinstance(answer, dict):
        raise ApiError(STATISTICS_UNAVAILABLE)
    found = stat_glossary.glossary(answer)
    if found:  # One that's empty is asked for again next time.
        with _GLOSSARY_CACHE_LOCK:
            _GLOSSARY_CACHE[key] = found
    return found


def most_used_home_venue(events, team_id):
    """The venue of most of a team's home games in these schedule events, or None. The
    later one wins a tie. A one-off doesn't count as the team moving, and a game at a
    neutral site isn't a home game even when ESPN lists the team as home for it."""
    uses = {}
    for order, event in enumerate(_dicts(events)):
        comp = next(iter(_dicts(event.get("competitions"))), {})
        venue = _as_dict(comp.get("venue"))
        name = venue.get("fullName") or venue.get("displayName")
        if comp.get("neutralSite") or not name:
            continue
        home = next((c for c in _dicts(comp.get("competitors")) if c.get("homeAway") == "home"), {})
        if str(_as_dict(home.get("team")).get("id")) == str(team_id):
            count = uses[name][0] + 1 if name in uses else 1
            uses[name] = (count, order, venue)
    return max(uses.values(), key=lambda use: use[:2])[2] if uses else None


def _team_home_venue(league_path, team_id):
    """Where a team is playing its home games this season, or None. Asks for the regular
    season, since the default can be an empty postseason (MLB, November) and spring
    training is somewhere else. A soccer league's season type is its own number, so 2
    finds nothing there and the default is the league season. A World Cup team has no
    home: its "home" games are tournament draws, so Brazil would read MetLife Stadium."""
    if league_path.startswith("soccer/fifa."):
        return None
    query = "" if league_path.startswith("soccer/") else "?seasontype=2"
    try:
        # Only one line of the page, so it doesn't get to hold the rest up for long.
        resp = _http_get(f"{BASE_URL}/{league_path}/teams/{team_id}/schedule{query}", timeout=8)
        if resp.status_code != 200:
            return None
        return most_used_home_venue(_as_dict(resp.json()).get("events"), team_id)
    except Exception as e:
        print(f"[get_team_info] schedule of team {team_id}: {e}")
        return None


def _team_record_and_standing(league_path, team_id, team):
    """(record, standingSummary, whether a failure cost the record, season type) for a team page,
    from its regular season, as Standings has it. A league with no record to show isn't a failure.

    `team` is /teams/{id} with no season, which answers with whatever the league is doing now.
    In the WNBA playoffs that read the Lynx, 33-11 and first, as 0-2 and 8th, and the teams left
    out as 0-0. In the MLB playoffs the record holds and the standing doesn't: the Dodgers read
    5th in a division they won. College hockey's has no record at all, any time of year.

    Only these two come from the season asked for. Its nextEvent is wrong: the Nets' game
    tomorrow reads as one in January, and in MLB's off-season there isn't one.

    If the regular season can't be had, the answer with no season stands only when the league
    is in its regular season, when it's the same thing. Otherwise no record beats a wrong one.

    Soccer has no such thing as season type 2: its team page is already the league season,
    even in the NWSL's playoffs, and asking can name another competition's standing.
    """
    if league_path.startswith("soccer/"):
        return team.get("record"), team.get("standingSummary"), False, None
    try:
        season = core_season(league_path)
    except ApiError as e:
        print(f"[get_team_info] current season of {league_path}: {e}")
        return None, None, True, None
    regular, failed = {}, False
    try:
        year = latest_regular_season(season)
        resp = _http_get(f"{BASE_URL}/{league_path}/teams/{team_id}?season={year}&seasontype={REGULAR_SEASON}",
                         timeout=8)
        if resp.status_code == 200:
            answer = resp.json()
            failed = not isinstance(answer, dict)
            regular = _as_dict(_as_dict(answer).get("team"))
        else:
            failed = resp.status_code not in (400, 404)  # those say ESPN has nothing there
    except (requests.RequestException, ValueError) as e:
        print(f"[get_team_info] regular season of team {team_id}: {e}")
        failed = True
    season_type = _as_dict(season.get("type")).get("type")
    fallback = team if season_type == REGULAR_SEASON else {}
    record = regular.get("record") if _dicts(_as_dict(regular.get("record")).get("items")) else fallback.get("record")
    return (record, regular.get("standingSummary") or fallback.get("standingSummary"),
            failed and not _dicts(_as_dict(record).get("items")), season_type)


def _shown_standing(standing):
    """A standing as a team page says it. College hockey says "1st" of every team, whatever its
    record, and of nothing. The NBA's and WNBA's conferences aren't divisions."""
    if not standing or " in " not in standing:
        return ""
    return standing.replace(" Conference Division", " Conference")


def get_team_info(league_key, team_id, home_venue=True):
    """Get full team details: record splits, venue, head coach, next game.

    The record and standing are the regular season's, see _team_record_and_standing, at the
    cost of up to two more requests. `record_unavailable` says a failure cost the page its record,
    and `record_regular_season_only` that it leaves out games: a college team's postseason counts
    in Standings, but not here, from when it starts until the next regular season.

    franchise.venue is years out of date for some teams (Nets at Prudential Center,
    Warriors at Oracle) and missing for college, WNBA and soccer, so the venue comes from
    the team's home games, at the cost of one more request. Pass home_venue=False if the
    venue isn't going to be shown.
    """
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return {}
    answer = _espn_answer(TEAM_UNAVAILABLE, f"{BASE_URL}/{league_path}/teams/{team_id}")
    if answer is None:
        return {}
    team = _as_dict(answer.get("team"))
    if not team:
        return {}
    result = {
        "name":         team.get("displayName") or "",
        "abbreviation": team.get("abbreviation") or "",
        "nickname":     team.get("name") or "",
        "location":     team.get("location") or "",
    }
    # Venue
    venue = (home_venue and _team_home_venue(league_path, team_id)) \
        or _as_dict(team.get("venue")) or _as_dict(_as_dict(team.get("franchise")).get("venue"))
    result["venue_name"] = venue.get("fullName") or venue.get("displayName") or ""
    addr = _as_dict(venue.get("address"))
    city, state = addr.get("city") or "", addr.get("state") or ""
    result["venue_location"] = f"{city}, {state}" if city and state else city or state
    record, standing, result["record_unavailable"], season_type = _team_record_and_standing(
        league_path, team_id, team)
    result["record_regular_season_only"] = (
        league_key.startswith("NCAA") and season_type not in (None, REGULAR_SEASON))
    # Record splits
    for item in _dicts(_as_dict(record).get("items")):
        rtype = item.get("type", "")
        summary = item.get("summary") or ""
        if rtype == "total":
            # NHL totals have "10-4" here and the overtime losses in the stats. College
            # hockey's has its ties in the summary if there are any: 5-4-1, and Army's 5-1.
            ot_losses = next((st.get("value") for st in _dicts(item.get("stats"))
                              if st.get("name") == "otLosses"), None)
            if league_key == "NHL" and isinstance(ot_losses, (int, float)) and summary.count("-") == 1:
                summary = f"{summary}-{int(ot_losses)}"
            result["record_overall"] = summary
        elif rtype == "home":
            result["record_home"] = summary
        elif rtype == "road":
            result["record_road"] = summary
    # Division / Conference
    groups = _as_dict(team.get("groups"))
    result["division"] = groups.get("name") or ""
    result["standing"] = _shown_standing(standing)
    result["conference"] = _as_dict(groups.get("parent")).get("name") or ""
    # Head coach
    coaches = _dicts(team.get("coaches"))
    if coaches:
        c = coaches[0]
        result["head_coach"] = f"{c.get('firstName') or ''} {c.get('lastName') or ''}".strip()
    # Next event
    # For a while after a game ESPN's nextEvent is still that game.
    events = [e for e in _dicts(team.get("nextEvent"))
              if (((_dicts(e.get("competitions")) or [{}])[0].get("status") or {}).get("type") or {}).get("state") != "post"]
    if events:
        comps = _dicts(events[0].get("competitions"))
        if comps:
            competitors = _dicts(comps[0].get("competitors"))
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if home and away:
                is_home = str(_as_dict(home.get("team")).get("id") or "") == str(team_id)
                opp = away if is_home else home
                result["next_game_opponent"] = _as_dict(opp.get("team")).get("displayName") or ""
                result["next_game_home_away"] = "vs" if is_home else "@"
        date_str = events[0].get("date") or ""
        if date_str:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                dt_local = dt.astimezone()
                result["next_game_date"] = dt_local.strftime("%a, %b %d").replace(" 0", " ")
            except Exception:
                result["next_game_date"] = date_str[:10]
    return result


def get_team_roster(league_key, team_id):
    """Get a team's current roster as a list of player dicts."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    data = _espn_answer(ROSTER_UNAVAILABLE, f"{BASE_URL}/{league_path}/teams/{team_id}/roster")
    if data is None:
        return []
    players = []
    # ESPN returns athletes grouped by position group
    for group in _listed(data, "athletes", ROSTER_UNAVAILABLE):
        items = group.get("items", [group] if "displayName" in group else [])
        for p in _dicts(items):
            jersey = str(p.get("jersey") or "")
            name = p.get("displayName") or p.get("fullName") or ""
            pos = p.get("position", {})
            pos_abbr = (pos.get("abbreviation") or pos.get("name") or "") if isinstance(pos, dict) else str(pos or "")
            age = str(p.get("age") or "")
            height_str = format_height(p.get("height"))
            weight_str = format_weight(p.get("weight"))
            players.append({
                "jersey": jersey, "name": name, "position": pos_abbr,
                "age": age, "height": height_str, "weight": weight_str,
            })
    return players


def get_team_news(league_key, team_id, limit=25):
    """Get news articles for a specific team."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    # /teams/{id}/news returns no articles; /news?team={id} does.
    answer = _espn_answer(NEWS_UNAVAILABLE, f"{BASE_URL}/{league_path}/news",
                          params={"team": team_id, "limit": limit})
    if answer is None:
        return []
    try:
        from text_utils import text_processor
    except ImportError:
        text_processor = None
    articles = []
    for a in _listed(answer, "articles", NEWS_UNAVAILABLE):
        raw_desc = a.get("description") or ""
        desc = text_processor.clean_description(raw_desc, a) if text_processor else raw_desc
        articles.append({
            "headline":  a.get("headline") or "",
            "description": desc,
            "web_url":   _article_href(a, "web"),
            "published": a.get("published") or "",
            "byline":    a.get("byline") or "",
        })
    return articles


def _transaction_date(item):
    """A transaction's date as text, or "" if it has none that can be read as one."""
    date_str = item.get("date", item.get("timestamp", ""))
    if not isinstance(date_str, str) or not date_str:
        return ""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return date_str[:10]


def get_transactions(league_key, team_id=None, limit=50, page=1):
    """Get league-wide (or team-filtered) transactions with pagination.

    Returns (list_of_dicts, has_more).
    Each dict: {date, team, description}.
    """
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return [], False
    params = {"limit": limit, "page": page}
    if team_id:
        params["team"] = team_id
    data = _espn_answer(TRANSACTIONS_UNAVAILABLE, f"{BASE_URL}/{league_path}/transactions", params=params)
    if data is None:
        return [], False
    raw_items = _listed(data, "transactions" if "transactions" in data else "items", TRANSACTIONS_UNAVAILABLE)
    # ESPN returns pageIndex / pageCount as top-level integers. A null is no more pages, not
    # a reason to lose the page it came with.
    page_count = data.get("pageCount")
    has_more = int(page) < _stat_number({"value": page_count, "displayValue": page_count})
    result = []
    for item in raw_items:
        date_display = _transaction_date(item)
        team = item.get("team") or {}
        team_abbr = (team.get("abbreviation") or "") if isinstance(team, dict) else ""
        result.append({
            "date":        date_display,
            "team":        team_abbr,
            "description": item.get("description") or "",
            # Keep legacy keys so callers using player/type/position still work.
            "type":        "",
            "player":      "",
            "position":    "",
        })
    return result, has_more


# One request has a whole draft, as on the iPhone. It's kept briefly, since each round's tab asks for
# it, and a draft in progress has to move on.
DRAFT_CACHE_SECONDS = 30
_DRAFT_CACHE = {}  # year: (when it was asked, ESPN's answer)
# Ids athletes carry that an older draft's own list of positions doesn't have: 2001 to 2014 list
# a center as 4 while they're 91, and 2018 its kickers as 80 while they're 22. The iPhone has these too.
DRAFT_POSITIONS_LEFT_OUT = {"91": "C", "22": "PK"}


def _fetch_draft(year):
    """One NFL draft, or None if ESPN has no such thing. An empty body isn't a finished draft."""
    year = int(year)
    cached = _DRAFT_CACHE.get(year)
    if cached and time.monotonic() - cached[0] < DRAFT_CACHE_SECONDS:
        return cached[1]
    data = _as_dict(_espn_answer(DRAFT_UNAVAILABLE, f"{BASE_URL}/football/nfl/draft", params={"season": year}))
    # Before it's kept: a null here would read as a round with no picks for as long as it was.
    _listed(data, "picks", DRAFT_UNAVAILABLE)
    if not any(data.get(field) for field in ("year", "rounds", "picks", "status")):
        return None
    _DRAFT_CACHE[year] = (time.monotonic(), data)
    return data


def _ordinal(number):
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def get_draft(year):
    """Return draft metadata for the given NFL season year.

    Returns dict: {year, num_rounds, status ('pre'/'in'/'post'), rounds: [{number, display_name, short_name}]}
    or None if unavailable.
    """
    data = _fetch_draft(year)
    if data is None:
        return None
    num_rounds = data.get("rounds")
    num_rounds = num_rounds if isinstance(num_rounds, int) and num_rounds > 0 else 7
    rounds = [{"number": number, "display_name": f"{_ordinal(number)} Round", "short_name": _ordinal(number)}
              for number in range(1, num_rounds + 1)]
    status = str(_as_dict(data.get("status")).get("state") or "post").lower()
    return {"year": int(year), "num_rounds": num_rounds, "status": status, "rounds": rounds}


def get_draft_round(year, round_num):
    """Return a list of pick dicts for one round of the NFL Draft, in order.

    Each dict: {overall, pick, round, traded, trade_note, team_abbrev, team_name,
                player_name, position, college, status_name}
    """
    data = _fetch_draft(year)
    if data is None:
        return []
    teams = {str(team.get("id")): team for team in _dicts(data.get("teams"))}
    positions = {str(position.get("id")): position for position in _dicts(data.get("positions"))}

    picks = []
    for pick in _listed(data, "picks", DRAFT_UNAVAILABLE):
        if pick.get("round") != round_num:
            continue
        team = teams.get(str(pick.get("teamId")), {})
        athlete = _as_dict(pick.get("athlete"))
        school = _as_dict(athlete.get("team"))
        position_id = str(_as_dict(athlete.get("position")).get("id"))
        position = positions.get(position_id, {})
        picks.append({
            "overall": pick.get("overall") or 0,
            "pick": pick.get("pick") or 0,
            "round": round_num,
            "traded": bool(pick.get("traded")),
            "trade_note": pick.get("tradeNote") or "",
            "team_abbrev": team.get("abbreviation") or "?",
            "team_name": team.get("displayName") or team.get("shortDisplayName") or "Unknown",
            "player_name": athlete.get("displayName") or "",
            "position": position.get("abbreviation") or position.get("displayName")
                        or DRAFT_POSITIONS_LEFT_OUT.get(position_id, ""),
            # Not the short name first: that reads OSU, FSU and Miss St.
            "college": school.get("location") or school.get("shortDisplayName") or school.get("abbreviation") or "",
            "status_name": pick.get("status") or "",
        })
    picks.sort(key=lambda pick: pick["overall"])
    return picks


def get_team_transactions(league_key, team_id, limit=25):
    """Get recent transactions for a team. Returns [] if the league has no transaction feed."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    data = _espn_answer(
        TRANSACTIONS_UNAVAILABLE,
        f"{BASE_URL}/{league_path}/transactions",
        params={"team": team_id, "limit": limit},
    )
    if data is None:
        return []
    items = _listed(data, "transactions" if "transactions" in data else "items", TRANSACTIONS_UNAVAILABLE)
    result = []
    for item in items:
        date_display = _transaction_date(item)
        result.append({
            "date":        date_display,
            "description": item.get("description") or "",
            # Keep legacy keys so callers using player/type/position still work.
            "type":        "",
            "player":      "",
            "position":    "",
        })
    return result


def get_golf_leaderboard(tour_key, date=None, event_id=None):
    """Return a tournament's info and leaderboard for PGA or LPGA.

    With no date, the tour's scoreboard now. With `date` ("YYYY-MM-DD" or "YYYYMMDD"),
    the scoreboard for that day (`dates=YYYYMMDD`), which is how a past tournament this
    season is opened from the schedule, as the iPhone does. The event shown is the one
    `event_id` names if it's there, else the first in progress, else the first
    (golf.pick_event, the rule both apps share): a week can have two events.

    Returns dict: {id, name, short_name, date, end_date, state, round_num, status_detail,
                   players: [{position, name, country, total_score, rounds: [str]}]}
    or None if no event is available.
    """
    league_path = LEAGUES.get(tour_key)
    if not league_path:
        return None
    params = None
    if date:
        day = str(date).replace("-", "")[:8]
        if not (len(day) == 8 and day.isdigit()):
            return None
        params = {"dates": day}
    data = _espn_answer(LEADERBOARD_UNAVAILABLE, f"{BASE_URL}/{league_path}/scoreboard", params=params)
    if data is None:
        return None
    event = golf.pick_event(_listed(data, "events", LEADERBOARD_UNAVAILABLE), event_id)
    if event is None:
        return None
    comps = _dicts(event.get("competitions"))
    if not comps:
        return None
    comp = comps[0]
    comp_status = _as_dict(comp.get("status"))

    players = []
    for index, competitor in enumerate(golf.by_order(comp.get("competitors"))):
        athlete = _as_dict(competitor.get("athlete"))
        rounds = [
            ls["displayValue"]
            for ls in sorted(_dicts(competitor.get("linescores")),
                             key=lambda x: x.get("period") if isinstance(x.get("period"), int) else 0)
            if "value" in ls and isinstance(ls.get("displayValue"), str)
        ]
        order = competitor.get("order")
        players.append({
            "position": order if isinstance(order, int) and not isinstance(order, bool) else index + 1,
            "name": golf.competitor_name(competitor),
            "country": _as_dict(athlete.get("flag")).get("alt") or "",
            "total_score": golf_total_to_par(competitor),
            "rounds": rounds,
        })

    return {
        "id": str(event.get("id") or ""),
        "state": golf.event_state(event),
        "name": event.get("name") or "",
        "short_name": event.get("shortName") or "",
        "date": (event.get("date") or "")[:10],
        "end_date": (event.get("endDate") or "")[:10],
        "round_num": comp_status.get("period") or 0,
        "status_detail": _as_dict(comp_status.get("type")).get("detail") or "",
        "players": players,
    }


def get_golf_schedule(tour_key):
    """Return this season's tournament schedule for PGA or LPGA.

    Returns list of {id, name, start_date, end_date, status, state, winner}. The winner,
    "Chris Gotterup (-16)", is golf.winner's, the rule the iPhone's schedule follows too.
    """
    league_path = LEAGUES.get(tour_key)
    if not league_path:
        return []
    year = datetime.now().year
    # A bare year, not a START-END range: ESPN rejects ranges on team sports
    # and only still tolerates them here. The year returns the same 49 events.
    answer = _espn_answer(
        SCHEDULE_UNAVAILABLE,
        f"{BASE_URL}/{league_path}/scoreboard",
        params={"dates": str(year)},
    )
    if answer is None:
        return []
    result = []
    for event in _listed(answer, "events", SCHEDULE_UNAVAILABLE):
        status_type = _as_dict(_as_dict(event.get("status")).get("type"))
        result.append({
            "id": str(event.get("id") or ""),
            "name": event.get("name") or "",
            "start_date": (event.get("date") or "")[:10],
            "end_date": (event.get("endDate") or "")[:10],
            "status": status_type.get("description") or "Scheduled",
            "state": golf.event_state(event) or "pre",
            "winner": golf.winner_text(golf.winner(event)),
        })
    return result


# ─────────────────────────── Racing ──────────────────────────────────────────
# Formula 1, IndyCar and NASCAR Cup, from the same requests the iPhone makes. racing.py reads
# the answers; these only fetch them and say when ESPN didn't answer.

def get_race_event(series_key):
    """The series' current or next race weekend, and the season ESPN says it's in.

    Returns {"event": racing.parse_race_event(...) or None, "season": year or None}. No event
    is the off-season; a request that fails raises ApiError(RACE_UNAVAILABLE).
    """
    path = racing.series_path(series_key)
    if not path:
        return {"event": None, "season": None}
    answer = _espn_answer(RACE_UNAVAILABLE, f"{BASE_URL}/{path}/scoreboard")
    if answer is None:
        return {"event": None, "season": None}
    _listed(answer, "events", RACE_UNAVAILABLE)
    return {"event": racing.parse_race_event(answer), "season": racing.season_year(answer)}


def get_racing_schedule(series_key, year):
    """Every race of the season, with its winner, from the season's scoreboard. The year comes
    from get_race_event, which has it from ESPN, rather than from the calendar."""
    path = racing.series_path(series_key)
    if not path or not year:
        return []
    # A bare year, never a START-END range, which ESPN rejects.
    answer = _espn_answer(SCHEDULE_UNAVAILABLE, f"{BASE_URL}/{path}/scoreboard",
                          params={"dates": str(year)})
    if answer is None:
        return []
    _listed(answer, "events", SCHEDULE_UNAVAILABLE)
    return racing.parse_schedule(answer)


def get_racing_standings(series_key):
    """Championship standings: drivers, and constructors for Formula 1."""
    path = racing.series_path(series_key)
    if not path:
        return []
    answer = _espn_answer(STANDINGS_UNAVAILABLE, f"https://site.api.espn.com/apis/v2/sports/{path}/standings")
    if answer is None:
        return []
    _listed(answer, "children", STANDINGS_UNAVAILABLE)
    return racing.parse_standings(answer)


# ─────────────────────────── World Cup ───────────────────────────────────────

def get_world_cup_standings(league_key):
    """Fetch World Cup group standings (men's WC2026 or women's WWC2027).

    Returns a list of group dicts, each containing:
      { 'id', 'name', 'teams': [ { team fields … } ] }
    """
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    url = f"https://site.api.espn.com/apis/v2/sports/{league_path}/standings"
    data = _espn_answer(STANDINGS_UNAVAILABLE, url, timeout=15)
    if data is None:
        return []
    groups = []
    for child in _listed(data, "children", STANDINGS_UNAVAILABLE):
        group_id   = str(child.get("id") or "")
        group_name = child.get("name") or "Group"
        entries    = _dicts(_as_dict(child.get("standings")).get("entries"))
        teams = []
        for idx, entry in enumerate(entries):
            team  = _as_dict(entry.get("team"))
            stats = {s["name"]: s for s in _dicts(entry.get("stats")) if isinstance(s.get("name"), str)}

            def number(name):
                return _stat_number(_as_dict(stats.get(name)))

            note  = _as_dict(entry.get("note"))
            rank  = number("rank") or idx + 1
            gd    = number("pointDifferential")
            teams.append({
                "team_id":          str(team.get("id") or ""),
                "team_name":        team.get("displayName") or "",
                "abbreviation":     team.get("abbreviation") or "",
                "rank":             rank,
                "games_played":     number("gamesPlayed"),
                "wins":             number("wins"),
                "draws":            number("ties"),
                "losses":           number("losses"),
                "goals_for":        number("pointsFor"),
                "goals_against":    number("pointsAgainst"),
                "goal_difference":  gd,
                "points":           number("points"),
                "advancement_note": note.get("description") or "",
            })
        teams.sort(key=lambda t: t["rank"])
        groups.append({"id": group_id, "name": group_name, "teams": teams})
    return groups


def get_world_cup_scores_range(league_key, start_date, end_date):
    """Fetch all World Cup games between start_date and end_date (inclusive).

    Returns the same list-of-dicts format as get_scores(). A day that fails doesn't cost the
    others, but with no games from any, the failure may be why, so it says so.
    """
    from datetime import timedelta
    all_games = []
    seen_ids: set = set()
    failed = False
    current = start_date
    while current <= end_date:
        try:
            day_games = get_scores(league_key, date=current)
            for g in day_games:
                gid = g.get("id", "")
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    all_games.append(g)
        except Exception as e:
            print(f"[get_world_cup_scores_range] {current}: {e}")
            failed = True
        current += timedelta(days=1)
    if failed and not all_games:
        raise ApiError(SCORES_UNAVAILABLE)
    return all_games


# ---------------------------------------------------------------------------
# Fantasy football cheatsheet
# ---------------------------------------------------------------------------
#
# Backed by ESPN's fantasy player universe:
#   lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/players
#     ?view=kona_player_info
#
# Unlike the public site/core APIs (raw stats only) this feed carries the draft
# data a cheatsheet needs — average draft position, auction values, PPR and
# Standard consensus ranks, and season projections — all in one response.
#
# Quirks handled below:
#  * The X-Fantasy-Filter header must be PRESENT to get the full pool, but ESPN
#    ignores its limit/sort fields, so we always receive every player (~11.5k)
#    and filter/sort here.
#  * The payload is ~38 MB. We map each player to a small dict and drop the raw
#    list immediately, so the ~300 MB spike is confined to this call.
#  * A player's `stats` array holds a projected-season set for BOTH the upcoming
#    and the prior season. They are not in a stable order, so the projection
#    lookup matches on seasonId — taking "the first match" silently returns last
#    year's numbers for a chunk of the pool.
#  * ESPN's own `appliedTotal` is unusable (kickers read ~6,600, defenses
#    ~1,900), so points are scored here from the raw projected stat line.

FANTASY_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"

# ESPN defaultPositionId -> fantasy position. Ids absent here (IDL, LB, DB, P…)
# are not fantasy-relevant and are dropped.
FANTASY_POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}

# ESPN proTeamId -> abbreviation. 0 means free agent.
NFL_PRO_TEAMS = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL",
    7: "DEN", 8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC",
    13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO",
    19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX",
    33: "BAL", 34: "HOU",
}

# Projected-stat ids and their value under ESPN's default scoring. Receptions
# (id 53) are deliberately excluded — they are carried separately so the UI can
# price them per scoring format (Standard 0, Half-PPR 0.5, PPR 1) without a refetch.
_FANTASY_SCORING = {
    "3": 0.04,    # passing yards, 1 point per 25
    "4": 4.0,     # passing touchdown
    "19": 2.0,    # two-point conversion passed
    "20": -2.0,   # interception thrown
    "24": 0.1,    # rushing yards, 1 point per 10
    "25": 6.0,    # rushing touchdown
    "26": 2.0,    # two-point conversion rushed
    "42": 0.1,    # receiving yards, 1 point per 10
    "43": 6.0,    # receiving touchdown
    "44": 2.0,    # two-point conversion caught
    "72": -2.0,   # fumble lost
}

_FANTASY_RECEPTIONS_STAT = "53"


def _fantasy_projection(raw_player, season):
    """Return (base_points, receptions) from a player's projected season stat line.

    base_points excludes receptions and is None when the feed carries no
    projection for this season. Only the projected (statSourceId 1), full-season
    (statSplitTypeId 0, scoringPeriodId 0) set for the requested season counts.
    """
    for stat_set in raw_player.get("stats") or []:
        if (stat_set.get("statSourceId") != 1
                or stat_set.get("statSplitTypeId") != 0
                or stat_set.get("scoringPeriodId") != 0
                or stat_set.get("seasonId") != season):
            continue
        stats = stat_set.get("stats") or {}
        if not stats:
            continue
        # `or 0` rather than a default: ESPN sometimes carries an explicit null,
        # and one bad stat should not take the whole board down.
        base = sum((stats.get(stat_id) or 0) * value
                   for stat_id, value in _FANTASY_SCORING.items())
        return base, stats.get(_FANTASY_RECEPTIONS_STAT) or 0
    return None, 0


def _is_fantasy_rookie(raw, season):
    """True when the feed carries no stat line from before this season.

    The fantasy feed has no rookie flag, and the draft endpoint exposes only
    player names — too fragile to join on, since the 2026 class alone contains a
    second Justin Jefferson. But every player's `stats` array holds the prior
    season alongside the projected one, and a rookie has no prior season to hold.

    Checked against the full 2026 draft class: of the players flagged on a
    368-player board, all but two were drafted that year, and those two were
    undrafted rookies — which this catches and a draft-list join would miss.

    A veteran who missed an entire season would also be flagged, so this is a
    strong signal rather than a certainty.
    """
    seasons = {s.get("seasonId") for s in raw.get("stats") or []}
    seasons.discard(None)
    if not seasons:
        return False  # nothing to judge on; do not guess
    return not any(s < season for s in seasons)


def _map_fantasy_player(raw, season, max_rank=None):
    """Map one raw feed player to a cheatsheet row, or None if not draftable.

    Draftability is decided by whether ESPN publishes a draft rank for the
    player, which is ESPN's own answer to the question. `max_rank` additionally
    caps the pool and defaults to no cap.
    """
    position = FANTASY_POSITIONS.get(raw.get("defaultPositionId"))
    if not position:
        return None
    # ESPN keeps ranking players it has flagged inactive — retirees like Matthew
    # Slater still carry a rank. All 142 of them are owned in 0.0% of leagues.
    if raw.get("active") is False:
        return None

    ranks = raw.get("draftRanksByRankType") or {}

    def rank_for(rank_type):
        value = (ranks.get(rank_type) or {}).get("rank")
        return int(value) if isinstance(value, (int, float)) and value > 0 else None

    ppr_rank = rank_for("PPR")
    standard_rank = rank_for("STANDARD")
    best_rank = min([r for r in (ppr_rank, standard_rank) if r], default=None)
    # An unranked player is one ESPN does not consider fantasy-relevant: every
    # one of them is owned in 0.0% of leagues — retirees and camp bodies.
    if best_rank is None:
        return None
    if max_rank is not None and best_rank > max_rank:
        return None

    pro_team_id = raw.get("proTeamId") or 0
    ownership = raw.get("ownership") or {}
    is_dst = position == "D/ST"

    # Kickers and defenses have no usable projection: their raw stat lines use a
    # different id space (field-goal distance buckets, points/yards allowed
    # tiers) that the offensive scoring table above cannot price. Their rank,
    # ADP and auction value still come through, which is what a draft needs.
    if is_dst or position == "K":
        proj_base, proj_receptions = None, 0
    else:
        proj_base, proj_receptions = _fantasy_projection(raw, season)

    return {
        "id": f"dst-{pro_team_id}" if is_dst else str(raw.get("id")),
        "name": raw.get("fullName") or "Unknown",
        "position": position,
        "team": NFL_PRO_TEAMS.get(pro_team_id, "FA"),
        "injury": _normalize_fantasy_injury(raw.get("injuryStatus")),
        # A team defense is never a rookie, whatever its stat history looks like.
        "rookie": False if is_dst else _is_fantasy_rookie(raw, season),
        "adp": ownership.get("averageDraftPosition"),
        "auction": ownership.get("auctionValueAverage"),
        "ppr_rank": ppr_rank,
        "standard_rank": standard_rank,
        "proj_base": proj_base,
        "proj_receptions": proj_receptions,
    }


def _normalize_fantasy_injury(status):
    """ESPN reports healthy players as ACTIVE; surface only real designations."""
    if not status or str(status).upper() in ("ACTIVE", "NORMAL"):
        return ""
    return " ".join(part.capitalize() for part in str(status).split("_"))


def _blank_placeholder_adp(players):
    """Clear the placeholder ADP ESPN gives players nobody is actually drafting.

    ESPN does not omit `averageDraftPosition` for undrafted players — it hands
    out a value just past the end of a real draft, jittered by a fraction. In the
    2026 pool that is ~170, shared by 788 of 1,168 players, while genuine ADPs
    stop around 168. Left alone it reads as a real draft position, and because
    the jitter is in the third decimal it also defeats sorting: rows that all
    display "170.0" order by invisible noise rather than by the rank tiebreak.

    The placeholder is found rather than hard-coded, since it tracks the size of
    the draft ESPN samples and would drift between seasons.
    """
    from collections import Counter
    counts = Counter(round(p["adp"]) for p in players if p.get("adp"))
    if not counts:
        return
    value, hits = counts.most_common(1)[0]
    # A real ADP is never shared by a large slice of the pool; a placeholder is.
    if hits < max(20, 0.05 * len(players)):
        return
    threshold = value - 1
    for player in players:
        if player.get("adp") and player["adp"] >= threshold:
            player["adp"] = None


def _assign_board_ranks(players):
    """Number the board densely from 1, keeping ESPN's ordering.

    ESPN's published rank orders a much larger pool than a fantasy board: it
    interleaves ~1,750 IDP players, 51 punters and the 32 'Team QB' slots that
    only a few league formats use. Shown raw it reads as a broken sequence — the
    2026 board covers ranks 1 to 2565 with 1,539 holes and 251 jumps, running
    36 -> 69 near the top and 519 -> 978 further down.

    The dense number preserves ESPN's order exactly while answering the question
    a draft board is actually asked: how many players are ahead of this one. The
    published rank is kept alongside for anyone cross-referencing ESPN.
    """
    for source, target in (("ppr_rank", "ppr_board_rank"),
                           ("standard_rank", "standard_board_rank")):
        ranked = sorted((p for p in players if p.get(source)), key=lambda p: p[source])
        for position, player in enumerate(ranked, start=1):
            player[target] = position
        for player in players:
            player.setdefault(target, None)


class _FantasySeasonNotThere(ApiError):
    """A 400 or 404: ESPN hasn't made this season's feed. Any other failure says nothing about that."""


def _load_fantasy_season(season, max_rank):
    """Fetch and map one season's draft board. Returns [] when unavailable."""
    url = f"{FANTASY_BASE}/{season}/players?view=kona_player_info&scoringPeriodId=0"
    # The header must be present to receive the full pool; ESPN ignores its body.
    headers = {
        "X-Fantasy-Filter": '{"players":{"limit":12000}}',
        "Accept": "application/json",
    }
    # Raised, not swallowed: an empty list here would be indistinguishable from
    # "ESPN has not published this season yet", and the caller reports those two
    # very differently. A 404 has its own exception, which the fallback below reads.
    try:
        resp = _http_get(url, headers=headers, timeout=90)
        raw_players = resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError) as e:
        print(f"[get_fantasy_cheatsheet] {season}: {e}")
        raise ApiError(FANTASY_UNAVAILABLE) from e
    if resp.status_code in (400, 404):
        raise _FantasySeasonNotThere(FANTASY_UNAVAILABLE)
    if resp.status_code != 200:
        raise ApiError(FANTASY_UNAVAILABLE)
    # An empty list is a season ESPN hasn't published. Anything but a list isn't that.
    if not isinstance(raw_players, list):
        raise ApiError(FANTASY_UNAVAILABLE)
    players = [p for p in (_map_fantasy_player(r, season, max_rank) for r in raw_players) if p]
    del raw_players  # release the ~38 MB payload before returning
    _blank_placeholder_adp(players)
    _assign_board_ranks(players)
    players.sort(key=lambda p: p["ppr_rank"] or p["standard_rank"] or 9999)
    return players


def get_fantasy_cheatsheet(season=None, max_rank=None):
    """Return the fantasy draft board: {'season': int, 'players': [...]}.

    Defaults to the current calendar year, which is the season ESPN publishes
    draft data for from late winter onward. In the deep offseason — before ESPN
    populates the new season, when the feed answers with a near-empty pool or a
    404 — falls back to the prior season so the board is never empty. A network
    or server failure propagates instead, so the caller can say so.

    Every fantasy-position player ESPN ranks is included: about 1,170 of the
    ~11.5k ids in the feed. There is deliberately no rank cutoff. ESPN's overall
    rank is not an ordering of draft relevance — Ricky Pearsall sits at 1507 and
    Tyreek Hill at 1899, both rostered in real leagues — so any cap silently
    hides players people are drafting. `max_rank` still exists for callers that
    want a smaller pool, and defaults to no cap.
    """
    from datetime import datetime
    season = int(season or datetime.now().year)
    try:
        players = _load_fantasy_season(season, max_rank)
    except _FantasySeasonNotThere as e:
        # The upcoming season's feed can 404 before ESPN creates it.
        print(f"[get_fantasy_cheatsheet] {season}: {e}")
        return {"season": season - 1, "players": _load_fantasy_season(season - 1, max_rank)}

    if len(players) < 50:
        try:
            fallback = _load_fantasy_season(season - 1, max_rank)
            if len(fallback) > len(players):
                return {"season": season - 1, "players": fallback}
        except Exception as e:
            print(f"[get_fantasy_cheatsheet] fallback to {season - 1}: {e}")
    return {"season": season, "players": players}
