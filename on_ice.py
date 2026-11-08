"""Who is on the ice right now, from an NHL game's `summary`.

No PyQt import, so it can be tested against real ESPN payloads on any platform.
The iPhone's twin is `Models/OnIce.swift`; both are held to
tests/fixtures/on_ice_grid.json. Change both together.

ESPN's `onIce` block holds one entry per team:
`{"teamId": "13", "entries": [{"athleteid": "3042095", "whereabouts": {"name":
"ROSTER_WHEREABOUTS_IN_PLAY"}}, ...]}`. It carries ids only. The names, jersey
numbers and positions come from the same summary's box score, whose player groups
are `forwards`, `defenses` and `goalies`, so no second request is needed.

- The block is in every NHL summary, a finished game's too, where it is the last
  shift of the game. It is shown only while the game is being played, and not in an
  intermission (STATUS_END_PERIOD), when it is the period's last shift.
- College hockey summaries have no `onIce` block at all (checked 2026-11-07).
- An id the box score doesn't know is left out rather than read as "Unknown player".
"""

from typing import Any, Dict, List

IN_PLAY = "ROSTER_WHEREABOUTS_IN_PLAY"
INTERMISSION = "STATUS_END_PERIOD"

# Box score group name, then position abbreviation, to the group a player is listed in.
_GROUP_BY_BOX = {"forwards": "forward", "defenses": "defense", "goalies": "goalie"}
_GROUP_BY_POSITION = {"C": "forward", "LW": "forward", "RW": "forward", "F": "forward",
                      "W": "forward", "D": "defense", "G": "goalie"}
_GROUP_ORDER = {"forward": 0, "defense": 1, "goalie": 2}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _competition(summary: Any) -> Dict[str, Any]:
    competitions = _list(_dict(_dict(summary).get("header")).get("competitions"))
    return _dict(competitions[0]) if competitions else {}


def is_live(summary: Any) -> bool:
    """True while the game is being played: state "in", past period 0 (a delay), and not
    an intermission, when the block still holds the period's last shift."""
    status = _dict(_competition(summary).get("status"))
    status_type = _dict(status.get("type"))
    state = _text(status_type.get("state"))
    period = status.get("period")
    return (state == "in" and not (isinstance(period, int) and period == 0)
            and _text(status_type.get("name")) != INTERMISSION)


def _box_players(summary: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Team id to athlete id to the player as shown."""
    teams: Dict[str, Dict[str, Dict[str, str]]] = {}
    for team_block in _list(_dict(summary.get("boxscore")).get("players")):
        team_block = _dict(team_block)
        team_id = str(_dict(team_block.get("team")).get("id") or "")
        players = teams.setdefault(team_id, {})
        for group in _list(team_block.get("statistics")):
            group = _dict(group)
            box_group = _GROUP_BY_BOX.get(_text(group.get("name")), "")
            for row in _list(group.get("athletes")):
                athlete = _dict(_dict(row).get("athlete"))
                athlete_id = str(athlete.get("id") or "")
                name = _text(athlete.get("displayName")) or _text(athlete.get("shortName"))
                if not athlete_id or not name or athlete_id in players:
                    continue
                position = _dict(athlete.get("position"))
                abbreviation = _text(position.get("abbreviation"))
                players[athlete_id] = {
                    "id": athlete_id,
                    "name": name,
                    "last_name": _text(athlete.get("lastName")) or name,
                    "jersey": _text(athlete.get("jersey")),
                    "position": _text(position.get("displayName")) or _text(position.get("name")),
                    "group": box_group or _GROUP_BY_POSITION.get(abbreviation, ""),
                }
    return teams


def _header_teams(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """The two teams from the header, away first."""
    teams = []
    for competitor in _list(_competition(summary).get("competitors")):
        competitor = _dict(competitor)
        team = _dict(competitor.get("team"))
        team_id = str(team.get("id") or "")
        name = _text(team.get("displayName")) or _text(team.get("name")) or _text(team.get("abbreviation"))
        if not team_id or not name:
            continue
        teams.append({
            "id": team_id,
            "name": name,
            "short_name": _text(team.get("shortDisplayName")) or _text(team.get("name")) or name,
            "home_away": _text(competitor.get("homeAway")),
        })
    teams.sort(key=lambda t: 0 if t["home_away"] == "away" else 1)
    return teams


def lineup(summary: Any) -> List[Dict[str, Any]]:
    """Each team's players on the ice, away team first: forwards, then defense, then
    the goalie. Empty when the game isn't being played or ESPN says nothing."""
    if not isinstance(summary, dict) or not is_live(summary):
        return []
    on_ice = {}
    for block in _list(summary.get("onIce")):
        block = _dict(block)
        team_id = str(block.get("teamId") or "")
        if team_id:
            on_ice[team_id] = _list(block.get("entries"))
    if not on_ice:
        return []

    box = _box_players(summary)
    result = []
    for team in _header_teams(summary):
        roster = box.get(team["id"], {})
        players, seen = [], set()
        for entry in on_ice.get(team["id"], []):
            entry = _dict(entry)
            where = _text(_dict(entry.get("whereabouts")).get("name"))
            athlete_id = str(entry.get("athleteid") or "")
            if (where and where != IN_PLAY) or athlete_id in seen or athlete_id not in roster:
                continue
            seen.add(athlete_id)
            players.append(dict(roster[athlete_id]))
        if not players:
            continue
        players.sort(key=lambda p: _GROUP_ORDER.get(p["group"], 3))  # stable: ESPN's order within a group
        result.append({**team, "players": players})
    return result


def player_text(player: Dict[str, Any]) -> str:
    """One player as read out: "Oliver Bjorkstrand, number 28, Right Wing"."""
    parts = [player.get("name") or ""]
    if player.get("jersey"):
        parts.append(f"number {player['jersey']}")
    if player.get("position"):
        parts.append(player["position"])
    return ", ".join(p for p in parts if p)


def team_heading(team: Dict[str, Any]) -> str:
    """A team's heading: "New York Rangers, 6 on the ice"."""
    return f"{team['name']}, {len(team['players'])} on the ice"


def summary_line(teams: List[Dict[str, Any]]) -> str:
    """The one row that stands for them all, by last name:
    "On the ice: Rangers: Bjorkstrand, Zibanejad; Kraken: Beniers, Dunn"."""
    if not teams:
        return ""
    sides = [f"{t['short_name']}: " + ", ".join(p["last_name"] for p in t["players"]) for t in teams]
    return "On the ice: " + "; ".join(sides)
