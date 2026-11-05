"""Pure: ESPN's soccer answers to what the screens show. No PyQt and no requests.

Soccer differs from the leagues around it. A team's record is wins, draws, losses, points rank the
table rather than a percentage, and ESPN's rank holds the tiebreakers, so that's what puts a table
in order. The shape of /standings differs too: a league has one group named for its season, MLS has two
conferences, a cup has its league phase (or its groups, as the Champions League had until 2023-24),
and the CONCACAF Champions Cup is all knockout and has no groups at all.

Leaders come from the core API, as on the iPhone: its entries are references, so a name takes a
request. espn_api makes those. What's here is which lists to show and how their numbers read.

The iPhone's twins are SoccerTableRow in Standings.swift and coreLeaderLists in ESPNAPIService.swift.
tests/fixtures/soccer_grid.json holds both apps to the same rows and lists.
"""
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
TEAMS_WITH_NO_GROUP = "Teams"


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


def parse_team_list(data):
    """A /teams answer as rows the Teams dialog can show and open a team from."""
    sports = _dicts(_as_dict(data).get("sports"))
    leagues = _dicts(sports[0].get("leagues")) if sports else []
    rows = []
    for entry in _dicts(leagues[0].get("teams")) if leagues else []:
        team = _as_dict(entry.get("team"))
        if team.get("displayName"):
            rows.append({"team_name": team["displayName"], "team_id": str(team.get("id") or ""),
                         "abbreviation": team.get("abbreviation") or "", "division": TEAMS_WITH_NO_GROUP})
    return rows


def no_table_message(league):
    """Asked for a table and ESPN has none. It holds for a league too, if that ever happens."""
    return f"ESPN has no league table for {league} right now. A knockout competition doesn't have one."


def _secure(reference):
    """The core API's references say http://, and it answers on https:// too."""
    if not isinstance(reference, str):
        return ""
    return "https://" + reference[len("http://"):] if reference.startswith("http://") else reference


def core_leader_lists(data):
    """A core API leaders answer as the lists to show, with references where the names go:
    [{"title", "leaders": [{"athlete", "team", "value"}]}], in ESPN's order.

    A list where everyone is on nothing isn't a list of leaders. A list that repeats an earlier one
    is left out: goalsLeaders and goals are both called Goals, with the same players in the same
    order, and reading the same once their text is a number. A list that differs in any row stays."""
    lists = []
    for category in _dicts(_as_dict(data).get("categories")):
        key = category.get("name") or "unknown"
        leaders = _dicts(category.get("leaders"))
        if not any(leader.get("value") for leader in leaders):
            continue
        rows = [{"athlete": _secure(_as_dict(leader.get("athlete")).get("$ref")),
                 "team": _secure(_as_dict(leader.get("team")).get("$ref")),
                 "value": leader_display_value(key, leader.get("value"), leader.get("displayValue"))
                 or NOTHING_TO_SHOW}
                for leader in leaders]
        title = category.get("displayName") or key.title()
        if not any(earlier["title"] == title and earlier["leaders"] == rows for earlier in lists):
            lists.append({"title": title, "leaders": rows})
    return lists
