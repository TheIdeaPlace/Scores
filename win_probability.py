"""Win probability over a game, from an MLB `summary`.

No PyQt import, so it can be tested against real ESPN payloads on any platform.
The iPhone's twin is `Models/WinProbability.swift`; the percent and the leader
text are held to tests/fixtures/win_probability_grid.json on both. Change both
together.

ESPN's `winprobability` block is a list, one entry per play, oldest first:
`{"homeWinPercentage": 0.698, "tiePercentage": 0.0, "playId": "4018170910001990057"}`.

- `homeWinPercentage` is a fraction, 0 to 1, after that play. The away team's
  chance is what's left; baseball has no ties, so `tiePercentage` is always 0.
- Each `playId` is the id of a play in the same summary's `plays`, which gives the
  play's text, inning and score, so no second request is needed. An entry whose
  play isn't there is still a point on the line, shown without its text.
- There is no entry before the first pitch: the first change is from the first play.
- A percent is rounded half up, floor(fraction * 100 + 0.5), the same on both apps,
  and the away percent is 100 minus the home one, so the two always add to 100.
"""

import math
from typing import Any, Dict, List, Optional

TOP_SWINGS = 5


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def percent(fraction: float) -> int:
    """A fraction from 0 to 1 as a whole percent, rounded half up and kept in 0 to 100."""
    return max(0, min(100, math.floor(fraction * 100 + 0.5)))


def leader_text(home_fraction: float, home_name: str, away_name: str) -> str:
    """Who is more likely to win, and how likely: "Mets 70%". "Even, 50%" when neither is."""
    home = percent(home_fraction)
    away = 100 - home
    if home > away:
        return f"{home_name} {home}%"
    if away > home:
        return f"{away_name} {away}%"
    return "Even, 50%"


def entries(summary: Any) -> List[Dict[str, Any]]:
    """The points on the line, oldest first: {"play_id", "home"}. An entry without a
    number for the home team is left out, as the iPhone's decoding leaves it out."""
    points = []
    for entry in _list(_dict(summary).get("winprobability")):
        entry = _dict(entry)
        home = _number(entry.get("homeWinPercentage"))
        if home is None:
            continue
        play_id = entry.get("playId")
        points.append({"play_id": str(play_id) if play_id is not None else "", "home": home})
    return points


def team_names(summary: Any) -> Dict[str, str]:
    """{"home": "Nationals", "away": "Mets"}: the short name a screen reader says well."""
    names = {"home": "Home", "away": "Away"}
    competitions = _list(_dict(_dict(summary).get("header")).get("competitions"))
    competition = _dict(competitions[0]) if competitions else {}
    for competitor in _list(competition.get("competitors")):
        competitor = _dict(competitor)
        side = competitor.get("homeAway")
        if side not in names:
            continue
        team = _dict(competitor.get("team"))
        name = (_text(team.get("name")) or _text(team.get("shortDisplayName"))
                or _text(team.get("abbreviation")) or _text(team.get("displayName")))
        if name:
            names[side] = name
    return names


def summary_line(summary: Any) -> str:
    """The game details row: "Win probability: Mets 100%". Empty with no entries."""
    points = entries(summary)
    if not points:
        return ""
    names = team_names(summary)
    return f"Win probability: {leader_text(points[-1]['home'], names['home'], names['away'])}"


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _inning(period: Dict[str, Any]) -> str:
    number = period.get("number")
    half = _text(period.get("type"))
    if isinstance(number, int) and not isinstance(number, bool) and number > 0:
        return f"{half} {_ordinal(number)}".strip()
    return _text(period.get("displayValue")) or half


def _change(delta: Optional[int], names: Dict[str, str]) -> str:
    """Who gained, in percentage points: "Nationals +3". Empty for the first play."""
    if delta is None:
        return ""
    if delta > 0:
        return f"{names['home']} +{delta}"
    if delta < 0:
        return f"{names['away']} +{-delta}"
    return "No change"


def play_rows(summary: Any) -> List[Dict[str, Any]]:
    """Every point on the line, oldest first, with its play where the summary has it:
    {"number", "inning", "half_key", "play", "score", "away", "home", "delta", "change"}.
    `number` counts from 1. `delta` is the home team's gain in points since the play
    before, None for the first."""
    names = team_names(summary)
    plays = {}
    for play in _list(_dict(summary).get("plays")):
        play = _dict(play)
        if play.get("id") is not None:
            plays[str(play["id"])] = play
    rows = []
    previous = None
    for point in entries(summary):
        play = plays.get(point["play_id"], {})
        period = _dict(play.get("period"))
        home = percent(point["home"])
        delta = None if previous is None else home - previous
        previous = home
        away_score, home_score = play.get("awayScore"), play.get("homeScore")
        score = (f"{names['away']} {away_score}, {names['home']} {home_score}"
                 if _number(away_score) is not None and _number(home_score) is not None else "")
        rows.append({
            "number": len(rows) + 1,
            "inning": _inning(period),
            "half_key": (period.get("number"), _text(period.get("type"))) if period else None,
            "play": _text(play.get("text")),
            "score": score,
            "away": 100 - home,
            "home": home,
            "delta": delta,
            "change": _change(delta, names),
        })
    return rows


def by_inning(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The last point of each half inning: where things stood as each half ended, or
    stand now in the half being played. Rows without an inning are left out."""
    last: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for row in rows:
        key = row.get("half_key")
        if not key or not row.get("inning"):
            continue
        if key not in last:
            order.append(key)
        last[key] = row
    return [last[key] for key in order]


def biggest_swings(rows: List[Dict[str, Any]], count: int = TOP_SWINGS) -> List[Dict[str, Any]]:
    """The plays that moved the chances most, biggest first, earlier first on a tie.
    A play that moved nothing is never a swing."""
    moved = [(i, row) for i, row in enumerate(rows) if row.get("delta")]
    moved.sort(key=lambda pair: (-abs(pair[1]["delta"]), pair[0]))
    return [row for _i, row in moved[:count]]


def headers(names: Dict[str, str]) -> List[str]:
    """The table's columns, away team before home as in a score."""
    return ["Inning", "Play", "Score", f"{names['away']} chance", f"{names['home']} chance", "Change"]


def table_row(row: Dict[str, Any]) -> List[str]:
    """A row for the table. A play the summary doesn't have is named by its number."""
    return [row["inning"], row["play"] or f"Play {row['number']}", row["score"],
            f"{row['away']}%", f"{row['home']}%", row["change"]]


def overview(summary: Any) -> str:
    """The sentence above the tables: where it stands and the biggest swing."""
    rows = play_rows(summary)
    if not rows:
        return "ESPN has no win probability for this game."
    names = team_names(summary)
    last = rows[-1]
    text = f"{names['away']} {last['away']}%, {names['home']} {last['home']}% after the last play."
    swings = biggest_swings(rows, 1)
    if swings:
        swing = swings[0]
        where = ", ".join(part for part in (swing["inning"], swing["play"].rstrip(".")) if part)
        text += f" Biggest swing: {swing['change']}" + (f", {where}." if where else ".")
    return text
