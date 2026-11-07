"""Pure: ESPN's racing answers to what the Racing screens show. Formula 1, IndyCar and NASCAR Cup.

No PyQt import, so it is tested on any platform. The iPhone reads the same answers in
`ESPNAPIService.fetchRaceEvent` and `fetchRacingStandings`, and tests/fixtures/racing_grid.json
holds the two apps to the same reading (tests/unit/test_racing.py and RacingGridTests.swift).

How ESPN's racing answers differ from the team sports, all seen in tests/fixtures/espn/racing_*:

- An event is a race weekend. Formula 1 lists each session as its own competition (FP1, FP2,
  FP3, Qual, or SS and SR on a sprint weekend, then Race); IndyCar and NASCAR list one, with no
  type, which is the race.
- The event's own status can't be trusted for Formula 1: it said Final for the Sao Paulo Grand
  Prix with the race itself the next day. The race's own competition says what the race is.
- A race not yet run lists its field with no `order` at all: an entry list, not a result.
  NASCAR's lists nobody until race day.
- A canceled race is state post, completed false, with no field.
- `winner` isn't always set on the race's winner (IndyCar at Mid-Ohio, NASCAR's Clash), so the
  winner is whoever finished first in a completed race.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from game_labels import broadcast_names, local_schedule_datetime

# key: (ESPN path, name, full name, whether it has constructors and practice sessions)
RACING_SERIES = {
    "F1": ("racing/f1", "Formula 1", "FIA Formula One World Championship", True),
    "IndyCar": ("racing/irl", "IndyCar Series", "NTT IndyCar Series", False),
    "NASCAR": ("racing/nascar-premier", "NASCAR Cup Series", "NASCAR Cup Series", False),
}

# ESPN's session abbreviations, as Formula 1 names them.
SESSION_NAMES = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "Qual": "Qualifying",
    "SS": "Sprint Qualifying",
    "SR": "Sprint",
    "Race": "Race",
}

RESULTS = "Results"
RUNNING_ORDER = "Running Order"
ENTRY_LIST = "Entry List"


def series_path(key: str) -> Optional[str]:
    entry = RACING_SERIES.get(key)
    return entry[0] if entry else None


def series_name(key: str) -> str:
    entry = RACING_SERIES.get(key)
    return entry[1] if entry else key


def series_full_name(key: str) -> str:
    entry = RACING_SERIES.get(key)
    return entry[2] if entry else key


def has_constructors(key: str) -> bool:
    """Formula 1: a constructors' championship, and a weekend of sessions before the race."""
    entry = RACING_SERIES.get(key)
    return bool(entry and entry[3])


has_sessions = has_constructors


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dicts(value: Any) -> List[Dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def utc_iso(value: Any) -> str:
    """ESPN's "2026-11-08T17:00Z" as "2026-11-08T17:00:00Z", the form the shared grid uses.
    Anything that isn't a date is empty."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def race_competition(event: Dict[str, Any]) -> Dict[str, Any]:
    """The race itself among an event's competitions: the one typed Race, else the last."""
    comps = _dicts(_dict(event).get("competitions"))
    for comp in comps:
        if _dict(comp.get("type")).get("abbreviation") == "Race":
            return comp
    return comps[-1] if comps else {}


def _status(comp: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """The race's status, or the event's when the race has none."""
    status = _dict(_dict(comp.get("status")).get("type"))
    return status or _dict(_dict(event.get("status")).get("type"))


def _state(status: Dict[str, Any]) -> str:
    return status.get("state") or "pre"


def _completed(status: Dict[str, Any]) -> bool:
    return _state(status) == "post" and status.get("completed") is True


def _ordered(competitors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """By finishing or running order; anyone without one after, in ESPN's order."""
    def key(pair):
        index, c = pair
        order = c.get("order")
        return (order if isinstance(order, int) else 10 ** 6, index)
    return [c for _, c in sorted(enumerate(competitors), key=key)]


def _driver(competitor: Dict[str, Any]) -> Dict[str, str]:
    athlete = _dict(competitor.get("athlete"))
    return {
        "driver": athlete.get("displayName") or athlete.get("fullName") or "Unknown driver",
        "nationality": _dict(athlete.get("flag")).get("alt") or "",
    }


def _winner(comp: Dict[str, Any], status: Dict[str, Any]) -> str:
    if not _completed(status):
        return ""
    for c in _dicts(comp.get("competitors")):
        if c.get("order") == 1:
            return _driver(c)["driver"]
    return ""


def _circuit(event: Dict[str, Any], comp: Dict[str, Any]) -> str:
    return (_dict(event.get("circuit")).get("fullName")
            or _dict(comp.get("venue")).get("fullName") or "")


def session_name(comp: Dict[str, Any]) -> str:
    abbreviation = _dict(comp.get("type")).get("abbreviation")
    if not abbreviation:
        return "Race"
    return SESSION_NAMES.get(abbreviation, abbreviation)


def parse_race_event(scoreboard: Any) -> Optional[Dict[str, Any]]:
    """The scoreboard's race weekend, or None when there isn't one (the off-season).

    `competitors` are the race's field, with a position only once the race has begun: before
    then the list is who's entered, in ESPN's order, and `kind` says which it is.
    """
    events = _dicts(_dict(scoreboard).get("events"))
    if not events:
        return None
    event = events[0]
    comp = race_competition(event)
    status = _status(comp, event)
    state = _state(status)
    canceled = state == "post" and not _completed(status)

    competitors = []
    for c in _ordered(_dicts(comp.get("competitors"))):
        order = c.get("order")
        position = order if state != "pre" and isinstance(order, int) else None
        competitors.append({"position": position, **_driver(c)})

    if not competitors or canceled:
        kind = ""
    elif state == "pre":
        kind = ENTRY_LIST
    elif state == "in":
        kind = RUNNING_ORDER
    else:
        kind = RESULTS

    sessions = []
    for session in _dicts(event.get("competitions")):
        session_status = _status(session, event)
        sessions.append({
            "name": session_name(session),
            "date": utc_iso(session.get("date") or session.get("startDate")),
            "state": _state(session_status),
            "status": session_status.get("description") or "",
        })

    return {
        "id": str(event.get("id") or ""),
        "name": event.get("name") or "Race",
        "circuit": _circuit(event, comp),
        "date": utc_iso(comp.get("date") or event.get("date")),
        "state": state,
        "status": status.get("description") or "",
        "completed": _completed(status),
        "canceled": canceled,
        "broadcasts": broadcast_names(comp.get("broadcasts")),
        "kind": kind,
        "competitors": competitors if not canceled else [],
        "winner": _winner(comp, status),
        "sessions": sessions,
    }


def season_year(scoreboard: Any) -> Optional[int]:
    """The season ESPN's scoreboard says it's in, for asking for that season's races."""
    for league in _dicts(_dict(scoreboard).get("leagues")):
        year = _dict(league.get("season")).get("year")
        if isinstance(year, int):
            return year
    return None


def parse_schedule(scoreboard: Any) -> List[Dict[str, Any]]:
    """Every race of a season's scoreboard (`dates=` the year), in date order, with its winner."""
    races = []
    for event in _dicts(_dict(scoreboard).get("events")):
        comp = race_competition(event)
        status = _status(comp, event)
        races.append({
            "name": event.get("name") or "Race",
            "date": utc_iso(comp.get("date") or event.get("date")),
            "circuit": _circuit(event, comp),
            "state": _state(status),
            "status": status.get("description") or "",
            "completed": _completed(status),
            "winner": _winner(comp, status),
        })
    races.sort(key=lambda race: race["date"])
    return races


def parse_standings(body: Any) -> List[Dict[str, Any]]:
    """Championship standings: drivers, and for Formula 1 constructors too. An entry with no
    whole-number rank is left out, and a group with no entries, as the iPhone does."""
    groups = []
    for child in _dicts(_dict(body).get("children")):
        name = child.get("name") or "Standings"
        constructors = "constructor" in name.lower()
        entries = []
        for entry in _dicts(_dict(child.get("standings")).get("entries")):
            stats = {}
            for stat in _dicts(entry.get("stats")):
                if stat.get("name") and stat.get("displayValue") is not None:
                    stats.setdefault(stat["name"], stat["displayValue"])
            try:
                rank = int(stats.get("rank", ""))
            except (TypeError, ValueError):
                continue
            points = stats.get("championshipPts") or stats.get("points") or ""
            team = _dict(entry.get("team"))
            athlete = _dict(entry.get("athlete"))
            if constructors and team:
                who, nationality = team.get("displayName") or team.get("abbreviation") or "", ""
            elif athlete:
                who = athlete.get("displayName") or ""
                nationality = _dict(athlete.get("flag")).get("alt") or ""
            else:
                continue
            entries.append({"rank": rank, "name": who or "Unknown", "nationality": nationality,
                            "points": points})
        if entries:
            groups.append({"name": name, "constructors": constructors, "entries": entries})
    return groups


# ------------------------------------------------------------------ what the tables show

RACE_HEADERS = ["Pos", "Driver", "Nationality"]
ENTRY_HEADERS = ["Driver", "Nationality"]
SESSION_HEADERS = ["Session", "Starts", "Status"]
DRIVER_STANDINGS_HEADERS = ["Pos", "Driver", "Nationality", "Points"]
CONSTRUCTOR_STANDINGS_HEADERS = ["Pos", "Constructor", "Points"]


def _or_none(text: str) -> str:
    """A cell is never blank: a screen reader says "blank", which sounds like a fault."""
    return text or "Not given"


def race_rows(event: Dict[str, Any]) -> List[List[str]]:
    """The race's field under RACE_HEADERS, or ENTRY_HEADERS for an entry list."""
    rows = []
    for c in event.get("competitors") or []:
        cells = [c["driver"], _or_none(c["nationality"])]
        if event.get("kind") != ENTRY_LIST:
            cells.insert(0, str(c["position"]) if c["position"] is not None else "-")
        rows.append(cells)
    return rows


def race_headers(event: Dict[str, Any]) -> List[str]:
    return ENTRY_HEADERS if event.get("kind") == ENTRY_LIST else RACE_HEADERS


def local_when(iso: str, with_time: bool = True) -> str:
    """"Sunday, November 8, 12:00 PM" in local time, from a UTC date. Empty if there's none."""
    if not iso:
        return ""
    moment = local_schedule_datetime(iso)
    day = f"{moment.strftime('%A, %B')} {moment.day}"
    if not with_time:
        return day
    return f"{day}, {moment.strftime('%I:%M %p').lstrip('0')}"


def session_rows(event: Dict[str, Any]) -> List[List[str]]:
    return [[s["name"], _or_none(local_when(s["date"])), _or_none(s["status"])]
            for s in event.get("sessions") or []]


def race_summary(event: Dict[str, Any], series: str = "") -> str:
    """One sentence for the race: what, where, when or how it stands, and on what."""
    parts = [event["name"]]
    if event.get("circuit"):
        parts.append(event["circuit"])
    if event.get("canceled"):
        parts.append(event.get("status") or "Canceled")
    elif event.get("state") == "pre":
        when = local_when(event.get("date", ""))
        if when:
            parts.append(when)
    elif event.get("state") == "in":
        parts.append("In progress")
    else:
        parts.append(f"Won by {event['winner']}" if event.get("winner") else "Final")
    if event.get("broadcasts"):
        parts.append("On " + ", ".join(event["broadcasts"]))
    return ". ".join(parts) + "."


def schedule_headers(races: List[Dict[str, Any]]) -> List[str]:
    """A Circuit column only when ESPN names every race's: IndyCar and NASCAR name a few."""
    headers = ["Race", "Date", "Result"]
    if races and all(race.get("circuit") for race in races):
        headers.insert(1, "Circuit")
    return headers


def _result(race: Dict[str, Any]) -> str:
    if race.get("winner"):
        return f"Won by {race['winner']}"
    if race.get("state") == "in":
        return "In progress"
    if race.get("state") == "post" and not race.get("completed"):
        return race.get("status") or "Canceled"
    if race.get("state") == "post":
        return "Final"
    return "Upcoming"


def schedule_rows(races: List[Dict[str, Any]]) -> List[List[str]]:
    with_circuit = "Circuit" in schedule_headers(races)
    rows = []
    for race in races:
        cells = [race["name"], _or_none(local_when(race["date"], with_time=False)), _result(race)]
        if with_circuit:
            cells.insert(1, _or_none(race.get("circuit", "")))
        rows.append(cells)
    return rows


def current_row(items: List[Dict[str, Any]]) -> int:
    """The race or session to start on: the one on now, else the next, else the last."""
    for i, item in enumerate(items):
        if item.get("state") in ("in", "pre"):
            return i
    return max(len(items) - 1, 0)


def standings_headers(group: Dict[str, Any]) -> List[str]:
    return CONSTRUCTOR_STANDINGS_HEADERS if group.get("constructors") else DRIVER_STANDINGS_HEADERS


def standings_rows(group: Dict[str, Any]) -> List[List[str]]:
    rows = []
    for e in group.get("entries") or []:
        if group.get("constructors"):
            rows.append([str(e["rank"]), e["name"], _or_none(e["points"])])
        else:
            rows.append([str(e["rank"]), e["name"], _or_none(e["nationality"]), _or_none(e["points"])])
    return rows
