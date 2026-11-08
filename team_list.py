"""Pure: a league's list of teams, for the Teams screen and the Transactions team filter.

Every league's teams come from ESPN's team list, `/teams?limit=1000`, as on the iPhone, except
where that list can't say which teams are the league's. College football's is every team ESPN
knows, 762 across all divisions, with nothing on a team to tell them apart, and its standings are
the one request that follows the coverage setting. Men's college basketball's is every division
too, over 1,000 teams and cut off at 1,000, with Division I teams such as NJIT past the cut. College
hockey's, men's and women's, has Division III schools and programs that no longer play. All of these
come from their standings, Division I alone. Women's college basketball's list is Division I alone.

The standings still give the Teams screen its divisions and conferences and each team's record.
A team on the list and not in the standings, such as in a preseason, is still listed, under
OTHER_TEAMS, or under TEAMS_WITH_NO_GROUP if there are no standings at all. A team in the standings
and not on the list stays too, and one school under two ids is listed once, by its name.

tests/fixtures/team_list_sources.json holds both apps to which leagues come from where.
"""

# ESPN league paths whose team list is their standings'.
FROM_STANDINGS = frozenset({"football/college-football", "basketball/mens-college-basketball",
                            "hockey/mens-college-hockey", "hockey/womens-college-hockey"})

STANDINGS = "standings"
TEAM_LIST = "teams"

# The group for listed teams the standings don't have, when the standings have some.
OTHER_TEAMS = "Other teams"
# The one group when there are no standings to group by: a cup with no table, or a preseason.
TEAMS_WITH_NO_GROUP = "Teams"
# Said with the teams when the team list came and the standings, with their records, didn't.
RECORDS_UNAVAILABLE = "ESPN isn't providing records right now."


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def source(league_path):
    """Where a league's teams come from: STANDINGS or TEAM_LIST."""
    return STANDINGS if league_path in FROM_STANDINGS else TEAM_LIST


def parse_team_list(data):
    """A /teams answer as rows the Teams screen can show and open a team from, in ESPN's order.
    An entry with no name is left out, since there would be nothing to read for it."""
    sports = _dicts(_as_dict(data).get("sports"))
    leagues = _dicts(sports[0].get("leagues")) if sports else []
    rows = []
    for entry in _dicts(leagues[0].get("teams")) if leagues else []:
        team = _as_dict(entry.get("team"))
        if not team.get("displayName"):
            continue
        logo = next(iter(_dicts(team.get("logos"))), {}).get("href") or ""
        rows.append({"team_name": team["displayName"], "team_id": str(team.get("id") or ""),
                     "abbreviation": team.get("abbreviation") or "", "logo": logo,
                     "division": TEAMS_WITH_NO_GROUP})
    return rows


def with_standings(listed, standings):
    """Every team on the list or in the standings, each once. A team in the standings is its
    standings row, with its group and record. A listed team that isn't goes under OTHER_TEAMS,
    or TEAMS_WITH_NO_GROUP if the standings have nobody, and has no record. A listed team is the
    same team as a standings row if the id matches, or failing that the name: college hockey's
    list and standings have given one school two ids."""
    rows = list(standings or [])
    ids = {str(row.get("team_id")) for row in rows if row.get("team_id")}
    names = {row.get("team_name") for row in rows if row.get("team_name")}
    group = OTHER_TEAMS if rows else TEAMS_WITH_NO_GROUP
    for team in listed:
        if (team["team_id"] and team["team_id"] in ids) or team["team_name"] in names:
            continue
        rows.append({**team, "division": group})
        ids.add(team["team_id"])
        names.add(team["team_name"])
    return rows


def has_records(teams):
    """True if any of these rows has a record to show. A row from the team list alone has none,
    and showing it 0-0 would be a record it doesn't have."""
    return any("wins" in team for team in teams)
