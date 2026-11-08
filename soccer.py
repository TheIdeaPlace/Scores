"""Pure: ESPN's soccer answers to what the screens show. No PyQt and no requests.

Soccer differs from the leagues around it. A team's record is wins, draws, losses, points rank the
table rather than a percentage, and ESPN's rank holds the tiebreakers, so that's what puts a table
in order. The shape of /standings differs too: a league has one group named for its season, MLS has two
conferences, a cup has its league phase (or its groups, as the Champions League had until 2023-24),
and the CONCACAF Champions Cup is all knockout and has no groups at all.

Leaders come from /leaders, as on the iPhone, with names and teams inside the answer. espn_api asks;
what's here is which season type to ask for, which lists to show, how their numbers read and what
the season is called.

The iPhone's twins are SoccerTableRow in Standings.swift and soccerLeaderCategories and
soccerLeadersSeasonTypes in ESPNAPIService.swift. tests/fixtures/soccer_grid.json holds both apps to
the same rows, lists and season types.
"""
from datetime import datetime, timezone

from game_labels import leader_display_value

# espn_api.LEAGUES names these, and tests/unit/replay/test_soccer.py holds the two together. The
# World Cups are soccer too, but have their own dialog.
SOCCER_LEAGUES = frozenset({"EPL", "MLS", "NWSL", "La Liga", "Bundesliga", "Serie A", "Ligue 1",
                            "UCL", "UEL", "Liga MX", "CONCACAF"})

# The World Cup dialog's columns, plus the goals behind the difference, and where a place leads.
SOCCER_TABLE_HEADERS = ["Pos", "Team", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts", "Status"]
SOCCER_TEAM_HEADERS = ["Team", "Played", "Wins", "Draws", "Losses", "Points"]
# A cup with no table has teams and nothing to say about them yet.
TEAM_NAME_ONLY_HEADERS = ["Team"]
# A blank cell would be silent in a screen reader.
NOTHING_TO_SHOW = "N/A"
NAME_UNAVAILABLE = "Name not available"


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _stat_number(stat):
    """A stat's number, from its text if the number is missing. ESPN can send a null."""
    value = stat.get("value")
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(stat.get("displayValue")))
    except ValueError:
        return 0


def _table_row(entry, group, season, position):
    team = _as_dict(entry.get("team"))
    stats = {stat["name"]: stat for stat in _dicts(entry.get("stats")) if isinstance(stat.get("name"), str)}

    def number(name):
        return _stat_number(_as_dict(stats.get(name)))

    wins, draws, losses = number("wins"), number("ties"), number("losses")
    difference = number("pointDifferential")
    return {
        "team_name": team.get("displayName") or "Unknown",
        "team_id": str(team.get("id") or ""),
        "abbreviation": team.get("abbreviation") or "",
        # Where ESPN puts this team, with its tiebreakers. If there's no rank, its place in the answer.
        "table_rank": number("rank") or position,
        "games_played": number("gamesPlayed"),
        "wins": wins,
        "ties": draws,
        "losses": losses,
        "goals_for": number("pointsFor"),
        "goals_against": number("pointsAgainst"),
        "goal_difference": difference,
        "goal_difference_text": _as_dict(stats.get("pointDifferential")).get("displayValue")
                                or (f"+{difference}" if difference > 0 else str(difference)),
        "points": number("points"),
        "record": f"{wins}-{draws}-{losses}",
        # ESPN's can end in a stray tab.
        "note": str(_as_dict(entry.get("note")).get("description") or "").strip(),
        "division": group,
        "season": season or "",
    }


def parse_soccer_standings(data):
    """Every team in a soccer /standings answer, group by group, each in the order of ESPN's rank.
    The answer's own order won't do: in MLS and a cup's groups, it reads 4th, 8th, 3rd. A competition
    with no table answers with no groups, so this is empty: that isn't a failure."""
    rows = []

    def walk(node, group):
        name = node.get("name") or group
        standings = _as_dict(node.get("standings"))
        table = [_table_row(entry, name, standings.get("seasonDisplayName"), position)
                 for position, entry in enumerate(_dicts(standings.get("entries")), 1)]
        rows.extend(sorted(table, key=lambda row: row["table_rank"]))
        for child in _dicts(node.get("children")):
            walk(child, name)

    walk(_as_dict(data), "League")
    return rows


def soccer_table_cells(position, team):
    """A team's row for SOCCER_TABLE_HEADERS. `position` is its place in the list, which ESPN's
    rank is unless it's missing."""
    return [str(team.get("table_rank") or position),
            team.get("team_name") or team.get("name", ""),
            str(team.get("games_played", "")),
            str(team.get("wins", "")),
            str(team.get("ties", "")),
            str(team.get("losses", "")),
            str(team.get("goals_for", "")),
            str(team.get("goals_against", "")),
            team.get("goal_difference_text") or "",
            str(team.get("points", "")),
            team.get("note") or NOTHING_TO_SHOW]


def soccer_teams_table(teams):
    """(headers, teams in order, a row for each) for the Teams dialog. In table order where they
    have one. A cup's team list has no records, so it's by name, and names are all it can show."""
    if all("table_rank" in team for team in teams):
        ordered = sorted(teams, key=lambda team: team["table_rank"])
        return SOCCER_TEAM_HEADERS, ordered, [
            [team.get("team_name", "Unknown Team"), str(team.get("games_played", "")), str(team.get("wins", "")),
             str(team.get("ties", "")), str(team.get("losses", "")), str(team.get("points", ""))]
            for team in ordered]
    ordered = sorted(teams, key=lambda team: team.get("team_name", ""))
    return TEAM_NAME_ONLY_HEADERS, ordered, [[team.get("team_name", "Unknown Team")] for team in ordered]


def no_table_message(league):
    """Asked for a table and ESPN has none. It holds for a league too, if that ever happens."""
    return f"ESPN has no league table for {league} right now. A knockout competition doesn't have one."


# A league season's leaders are all under type 1, through its knockouts: 2 and 3 are a 404 for the
# big European leagues, and the type ESPN calls current is a playoff round, such as NWSL's
# "Playoffs - Quarterfinals", with the wrong numbers or none. The type 1 of a cup is named for its
# first stage ("League Phase", "Round One") and holds the whole competition anyway.
LEADERS_SEASON_TYPE = 1
# A season of two torneos, each with leaders of its own: the Apertura is type 1, and the Clausura's
# number changes from season to season (8 in 2025, with play-in rounds before the quarterfinals, and
# 5 in 2026), so it is found by name.
TORNEO_LEAGUES = frozenset({"Liga MX"})
CLAUSURA_NAME = "Torneo Clausura"
# Before any date: where an Apertura with no start date to read goes.
SEASON_BEGINS = datetime.min.replace(tzinfo=timezone.utc)


def _start(season_type):
    """When a core season type starts, as an aware datetime, or None. ESPN writes 2027-01-01T05:00Z."""
    text = season_type.get("startDate")
    if not isinstance(text, str):
        return None
    try:
        start = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return start if start.tzinfo else start.replace(tzinfo=timezone.utc)


def _type_id(season_type):
    try:
        return int(str(season_type.get("id")))
    except ValueError:
        return None


def leaders_season_types(league, season, now):
    """The season types to ask for a season's leaders, most recent first. `season` is the core API's
    answer for that season, with its types inside, and `now` an aware datetime.

    Every league but Liga MX has one: type 1. Liga MX has the torneos that have started by `now`,
    by their dates, never by the type ESPN calls current, which names playoff rounds (and dates its
    Clausura playoffs in the November before). So from January it's the Clausura and then the
    Apertura before it, and before the season's Apertura starts it's nothing: the season before.
    If ESPN lists no torneo at all, the Apertura is all there is to ask for, and an Apertura with
    no date to read is taken as started, since a season begins with it. A Clausura with none isn't."""
    if league not in TORNEO_LEAGUES:
        return [LEADERS_SEASON_TYPE]
    torneos = []
    for season_type in _dicts(_as_dict(_as_dict(season).get("types")).get("items")):
        type_id = _type_id(season_type)
        if type_id is None:
            continue
        start = _start(season_type)
        if type_id == LEADERS_SEASON_TYPE:
            torneos.append((start or SEASON_BEGINS, type_id))
        elif season_type.get("name") == CLAUSURA_NAME and start:
            torneos.append((start, type_id))
    if not torneos:
        return [LEADERS_SEASON_TYPE]
    started = sorted(((start, type_id) for start, type_id in torneos if start <= now), reverse=True)
    return [type_id for _, type_id in started]


def soccer_leader_lists(data):
    """A /leaders answer as the lists to show, in ESPN's order:
    [{"title", "key", "stats": [{"player_name", "team", "value", "stat_name"}]}].

    A list where everyone is on nothing isn't a list of leaders. A list that repeats an earlier one
    is left out: goalsLeaders and goals are both called Goals, with the same players in the same
    order, and read the same once their text is a number. A list that differs in any row stays.
    A row whose name is missing says so and keeps its place; a missing team is blank, which the
    table reads as N/A."""
    lists = []
    for category in _dicts(_as_dict(_as_dict(data).get("leaders")).get("categories")):
        key = category.get("name") or "unknown"
        leaders = _dicts(category.get("leaders"))
        if not any(leader.get("value") for leader in leaders):
            continue
        title = category.get("displayName") or key.title()
        stats = []
        for leader in leaders:
            athlete, team = _as_dict(leader.get("athlete")), _as_dict(leader.get("team"))
            stats.append({
                "player_name": athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName")
                or NAME_UNAVAILABLE,
                "team": team.get("abbreviation") or team.get("displayName") or "",
                "value": leader_display_value(key, leader.get("value"), leader.get("displayValue")) or NOTHING_TO_SHOW,
                "stat_name": title,
            })
        if not any(earlier["category"] == title and earlier["stats"] == stats for earlier in lists):
            # `key` is ESPN's name for the category, which stat_glossary finds its definition by.
            lists.append({"category": title, "key": key, "stats": stats})
    return lists


def soccer_leaders_season(data, league, year):
    """What the leaders are from: ESPN's name for the season, such as "2026-27 English Premier
    League", and for Liga MX the torneo too, "2026-27 Liga BBVA MX Torneo Apertura". Other leagues'
    type names would mislead: a cup's type 1 is named for its first stage and holds the whole
    competition. With no name, the year still says which season it is."""
    requested = _as_dict(_as_dict(data).get("requestedSeason"))
    name = requested.get("displayName") if isinstance(requested.get("displayName"), str) else ""
    name = name or str(year)
    torneo = _as_dict(requested.get("type")).get("name")
    if league in TORNEO_LEAGUES and isinstance(torneo, str) and torneo:
        return f"{name} {torneo}"
    return name
