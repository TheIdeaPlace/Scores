"""Pure: ESPN's statistics/byteam to the lists the Statistics dialog shows, best first.

The payload is by column. Its top-level `categories` name the stats, each category once per
split, and each team's own `categories` carry `totals` (what to show), `values` (what to rank by)
and `ranks` in that order. A category comes as the team's own numbers (splitId 0) and, in football
and basketball, what its opponents did against it (splitId 900).

ESPN's `ranks` aren't used. They're blank for NBA and NHL points and goals, and the NFL's
totalGiveaways rank 1 is the team with the most giveaways. Ranking the values here also means the
apps agree: the iPhone does the same in ESPNAPIService.swift, and TeamStatCatalog.swift holds the
same table, with tests/fixtures/team_stat_directions.json checking both.
"""

OPPONENT_SPLIT = "900"
GAMES_PLAYED = {"gamesPlayed", "games"}

# The team's own stats where less is better, by the sport in the league's path. The opponent's
# version of a stat goes the other way: a team wants its opponents to score less, and to turn it
# over more. A stat nobody has listed here reads highest first, and the validator warns about a
# stat it doesn't know.
LOW_IS_GOOD = {
    "baseball": {
        "batting.strikeouts",
        "pitching.losses", "pitching.ERA", "pitching.hits", "pitching.earnedRuns", "pitching.homeRuns",
        "pitching.walks", "pitching.opponentAvg", "pitching.WHIP",
        "fielding.errors",
    },
    "football": {
        "general.fumblesLost",
        "passing.interceptions", "passing.sacks", "passing.sackYardsLost",
        "rushing.rushingFumbles", "rushing.rushingFumblesLost",
        "receiving.receivingFumbles", "receiving.receivingFumblesLost",
        "miscellaneous.totalPenalties", "miscellaneous.totalPenaltyYards", "miscellaneous.totalGiveaways",
        "punting.puntsBlocked", "punting.touchbacks", "punting.puntReturns", "punting.puntReturnYards",
        "punting.avgPuntReturnYards",
    },
    "basketball": {
        "general.fouls", "general.avgFouls", "general.technicalFouls",
        "offensive.turnovers", "offensive.avgTurnovers",
        "differential.turnoversDifferential", "differential.avgTurnoversDifferential",
        "differential.avgFoulsDifferential",
    },
    "hockey": {
        "general.losses",
        "defensive.avgGoalsAgainst", "defensive.goalsAgainst", "defensive.shotsAgainst",
        "defensive.overtimeLosses", "defensive.shootoutShotsAgainst",
        "penalties.penaltyMinutes",
    },
}


# Counts of tries, which aren't good or bad in themselves, so they read highest first for the team
# and its opponents alike: a defense wants to force punts, and an attempt isn't a miss.
COUNTS_OF_TRIES = {
    "baseball": {"batting.atBats", "pitching.innings", "fielding.totalChances"},
    "football": {
        "passing.passingAttempts", "rushing.rushingAttempts",
        "miscellaneous.thirdDownAttempts", "miscellaneous.fourthDownAttempts",
        "kicking.fieldGoalAttempts", "kicking.fieldGoalAttempts1_19", "kicking.fieldGoalAttempts20_29",
        "kicking.fieldGoalAttempts30_39", "kicking.fieldGoalAttempts40_49", "kicking.fieldGoalAttempts50",
        "kicking.extraPointAttempts",
        "punting.punts", "returning.kickReturns", "returning.puntReturns",
    },
    "basketball": {
        "offensive.fieldGoalsAttempted", "offensive.avgFieldGoalsAttempted",
        "offensive.threePointFieldGoalsAttempted", "offensive.avgThreePointFieldGoalsAttempted",
        "offensive.freeThrowsAttempted", "offensive.avgFreeThrowsAttempted",
    },
    "hockey": {"offensive.powerPlayOpportunities", "offensive.shootoutAttempts"},
}

# ESPN's name for a stat where it says something else. Passing's "Yards Per Game" is the whole
# offense's. "First Downs Attempts" is fourth down tries. A punting team's punt returns are the ones
# it gave up.
STAT_TITLES = {
    "football": {
        "passing.sacks": "Sacks Taken",
        "passing.interceptions": "Interceptions Thrown",
        "passing.yardsPerGame": "Total Yards Per Game",
        "receiving.yardsPerGame": "Total Yards Per Game",
        "miscellaneous.fourthDownAttempts": "Fourth Down Attempts",
        "miscellaneous.turnOverDifferential": "Turnover Differential",
        "punting.puntReturns": "Punt Returns Allowed",
        "punting.puntReturnYards": "Punt Return Yards Allowed",
        "punting.avgPuntReturnYards": "Average Punt Return Yards Allowed",
    },
}


def low_is_good(sport, section, stat, opponent=False):
    """Whether the lowest number ranks first. `sport` is the first part of a league's path."""
    key = f"{section}.{stat}"
    if stat in GAMES_PLAYED or key in COUNTS_OF_TRIES.get(sport, ()):
        return False
    low = key in LOW_IS_GOOD.get(sport, ())
    return not low if opponent else low


def _dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list(value):
    return value if isinstance(value, list) else []


def _strings(value):
    """A column of names, in place: something else where a name belongs mustn't shift the rest."""
    return [item if isinstance(item, str) else "" for item in _list(value)]


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _columns(data):
    """Section to (stat names, display names). ESPN lists a section once per split, and only
    the first copy has the names."""
    columns = {}
    for meta in _dicts(data.get("categories")):
        section, names = meta.get("name"), _strings(meta.get("names"))
        if isinstance(section, str) and names and section not in columns:
            columns[section] = (names, _strings(meta.get("displayNames")))
    return columns


def _is_opponent(block):
    return str(block.get("splitId")) == OPPONENT_SPLIT


def _has_opponents(team):
    return any(_is_opponent(block) for block in _dicts(team.get("categories")))


def needs_team_list(data):
    """Whether any team in the answer has no opponents' numbers, so only ESPN's team list can say
    if it's Division I."""
    return not all(_has_opponents(team) for team in _dicts(data.get("teams")))


def qualified_teams(data, team_list):
    """The Division I teams of a college basketball list. ESPN's has every school that played a
    Division I team, so a Division II school with one game can top a per-game stat: 722 teams in
    2025-26's men's basketball, 362 of them Division I. ESPN only has opponents' numbers for
    Division I teams, which tells them apart when everyone has played once. A few schools moving up
    to Division I have none (East Texas A&M, Southern Indiana, Queens and Lindenwood in the women's
    game in 2026-27), and those are on ESPN's team list, `team_list`, which has no other schools."""
    return [team for team in _dicts(data.get("teams"))
            if _has_opponents(team)
            or str((team.get("team") if isinstance(team.get("team"), dict) else {}).get("id")) in team_list]


def _category_title(block, section):
    title = block.get("displayName")
    if title:
        return title[4:] if title.startswith("Own ") else title
    title = section.title()
    return f"Opponent {title}" if _is_opponent(block) else title


def parse_team_stats(data, sport, team_list=None):
    """The categories of a byteam payload: {category, low_is_good, stats}, the team's own numbers
    before its opponents'. Each of `stats` is a team: {team_name, team_id, stats, values}, with what
    to show and what to rank by, under the stat's name. A stat ESPN has no number for is left out,
    rather than ranking as a zero, unless it shows a zero: an NHL team that has yet to go to a
    shootout has "0" with a null. `team_list` is for college basketball: see qualified_teams."""
    data = data if isinstance(data, dict) else {}
    columns = _columns(data)
    titles_for_sport = STAT_TITLES.get(sport, {})
    own, opponents = {}, {}
    for team in (_dicts(data.get("teams")) if team_list is None else qualified_teams(data, team_list)):
        info = team.get("team") if isinstance(team.get("team"), dict) else {}
        team_name = info.get("displayName") or info.get("name")
        if not team_name:
            continue
        for block in _dicts(team.get("categories")):
            section = block.get("name")
            if not isinstance(section, str):
                continue
            names, titles = columns.get(section, ((), ()))
            totals, values = _list(block.get("totals")), _list(block.get("values"))
            opponent = _is_opponent(block)
            shown, numbers, directions = {}, {}, {}
            # A few display names repeat within a section, and the later stat is the one to use:
            # NBA "Assist To Turnover Ratio" reads 27.4, then the real 1.8.
            for index, (name, title) in enumerate(zip(names, titles)):
                total = totals[index] if index < len(totals) else None
                value = values[index] if index < len(values) else None
                if value is None and total == "0":
                    value = 0
                if title and total not in (None, "", "-") and _is_number(value):
                    title = titles_for_sport.get(f"{section}.{name}", title)
                    shown[title], numbers[title] = str(total), value
                    directions[title] = low_is_good(sport, section, name, opponent)
            if not shown:
                continue
            categories = opponents if opponent else own
            category = categories.setdefault(section, {"category": _category_title(block, section),
                                                       "low_is_good": [], "stats": []})
            category["low_is_good"] += [title for title, low in directions.items()
                                        if low and title not in category["low_is_good"]]
            category["stats"].append({"team_name": team_name, "team_id": str(info.get("id") or ""),
                                      "stats": shown, "values": numbers})
    return list(own.values()) + list(opponents.values())


def rank_teams(rows, low_first):
    """The rows best first, each with its rank. Teams level on the number share a rank, and the
    next one's rank counts them, so it matches a rank read off the league list on the iPhone."""
    ordered = sorted(rows, key=lambda row: (row["value"] if low_first else -row["value"], row["name"]))
    ranks = _shared_ranks(row["value"] for row in ordered)
    return [{**row, "rank": rank} for row, rank in zip(ordered, ranks)]


def _shared_ranks(values):
    """Each value's rank, best first: one level with the one before shares its rank, and the next
    rank counts them, so 1, 1, 3."""
    rank, previous = 0, None
    for position, value in enumerate(values, 1):
        if value != previous:
            rank, previous = position, value
        yield rank


def team_stat_lists(team_stats):
    """One ranked list per stat of each category, for the dialog to offer."""
    lists = []
    for category in team_stats:
        name = category.get("category", "Unknown")
        titles = {}
        for team in category.get("stats", []):
            titles.update(dict.fromkeys(team.get("values", {})))
        for title in titles:
            rows = [{"name": team.get("team_name", "Unknown"), "value": team["values"][title],
                     "displayValue": team["stats"][title]}
                    for team in category.get("stats", []) if title in team.get("values", {})]
            lists.append({"name": f"{title} ({name})", "category": name, "stat_name": title,
                          "data": rank_teams(rows, title in category.get("low_is_good", ())), "type": "team"})
    return lists


RANKING_HEADERS = {
    "player": ["Rank", "Player", "Team", "Value"],
    "team": ["Rank", "Team", "Value"],
}


def _shown(value):
    return "" if value is None else value


def ranking_rows(stat_type, data):
    """A ranked list as rows for RANKING_HEADERS, in the order it came, which is best first.
    A team's rows carry their rank. A player's comes from the list, by the same rule, comparing the
    number as shown, since /leaders has no rank.
    A player with no team reads N/A, so no cell of the table is silent."""
    if stat_type == "team":
        return [[item.get("rank"), item.get("name") or "Unknown", _shown(item.get("displayValue"))]
                for item in data]
    values = [_shown(item.get("value")) for item in data]
    return [[rank, item.get("player_name") or "Unknown", item.get("team") or "N/A", value]
            for rank, item, value in zip(_shared_ranks(values), data, values)]
