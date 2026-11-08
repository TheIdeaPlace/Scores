"""Pure: ESPN's definition of a statistic, from the glossary that comes with statistics/byteam.

Each of byteam's top-level `categories` has `names` and, parallel to them, `descriptions`: ESPN's
own sentence for each stat. The same name can mean different things in two categories. MLB has
strikeouts, hits, home runs and walks as a batter's and as a pitcher's, and the NFL has
interceptions thrown (passing) and made (defensiveInterceptions), and punt returns made
(returning) and allowed (punting). So the glossary is keyed by category and name, never the name
alone: a lookup by name gave the pitchers' strikeout leaders the batters' definition (#193).

A team statistic's key is the category and name it is in byteam, `section.stat`, or
`opponent.section.stat` for what a team's opponents did against it, which takes the same
definition. A player leader category from /leaders has a key of its own (`pointsPerGame`,
`strikeouts`), and LEADER_STATS says which category and name in the glossary it is. Those come
from tools/stat_categories.py, which matched each leader to the stat in a leading player's own
statistics (docs/stat-categories.csv). A leader that isn't listed, or whose stat byteam has no
definition for, has none: a definition from another category could be the wrong one, as the
NFL's sack leaders would get the sacks a passer took.

The iPhone's twin is StatGlossary.swift. tests/fixtures/stat_glossary_grid.json holds both to
the same table and the same answers on real byteam payloads.
"""

OPPONENT = "opponent"

# Sport (the first part of a league's path) -> leader key -> (category, stat name).
LEADER_STATS = {
    "baseball": {
        "avg": ("batting", "avg"),
        "hits": ("batting", "hits"),
        "homeRuns": ("batting", "homeRuns"),
        "MLBRating": ("batting", "MLBRating"),
        "onBasePct": ("batting", "onBasePct"),
        "OPS": ("batting", "OPS"),
        "runs": ("batting", "runs"),
        "RBIs": ("batting", "RBIs"),
        "slugAvg": ("batting", "slugAvg"),
        "stolenBases": ("batting", "stolenBases"),
        "WARBR": ("batting", "WARBR"),
        "avgGameScore": ("pitching", "avgGameScore"),
        "ERA": ("pitching", "ERA"),
        "holds": ("pitching", "holds"),
        "opponentAvg": ("pitching", "opponentAvg"),
        "qualityStarts": ("pitching", "qualityStarts"),
        "saves": ("pitching", "saves"),
        "strikeouts": ("pitching", "strikeouts"),
        "WHIP": ("pitching", "WHIP"),
        "wins": ("pitching", "wins"),
    },
    "football": {
        "passesDefended": ("defensive", "passesDefended"),
        "sacks": ("defensive", "sacks"),
        "totalTackles": ("defensive", "totalTackles"),
        "interceptions": ("defensiveInterceptions", "interceptions"),
        "interceptionYards": ("defensiveInterceptions", "interceptionYards"),
        "kickoffYards": ("kicking", "kickoffYards"),
        "passingTouchdowns": ("passing", "passingTouchdowns"),
        "passingYards": ("passing", "passingYards"),
        "quarterbackRating": ("passing", "QBRating"),
        "totalTouchdowns": ("passing", "totalTouchdowns"),
        "puntYards": ("punting", "puntYards"),
        "receivingTouchdowns": ("receiving", "receivingTouchdowns"),
        "receivingYards": ("receiving", "receivingYards"),
        "receptions": ("receiving", "receptions"),
        "rushingTouchdowns": ("rushing", "rushingTouchdowns"),
        "rushingYards": ("rushing", "rushingYards"),
        "totalPoints": ("scoring", "totalPoints"),
    },
    "basketball": {
        "blocksPerGame": ("defensive", "avgBlocks"),
        "stealsPerGame": ("defensive", "avgSteals"),
        "defensiveReboundsPerGame": ("defensive", "avgDefensiveRebounds"),
        "doubleDouble": ("general", "doubleDouble"),
        "tripleDouble": ("general", "tripleDouble"),
        "minutesPerGame": ("general", "avgMinutes"),
        "foulsPerGame": ("general", "avgFouls"),
        "PER": ("general", "PER"),
        "NBARating": ("general", "NBARating"),
        "reboundsPerGame": ("general", "avgRebounds"),
        "3PointPct": ("offensive", "threePointFieldGoalPct"),
        "assistsPerGame": ("offensive", "avgAssists"),
        "3PointsMadePerGame": ("offensive", "avgThreePointFieldGoalsMade"),
        "3PointMadePerGame": ("offensive", "avgThreePointFieldGoalsMade"),
        "fieldGoalPercentage": ("offensive", "fieldGoalPct"),
        "FreeThrowPct": ("offensive", "freeThrowPct"),
        "offensiveReboundsPerGame": ("offensive", "avgOffensiveRebounds"),
        "points": ("offensive", "points"),
        "pointsPerGame": ("offensive", "avgPoints"),
        "avgTurnovers": ("offensive", "avgTurnovers"),
        "turnoversPerGame": ("offensive", "avgTurnovers"),
    },
    "hockey": {
        "avgGoalsAgainst": ("defensive", "avgGoalsAgainst"),
        "savePct": ("defensive", "savePct"),
        "shutouts": ("defensive", "shutouts"),
        "plusMinus": ("general", "plusMinus"),
        "wins": ("general", "wins"),
        "assists": ("offensive", "assists"),
        "goals": ("offensive", "goals"),
        "points": ("offensive", "points"),
        "penaltyMinutes": ("penalties", "penaltyMinutes"),
    },
}


def glossary_key(category, name):
    """ESPN writes a category's name in two cases (byteam's `defensiveinterceptions` is the core
    API's `defensiveInterceptions`), so the category part is lowercased. A stat name keeps its case."""
    return f"{category.lower()}.{name}"


def glossary(byteam):
    """{glossary_key: definition} from a byteam payload. A category comes once per split and only
    the first copy has names. The first definition that says something wins, and an empty one or
    anything that isn't text is no definition."""
    found = {}
    categories = byteam.get("categories") if isinstance(byteam, dict) else None
    for meta in categories if isinstance(categories, list) else []:
        if not isinstance(meta, dict) or not isinstance(meta.get("name"), str):
            continue
        names, descriptions = meta.get("names"), meta.get("descriptions")
        if not isinstance(names, list) or not isinstance(descriptions, list):
            continue
        for name, text in zip(names, descriptions):
            if not isinstance(name, str) or not name or not isinstance(text, str):
                continue
            text = " ".join(text.split())
            key = glossary_key(meta["name"], name)
            if text and key not in found:
                found[key] = text
    return found


def stat_for(sport, key, team):
    """(category, name) in the glossary for a stat the apps show, or None if there's no telling.
    `team` says whether `key` is a team statistic (`section.stat`, `opponent.section.stat`) or a
    player leader category."""
    if team:
        parts = key.split(".")
        if parts[0] == OPPONENT:
            parts = parts[1:]
        return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None
    return LEADER_STATS.get(sport, {}).get(key)


def definition(found, sport, key, team):
    """ESPN's definition of a stat, or None where ESPN gives none. `found` is from glossary()."""
    stat = stat_for(sport, key, team) if isinstance(key, str) else None
    return found.get(glossary_key(*stat)) if stat else None


# What the Windows Statistics dialog's definitions say.
NO_DEFINITION = "No definition from ESPN."
NOT_LOADED = "ESPN's definitions couldn't be loaded. Close the statistics and open them again to try again."
NOTHING_SHOWN = "No statistics are showing, so there are no definitions to show."
STILL_LOADING = "The statistics and their definitions are still loading. Press Alt+D again in a moment."
# ESPN's text defines the stat itself, which reads backwards under an opponents' list. The iPhone
# says the same before it.
OPPONENT_NOTE = "This ranks teams by what their opponents did against them. ESPN defines the statistic as: "


def definition_lines(stats, found, sport, still_loading=False):
    """One line per statistic on screen, "Name: definition", in the order they're listed. `stats`
    are the dialog's: {name, key, type}, type "team" or "player". `found` is the glossary, or None
    if it couldn't be had, which is one line saying so rather than a "no definition" for each.
    `still_loading` is the statistics or their definitions not there yet, which isn't "none"."""
    if still_loading:
        return [STILL_LOADING]
    if not stats:
        return [NOTHING_SHOWN]
    if found is None:
        return [NOT_LOADED]
    lines = []
    for stat in stats:
        team = stat.get("type") == "team"
        key = stat.get("key")
        text = definition(found, sport, key, team)
        if text and team and key.startswith(f"{OPPONENT}."):
            text = OPPONENT_NOTE + text
        lines.append(f"{stat.get('name') or 'Unknown'}: {text or NO_DEFINITION}")
    return lines
