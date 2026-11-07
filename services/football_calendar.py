import requests
from datetime import datetime, timedelta, date as date_type

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
CORE_BASE = "https://sports.core.api.espn.com/v2/sports"

_LEAGUE_PATHS = {"NFL": "football/nfl", "NCAAF": "football/college-football"}

# ESPN season type ids. Off Season (4) is deliberately not navigable: it holds no
# games for the NFL, and only the college all-star exhibition for NCAAF.
SEASON_TYPE_PRESEASON = 1
SEASON_TYPE_REGULAR = 2
SEASON_TYPE_POSTSEASON = 3
_NAVIGABLE_SEASON_TYPES = (SEASON_TYPE_PRESEASON, SEASON_TYPE_REGULAR, SEASON_TYPE_POSTSEASON)

_WEEK_DATE_CACHE: dict = {}  # (league_key, season, season_type, week) -> (start_YYYYMMDD, end_YYYYMMDD)
_SEASON_WEEKS_CACHE: dict = {}  # (league_key, season) -> [week dicts]
# The season ESPN's scoreboard calendar describes, per league, as last fetched.
# Any other season has no calendar there, so it is answered from the Core API.
_SERVED_SEASON: dict = {}  # league_key -> season year
# A season the calendar doesn't cover, from the Core API: its weeks in order, and
# each week's name. Only successes are stored, like _WEEK_DATE_CACHE.
_CORE_SEASON_CACHE: dict = {}  # (league_key, season) -> [(season_type, week), ...]
_CORE_WEEK_TEXT_CACHE: dict = {}  # (league_key, season, season_type, week) -> ESPN's `text`

_CORE_LEAGUES = {"NFL": "nfl", "NCAAF": "college-football"}


def _bound_dates(start_iso, end_iso):
    """Convert an ESPN week's ISO bounds to inclusive (start_date, end_date).

    ESPN stamps week bounds at Pacific midnight — a start of `T07:00Z` and an end
    of `T06:59Z`, which is 23:59 Pacific on the day *before* the UTC date reads.
    Taking the UTC date of the end therefore overshoots by a day and drags the
    next week's Thursday games into this week; in preseason, where games run
    Thursday through Sunday, that is most of the following week. Subtracting the
    day gives the last day the week actually covers, and holds across daylight
    saving (the offset moves to 08:00Z/07:59Z, still the same UTC calendar day).
    """
    start = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).date()
    end = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).date() - timedelta(days=1)
    if end < start:
        end = start
    return start, end


def _fetch_calendar(league_key, season=None):
    """Fetch a season calendar. Returns (actual_season_year, weeks) or (None, []).

    The season year comes back from the response rather than the request, because
    ESPN ignores `season=` on the scoreboard and always serves whatever season it
    considers current. Asking for 2025 in 2026 yields the 2026 calendar with no
    error, so the caller has to check what it actually got.
    """
    league_path = _LEAGUE_PATHS.get(league_key)
    if not league_path:
        return None, []

    url = f"{BASE_URL}/{league_path}/scoreboard"
    if season is not None:
        url += f"?season={season}"

    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return None, []
    leagues = resp.json().get('leagues', [])
    if not leagues:
        return None, []

    try:
        actual_season = int(leagues[0].get('season', {}).get('year'))
    except (TypeError, ValueError):
        actual_season = None
    if actual_season is not None:
        _SERVED_SEASON[league_key] = actual_season

    weeks = []
    for block in leagues[0].get('calendar', []):
        try:
            season_type = int(block.get('value', 0))
        except (TypeError, ValueError):
            continue
        if season_type not in _NAVIGABLE_SEASON_TYPES:
            continue
        for entry in block.get('entries', []):
            try:
                start, end = _bound_dates(entry.get('startDate', ''), entry.get('endDate', ''))
                week = int(entry.get('value', 0))
            except (TypeError, ValueError, AttributeError):
                continue
            if not week:
                continue
            weeks.append({
                'season_type': season_type,
                'week': week,
                'label': entry.get('label') or f"Week {week}",
                'start': start,
                'end': end,
            })

    # Sorted by date, not by (type, week): NCAAF numbers its College Football
    # Playoff entry 999, so week order and calendar order are not the same thing.
    weeks.sort(key=lambda w: (w['start'], w['season_type'], w['week']))
    return actual_season, weeks


def get_season_weeks(league_key, season=None):
    """Every week of a football season in date order, across all season types.

    Returns a list of dicts: {'season_type', 'week', 'label', 'start', 'end'}.
    `week` is the week number *within* its season type, which is what ESPN's
    endpoints expect, so (season_type, week) is the pair that identifies a week —
    the number alone is ambiguous.

    Returns [] when ESPN has no calendar for the requested season. That is not the
    same as a failure: ESPN only publishes the season it considers current, and it
    does not switch to a new one until roughly late July, months after
    `get_football_season_year` starts naming it. Handing back the wrong season's
    weeks would put the app on last February's Super Bowl all spring.
    """
    if league_key not in _LEAGUE_PATHS:
        return []

    cache_key = (league_key, season)
    if cache_key in _SEASON_WEEKS_CACHE:
        return _SEASON_WEEKS_CACHE[cache_key]
    if season is not None and _SERVED_SEASON.get(league_key, season) != season:
        # ESPN has already said which season its calendar is for, and it isn't this
        # one. Asking again would only fetch the same calendar to learn that twice.
        # Opening a league view asks afresh (get_current_season_week_and_type), so
        # ESPN moving on to a new season in late July is still noticed.
        return []

    try:
        actual_season, weeks = _fetch_calendar(league_key, season)
    except Exception as e:
        print(f"[get_season_weeks] {league_key} {season}: {e}")
        return []

    if not weeks:
        return []
    if season is not None and actual_season is not None and actual_season != season:
        # ESPN served a different season than the one asked for. Cache it under
        # the season it really is, so a later request for that year is free, and
        # report nothing for the year that was asked about.
        _SEASON_WEEKS_CACHE[(league_key, actual_season)] = weeks
        _seed_week_dates(league_key, actual_season, weeks)
        return []

    resolved = actual_season if actual_season is not None else season
    _SEASON_WEEKS_CACHE[cache_key] = weeks
    if resolved is not None:
        _SEASON_WEEKS_CACHE[(league_key, resolved)] = weeks
        _seed_week_dates(league_key, resolved, weeks)
    return weeks


def _seed_week_dates(league_key, season, weeks):
    """Fill the per-week bounds cache from a calendar already in hand.

    The calendar knows every week's dates, so seeding here spares the Core API a
    request per arrow tap during navigation.
    """
    for entry in weeks:
        _WEEK_DATE_CACHE[(league_key, season, entry['season_type'], entry['week'])] = (
            entry['start'].strftime("%Y%m%d"), entry['end'].strftime("%Y%m%d"))


def get_current_season_week_and_type(league_key, today=None):
    """Return (season, season_type, week) for right now, per ESPN.

    The season comes from ESPN rather than from `get_football_season_year`, whose
    calendar-year heuristic rolls over on 1 March while ESPN keeps serving the
    previous season until around late July. Trusting the heuristic through that
    window resolves every date as past the end of the season and lands the view on
    the last Super Bowl.
    """
    today = today or datetime.now().date()
    if isinstance(today, datetime):
        today = today.date()

    try:
        actual_season, weeks = _fetch_calendar(league_key)
    except Exception as e:
        print(f"[get_current_season_week_and_type] {league_key}: {e}")
        actual_season, weeks = None, []

    season = actual_season if actual_season is not None else get_football_season_year(league_key, today)
    if not weeks:
        return season, SEASON_TYPE_REGULAR, 1

    _SEASON_WEEKS_CACHE[(league_key, season)] = weeks
    _seed_week_dates(league_key, season, weeks)
    season_type, week = _week_for_date(weeks, today)
    return season, season_type, week


def _week_for_date(weeks, today):
    """Pick the week covering `today`, else the next one, else the last."""
    for entry in weeks:
        if entry['start'] <= today <= entry['end']:
            return entry['season_type'], entry['week']
    upcoming = [w for w in weeks if w['start'] > today]
    entry = upcoming[0] if upcoming else weeks[-1]
    return entry['season_type'], entry['week']


def get_current_week_and_type(league_key, season=None, today=None):
    """Return (season_type, week) for today, resolved from the season calendar.

    Falls back to (2, 1) — regular season, week 1 — when the calendar is
    unavailable. Preferred over `get_current_football_week`, which returns a bare
    week number: during preseason, week 1 means the Hall of Fame game, not the
    regular season opener a month later.
    """
    today = today or datetime.now().date()
    if isinstance(today, datetime):
        today = today.date()
    if season is None:
        season = get_football_season_year(league_key, today)

    weeks = get_season_weeks(league_key, season)
    if not weeks:
        return SEASON_TYPE_REGULAR, 1
    return _week_for_date(weeks, today)


def _core_week_url(league_key, season, season_type, week=None):
    league = _CORE_LEAGUES.get(league_key, league_key.lower())
    url = f"{CORE_BASE}/football/leagues/{league}/seasons/{season}/types/{season_type}/weeks"
    return url if week is None else f"{url}/{week}"


def _fetch_core_week(league_key, season, season_type, week):
    """One week from the Core API, `weeks/{n}`, or None if it can't be had.

    The answer carries the week's dates and its name (`text`: "Wild Card",
    "Bowls"), and both are cached from the one request. Failures are not cached:
    the caches never expire, so storing a miss would make one timeout, a laptop
    resuming from sleep mid-navigation, cost that week for the rest of the session.
    """
    try:
        resp = requests.get(_core_week_url(league_key, season, season_type, week), timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"[core week] {league_key} {season}/t{season_type}/w{week}: {e}")
        return None
    if not isinstance(data, dict):
        return None
    key = (league_key, season, season_type, week)
    text = data.get("text")
    if isinstance(text, str) and text.strip():
        _CORE_WEEK_TEXT_CACHE[key] = text.strip()
    try:
        start, end = _bound_dates(data.get("startDate") or "", data.get("endDate") or "")
        _WEEK_DATE_CACHE[key] = (start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    except (TypeError, ValueError, AttributeError):
        pass
    return data


def _core_type_weeks(league_key, season, season_type):
    """The week numbers of one season type from the Core API's `weeks` list.

    Returns a list, [] when ESPN says the type has no weeks (a 404, or an empty
    list), or None when the request failed, so the caller knows not to cache.
    """
    try:
        resp = requests.get(f"{_core_week_url(league_key, season, season_type)}?limit=100", timeout=20)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"[core weeks] {league_key} {season}/t{season_type}: {e}")
        return None
    if not isinstance(data, dict):
        return None
    weeks = []
    for item in data.get("items") or []:
        ref = item.get("$ref", "") if isinstance(item, dict) else ""
        try:
            weeks.append(int(ref.split("?")[0].rstrip("/").rsplit("/", 1)[1]))
        except (IndexError, ValueError):
            continue
    if not weeks:
        # No readable references: fall back to the count, numbered from 1, which is
        # how the iPhone reads the same list.
        try:
            weeks = list(range(1, int(data.get("count") or 0) + 1))
        except (TypeError, ValueError):
            weeks = []
    return sorted(set(weeks))


def _fetch_core_season(league_key, season):
    """Every navigable week of a season from the Core API, in order, cached.

    Season types run preseason, regular, postseason and their weeks in number
    order, as the iPhone steps through them. Cached only when all three lists
    answered, so a failure is asked about again next time.
    """
    cache_key = (league_key, season)
    if cache_key in _CORE_SEASON_CACHE:
        return _CORE_SEASON_CACHE[cache_key]
    weeks, complete = [], True
    for season_type in _NAVIGABLE_SEASON_TYPES:
        numbers = _core_type_weeks(league_key, season, season_type)
        if numbers is None:
            complete = False
            continue
        weeks.extend((season_type, number) for number in numbers)
    if complete and weeks:
        _CORE_SEASON_CACHE[cache_key] = weeks
    return weeks


def prepare_week(league_key, season, season_type, week):
    """Fetch what labelling and stepping from this week will need. Network: call it
    off the UI thread (LeagueScoresLoader does), then `get_week_label` and
    `step_week` answer from the caches.

    The season the scoreboard calendar describes needs nothing more. Any other
    season, a past one, is read from the Core API as the iPhone reads it: the
    season's weeks once, and this week's name. Nothing here raises: a week whose
    name can't be had is called "Week N", as on the iPhone, and the games, which
    come from their own request, still say if they fail.
    """
    if league_key not in _LEAGUE_PATHS or season is None or week is None:
        return
    try:
        if get_season_weeks(league_key, season):
            return
        _fetch_core_season(league_key, season)
        if (league_key, season, season_type, week) not in _CORE_WEEK_TEXT_CACHE:
            _fetch_core_week(league_key, season, season_type, week)
    except Exception as e:  # a name is never worth losing the games over
        print(f"[prepare_week] {league_key} {season}/t{season_type}/w{week}: {e}")


def _known_weeks(league_key, season):
    """The season's weeks in order as (season_type, week), from the caches only:
    the scoreboard calendar's if it covers the season, else the Core API's."""
    calendar = _SEASON_WEEKS_CACHE.get((league_key, season))
    if calendar:
        return [(entry['season_type'], entry['week']) for entry in calendar]
    return _CORE_SEASON_CACHE.get((league_key, season), [])


def get_week_label(league_key, season, season_type, week):
    """Human label for a week, e.g. 'Hall of Fame Weekend' or 'Wild Card'.

    ESPN's live `week` block carries only a number, so the calendar label is what
    distinguishes preseason Week 1 from the regular season opener. The scoreboard
    calendar names the weeks of the season it describes; any other season's
    names are ESPN's Core API `text`, which `prepare_week` fetched.

    Never touches the network, so the UI thread can call it: what isn't cached
    yet is "Week N", and `prepare_week` on the loader thread fills it in.
    """
    calendar = _SEASON_WEEKS_CACHE.get((league_key, season))
    if calendar:
        for entry in calendar:
            if entry['season_type'] == season_type and entry['week'] == week:
                return entry['label']
        return f"Week {week}"
    return _CORE_WEEK_TEXT_CACHE.get((league_key, season, season_type, week)) or f"Week {week}"


def step_week(league_key, season, season_type, week, delta):
    """Move one week forward or back, rolling over between season types.

    Returns (season_type, week), unchanged at the ends of the season. Stepping
    past the last preseason week lands on regular season Week 1 rather than
    dead-ending, which is the only way to reach preseason at all once the
    regular season view is the default. A past season steps the same way through
    the Core API's weeks.

    Answers from the caches only, so the UI thread can call it; with nothing
    cached, it moves within the season type.
    """
    weeks = _known_weeks(league_key, season)
    if not weeks:
        return season_type, max(1, week + delta)
    try:
        index = weeks.index((season_type, week))
    except ValueError:
        return season_type, week
    target = index + delta
    if 0 <= target < len(weeks):
        return weeks[target]
    return season_type, week


def get_football_season_year(league_key="NFL", today=None):
    """Return the ESPN season year for the given date and league.

    ESPN names a football season by the calendar year it *starts* in
    (e.g., the season that kicks off September 2026 is 'year 2026').
    - January–February: still inside the previous year's playoffs/Super Bowl
    - March–December: we're either in the upcoming season or deep in the
      current one, so the current calendar year is correct.
    """
    today = today or datetime.now().date()
    if isinstance(today, datetime):
        today = today.date()
    if today.month <= 2:
        return today.year - 1
    return today.year

# This function finds the current week number for NFL/NCAAF based on today
def get_current_football_week(league_key, season=None, today=None):
    """Current week number, without its season type.

    Kept for callers that only need a number. Prefer `get_current_week_and_type`:
    a week number on its own is ambiguous, and during preseason ESPN's own
    `week.number` of 1 means the Hall of Fame game, which a caller assuming the
    regular season will render as the September opener.
    """
    if league_key not in _LEAGUE_PATHS:
        return None
    return get_current_week_and_type(league_key, season, today)[1]


def get_week_dates(league_key, week_num, season, season_type=SEASON_TYPE_REGULAR):
    """Return (start_YYYYMMDD, end_YYYYMMDD) for one week, or (None, None).

    These bounds drive the scoreboard's `dates=` parameter, which is how football
    weeks are fetched at all: ESPN ignores `season=` whenever `week=` is present
    and serves the previous season instead.

    The season calendar is consulted first and covers every week in one request;
    the Core API is the per-week fallback. Both are normalised through
    `_bound_dates`, so the end bound is the last day the week actually covers.
    """
    cache_key = (league_key, season, season_type, week_num)
    if cache_key in _WEEK_DATE_CACHE:
        return _WEEK_DATE_CACHE[cache_key]

    # Populates the cache for every week of the season in a single request.
    get_season_weeks(league_key, season)
    if cache_key in _WEEK_DATE_CACHE:
        return _WEEK_DATE_CACHE[cache_key]

    # The Core API caches the bounds (and the week's name) on success only.
    _fetch_core_week(league_key, season, season_type, week_num)
    return _WEEK_DATE_CACHE.get(cache_key, (None, None))
