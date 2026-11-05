"""Period names and small game facts read from ESPN data. No PyQt import, so tested directly."""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Men's college basketball is played in two halves; everything else here in four quarters.
_HALVES_LEAGUES = {"NCAAM"}

_PLAIN_NUMBER = re.compile(r"[+-]?[\d,]*\.?\d+$")
_THREE_PLACE_STATS = {"avg", "ops", "onbasepct", "slugavg", "opponentavg", "savepct"}
_TWO_PLACE_STATS = {"era", "whip"}
_WHOLE_NUMBER_STATS = {"points", "doubledouble"}


def leader_display_value(category: Optional[str], value: Any, display_value: Any) -> str:
    """How a league leader's number reads. ESPN's displayValue is the right text for most
    stats, 38.3 for 38.2857, and these are where it isn't. On the iPhone this is
    ESPNAPIService.leaderDisplayValue, and tests/fixtures/leader_display_grid.json holds both.

    Baseball's is a stat line ("179-567, 42 HR, 3B, ..."), for every category.
    A fraction gets rounded away: 7.5 sacks reads 8, a 137.3 quarterback rating reads 137.
    Three-point and college free throw percentages are fractions: 0.6154 reads 0.6. A save
    percentage is one too, but reads as one: .945.
    Season totals read as if they were averages: 268 points reads 268.0.
    """
    display = str(display_value or "").strip()
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return display
    number = float(value)
    name = str(category or "").lower()

    if not _PLAIN_NUMBER.match(display):
        if name in _THREE_PLACE_STATS:
            text = f"{number:.3f}"
            return text[1:] if text.startswith("0.") else text
        if number.is_integer() and name not in _TWO_PLACE_STATS:
            return str(int(number))
        return f"{number:.2f}"

    if name in _WHOLE_NUMBER_STATS and number.is_integer():
        return str(int(number))
    if "pct" in name and name not in _THREE_PLACE_STATS and 0 <= number <= 1 and float(display.replace(",", "")) <= 1:
        return f"{number * 100:.1f}"
    if "." not in display and not number.is_integer():
        return f"{number:.1f}"
    return display


def scoreboard_today(now: Optional[datetime] = None):
    """The date whose scoreboard is "today". Until 5 AM local it's still last night's,
    which is what's on: a West Coast game runs well past midnight in the East, and
    ESPN files it under the day it started. Asking for the new date loses it."""
    now = now or datetime.now()
    return (now - timedelta(hours=5)).date()


def _overtime_label(number: int) -> str:
    return "OT" if number <= 1 else f"{number}OT"


def basketball_period_label(league: Optional[str], period: int, fallback: str = "") -> str:
    """1st Half, 3rd Quarter, OT, 2OT."""
    regulation, unit = (2, "Half") if league in _HALVES_LEAGUES else (4, "Quarter")
    if period > regulation:
        return _overtime_label(period - regulation)
    ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    if period in ordinals:
        return f"{ordinals[period]} {unit}"
    return fallback or f"Period {period}"


def football_period_label(period: Any) -> str:
    """Quarter 1 to Quarter 4, then OT, 2OT."""
    try:
        number = int(period)
    except (TypeError, ValueError):
        return "Unknown Quarter"
    return f"Quarter {number}" if number <= 4 else _overtime_label(number - 4)


def football_period_sort_key(label: str) -> int:
    """Play order for the labels above, so OT follows Quarter 4 and 2OT follows OT."""
    if label.startswith("Quarter "):
        try:
            return int(label.split()[1])
        except (IndexError, ValueError):
            return 99
    if label == "OT":
        return 5
    if label.endswith("OT"):
        try:
            return 4 + int(label[:-2])
        except ValueError:
            return 99
    return 99


def broadcast_names(*sources: Any) -> List[str]:
    """Network names from ESPN's broadcast lists, without repeats, from the first
    source that has any. The scoreboard form is {names: [...]}; the summary form is
    {media: {shortName}} or {station}. A summary's own list can be empty when its
    header has one, so pass both."""
    for broadcasts in sources:
        names: List[str] = []
        for broadcast in broadcasts or []:
            if not isinstance(broadcast, dict):
                continue
            found = list(broadcast.get("names") or [])
            if not found:
                media = broadcast.get("media") or {}
                name = (media.get("shortName") or media.get("name") or broadcast.get("station")
                        if isinstance(media, dict) else broadcast.get("station"))
                if name:
                    found = [name]
            for name in found:
                if name not in names:
                    names.append(name)
        if names:
            return names
    return []


def injured_player_count(injuries: Any) -> int:
    """ESPN lists injuries per team, so the list's own length is the number of teams."""
    if not isinstance(injuries, list):
        return 0
    return sum(len(team.get("injuries") or []) for team in injuries if isinstance(team, dict))


def best_odds(details: Dict[str, Any]) -> Dict[str, Any]:
    """The first line with something in it. `odds` is usually empty; `pickcenter` has them."""
    for source in (details.get("odds"), details.get("pickcenter")):
        for line in source or []:
            if isinstance(line, dict) and (line.get("details") or line.get("overUnder")):
                return line
    return {}


def local_schedule_datetime(date_str: str, time_valid: bool = True) -> datetime:
    """A schedule date as naive local time. ESPN's dates are UTC, so a 7 PM Central
    game is tomorrow in UTC. A game whose time isn't set (`timeValid: false`) is
    stored at a placeholder hour, where the UTC date is the true one."""
    parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if time_valid and parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.replace(tzinfo=None)


def _first_text(*values: Any) -> str:
    return next((v for v in values if isinstance(v, str) and v.strip()), "")


def schedule_game_label(event: Any) -> str:
    """What sets a game apart on a team's schedule, from ESPN's event: "Super Bowl LX",
    "SEC Championship", "Preseason Week 1". Empty for an everyday game.

    ESPN's note says it best, and appears in any season type: FCS playoffs are filed
    under the regular season. Soccer has no season types, only long ids, and a note can
    be a bare ingest record with no headline. "Week 5" isn't worth reading on every row,
    so the week and the season type's own name only count for preseason and postseason.
    """
    if not isinstance(event, dict):
        return ""
    competitions = event.get("competitions")
    competition = competitions[0] if isinstance(competitions, list) and competitions else None
    notes = competition.get("notes") if isinstance(competition, dict) else None
    for note in notes if isinstance(notes, list) else []:
        if isinstance(note, dict):
            headline = _first_text(note.get("headline"))
            if headline:
                return headline
    season_type = event.get("seasonType")
    season_type = season_type if isinstance(season_type, dict) else {}
    if season_type.get("type") in (1, 3):
        week = event.get("week")
        return _first_text(week.get("text") if isinstance(week, dict) else None, season_type.get("name"))
    return ""


_CALLED_OFF = ("Canceled", "Cancelled", "Postponed")


def schedule_game_is_over(game: Dict[str, Any]) -> bool:
    """True for a row with nothing still to come. Soccer's finals say "Full Time", or
    "Final Score - After Penalties", so the word Final doesn't settle it."""
    return bool(game.get("completed")) or game.get("status") in _CALLED_OFF


def schedule_start_row(rows: List[Dict[str, Any]], current_season: bool = True) -> int:
    """The row a team's schedule opens on: today's game, else the next one to play.

    With nothing left to play, the current season opens on its last game, the most
    recent news, rather than a preseason game from months ago. A past season opens
    at its start, to read through from the beginning.
    """
    today = [i for i, game in enumerate(rows) if game.get("is_today")]
    if today:
        return today[-1]
    upcoming = next((i for i, game in enumerate(rows) if not schedule_game_is_over(game)), None)
    if upcoming is not None:
        return upcoming
    return max(len(rows) - 1, 0) if current_season else 0


def _schedule_result(game: Dict[str, Any]) -> str:
    """W 29-13, the team asked for first. Empty unless there are two scores."""
    home, away = game.get("home_score"), game.get("away_score")
    try:
        home_points, away_points = int(home), int(away)
    except (TypeError, ValueError):
        return ""
    if home_points == away_points:
        return f"T {home}-{away}"
    if game.get("home_away") == "vs":
        return f"{'W' if home_points > away_points else 'L'} {home}-{away}"
    return f"{'W' if away_points > home_points else 'L'} {away}-{home}"


def schedule_row_text(game: Dict[str, Any]) -> str:
    """One row of a team's schedule, which is all a screen reader gets for it:
    "Sun, Feb 08, 2026: vs New England Patriots - W 29-13, Super Bowl LX".

    The result or time comes before the label because a label can run long, and
    this way the part you came for isn't behind it. A neutral site isn't an away
    game, whichever team ESPN files as the home one.
    """
    where = "vs" if game.get("neutral_site") else game.get("home_away", "")
    status = game.get("status", "")
    if game.get("completed"):
        outcome = _schedule_result(game) or status
    elif status in _CALLED_OFF:
        outcome = status
    else:
        outcome = game.get("time", "")
        venue = game.get("venue", "")
        if venue and venue != "TBD":
            outcome += f" ({venue})"
    text = f"{game.get('date_display', '')}: {where} {game.get('opponent', 'Unknown')} - {outcome}"
    label = game.get("label")
    return f"{text}, {label}" if label else text


def format_height(height: Any) -> str:
    """ESPN sends inches, sometimes as a float: 77.0 is 6'5"."""
    try:
        inches = int(float(height))
    except (TypeError, ValueError):
        return ""
    return f"{inches // 12}'{inches % 12}\"" if inches > 0 else ""


def format_weight(weight: Any) -> str:
    try:
        pounds = int(float(weight))
    except (TypeError, ValueError):
        return ""
    return f"{pounds} lbs" if pounds > 0 else ""


def game_standings_tables(standings: Any) -> List[Dict[str, Any]]:
    """The conference or division tables a game summary carries:
    [{title, headers, rows}], one per group, or an empty list."""
    if not isinstance(standings, dict):
        return []
    tables = []
    for group in standings.get("groups") or []:
        entries = (group.get("standings") or {}).get("entries") or []
        if not entries:
            continue
        stat_keys: List[str] = []
        labels: Dict[str, str] = {}
        for entry in entries:
            for stat in entry.get("stats") or []:
                key = stat.get("name")
                if key and key not in labels:
                    stat_keys.append(key)
                    labels[key] = stat.get("shortDisplayName") or stat.get("abbreviation") or key
        rows = []
        for entry in entries:
            values = {s.get("name"): s.get("displayValue", "") for s in entry.get("stats") or []}
            rows.append([str(entry.get("team", ""))] + [str(values.get(k, "")) for k in stat_keys])
        tables.append({
            "title": group.get("header") or "Standings",
            "headers": ["Team"] + [labels[k] for k in stat_keys],
            "rows": rows,
        })
    return tables
