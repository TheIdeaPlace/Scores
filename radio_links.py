"""Pure: where to listen to a game on the radio.

`radio_links.json` lists, for each league it covers, places to hear any game
(SiriusXM, a league's app) and each team's own radio: the team's listen page,
its flagship station's stream. Everything is a web page the browser opens; the
person signs in there if the service asks. Nothing is streamed or embedded here.

The file is keyed by ESPN team id within a table. College teams share one table,
since a school's radio network carries its football and its basketball.

The iPhone reads the same file (a copy, held equal by
tests/unit/test_radio_links_data.py) through `RadioLinks.swift`, and both are held
to tests/fixtures/radio_links_grid.json. Change both together.
"""

import json
from typing import Any, Dict, List, Optional

# Which table each league reads. A league not here has no radio links yet.
LEAGUE_TABLES = {
    "NFL": "NFL",
    "NBA": "NBA",
    "NHL": "NHL",
    "NCAAF": "NCAA",
    "NCAAM": "NCAA",
    "NCAAWB": "NCAA",
}


def load(path: str) -> Dict[str, Any]:
    """The links file, or an empty one when it can't be read, so a missing file
    means no links rather than a broken screen."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _table(data: Dict[str, Any], league: str) -> Dict[str, Any]:
    name = LEAGUE_TABLES.get(league)
    tables = data.get("tables") if isinstance(data, dict) else None
    table = tables.get(name) if isinstance(tables, dict) and name else None
    return table if isinstance(table, dict) else {}


def _links(entry: Any) -> List[Dict[str, str]]:
    """An entry's usable links: a label and an https address, in the file's order."""
    found = []
    for link in (entry.get("links") if isinstance(entry, dict) else None) or []:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "").strip()
        url = str(link.get("url") or "").strip()
        if label and url.startswith("https://"):
            found.append({"label": label, "url": url})
    return found


def team_entry(data: Dict[str, Any], league: str, team_id: Any) -> Optional[Dict[str, Any]]:
    teams = _table(data, league).get("teams")
    entry = teams.get(str(team_id)) if isinstance(teams, dict) and team_id not in (None, "") else None
    return entry if isinstance(entry, dict) else None


def league_options(data: Dict[str, Any], league: str) -> List[Dict[str, str]]:
    """Places that carry the whole league's games."""
    return _links(_table(data, league))


def team_options(data: Dict[str, Any], league: str, team_id: Any, team_name: str) -> List[Dict[str, str]]:
    """One team's own radio, each labelled with the team's name as the screen shows it."""
    entry = team_entry(data, league, team_id)
    name = (team_name or "").strip() or str((entry or {}).get("name") or "").strip()
    return [{"label": f"{name}: {link['label']}" if name else link["label"], "url": link["url"]}
            for link in _links(entry)]


def _unique(options: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen, kept = set(), []
    for option in options:
        if option["url"] not in seen:
            seen.add(option["url"])
            kept.append(option)
    return kept


def game_options(data: Dict[str, Any], league: str,
                 away_id: Any, away_name: str, home_id: Any, home_name: str) -> List[Dict[str, str]]:
    """Where to hear a game, nearest first: the away team's radio, the home team's,
    then the places that carry the whole league. Away first, as the row reads."""
    return _unique(team_options(data, league, away_id, away_name)
                   + team_options(data, league, home_id, home_name)
                   + league_options(data, league))


def team_listen_options(data: Dict[str, Any], league: str, team_id: Any, team_name: str) -> List[Dict[str, str]]:
    """Where to hear a team's games: its own radio, then the league-wide places."""
    return _unique(team_options(data, league, team_id, team_name) + league_options(data, league))


def covers(data: Dict[str, Any], league: str) -> bool:
    table = _table(data, league)
    return bool(_links(table)) or bool(table.get("teams"))


def directory(data: Dict[str, Any], league: str) -> List[Dict[str, Any]]:
    """Every team in a league's table, by name, with its station and links, for a
    screen that lists them all. Teams with no links are kept, so the list says what
    isn't known rather than leaving a team out."""
    teams = _table(data, league).get("teams")
    rows = []
    for team_id, entry in (teams.items() if isinstance(teams, dict) else []):
        if not isinstance(entry, dict):
            continue
        rows.append({"id": str(team_id), "name": str(entry.get("name") or team_id),
                     "station": str(entry.get("station") or ""), "links": _links(entry)})
    return sorted(rows, key=lambda row: row["name"].lower())


def competitors(competition: Any):
    """(away id, away name, home id, home name) from an ESPN competition, with the
    team's full name, as the iPhone names it, or "" for parts that are missing."""
    found = {"away": ("", ""), "home": ("", "")}
    for competitor in (competition.get("competitors") if isinstance(competition, dict) else None) or []:
        if not isinstance(competitor, dict) or competitor.get("homeAway") not in found:
            continue
        team = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
        name = team.get("displayName") or team.get("shortDisplayName") or team.get("name") or ""
        found[competitor["homeAway"]] = (str(team.get("id") or ""), str(name))
    return found["away"] + found["home"]


def options_for_competition(data: Dict[str, Any], league: str, competition: Any) -> List[Dict[str, str]]:
    away_id, away_name, home_id, home_name = competitors(competition)
    return game_options(data, league, away_id, away_name, home_id, home_name)
