"""How the two teams in an MLB game have done against each other, from its `summary`.

No PyQt import, so it can be tested against real ESPN payloads on any platform.
The iPhone's twin is `Models/SeasonSeries.swift`; the order, labels and record
text are held to tests/fixtures/season_series_grid.json on both. Change both
together.

ESPN's `seasonseries` block is a list of series, each with its games under `events`:
`{"type": "season", "title": "Regular Season Series", "summary": "NYM lead series 7-5",
"totalCompetitions": 13, "events": [...]}`. Types seen: `current` (this set of games),
`season` (the regular season), `preseason`, and `playoff` (with `round`, "World Series").

- `events` runs to the end of the series, past the game being looked at, but the
  record is as of that game, as ESPN's `summary` is: game 4 of a World Series says
  "Brewers lead 3-1" though Milwaukee went on to win it. Games after it aren't counted,
  so an old game doesn't give away how the series ended. A game not in `events` (a
  spring training series seen from a regular season game) counts every game.
- The record is counted from the games, each finished game's `winner`, rather than read
  from ESPN's `summary`, which isn't always right: in that World Series game the
  `current` series said "TB leads series 3-2".
- A game is finished when `statusType.completed` says so; `status` ("post") is read
  only without a `statusType`, since a postponed game can be "post" too.
- In a postseason game `current` is the same games as `playoff`, and is left out.
- A series is won once every game in it is played, or, for a playoff series, once one
  team has won more than half of `totalCompetitions` (a best of seven at four). A
  regular season series clinched early still "leads" until its last game, as ESPN says.
"""

from typing import Any, Dict, List, Optional

from game_labels import local_schedule_datetime

_ORDER = {"playoff": 0, "season": 1, "current": 2, "preseason": 3}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _count(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def team_names(summary: Any) -> Dict[str, str]:
    """Team id to the short name a screen reader says well ("Mets"), from the header."""
    names = {}
    competitions = _list(_dict(_dict(summary).get("header")).get("competitions"))
    competition = _dict(competitions[0]) if competitions else {}
    for competitor in _list(competition.get("competitors")):
        team = _dict(_dict(competitor).get("team"))
        team_id = str(team.get("id") or "")
        name = (_text(team.get("name")) or _text(team.get("shortDisplayName"))
                or _text(team.get("abbreviation")) or _text(team.get("displayName")))
        if team_id and name:
            names[team_id] = name
    return names


def _finished(event: Dict[str, Any]) -> bool:
    status_type = event.get("statusType")
    if isinstance(status_type, dict):
        return status_type.get("completed") is True
    return _text(event.get("status")) == "post"


def this_game_id(summary: Any) -> str:
    """The id of the game the summary is for."""
    return str(_dict(_dict(summary).get("header")).get("id") or "").strip()


def _event_ids(entry: Dict[str, Any]) -> frozenset:
    return frozenset(str(e["id"]).strip() for e in _events(entry) if str(e.get("id") or "").strip())


def _name(team: Dict[str, Any], names: Dict[str, str]) -> str:
    return (names.get(str(team.get("id") or "")) or _text(team.get("displayName"))
            or _text(team.get("abbreviation")) or "Unknown")


def _events(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in _list(entry.get("events")) if isinstance(e, dict)]


def games(entry: Dict[str, Any]) -> int:
    """How many games the series has: ESPN's total, else the games it lists."""
    return _count(entry.get("totalCompetitions")) or len(_events(entry))


def label(entry: Dict[str, Any]) -> str:
    """"World Series" for a playoff series with a round, else ESPN's title."""
    if _text(entry.get("type")) == "playoff" and _text(entry.get("round")):
        return _text(entry.get("round"))
    return _text(entry.get("title")) or "Series"


def record_text(entry: Dict[str, Any], names: Dict[str, str], this_game: str = "") -> str:
    """"Mets lead 7-5", "Mets won 7-6", "Tied 2-2", "Split 3-3", "No games played yet",
    as of `this_game` when it is one of the series' games."""
    events = _events(entry)
    total = games(entry)
    ids = [str(e.get("id") or "").strip() for e in events]
    counted = events[:ids.index(this_game) + 1] if this_game and this_game in ids else events
    finished = [e for e in counted if _finished(e)]
    wins: Dict[str, int] = {}
    team_by_id: Dict[str, Dict[str, Any]] = {}
    for event in events:
        for competitor in _list(event.get("competitors")):
            team = _dict(_dict(competitor).get("team"))
            team_id = str(team.get("id") or "")
            if team_id:
                wins.setdefault(team_id, 0)
                team_by_id.setdefault(team_id, team)
    for event in finished:
        for competitor in _list(event.get("competitors")):
            competitor = _dict(competitor)
            team_id = str(_dict(competitor.get("team")).get("id") or "")
            if competitor.get("winner") is True and team_id in wins:
                wins[team_id] += 1
    if not finished or not wins:
        return "No games played yet"
    ranked = sorted(wins.items(), key=lambda pair: -pair[1])
    lead_id, lead_wins = ranked[0]
    trail_wins = ranked[1][1] if len(ranked) > 1 else 0
    decided = len(finished) >= total or (_text(entry.get("type")) == "playoff" and lead_wins * 2 > total)
    if lead_wins == trail_wins:
        return f"{'Split' if decided else 'Tied'} {lead_wins}-{trail_wins}"
    name = _name(team_by_id[lead_id], names)
    return f"{name} {'won' if decided else 'lead'} {lead_wins}-{trail_wins}"


def ordered(summary: Any) -> List[Dict[str, Any]]:
    """The series to show, in order: playoff, regular season, current, preseason, then
    anything else as ESPN sent it. A series with the same games as one before it, as
    `current` is in the postseason, is left out."""
    entries = [_dict(e) for e in _list(_dict(summary).get("seasonseries")) if isinstance(e, dict)]
    ranked = sorted(enumerate(entries), key=lambda pair: (_ORDER.get(_text(pair[1].get("type")), 4), pair[0]))
    shown, seen = [], []
    for _i, entry in ranked:
        ids = _event_ids(entry)
        if ids and ids in seen:
            continue
        seen.append(ids)
        shown.append(entry)
    return shown


def series(summary: Any, names: Optional[Dict[str, str]] = None,
           this_game: Optional[str] = None) -> List[Dict[str, Any]]:
    """Each series as shown: {"label", "text", "games", "entry"}, the record as of
    `this_game`, which is the summary's own game unless given."""
    names = team_names(summary) if names is None else names
    this_game = this_game_id(summary) if this_game is None else this_game
    return [{
        "label": label(entry),
        "text": record_text(entry, names, this_game),
        "games": games(entry),
        "entry": entry,
    } for entry in ordered(summary)]


def summary_line(summary: Any) -> str:
    """The game details row: "Regular Season Series: Mets lead 7-5". Empty with none."""
    shown = series(summary)
    if not shown:
        return ""
    return f"{shown[0]['label']}: {shown[0]['text']}"


GAME_HEADERS = ["Date", "Game", "Winner", "Status"]
THIS_GAME = "this game"  # the end of the status of the game being looked at


def game_rows(entry: Dict[str, Any], names: Dict[str, str], this_game: str = "") -> List[List[str]]:
    """One row per game: date, "Mets 7 at Nationals 1", the winner, and the status, or
    the local start time for a game still to come. The game being looked at says so."""
    rows = []
    for event in _list(entry.get("events")):
        event = _dict(event)
        sides = {}
        for competitor in _list(event.get("competitors")):
            competitor = _dict(competitor)
            sides[_text(competitor.get("homeAway"))] = competitor
        away, home = sides.get("away", {}), sides.get("home", {})
        away_name, home_name = _name(_dict(away.get("team")), names), _name(_dict(home.get("team")), names)
        finished = _finished(event)
        joiner = "vs" if event.get("neutralSite") is True else "at"
        if finished and _text(str(away.get("score", ""))) and _text(str(home.get("score", ""))):
            game = f"{away_name} {away.get('score')} {joiner} {home_name} {home.get('score')}"
        else:
            game = f"{away_name} {joiner} {home_name}"
        winner = next((_name(_dict(c.get("team")), names) for c in (away, home)
                       if finished and c.get("winner") is True), "")
        date_text, time_text = "", ""
        date = _text(event.get("date"))
        if date:
            try:
                when = local_schedule_datetime(date, event.get("timeValid") is not False)
                date_text = when.strftime("%a, %b %d")
                if event.get("timeValid") is not False:
                    time_text = when.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                pass
        status_type = _dict(event.get("statusType"))
        status = _text(status_type.get("detail")) or _text(status_type.get("description"))
        if not finished and _text(status_type.get("state")) == "pre":
            status = time_text or status or "Scheduled"
        if this_game and str(event.get("id")) == str(this_game):
            status = f"{status}, {THIS_GAME}" if status else THIS_GAME.capitalize()
        rows.append([date_text, game, winner, status])
    return rows
