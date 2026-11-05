"""Turn ESPN's `boxscore` block into the tables the Boxscore dialog shows.

No PyQt import, so it can be tested against real ESPN payloads on any platform.
ESPN's shape differs by sport, and each of these has broken the display before:

- Player groups are named by `type` (baseball), `name` plus `text` (football,
  hockey) or nothing at all (basketball).
- Column headers are in `names` (baseball, basketball) or only `labels`
  (football, hockey).
- `active` is not "played". In basketball it means on the floor when the game
  ended, in baseball a pitcher who has finished is `active: false`, so it must
  never be used to hide a player.
- A player who did not play has an empty `stats` list, and some carry only
  `shortName` rather than `displayName`.
- Team statistics are flat `{name, label, displayValue}` rows everywhere except
  baseball, which nests `{displayName, stats: [...]}` per category.
- College hockey sends empty groups for both teams: there is nothing to show.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

DID_NOT_PLAY = "Did not play"
TOTALS = "Totals"

# Where ESPN's own group name isn't what a person would call it.
_GROUP_TITLES = {"defensive": "Defense", "defenses": "Defense"}


@dataclass
class BoxTable:
    """One tab of the dialog: a titled table. Rows may be shorter than headers
    when a player did not play, so a list view doesn't read a row of blanks."""
    title: str
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)


def _group_title(group: Dict[str, Any]) -> str:
    raw = group.get("type") or group.get("name")
    if not raw:
        return "Players"  # basketball: one unnamed group holding everybody
    if raw in _GROUP_TITLES:
        return _GROUP_TITLES[raw]
    # kickReturns -> Kick Returns
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw).title()


def _athlete_name(athlete: Dict[str, Any]) -> str:
    info = athlete.get("athlete") or {}
    return (info.get("displayName") or info.get("shortName") or "Unknown player").strip()


def _player_table(team_name: str, group: Dict[str, Any]) -> "BoxTable | None":
    athletes = group.get("athletes") or []
    stat_headers = list(group.get("names") or group.get("labels") or [])
    if not athletes or not stat_headers:
        return None
    positions = [((a.get("athlete") or {}).get("position") or {}).get("abbreviation") or ""
                 for a in athletes]
    # Football payloads carry no positions: don't offer a column of blanks.
    has_position = any(positions)
    headers = ["Player"] + (["Pos"] if has_position else []) + stat_headers
    lead_columns = 2 if has_position else 1
    rows = []
    for athlete, position in zip(athletes, positions):
        row = [_athlete_name(athlete)] + ([position] if has_position else [])
        stats = athlete.get("stats") or []
        row.extend(str(s) for s in stats) if stats else row.append(DID_NOT_PLAY)
        rows.append(row)
    totals = group.get("totals") or []
    if any(totals):
        rows.append([TOTALS] + [""] * (lead_columns - 1) + [str(t) for t in totals])
    return BoxTable(f"{team_name} {_group_title(group)}", headers, rows)


def _stat_label(stat: Dict[str, Any]) -> str:
    return stat.get("label") or stat.get("displayName") or stat.get("name") or ""


def _stat_value(stat: Dict[str, Any]) -> str:
    value = stat.get("displayValue")
    return str(value if value is not None else stat.get("value", ""))


def _comparison_rows(per_team: List[List[Dict[str, Any]]]) -> List[List[str]]:
    """One row per statistic, a value per team, in the first team's order.
    ESPN repeats some rows (NFL lists interceptions twice), so each name is kept once."""
    order: List[str] = []
    labels: Dict[str, str] = {}
    for stats in per_team:
        for stat in stats:
            key = stat.get("name") or _stat_label(stat)
            if key and key not in labels:
                order.append(key)
                labels[key] = _stat_label(stat)
    rows = []
    for key in order:
        row = [labels[key]]
        for stats in per_team:
            match = next((s for s in stats if (s.get("name") or _stat_label(s)) == key), None)
            row.append(_stat_value(match) if match else "")
        rows.append(row)
    return rows


def _team_tables(teams: List[Dict[str, Any]]) -> List[BoxTable]:
    names = [(t.get("team") or {}).get("displayName") or "Team" for t in teams]
    stats_by_team = [t.get("statistics") or [] for t in teams]
    if not any(stats_by_team):
        return []
    headers = ["Statistic"] + names
    nested = any(entry.get("stats") for stats in stats_by_team for entry in stats)
    if not nested:
        return [BoxTable("Team Stats", headers, _comparison_rows(stats_by_team))]
    # Baseball: a comparison per category (Batting, Pitching, Fielding).
    tables = []
    categories: List[str] = []
    for stats in stats_by_team:
        for entry in stats:
            title = entry.get("displayName") or entry.get("name") or "Team"
            if title not in categories:
                categories.append(title)
    for category in categories:
        per_team = []
        for stats in stats_by_team:
            entry = next((e for e in stats
                          if (e.get("displayName") or e.get("name") or "Team") == category), {})
            per_team.append(entry.get("stats") or [])
        rows = _comparison_rows(per_team)
        if rows:
            tables.append(BoxTable(f"Team {category}", headers, rows))
    return tables


def build_box_tables(boxscore: Any) -> List[BoxTable]:
    """Every table worth showing, player tables first. Empty when ESPN has no
    box score for the game: scheduled, postponed, or all of college hockey."""
    if not isinstance(boxscore, dict):
        return []
    tables: List[BoxTable] = []
    for team_players in boxscore.get("players") or []:
        team_name = (team_players.get("team") or {}).get("displayName") or "Team"
        for group in team_players.get("statistics") or []:
            table = _player_table(team_name, group)
            if table:
                tables.append(table)
    tables.extend(_team_tables(boxscore.get("teams") or []))
    return tables
