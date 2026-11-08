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
    """The categories of a byteam payload: {category, low_is_good, keys, stats}, the team's own
    numbers before its opponents'. `keys` has each stat title's `section.stat` (`opponent.section.stat`
    for the opponents'), the key stat_glossary takes. Each of `stats` is a team: {team_name, team_id, stats, values}, with what
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
            shown, numbers, directions, keys = {}, {}, {}, {}
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
                    keys[title] = f"{'opponent.' if opponent else ''}{section}.{name}"
            if not shown:
                continue
            categories = opponents if opponent else own
            # `keys` is each title's stat as byteam names it, for stat_glossary's definitions.
            category = categories.setdefault(section, {"category": _category_title(block, section),
                                                       "low_is_good": [], "keys": {}, "stats": []})
            category["low_is_good"] += [title for title, low in directions.items()
                                        if low and title not in category["low_is_good"]]
            category["keys"].update(keys)
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
                          "key": category.get("keys", {}).get(title),
                          "data": rank_teams(rows, title in category.get("low_is_good", ())), "type": "team"})
    return lists


RANKING_HEADERS = {
    "player": ["Rank", "Player", "Team", "Value"],
    "team": ["Rank", "Team", "Value"],
}


# ---------------------------------------------------------------- One team's ranks (Team Hub)
#
# Team Hub's Stats tab, as on the iPhone (ESPNAPIService.fetchTeamStatRankings): the core API's
# statistics for one team say which stats it has and their values, and the rank comes from the
# league's byteam list where that has the stat, so it's what the league list says. Where it doesn't,
# ESPN's own rank from the core API is used if it can be believed.

# Stat names that are technical, trivial or repeated, which Team Hub leaves out. The iPhone's list.
HUB_EXCLUDED = {
    "gamesPlayed", "teamGamesPlayed", "isQualified", "isQualifiedSteals",
    "isQualifiedCatcher", "isQualifiedPitcher", "playerRating", "pitcherRating",
    "batterRating", "MLBRating", "projectedHomeRuns", "WAR", "DWAR", "OWAR",
    "thirdInnings", "pitchesAsStarter", "pitchesPerStart", "gameScore",
    "pitchCount", "strikes", "strikesToPitchRatio", "pickoffAttempts",
    "runsCreated", "runsCreatedPer27Outs", "secondaryAvgMinusBA",
    "pinchAvg", "pinchHits", "pinchAtBats", "fullInnings", "partInnings",
    "catcherInterference", "gameWinningRBIs", "sacHits", "sacBunts",
    "sacFlies", "atBats", "plateAppearances", "pitches", "battersFaced",
    "thirdInningsPlayed", "saveOpportunitiesPerWin", "inheritedRunners",
    "inheritedRunnersScored", "blownSaves", "groundBalls", "flyBalls",
    "runSupportAvg", "groundToFlyRatio", "pitchesPerInning",
}
# With no list the team is on to say how many teams there are, a rank past these is against
# individual players or another pool: NFL kick return fair catch percentage reads 200th. 34 is more
# than any pro league has, and 400 more than Division I.
HUB_MOST_PRO_TEAMS = 34
HUB_MOST_COLLEGE_TEAMS = 400
# ESPN's rank for a stat everyone has nothing in, or that it can't rank.
HUB_RANKS_NOT_SHOWN = {"", "?", "Tied-1st"}


def ordinal(number):
    """1st, 2nd, 3rd, 11th, 21st, 113th."""
    if 11 <= number % 100 <= 13:
        return f"{number}th"
    return f"{number}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th') }"


def rank_display(rank, tied, out_of=None):
    """"9th", "Tied-9th", as ESPN writes them. A college list says what it's out of: "118th" is a
    good team among 300 and a bad one among 32, and a pro fan knows how many teams there are."""
    place = ("Tied-" if tied else "") + ordinal(rank)
    return place if out_of is None else f"{place} of {out_of}"


class LeagueRanks:
    """A season's byteam answer, ready to say where one team stands in one of its stats, the same
    as reading it off the league list. The iPhone's LeagueTeamStats. `team_list` is for college
    basketball: see qualified_teams."""

    def __init__(self, data, sport, team_list=None):
        data = data if isinstance(data, dict) else {}
        self.sport = sport
        self.teams = _dicts(data.get("teams")) if team_list is None else qualified_teams(data, team_list)
        self.team_ids = {str(_team_info(team).get("id")) for team in self.teams}
        # Lower-case section to stat name to column. The core API writes "defensiveInterceptions"
        # where byteam writes "defensiveinterceptions". A stat named twice in a section has the
        # same number both times, and the first is the one to use.
        self._columns = {}
        for section, (names, _titles) in _columns(data).items():
            index = {}
            for position, name in enumerate(names):
                index.setdefault(name, position)
            self._columns.setdefault(section.lower(), index)

    def _values(self, section, stat):
        """{team id: number} for the teams with a number for it, their own, not their opponents'."""
        column = self._columns.get(section.lower(), {}).get(stat)
        if column is None:
            return {}
        values = {}
        for team in self.teams:
            block = next((b for b in _dicts(team.get("categories"))
                          if str(b.get("name") or "").lower() == section.lower() and not _is_opponent(b)), None)
            if block is None:
                continue
            totals, numbers = _list(block.get("totals")), _list(block.get("values"))
            total = totals[column] if column < len(totals) else None
            value = numbers[column] if column < len(numbers) else None
            if value is None and total == "0":
                value = 0  # An NHL team yet to go to a shootout has "0" with a null.
            if total not in (None, "", "-") and _is_number(value):
                values[str(_team_info(team).get("id"))] = value
        return values

    def standing(self, team_id, section, stat):
        """(rank, tied) for the team in one of its stats, or None if this list doesn't have it.
        One plus how many teams are better, so teams level share a rank."""
        values = self._values(section, stat)
        own = values.get(str(team_id))
        if own is None:
            return None
        low = low_is_good(self.sport, section.lower(), stat)
        better = sum(1 for value in values.values() if (value < own if low else value > own))
        return 1 + better, sum(1 for value in values.values() if value == own) > 1


def _team_info(team):
    return team.get("team") if isinstance(team.get("team"), dict) else {}


def _espn_rank(stat, highest):
    """ESPN's rank and how it writes it, if it can be believed."""
    rank, shown = stat.get("rank"), stat.get("rankDisplayValue")
    if isinstance(rank, float) and rank.is_integer():
        rank = int(rank)
    if not isinstance(rank, int) or isinstance(rank, bool) or rank > highest:
        return None
    if not isinstance(shown, str) or shown in HUB_RANKS_NOT_SHOWN:
        return None
    return rank, shown


def hub_rankings(core, team_id, college, league=None):
    """The core API's statistics for one team as the rows Team Hub shows: {section, category,
    value, rank, rank_display, league_size}, grouped by section in the order they first come.

    `league` is the LeagueRanks of the same season's regular season, or None. A stat it has is
    ranked against the list, so it agrees with the league's Statistics screen. Fielding, the stats
    in HUB_EXCLUDED and a value of nothing are left out, and so is a stat with only ESPN's rank to
    go on when that rank says nothing: past the end of the league, "?" or everyone tied first.
    Montana is in FCS, and college football's list is FBS, so a team not on the list has no size."""
    listed = league if league is not None and str(team_id) in league.team_ids else None
    size = len(listed.team_ids) if listed is not None else None
    highest = size or (HUB_MOST_COLLEGE_TEAMS if college else HUB_MOST_PRO_TEAMS)
    out_of = size if college else None

    sections = {}
    splits = _as_dict(_as_dict(core).get("splits"))
    for category in _dicts(splits.get("categories")):
        section_name = category.get("displayName")
        if not isinstance(section_name, str) or section_name == "Fielding":
            continue
        section = category.get("name")
        for stat in _dicts(category.get("stats")):
            name, title, value = stat.get("name"), stat.get("displayName"), stat.get("displayValue")
            if not all(isinstance(text, str) for text in (name, title, value)):
                continue
            if name in HUB_EXCLUDED or value in ("0", "0.0"):
                continue
            standing = listed.standing(team_id, section, name) if listed and isinstance(section, str) else None
            if standing:
                rank, shown = standing[0], rank_display(*standing, out_of)
            else:
                espn = _espn_rank(stat, highest)
                if espn is None:
                    continue
                rank, shown = espn[0], espn[1] if out_of is None else f"{espn[1]} of {out_of}"
            sections.setdefault(section_name, []).append({
                "section": section_name, "category": title, "value": value,
                "rank": rank, "rank_display": shown, "league_size": size,
            })
    return [row for rows in sections.values() for row in rows]


def _as_dict(value):
    return value if isinstance(value, dict) else {}


HUB_HEADERS = {
    "players": ["Category", "Rank", "Player", "Value"],
    "team": ["Section", "Category", "Value", "Rank"],
}


def hub_player_rows(categories):
    """One team's leaders as rows for HUB_HEADERS["players"]: each category's players, ranked among
    themselves by the number as shown, as the league's list ranks its players."""
    rows = []
    for category in categories:
        title = category.get("category") or "Unknown"
        for rank, player, _team, value in ranking_rows("player", category.get("stats", [])):
            rows.append([title, rank, player, value])
    return rows


def hub_team_rows(rankings):
    """One team's ranks as rows for HUB_HEADERS["team"]."""
    return [[row["section"], row["category"], row["value"], row["rank_display"]] for row in rankings]


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
