import json
import requests
import time
from datetime import datetime
from exceptions import ApiError
from game_labels import (best_odds, broadcast_names, format_height, format_weight,
                         injured_player_count, local_schedule_datetime, schedule_game_label)
from timezone_utils import convert_espn_time_to_local

# Every ESPN request gets a timeout. requests has none by default, so one
# stalled response would block its caller forever; several screens fetch on
# the UI thread, where that is a frozen window. Callers that need longer pass
# their own timeout=.
DEFAULT_TIMEOUT = 15


def _http_get(url, **kwargs):
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return requests.get(url, **kwargs)


# ESPN sometimes sends null, or an empty list, where a dict or list belongs. A
# `.get(key, {})` default doesn't help when the key is there with a null in it.
def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    """The dicts in a list of them: nothing if it isn't a list, and no null elements."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


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

# ESPN's `groups=` scoreboard parameter, per college football coverage setting.
# 80 is the Football Bowl Subdivision; 90 is all of Division I, FBS plus FCS.
NCAAF_COVERAGE_GROUPS = {
    "fbs": "80",
    "all_d1": "90",
}

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
        import settings
        coverage = settings.get('ncaaf_coverage', 'all_d1')
        group = NCAAF_COVERAGE_GROUPS.get(coverage, NCAAF_COVERAGE_GROUPS['all_d1'])
        return [f"groups={group}", f"limit={NCAAF_SCOREBOARD_LIMIT}"]
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


# Leagues whose schedule comes one season type at a time, where a failed type is
# left out of the list. WNBA is here: ESPN's scoreboard, which it used to read,
# only reached 30 days either side of today and could not show a past season.
SEASON_TYPE_SCHEDULE_LEAGUES = ("MLB", "NBA", "NHL", "WNBA", "NCAAH", "NCAAWH", "NCAAM", "NCAAWB")
FOOTBALL_SCHEDULE_LEAGUES = ("NFL", "NCAAF")


def _schedule_events(resp):
    return _dicts(_as_dict(resp.json()).get("events"))


def _season_type_schedule_events(base_url, season_year):
    """Preseason, regular season and postseason, leaving out any that fails."""
    events = []
    for season_type in (1, 2, 3):
        try:
            resp = _http_get(f"{base_url}?season={season_year}&seasontype={season_type}")
            if resp.status_code == 200:
                events.extend(_schedule_events(resp))
        except Exception:
            pass  # Continue even if one season type fails
    return events


def _football_schedule_events(base_url, season_year):
    """All three season types, so the Super Bowl and the bowls are there.

    A timeout is not caught: the dialog reports it, where a schedule missing its
    playoffs or its regular season would look complete. Without a regular season
    there is no schedule worth showing, so an error there means none; an error on
    the other two leaves out only that part. FCS playoffs are type 2, and a team
    that missed the postseason gets an empty list for type 3, not an error.
    """
    events = []
    for season_type in (2, 1, 3):
        resp = _http_get(f"{base_url}?season={season_year}&seasontype={season_type}")
        if resp.status_code == 200:
            events.extend(_schedule_events(resp))
        elif season_type == 2:
            return []
    return events


def _soccer_schedule_events(base_url, season_year, current_season):
    """Results, plus the games to come if this is the current season.

    Soccer has no seasontype: 2 and 3 answer with nothing. `season=Y` gives the
    games played and `fixture=true` the games to come, whatever season is asked
    for, so a past season must not ask for it.

    Each league's seasons cross the new year on their own calendar, so the year
    ESPN calls current can be behind ours: in February 2027 `season=2027` is empty
    for the Premier League, whose 2026-27 season ESPN reports as `season.year` 2026.
    Its results are then the ones to show. As elsewhere, a timeout reaches the caller.
    """
    resp = _http_get(f"{base_url}?season={season_year}")
    if resp.status_code != 200:
        return []
    data = _as_dict(resp.json())
    events = _dicts(data.get("events"))
    espn_season = _as_dict(data.get("season")).get("year")
    if season_year not in (current_season, espn_season):
        return events

    if isinstance(espn_season, int) and espn_season < season_year:
        resp = _http_get(f"{base_url}?season={espn_season}")
        if resp.status_code == 200:
            events.extend(_schedule_events(resp))
    resp = _http_get(f"{base_url}?fixture=true")
    if resp.status_code == 200:
        events.extend(_schedule_events(resp))
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
    """A team's schedule for one season, from ESPN's team schedule endpoint.

    A season asked for is that season or nothing, never another year's games.
    Only a current season with nothing in it falls back, and only when no season
    was asked for, and those rows show their year.
    """
    from datetime import timedelta

    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []

    # Determine if we're viewing a historical season (not the current one)
    current_season = get_current_season_year(league_key)
    is_historical_season = season is not None and season != current_season
    season_year = season if season else current_season
    base_url = f"{BASE_URL}/{league_path}/teams/{team_id}/schedule"

    if league_key in FOOTBALL_SCHEDULE_LEAGUES:
        events = _football_schedule_events(base_url, season_year)
    elif league_key in SEASON_TYPE_SCHEDULE_LEAGUES:
        events = _season_type_schedule_events(base_url, season_year)
    elif league_path.startswith("soccer/"):
        events = _soccer_schedule_events(base_url, season_year, current_season)
    else:
        # The last resort, for a league with no team schedule: the scoreboard, filtered
        # to this team. It knows only the days around today, so it has no past seasons.
        if is_historical_season:
            return []
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
        return schedule

    # Offseason fallback: ESPN publishes a new season's schedule some weeks
    # after the previous one ends, so in that gap the current season year comes
    # back empty. Fall back to the season that just finished.
    if not events and season is None:
        return get_team_schedule(league_key, team_id, days_ahead, days_behind,
                                 season=current_season - 1)

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
        
        # Determine date display format - include year for historical seasons
        if is_historical_season:
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
    return schedule

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
                    
                    # Determine date display format - include year for historical seasons
                    if is_historical_season:
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
    resp = _http_get(f"{BASE_URL}/{league_path}/scoreboard")
    if resp.status_code != 200:
        return None
    for event in _dicts(resp.json().get("events")):
        comp = (_dicts(event.get("competitions")) or [{}])[0]
        status = _as_dict(_as_dict(comp.get("status")).get("type"))
        if status.get("state") != "in":
            continue
        players = sorted(_dicts(comp.get("competitors")), key=lambda c: c.get("order") or 999)
        scores = [golf_total_to_par(p) for p in players]
        top = []
        for i, player in enumerate(players[:leaders]):
            score = scores[i]
            first = scores.index(score) + 1
            tied = scores.count(score) > 1
            athlete = _as_dict(player.get("athlete"))
            top.append((f"T{first}" if tied else str(first),
                        athlete.get("displayName") or athlete.get("fullName") or "",
                        score))
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

    resp = _http_get(url)
    if resp.status_code != 200:
        return []
    data = resp.json()
    events = _dicts(data.get("events"))

    if ncaaf_needs_fbs_retry(league_key, events):
        retry = _http_get(_swap_to_fbs(url))
        if retry.status_code == 200:
            data = retry.json()
            events = _dicts(data.get("events"))

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
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    url = f"{BASE_URL}/{league_path}/news"
    params = {'limit': limit} if limit > 6 else {}
    resp = _http_get(url, params=params)
    if resp.status_code != 200:
        return []
    data = resp.json()
    articles = _dicts(data.get("articles"))
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
    resp = _http_get(url)
    if resp.status_code != 200:
        return {}
    details = resp.json()

    # ESPN hockey series games can occasionally expose fuller play groups via the
    # web gamepackage payload. Prefer whichever source has more events.
    if league_key in ["NHL", "NCAAH", "NCAAWH"]:
        api_plays = _dicts(details.get("plays")) if isinstance(details, dict) else []
        web_plays = _fetch_web_gamepackage_plays(league_path, game_id)
        if len(web_plays) > len(api_plays):
            details["plays"] = web_plays
            details["playsSource"] = "web_gamepackage"
        elif isinstance(details, dict):
            details["playsSource"] = "site_summary"

    return details


def _fetch_web_gamepackage_plays(league_path, game_id):
    """Fetch and flatten play groups from ESPN web gamepackage payload."""
    league_slug = league_path.split("/")[-1]
    page_url = f"https://www.espn.com/{league_slug}/playbyplay/_/gameId/{game_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = _http_get(page_url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []

        marker = "window['__espnfitt__']='"
        # Use exact marker assignment used by ESPN pages.
        marker = "window['__espnfitt__']='" if marker in resp.text else "window['__espnfitt__']="
        start_idx = resp.text.find(marker)
        if start_idx == -1:
            return []

        payload_start = start_idx + len(marker)
        payload, _ = json.JSONDecoder().raw_decode(resp.text[payload_start:])

        play_groups = (
            payload.get("page", {})
            .get("content", {})
            .get("gamepackage", {})
            .get("pbp", {})
            .get("playGrps", [])
        )

        flattened = []
        for group in play_groups:
            if isinstance(group, list):
                for play in group:
                    if isinstance(play, dict):
                        flattened.append(play)
            elif isinstance(group, dict):
                plays = group.get("plays", [])
                if isinstance(plays, list):
                    for play in plays:
                        if isinstance(play, dict):
                            flattened.append(play)

        return flattened
    except Exception:
        return []

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
    
    try:
        url = f"{BASE_URL}/{league_path}/rankings"
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return {'polls': []}
        
        data = resp.json()
        polls = data.get('rankings', [])
        
        return {'polls': polls}
    except Exception as e:
        print(f"Failed to fetch rankings for {league_key}: {e}")
        return {'polls': []}

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
        # The older path reads a team's playoff record once the season has ended.
        return _fetch_college_standings("WNBA", "basketball/wnba")
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
    else:
        # Fallback to original method for other leagues
        return _get_standings_original(league_key)

def _get_mlb_standings_fast():
    """Fast MLB standings using dedicated endpoint (0.15s vs 7s)"""
    try:
        # Use the fast dedicated standings endpoint
        url = "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings"
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
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
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
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
        
    except Exception as e:
        print(f"Error in fast NFL standings: {e}")
        return _get_standings_original("NFL")

def _get_nba_standings_fast():
    """Fast NBA standings using dedicated endpoint"""
    try:
        # Pin the request to the current season so the standings roll over with
        # it instead of staying on whatever season was current when this shipped
        season = get_current_season_year("NBA")
        url = f"https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={season}"
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
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
        
    except Exception as e:
        print(f"Error in fast NBA standings: {e}")
        return _get_standings_original("NBA")

def _get_nba_fresh_standings():
    """Create fresh NBA standings with all teams at 0-0 for new season"""
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
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
        
    except Exception as e:
        print(f"Error in fresh NBA standings: {e}")
        return []

def _get_nhl_standings_fast():
    """Fast NHL standings using dedicated endpoint"""
    try:
        url = "https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings"
        resp = _http_get(url)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
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


def _college_standing_row(entry, conference):
    team_info = entry.get("team", {})
    stats = entry.get("stats", [])
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
        # College conferences rank by record. A pro league's games back comes straight from ESPN.
        "games_back": _standing_stat(stats, "gamesbehind").get("displayValue") or "—",
        "conference_record": conf.get("summary") or conf.get("displayValue") or "",
        "division": conference,
        "streak": _standing_stat(stats, "streak").get("displayValue") or "",
        "logo": team_info.get("logos", [{}])[0].get("href", "") if team_info.get("logos") else "",
    }


def parse_college_standings(data):
    """Every team in a college /standings response. Conferences can nest (the Sun
    Belt does) and a league can have no conferences at all, with its entries at
    the root (women's college hockey)."""
    rows = []

    def walk(node, conference):
        name = node.get("name") or conference
        for entry in (node.get("standings") or {}).get("entries", []):
            rows.append(_college_standing_row(entry, name))
        for child in node.get("children") or []:
            walk(child, name)

    walk(data, "League")
    rows.sort(key=lambda r: (r["division"], -float(r["win_percentage"]), -r["wins"], r["losses"]))
    return rows


def _fetch_college_standings(league, path):
    try:
        resp = _http_get(f"https://site.api.espn.com/apis/v2/sports/{path}/standings")
        if resp.status_code == 200:
            rows = parse_college_standings(resp.json())
            if rows:
                return rows
    except Exception as e:
        print(f"Error in {league} standings: {e}")
    return _get_standings_original(league)


def _get_ncaaf_standings_fast():
    """College football standings, every conference."""
    return _fetch_college_standings("NCAAF", "football/college-football")


def _get_ncaam_standings_fast():
    """Men's college basketball standings, every conference."""
    return _fetch_college_standings("NCAAM", "basketball/mens-college-basketball")


def _get_ncaawb_standings_fast():
    """Women's college basketball standings, every conference."""
    return _fetch_college_standings("NCAAWB", "basketball/womens-college-basketball")


def _get_ncaah_standings_fast():
    """Men's college hockey standings, every conference."""
    return _fetch_college_standings("NCAAH", "hockey/mens-college-hockey")


def _get_ncaawh_standings_fast():
    """Women's college hockey standings. ESPN sends these at the root, with no conferences."""
    return _fetch_college_standings("NCAAWH", "hockey/womens-college-hockey")


def _get_standings_original(league_key):
    """Original standings method (slower but works for all leagues)"""
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    
    # Use teams API to get all teams and their records
    teams_url = f"{BASE_URL}/{league_path}/teams"
    resp = _http_get(teams_url)
    
    if resp.status_code != 200:
        return []
    
    data = resp.json()
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
                
                # The stats name each number. The summary can't be split blindly:
                # soccer's "8-0-1" is wins, draws, losses, and football's is wins,
                # losses, ties. Unpacking three parts into two used to fail, and the
                # team read 0-0.
                by_name = {stat.get("name"): stat.get("value") for stat in stats}
                if all(isinstance(by_name.get(n), (int, float)) for n in ("wins", "losses")):
                    wins, losses = int(by_name["wins"]), int(by_name["losses"])
                else:
                    first, second, third = _record_parts(summary)
                    is_soccer = (LEAGUES.get(league_key) or "").startswith("soccer/")
                    wins, losses = (first, third) if is_soccer else (first, second)
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

def _get_team_statistics(league_key):
    """Get team statistics for a league with parallel processing for speed"""
    import concurrent.futures
    
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    
    try:
        print(f"Fetching team statistics for {league_key}")
        
        # Get list of teams first
        teams_url = f"{BASE_URL}/{league_path}/teams"
        resp = _http_get(teams_url)
        
        if resp.status_code != 200:
            print(f"Failed to get teams list: {resp.status_code}")
            return []
        
        data = resp.json()
        
        # Navigate to teams data
        if 'sports' not in data or not data['sports']:
            print("No sports data found")
            return []
            
        leagues = data['sports'][0].get('leagues', [])
        if not leagues:
            print("No leagues data found")
            return []
            
        teams = leagues[0].get('teams', [])
        if not teams:
            print("No teams data found")
            return []
        
        print(f"Found {len(teams)} teams")
        
        def fetch_team_stats(team_entry):
            """Fetch statistics for a single team"""
            team = team_entry.get('team', {})
            team_id = team.get('id')
            team_name = team.get('displayName') or 'Unknown'
            
            if not team_id:
                return None
            
            try:
                # Get team statistics
                team_stats_url = f"{BASE_URL}/{league_path}/teams/{team_id}/statistics"
                team_resp = _http_get(team_stats_url)
                
                if team_resp.status_code == 200:
                    team_data = team_resp.json()
                    
                    # Parse team statistics
                    if 'results' in team_data and 'stats' in team_data['results']:
                        stats = team_data['results']['stats']
                        
                        if 'categories' in stats:
                            categories = stats['categories']
                            team_categories = []
                            
                            # Process each category for this team
                            for category in categories:
                                category_name = category.get('displayName') or category.get('name') or 'Unknown'
                                category_stats = category.get('stats', [])
                                
                                # Create team's stats for this category
                                team_category_stats = {
                                    'team_name': team_name,
                                    'team_id': str(team_id),
                                    'stats': {}
                                }
                                
                                # Process individual stats
                                for stat in category_stats:
                                    stat_name = stat.get('name', '')
                                    stat_display_name = stat.get('displayName') or stat_name
                                    stat_value = stat.get('displayValue', str(stat.get('value', '')))
                                    
                                    if stat_name and stat_value:
                                        team_category_stats['stats'][stat_display_name] = stat_value
                                
                                team_categories.append({
                                    'category': category_name,
                                    'team_stats': team_category_stats
                                })
                            
                            print(f"Processed team statistics for {team_name}")
                            return team_categories
                    
                else:
                    print(f"Failed to get statistics for {team_name}: {team_resp.status_code}")
                    
            except Exception as e:
                print(f"Error getting statistics for {team_name}: {e}")
                
            return None
        
        # Use parallel processing to fetch all team stats
        team_stats_categories = []
        teams_processed = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all team stat requests in parallel
            futures = [executor.submit(fetch_team_stats, team_entry) for team_entry in teams]
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    team_categories = future.result()
                    if team_categories:
                        teams_processed += 1
                        
                        # Merge this team's categories into the main structure
                        for team_category in team_categories:
                            category_name = team_category['category']
                            team_stats = team_category['team_stats']
                            
                            # Find or create the category
                            existing_category = None
                            for existing in team_stats_categories:
                                if existing['category'] == category_name:
                                    existing_category = existing
                                    break
                            
                            if not existing_category:
                                existing_category = {
                                    'category': category_name,
                                    'stats': []
                                }
                                team_stats_categories.append(existing_category)
                            
                            existing_category['stats'].append(team_stats)
                            
                except Exception as e:
                    print(f"Error processing team stats result: {e}")
        
        print(f"Successfully processed {teams_processed} teams with {len(team_stats_categories)} stat categories")
        return team_stats_categories
        
    except Exception as e:
        print(f"Error fetching team statistics: {e}")
        return []

def _get_mlb_statistics():
    """Get MLB player statistics from the official MLB Stats API with enhanced parallel loading"""
    import concurrent.futures
    from datetime import datetime
    
    # Determine the current season
    current_year = datetime.now().year
    season = current_year
    
    print(f"Fetching enhanced MLB statistics for {season} season")
    
    # Enhanced stat categories - all available from MLB API
    stat_categories = [
        # Hitting stats (16 categories)
        ("homeRuns", "hitting", "Home Runs"),
        ("battingAverage", "hitting", "Batting Average"),
        ("rbi", "hitting", "RBIs"),
        ("hits", "hitting", "Hits"),
        ("runs", "hitting", "Runs"),
        ("doubles", "hitting", "Doubles"),
        ("triples", "hitting", "Triples"),
        ("stolenBases", "hitting", "Stolen Bases"),
        ("onBasePercentage", "hitting", "On-Base %"),
        ("sluggingPercentage", "hitting", "Slugging %"),
        ("ops", "hitting", "OPS"),
        ("walks", "hitting", "Walks"),
        ("strikeouts", "hitting", "Strikeouts (Batting)"),
        ("hitByPitch", "hitting", "Hit By Pitch"),
        ("sacrificeFlies", "hitting", "Sacrifice Flies"),
        ("groundIntoDoublePlay", "hitting", "GIDP"),
        
        # Pitching stats (14 categories)
        ("wins", "pitching", "Wins"),
        ("losses", "pitching", "Losses"),
        ("era", "pitching", "ERA"),
        ("strikeouts", "pitching", "Strikeouts (Pitching)"),
        ("saves", "pitching", "Saves"),
        ("holds", "pitching", "Holds"),
        ("whip", "pitching", "WHIP"),
        ("inningsPitched", "pitching", "Innings Pitched"),
        ("hitBatsmen", "pitching", "Hit Batsmen"),
        ("wildPitches", "pitching", "Wild Pitches"),
        ("balks", "pitching", "Balks"),
        ("completeGames", "pitching", "Complete Games"),
        ("shutouts", "pitching", "Shutouts"),
        ("blownSaves", "pitching", "Blown Saves"),
        
        # Fielding stats (9 categories) - NEW!
        ("errors", "fielding", "Errors"),
        ("fieldingPercentage", "fielding", "Fielding %"),
        ("assists", "fielding", "Assists"),
        ("putouts", "fielding", "Putouts"),
        ("chances", "fielding", "Total Chances"),
        ("doublePlays", "fielding", "Double Plays"),
        ("triplePlays", "fielding", "Triple Plays"),
        ("passedBalls", "fielding", "Passed Balls"),
        ("caughtStealing", "fielding", "Caught Stealing"),
    ]
    
    print(f"Loading {len(stat_categories)} statistical categories in parallel...")
    
    def fetch_stat_category(stat_info):
        """Fetch a single stat category"""
        stat_key, stat_group, display_name = stat_info
        try:
            # Add limit parameter to get top 50 players instead of default 5
            url = f"https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories={stat_key}&statGroup={stat_group}&season={season}&limit=50"
            response = _http_get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'leagueLeaders' in data and len(data['leagueLeaders']) > 0:
                    leaders_data = data['leagueLeaders'][0]
                    if 'leaders' in leaders_data and len(leaders_data['leaders']) > 0:
                        
                        leaders = []
                        for leader in leaders_data['leaders'][:50]:  # Top 50 players
                            player_info = _as_dict(leader.get('person'))
                            team_info = _as_dict(leader.get('team'))
                            
                            leader_data = {
                                'name': player_info.get('fullName') or 'Unknown',
                                'value': leader.get('value') or 0,
                                'team': team_info.get('abbreviation') or team_info.get('name') or 'N/A',
                                'position': None  # MLB API doesn't provide position in leaders
                            }
                            leaders.append(leader_data)
                        
                        category_data = {
                            'name': display_name,
                            'display_name': display_name,
                            'abbreviation': stat_key,
                            'leaders': leaders
                        }
                        
                        return category_data, display_name, leaders[0]['name'], leaders[0]['value']
                        
        except Exception as e:
            print(f"  Error fetching {display_name}: {str(e)[:60]}")
        
        return None, display_name, None, None
    
    # Use parallel execution for much faster loading
    player_stats = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        # Submit all requests in parallel
        future_to_stat = {
            executor.submit(fetch_stat_category, stat_info): stat_info[2] 
            for stat_info in stat_categories
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_stat):
            stat_name = future_to_stat[future]
            try:
                category_data, display_name, leader_name, leader_value = future.result()
                if category_data:
                    player_stats.append(category_data)
                    print(f"  {display_name}: {leader_name} = {leader_value}")
                else:
                    print(f"  {display_name}: No data available")
            except Exception as e:
                print(f"  {stat_name}: Exception - {str(e)[:50]}")
    
    print(f"Successfully loaded {len(player_stats)} MLB statistical categories")
    
    return {
        "player_stats": player_stats,
        "team_stats": []
    }

# ESPN's /statistics answers this 404 on a good share of requests, mostly for college
# basketball, for a league it served a moment ago. It can stay cached for up to 30 seconds,
# so asking again for the same URL gets the same failure.
STATISTICS_BLIP = "Failed to retrieve league stats"
STATISTICS_TRIES = 3
STATISTICS_UNAVAILABLE = "ESPN isn't providing these right now. Try again in a minute."


def _is_statistics_blip(resp):
    if resp.status_code != 404:
        return False
    try:
        return resp.json().get("message") == STATISTICS_BLIP
    except (ValueError, AttributeError):
        return False


def _fetch_statistics(league_path):
    """The response from /statistics, the only ESPN endpoint with leaders, getting past ESPN's
    blip with a throwaway parameter, which earns a fresh answer rather than the cached failure.
    Raises ApiError if ESPN blips and no later try gets an answer: empty would read as no
    leaders existing, and the player statistics dialog has a row for this."""
    url = f"{BASE_URL}/{league_path}/statistics"
    resp = _http_get(url, timeout=10)
    if not _is_statistics_blip(resp):
        return resp
    for _ in range(STATISTICS_TRIES - 1):
        time.sleep(1)
        try:
            resp = _http_get(url, params={"_": int(time.time() * 1000)}, timeout=10)
        except requests.RequestException:
            continue
        if resp.status_code == 200:
            return resp
    raise ApiError(STATISTICS_UNAVAILABLE)


def get_statistics(league_key):
    """Get statistics/leaders data for a league"""
    # Handle case-insensitive league keys
    league_path = LEAGUES.get(league_key) or LEAGUES.get(league_key.upper())
    if not league_path:
        print(f"No league path found for {league_key}, providing sample data")
        return _get_sample_statistics_data(league_key)

    try:
        # For MLB, use the official MLB Stats API for full season player statistics
        if league_key.upper() == "MLB":
            print("Using MLB Stats API for full season player statistics")
            mlb_result = _get_mlb_statistics()
            if mlb_result['player_stats']:
                # Also get team statistics from ESPN
                team_stats = _get_team_statistics(league_key)
                if team_stats:
                    mlb_result['team_stats'] = team_stats
                return mlb_result
            else:
                print("MLB Stats API failed, falling back to ESPN")

        resp = _fetch_statistics(league_path)
        if resp.status_code == 200:
            result = _parse_statistics_data(resp.json())
            if result['player_stats']:
                team_stats = _get_team_statistics(league_key)
                if team_stats:
                    result['team_stats'] = team_stats
                return result
        else:
            print(f"Statistics for {league_key} returned status {resp.status_code}")

    except Exception as e:
        print(f"Error fetching statistics for {league_key}: {e}")
    
    
    # No player statistics, so try to get team statistics
    print(f"Attempting to fetch team statistics for {league_key}")
    team_stats = _get_team_statistics(league_key)
    
    sample_data = _get_sample_statistics_data(league_key)
    
    if team_stats:
        print(f"Successfully retrieved {len(team_stats)} team stat categories")
        return {
            "player_stats": sample_data.get("player_stats", []),
            "team_stats": team_stats
        }
    else:
        # Return sample data for both player and team stats
        return sample_data

def get_player_statistics(league_key):
    """Get only player statistics for a league (optimized for speed)"""
    # Handle case-insensitive league keys
    league_path = LEAGUES.get(league_key) or LEAGUES.get(league_key.upper())
    if not league_path:
        print(f"No league path found for {league_key}")
        return {"player_stats": [], "team_stats": []}

    try:
        # For MLB, use the official MLB Stats API for full season player statistics
        if league_key.upper() == "MLB":
            print("Using MLB Stats API for player statistics only")
            mlb_result = _get_mlb_statistics()
            if mlb_result['player_stats']:
                return mlb_result
            else:
                print("MLB Stats API failed, falling back to ESPN")

        resp = _fetch_statistics(league_path)
        if resp.status_code == 200:
            # Only return player stats, not team stats
            return {"player_stats": _parse_statistics_data(resp.json())["player_stats"], "team_stats": []}
        return {"player_stats": [], "team_stats": []}

    except ApiError:
        raise
    except Exception as e:
        print(f"Error fetching player statistics for {league_key}: {str(e)}")
        return {"player_stats": [], "team_stats": []}

def get_team_statistics(league_key):
    """Get only team statistics for a league (optimized for speed)"""
    try:
        print(f"Loading team statistics for {league_key}")
        team_stats = _get_team_statistics(league_key)
        return {"team_stats": team_stats, "player_stats": []}
    except Exception as e:
        print(f"Error fetching team statistics for {league_key}: {str(e)}")
        return {"team_stats": [], "player_stats": []}

def _parse_statistics_data(data):
    """Player leaders from ESPN's statistics endpoint: stats.categories, a list. A
    league with nothing to show has no stats key at all. Soccer leagues send stats as a
    list of leaders instead (goalsLeaders, assistsLeaders), which isn't read here and
    comes out as no players."""
    categories = _dicts(_as_dict(_as_dict(data).get("stats")).get("categories"))
    return {
        "player_stats": _parse_generic_player_stats(categories),
        "team_stats": [],
    }

def _parse_generic_player_stats(leaders):
    """[{name, displayName, leaders: [{athlete, value}]}] to the rows the dialog shows."""
    categories = []

    for category_data in leaders:
        category_key = category_data.get('name') or 'unknown'
        category_display_name = category_data.get('displayName') or category_key.title()
        leaders_list = _dicts(category_data.get('leaders'))

        if not leaders_list:
            continue

        stats = []
        for leader in leaders_list:
            athlete = _as_dict(leader.get("athlete"))
            team = _as_dict(leader.get("team") or athlete.get("team"))

            if athlete.get("displayName") or athlete.get("name"):
                # Use the raw value for the specific statistic, not the display value
                # displayValue contains full stat lines, value contains just the target stat
                raw_value = leader.get("value", "")

                # For most statistics, use the raw numeric value
                # For special cases like batting average, format appropriately
                if category_key.lower() in ['avg', 'era', 'whip', 'onbasepct', 'slugavg', 'ops']:
                    # For percentage/ratio stats, format to 3 decimal places
                    try:
                        stat_value = f"{float(raw_value):.3f}"
                    except (ValueError, TypeError):
                        stat_value = "" if raw_value is None else str(raw_value)
                else:
                    # For counting stats, use the numeric value as-is
                    stat_value = "" if raw_value is None else str(raw_value)

                stats.append({
                    "player_name": athlete.get("displayName") or athlete["name"],
                    "team": team.get("abbreviation") or team.get("name") or "",
                    "value": stat_value,
                    "stat_name": category_display_name
                })

        if stats:
            categories.append({
                "category": category_display_name,
                "stats": stats
            })

    return categories

def _get_sample_statistics_data(league_key):
    """No statistics. This used to return invented players (including "Sample Player 1"
    and years-old stars with made-up numbers) that the app showed as real leaders."""
    return {"player_stats": [], "team_stats": []}


def get_team_info(league_key, team_id):
    """Get full team details: record splits, venue, head coach, next game."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return {}
    try:
        resp = _http_get(f"{BASE_URL}/{league_path}/teams/{team_id}")
        if resp.status_code != 200:
            return {}
        team = resp.json().get("team", {})
        if not team:
            return {}
        result = {
            "name":         team.get("displayName") or "",
            "abbreviation": team.get("abbreviation") or "",
            "nickname":     team.get("name") or "",
            "location":     team.get("location") or "",
        }
        # Venue
        venue = team.get("venue") or (team.get("franchise") or {}).get("venue") or {}
        result["venue_name"] = venue.get("fullName") or venue.get("displayName") or ""
        addr = _as_dict(venue.get("address"))
        city, state = addr.get("city") or "", addr.get("state") or ""
        result["venue_location"] = f"{city}, {state}" if city and state else city or state
        # Record splits
        for item in _dicts(_as_dict(team.get("record")).get("items")):
            rtype = item.get("type", "")
            summary = item.get("summary") or ""
            if rtype == "total":
                # NHL totals have "10-4" here and the overtime losses in the stats.
                ot_losses = next((st.get("value") for st in item.get("stats", [])
                                  if st.get("name") == "otLosses"), None)
                if ot_losses is not None and summary.count("-") == 1:
                    summary = f"{summary}-{int(ot_losses)}"
                result["record_overall"] = summary
            elif rtype == "home":
                result["record_home"] = summary
            elif rtype == "road":
                result["record_road"] = summary
        # Division / Conference
        groups = _as_dict(team.get("groups"))
        result["division"] = groups.get("name") or ""
        result["standing"] = team.get("standingSummary") or ""
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
    except Exception as e:
        print(f"[get_team_info] team {team_id}: {e}")
        return {}


def get_team_roster(league_key, team_id):
    """Get a team's current roster as a list of player dicts."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    try:
        resp = _http_get(f"{BASE_URL}/{league_path}/teams/{team_id}/roster")
        if resp.status_code != 200:
            return []
        data = resp.json()
        players = []
        # ESPN returns athletes grouped by position group
        for group in data.get("athletes", []):
            items = group.get("items", [group] if "displayName" in group else [])
            for p in items:
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
    except Exception as e:
        print(f"[get_team_roster] team {team_id}: {e}")
        return []


def get_team_news(league_key, team_id, limit=15):
    """Get news articles for a specific team."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    try:
        # /teams/{id}/news returns no articles; /news?team={id} does.
        resp = _http_get(f"{BASE_URL}/{league_path}/news", params={"team": team_id, "limit": limit})
        if resp.status_code != 200:
            return []
        try:
            from text_utils import text_processor
        except ImportError:
            text_processor = None
        articles = []
        for a in _dicts(resp.json().get("articles")):
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
    except Exception as e:
        print(f"[get_team_news] team {team_id}: {e}")
        return []


def get_transactions(league_key, team_id=None, limit=50, page=1):
    """Get league-wide (or team-filtered) transactions with pagination.

    Returns (list_of_dicts, has_more).
    Each dict: {date, team, description}.
    """
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return [], False
    try:
        params = {"limit": limit, "page": page}
        if team_id:
            params["team"] = team_id
        resp = _http_get(f"{BASE_URL}/{league_path}/transactions", params=params)
        if resp.status_code != 200:
            return [], False
        data = resp.json()
        raw_items = data.get("transactions", data.get("items", []))
        # ESPN returns pageIndex / pageCount as top-level integers.
        page_count = int(data.get("pageCount", 1))
        has_more = int(page) < page_count
        result = []
        for item in raw_items:
            date_str = item.get("date", item.get("timestamp", ""))
            date_display = ""
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    date_display = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_display = date_str[:10]
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
    except Exception as e:
        print(f"[get_transactions] {league_key}: {e}")
        return [], False


_DRAFT_TEAM_CACHE: dict = {}


def _get_nfl_team_cache() -> dict:
    """Build {team_id: {abbrev, name}} from the NFL teams API. Cached for the process lifetime."""
    global _DRAFT_TEAM_CACHE
    if _DRAFT_TEAM_CACHE:
        return _DRAFT_TEAM_CACHE
    try:
        resp = _http_get(f"{BASE_URL}/football/nfl/teams", params={"limit": 50})
        if resp.status_code == 200:
            for sport in resp.json().get("sports", []):
                for league in sport.get("leagues", []):
                    for team in league.get("teams", []):
                        t = team.get("team", {})
                        _DRAFT_TEAM_CACHE[str(t.get("id", ""))] = {
                            "abbrev": t.get("abbreviation") or "",
                            "name": t.get("displayName") or t.get("shortDisplayName") or "",
                        }
    except Exception:
        pass
    return _DRAFT_TEAM_CACHE


def get_draft(year):
    """Return draft metadata for the given NFL season year.

    Returns dict: {year, num_rounds, status ('pre'/'in'/'post'), rounds: [{number, display_name, short_name}]}
    or None if unavailable.
    """
    import re
    base = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    try:
        resp = _http_get(f"{base}/seasons/{year}/draft")
        if resp.status_code != 200:
            return None
        data = resp.json()
        # An empty body isn't a finished seven-round draft.
        if not any(data.get(field) for field in ("year", "numberOfRounds", "rounds", "status")):
            return None
        num_rounds = data.get("numberOfRounds") or 7

        rounds_resp = _http_get(f"{base}/seasons/{year}/draft/rounds")
        rounds = []
        if rounds_resp.status_code == 200:
            for item in rounds_resp.json().get("items", []):
                rounds.append({
                    "number": item.get("number"),
                    "display_name": item.get("displayName") or f"Round {item.get('number')}",
                    "short_name": item.get("shortDisplayName") or str(item.get("number")),
                })
        else:
            rounds = [{"number": i, "display_name": f"Round {i}", "short_name": str(i)}
                      for i in range(1, num_rounds + 1)]

        status = "post"
        status_info = data.get("status", {})
        if isinstance(status_info, dict) and "$ref" in status_info:
            try:
                sr = _http_get(status_info["$ref"])
                if sr.status_code == 200:
                    state = sr.json().get("type", {}).get("state", "post")
                    status = str(state).lower()
            except Exception:
                pass

        return {"year": int(year), "num_rounds": num_rounds, "status": status, "rounds": rounds}
    except Exception as e:
        print(f"[get_draft] {year}: {e}")
        return None


def get_draft_round(year, round_num):
    """Return a list of pick dicts for one round of the NFL Draft.

    Each dict: {overall, pick, round, traded, trade_note, team_abbrev, team_name,
                player_name, position, college, status_name}
    """
    import re
    from concurrent.futures import ThreadPoolExecutor, as_completed

    base = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    try:
        rounds_resp = _http_get(f"{base}/seasons/{year}/draft/rounds")
        if rounds_resp.status_code != 200:
            return []
        target = next((rd for rd in rounds_resp.json().get("items", [])
                       if rd.get("number") == round_num), None)
        if not target:
            return []
        picks_raw = _dicts(target.get("picks"))
    except Exception as e:
        print(f"[get_draft_round] fetch rounds {year}/r{round_num}: {e}")
        return []

    teams = _get_nfl_team_cache()
    college_cache: dict = {}

    def _extract_id(pattern, url):
        m = re.search(pattern, url or "")
        return m.group(1) if m else ""

    def fetch_pick_data(pick):
        athlete_ref = _as_dict(pick.get("athlete")).get("$ref") or ""
        team_id = _extract_id(r"/teams/(\d+)", _as_dict(pick.get("team")).get("$ref") or "")
        team_info = teams.get(team_id, {"abbrev": "?", "name": "Unknown"})

        player_name = position = college_ref_url = ""
        if athlete_ref:
            try:
                ar = _http_get(athlete_ref)
                if ar.status_code == 200:
                    ad = ar.json()
                    player_name = ad.get("displayName") or ad.get("fullName") or ""
                    pos = ad.get("position", {})
                    position = (pos.get("abbreviation") or pos.get("name") or "") if isinstance(pos, dict) else ""
                    col = ad.get("college", {})
                    college_ref_url = (col.get("$ref") or "") if isinstance(col, dict) else ""
            except Exception:
                pass

        return {
            "overall": pick.get("overall") or 0,
            "pick": pick.get("pick") or 0,
            "round": pick.get("round") or round_num,
            "traded": bool(pick.get("traded")),
            "trade_note": pick.get("tradeNote") or "",
            "team_abbrev": team_info["abbrev"],
            "team_name": team_info["name"],
            "player_name": player_name,
            "position": position,
            "status_name": _as_dict(pick.get("status")).get("name") or "",
            "_college_ref": college_ref_url,
        }

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for future in as_completed({executor.submit(fetch_pick_data, p): p for p in picks_raw}):
            try:
                results.append(future.result())
            except Exception:
                pass

    # Resolve unique colleges concurrently
    unique_refs = {r["_college_ref"] for r in results if r.get("_college_ref")}

    def fetch_college(ref_url):
        cid = _extract_id(r"/colleges/(\d+)", ref_url)
        if not cid:
            return "", ""
        try:
            cr = _http_get(ref_url)
            if cr.status_code == 200:
                cd = cr.json()
                return cid, cd.get("name") or cd.get("shortName") or ""
        except Exception:
            pass
        return cid, ""

    with ThreadPoolExecutor(max_workers=20) as executor:
        for future in as_completed({executor.submit(fetch_college, ref): ref for ref in unique_refs}):
            cid, name = future.result()
            if cid:
                college_cache[cid] = name

    for pick in results:
        cid = _extract_id(r"/colleges/(\d+)", pick.pop("_college_ref", ""))
        pick["college"] = college_cache.get(cid, "")

    results.sort(key=lambda p: p.get("overall", 0))
    return results


def get_team_transactions(league_key, team_id, limit=25):
    """Get recent transactions for a team. Returns [] if the league has no transaction feed."""
    league_path = LEAGUES.get(league_key)
    if not league_path or not team_id:
        return []
    try:
        resp = _http_get(
            f"{BASE_URL}/{league_path}/transactions",
            params={"team": team_id, "limit": limit},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("transactions", data.get("items", []))
        result = []
        for item in items:
            date_str = item.get("date", item.get("timestamp", ""))
            date_display = ""
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    date_display = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_display = date_str[:10]
            result.append({
                "date":        date_display,
                "description": item.get("description") or "",
                # Keep legacy keys so callers using player/type/position still work.
                "type":        "",
                "player":      "",
                "position":    "",
            })
        return result
    except Exception as e:
        print(f"[get_team_transactions] team {team_id}: {e}")
        return []


def get_golf_leaderboard(tour_key):
    """Return current tournament info and leaderboard for PGA or LPGA.

    Returns dict: {name, short_name, date, end_date, round_num, status_detail,
                   players: [{position, name, country, total_score, rounds: [str]}]}
    or None if no event is available.
    """
    from datetime import datetime
    league_path = LEAGUES.get(tour_key)
    if not league_path:
        return None
    try:
        resp = _http_get(f"{BASE_URL}/{league_path}/scoreboard")
        if resp.status_code != 200:
            return None
        data = resp.json()
        events = _dicts(data.get("events"))
        if not events:
            return None
        event = events[0]
        comps = _dicts(event.get("competitions"))
        if not comps:
            return None
        comp = comps[0]
        comp_status = _as_dict(comp.get("status"))

        players = []
        for competitor in _dicts(comp.get("competitors")):
            athlete = _as_dict(competitor.get("athlete"))
            rounds = [
                ls["displayValue"]
                for ls in sorted(_dicts(competitor.get("linescores")), key=lambda x: x.get("period") or 0)
                if "value" in ls and "displayValue" in ls
            ]
            players.append({
                "position": competitor.get("order") or 0,
                "name": athlete.get("displayName") or athlete.get("fullName") or "",
                "country": _as_dict(athlete.get("flag")).get("alt") or "",
                "total_score": golf_total_to_par(competitor),
                "rounds": rounds,
            })
        players.sort(key=lambda p: p["position"])

        return {
            "name": event.get("name") or "",
            "short_name": event.get("shortName") or "",
            "date": (event.get("date") or "")[:10],
            "end_date": (event.get("endDate") or "")[:10],
            "round_num": comp_status.get("period") or 0,
            "status_detail": _as_dict(comp_status.get("type")).get("detail") or "",
            "players": players,
        }
    except Exception as e:
        print(f"[get_golf_leaderboard] {tour_key}: {e}")
        return None


def get_golf_schedule(tour_key):
    """Return this season's tournament schedule for PGA or LPGA.

    Returns list of {name, start_date, end_date, status, state, winner}.
    """
    from datetime import datetime
    league_path = LEAGUES.get(tour_key)
    if not league_path:
        return []
    try:
        year = datetime.now().year
        # A bare year, not a START-END range: ESPN rejects ranges on team sports
        # and only still tolerates them here. The year returns the same 49 events.
        resp = _http_get(
            f"{BASE_URL}/{league_path}/scoreboard",
            params={"dates": str(year)},
        )
        if resp.status_code != 200:
            return []
        result = []
        for event in _dicts(resp.json().get("events")):
            status_type = _as_dict(_as_dict(event.get("status")).get("type"))
            state = status_type.get("state") or "pre"

            winner = ""
            if state == "post":
                comps = _dicts(event.get("competitions"))
                if comps:
                    top = sorted(_dicts(comps[0].get("competitors")), key=lambda x: x.get("order") or 999)
                    if top:
                        w = top[0]
                        wname = _as_dict(w.get("athlete")).get("displayName") or ""
                        wscore = w.get("score") or ""
                        winner = f"{wname} ({wscore})" if wname and wscore else wname

            result.append({
                "name": event.get("name") or "",
                "start_date": (event.get("date") or "")[:10],
                "end_date": (event.get("endDate") or "")[:10],
                "status": status_type.get("description") or "Scheduled",
                "state": state,
                "winner": winner,
            })
        return result
    except Exception as e:
        print(f"[get_golf_schedule] {tour_key}: {e}")
        return []


# ─────────────────────────── World Cup ───────────────────────────────────────

def get_world_cup_standings(league_key):
    """Fetch World Cup group standings (men's WC2026 or women's WWC2027).

    Returns a list of group dicts, each containing:
      { 'id', 'name', 'teams': [ { team fields … } ] }
    """
    league_path = LEAGUES.get(league_key)
    if not league_path:
        return []
    try:
        url = f"https://site.api.espn.com/apis/v2/sports/{league_path}/standings"
        resp = _http_get(url, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        groups = []
        for child in data.get("children", []):
            group_id   = str(child.get("id") or "")
            group_name = child.get("name") or "Group"
            entries    = child.get("standings", {}).get("entries", [])
            teams = []
            for idx, entry in enumerate(entries):
                team  = entry.get("team", {})
                stats = {s["name"]: s.get("value", 0) for s in entry.get("stats", [])}
                note  = entry.get("note") or {}
                rank  = int(stats.get("rank", idx + 1))
                gd    = int(stats.get("pointDifferential", 0))
                teams.append({
                    "team_id":          str(team.get("id") or ""),
                    "team_name":        team.get("displayName") or "",
                    "abbreviation":     team.get("abbreviation") or "",
                    "rank":             rank,
                    "games_played":     int(stats.get("gamesPlayed", 0)),
                    "wins":             int(stats.get("wins", 0)),
                    "draws":            int(stats.get("ties", 0)),
                    "losses":           int(stats.get("losses", 0)),
                    "goals_for":        int(stats.get("pointsFor", 0)),
                    "goals_against":    int(stats.get("pointsAgainst", 0)),
                    "goal_difference":  gd,
                    "points":           int(stats.get("points", 0)),
                    "advancement_note": note.get("description") or "",
                })
            teams.sort(key=lambda t: t["rank"])
            groups.append({"id": group_id, "name": group_name, "teams": teams})
        return groups
    except Exception as e:
        print(f"[get_world_cup_standings] {league_key}: {e}")
        return []


def get_world_cup_scores_range(league_key, start_date, end_date):
    """Fetch all World Cup games between start_date and end_date (inclusive).

    Returns the same list-of-dicts format as get_scores().
    """
    from datetime import timedelta
    all_games = []
    seen_ids: set = set()
    current = start_date
    while current <= end_date:
        try:
            day_games = get_scores(league_key, date=current)
            for g in day_games:
                gid = g.get("id", "")
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    all_games.append(g)
        except Exception:
            pass
        current += timedelta(days=1)
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


def _load_fantasy_season(season, max_rank):
    """Fetch and map one season's draft board. Returns [] when unavailable."""
    url = f"{FANTASY_BASE}/{season}/players?view=kona_player_info&scoringPeriodId=0"
    # The header must be present to receive the full pool; ESPN ignores its body.
    headers = {
        "X-Fantasy-Filter": '{"players":{"limit":12000}}',
        "Accept": "application/json",
    }
    resp = _http_get(url, headers=headers, timeout=90)
    if resp.status_code != 200:
        # Raised, not swallowed: an empty list here would be indistinguishable
        # from "ESPN has not published this season yet", and the caller reports
        # those two very differently.
        raise RuntimeError(f"ESPN fantasy feed returned HTTP {resp.status_code}")
    raw_players = resp.json()
    if not isinstance(raw_players, list):
        return []
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
    except Exception as e:
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
