#!/usr/bin/env python3
"""Every statistic category ESPN (and the MLB Stats API) offers for the leagues the apps cover, and
whether each app shows it, as a CSV to review. It is the groundwork for letting someone pick the
categories they want, which isn't built yet. docs/stat-categories.md explains the columns.

    python tools/stat_categories.py                       every league, to docs/stat-categories.csv
    python tools/stat_categories.py --league MLB          just one (repeat for more)
    python tools/stat_categories.py --out somewhere.csv

It only reads, and opens no windows. It asks ESPN for the same season the apps would, and decides
what's shown by running the apps' own rules: espn_api's leader parser, soccer.core_leader_lists,
team_stats.parse_team_stats, the iPhone's catalog in tests/fixtures/team_stat_directions.json and
the iPhone's lists of names it leaves out, read from ESPNAPIService.swift. Some of that depends on
the season's numbers (a list where everyone is on nothing isn't shown), so a rerun early in a season
can differ from one late in it.

Sources, as the `source` column names them:
    leaders           site.web.api.espn.com .../leaders, player leaders (8 leagues), both apps
    core_leaders      the core API's seasons/{y}/types/{t}/leaders, soccer's player leaders
    byathlete         site.web.api.espn.com .../statistics/byathlete, every player ranked by column
    core_athlete_stats  the core API's athletes/{id}/statistics, one player at a time
    mlb_statsapi      statsapi.mlb.com stats/leaders, Windows' MLB leaders until #166
    byteam            site.web.api.espn.com .../statistics/byteam, team statistics, both apps
    site_team_stats   site.api.espn.com .../teams/{id}/statistics, Windows' team stats until #152
    core_team_stats   the core API's teams/{id}/statistics, one team at a time, the iPhone's Team Hub
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import espn_api  # noqa: E402
import team_stats  # noqa: E402
from exceptions import ApiError  # noqa: E402
from soccer import SOCCER_LEAGUES, core_leader_lists  # noqa: E402

CSV_PATH = os.path.join(ROOT, "docs", "stat-categories.csv")
SWIFT_SERVICE = os.path.join(ROOT, "iOS", "SportsScoresApp", "SportsScores", "Services", "ESPNAPIService.swift")
DIRECTIONS = os.path.join(ROOT, "tests", "fixtures", "team_stat_directions.json")

US_LEAGUES = ["MLB", "NFL", "NBA", "NHL", "WNBA", "NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"]
ALL_LEAGUES = US_LEAGUES + sorted(SOCCER_LEAGUES)

COLUMNS = ["league", "kind", "group", "key", "display_name", "abbreviation", "definition",
           "definition_source", "source", "available_in_current_source", "shown_windows",
           "shown_iphone", "low_is_good", "notes"]
PLAYER, TEAM = "player_leader", "team_stat"
TEAM_HUB = "Team Hub, one team, when it has a number and a rank"

SITE = espn_api.BASE_URL
CORE = espn_api.CORE_BASE_URL
WEB = espn_api.TEAM_STATS_BASE_URL
TIMEOUT = 20
WORKERS = 8
SOCCER_SEASON_TYPE = espn_api.SOCCER_LEADERS_SEASON_TYPE

# The MLB Stats API categories Windows showed until #166 moved its leaders to ESPN (#165), with the
# ESPN stat each one is, where ESPN has it: (MLB Stats API name, its group, title, ESPN group, ESPN
# stat). The list is the one from espn_api.py before #166.
MLB_STATSAPI_CATEGORIES = [
    ("homeRuns", "hitting", "Home Runs", "batting", "homeRuns"),
    ("battingAverage", "hitting", "Batting Average", "batting", "avg"),
    ("rbi", "hitting", "RBIs", "batting", "RBIs"),
    ("hits", "hitting", "Hits", "batting", "hits"),
    ("runs", "hitting", "Runs", "batting", "runs"),
    ("doubles", "hitting", "Doubles", "batting", "doubles"),
    ("triples", "hitting", "Triples", "batting", "triples"),
    ("stolenBases", "hitting", "Stolen Bases", "batting", "stolenBases"),
    ("onBasePercentage", "hitting", "On-Base %", "batting", "onBasePct"),
    ("sluggingPercentage", "hitting", "Slugging %", "batting", "slugAvg"),
    ("ops", "hitting", "OPS", "batting", "OPS"),
    ("walks", "hitting", "Walks", "batting", "walks"),
    ("strikeouts", "hitting", "Strikeouts (Batting)", "batting", "strikeouts"),
    ("hitByPitch", "hitting", "Hit By Pitch", "batting", "hitByPitch"),
    ("sacrificeFlies", "hitting", "Sacrifice Flies", "batting", "sacFlies"),
    ("groundIntoDoublePlay", "hitting", "GIDP", "batting", "GIDPs"),
    ("wins", "pitching", "Wins", "pitching", "wins"),
    ("losses", "pitching", "Losses", "pitching", "losses"),
    ("era", "pitching", "ERA", "pitching", "ERA"),
    ("strikeouts", "pitching", "Strikeouts (Pitching)", "pitching", "strikeouts"),
    ("saves", "pitching", "Saves", "pitching", "saves"),
    ("holds", "pitching", "Holds", "pitching", "holds"),
    ("whip", "pitching", "WHIP", "pitching", "WHIP"),
    ("inningsPitched", "pitching", "Innings Pitched", "pitching", "innings"),
    ("hitBatsmen", "pitching", "Hit Batsmen", "pitching", "battersHit"),
    ("wildPitches", "pitching", "Wild Pitches", "pitching", "wildPitches"),
    ("balks", "pitching", "Balks", "pitching", "balks"),
    ("completeGames", "pitching", "Complete Games", "pitching", "completeGames"),
    ("shutouts", "pitching", "Shutouts", "pitching", "shutouts"),
    ("blownSaves", "pitching", "Blown Saves", "pitching", "blownSaves"),
    ("errors", "fielding", "Errors", "fielding", "errors"),
    ("fieldingPercentage", "fielding", "Fielding %", "fielding", "fieldingPct"),
    ("assists", "fielding", "Assists", "fielding", "assists"),
    ("putouts", "fielding", "Putouts", "fielding", "putouts"),
    ("chances", "fielding", "Total Chances", "fielding", "totalChances"),
    ("doublePlays", "fielding", "Double Plays", "fielding", "doublePlays"),
    ("triplePlays", "fielding", "Triple Plays", "fielding", "triplePlays"),
    ("passedBalls", "fielding", "Passed Balls", "fielding", "passedBalls"),
    ("caughtStealing", "fielding", "Caught Stealing", "fielding", "catcherCaughtStealing"),
]

# Plain definitions for categories ESPN gives none for, written here. Only ones whose meaning is
# certain. Keyed by (sport, key) where sport is the first part of the league's path, or "*".
WRITTEN_DEFINITIONS = {
    ("baseball", "WARBR"): "Wins Above Replacement: how many more wins a player is worth than a "
                           "replacement-level player, from batting, baserunning, fielding and pitching.",
    ("baseball", "MLBRating"): "ESPN's own overall rating of a player's season.",
    ("baseball", "avgGameScore"): "A starting pitcher's average Game Score, Bill James's single number "
                                  "for a start: it begins at 50 and adds for outs and strikeouts and "
                                  "takes away for hits, walks and runs.",
    ("baseball", "qualityStarts"): "Starts of at least six innings with three or fewer earned runs allowed.",
    ("baseball", "opponentAvg"): "The batting average hitters have against this pitcher.",
    ("soccer", "goalsLeaders"): "Goals scored.",
    ("soccer", "assistsLeaders"): "Passes that led directly to a goal.",
    ("basketball", "doubleDouble"): "Games with ten or more in two of points, rebounds, assists, "
                                    "steals and blocks.",
    ("basketball", "tripleDouble"): "Games with ten or more in three of points, rebounds, assists, "
                                    "steals and blocks.",
    ("basketball", "PER"): "Player Efficiency Rating: John Hollinger's per-minute rating of a "
                           "player's whole box score, scaled so the league average is 15.",
    ("hockey", "plusMinus"): "Goals for the team minus goals against while the player is on the "
                             "ice at even strength or shorthanded.",
}

# /leaders and the stat feeds name some stats differently. The iPhone has the basketball ones as
# playerStatAliases in ESPNAPIService.swift, for its definitions.
LEADER_ALIASES = {
    "pointsPerGame": "avgPoints", "assistsPerGame": "avgAssists", "reboundsPerGame": "avgRebounds",
    "stealsPerGame": "avgSteals", "blocksPerGame": "avgBlocks", "turnoversPerGame": "avgTurnovers",
    "foulsPerGame": "avgFouls", "fieldGoalPercentage": "fieldGoalPct", "FreeThrowPct": "freeThrowPct",
    "3PointPct": "threePointFieldGoalPct", "3PointsMadePerGame": "avgThreePointFieldGoalsMade",
    "3PointMadePerGame": "avgThreePointFieldGoalsMade",
    "defensiveReboundsPerGame": "avgDefensiveRebounds", "offensiveReboundsPerGame": "avgOffensiveRebounds",
    "minutesPerGame": "avgMinutes", "quarterbackRating": "QBRating", "goalsLeaders": "totalGoals", "assistsLeaders": "goalAssists",
    "goals": "totalGoals", "assists": "goalAssists",
}

_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (Scores stat-categories tool)"
_session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=WORKERS))


def get_json(url, params=None, tries=3):
    """The answer as a dict, or None for a 404 or anything that isn't one after a few tries."""
    for _ in range(tries):
        try:
            resp = _session.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return None
            return data if isinstance(data, (dict, list)) else None
    return None


def as_dict(value):
    return value if isinstance(value, dict) else {}


def dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def secure(url):
    return "https://" + url[len("http://"):] if isinstance(url, str) and url.startswith("http://") else url


def yes(flag):
    return "yes" if flag else "no"


# --- What the iPhone leaves out, read from its own code so this can't drift from it -----------------

def swift_string_set(name, within=None):
    """A `let name: Set<String> = [...]` from ESPNAPIService.swift, or None if it's gone. `within`
    names the function to look in, so a set of the same name elsewhere can't be the one read."""
    try:
        with open(SWIFT_SERVICE, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    if within:
        start = text.find(f"func {within}(")
        if start < 0:
            return None
        text = text[start:]
    match = re.search(rf"let {name}: Set<String> = \[(.*?)\]", text, re.S)
    return set(re.findall(r'"([^"]+)"', match.group(1))) if match else None


def swift_team_hub_excluded():
    """The core per-team stat names the iPhone's Team Hub hides, or None if they can't be read."""
    return swift_string_set("excluded", within="buildTeamStatRankings")


def iphone_catalog():
    """sport -> {(split, section, stat)}, what the iPhone's league list of team stats shows.
    (beyondTheCatalog in the same file is more direction checks, not more stats shown.)"""
    with open(DIRECTIONS, encoding="utf-8") as f:
        data = json.load(f)
    return {sport: {(spec["split"], spec["section"].lower(), spec["stat"]) for spec in specs}
            for sport, specs in data["catalog"].items()}


# --- The rows -------------------------------------------------------------------------------------

class Rows:
    """One row per league, kind and key, merged across the sources that have it."""

    def __init__(self):
        self._rows = {}

    def get(self, league, kind, match):
        return self._rows.get((league, kind, match.lower()))

    def add(self, league, kind, match, *, key, group, display_name, abbreviation="", definition="",
            source, available=False, shown_windows=False, shown_iphone=False, low_is_good=None, note=""):
        """Adds a row, or a source to the row already there. The first source to name a field wins,
        except a definition, which any source can fill in."""
        row = self._rows.get((league, kind, match.lower()))
        if row is None:
            row = self._rows[(league, kind, match.lower())] = {
                "league": league, "kind": kind, "group": group, "key": key,
                "display_name": display_name, "abbreviation": abbreviation, "definition": "",
                "definition_source": "", "sources": [], "available_in_current_source": False,
                "shown_windows": False, "shown_iphone": False, "low_is_good": None, "notes": [],
            }
        if source not in row["sources"]:
            row["sources"].append(source)
        if definition and not row["definition"]:
            row["definition"], row["definition_source"] = " ".join(str(definition).split()), "espn"
        row["display_name"] = row["display_name"] or display_name
        row["abbreviation"] = row["abbreviation"] or abbreviation
        row["available_in_current_source"] |= available
        row["shown_windows"] |= shown_windows
        row["shown_iphone"] |= shown_iphone
        if row["low_is_good"] is None:
            row["low_is_good"] = low_is_good
        self.note(row, note)
        return row

    @staticmethod
    def note(row, note):
        if note and note not in row["notes"]:
            row["notes"].append(note)

    def all(self):
        return list(self._rows.values())


def sport_of(league):
    return espn_api.LEAGUES[league].split("/")[0]


def season_year(league):
    """The year whose regular season the apps would show, or None if ESPN won't say."""
    try:
        return espn_api.latest_regular_season(espn_api.core_season(espn_api.LEAGUES[league]))
    except ApiError:
        return None


def core_stat_categories(data):
    return dicts(as_dict(as_dict(data).get("splits")).get("categories"))


# --- Player leaders -------------------------------------------------------------------------------

def athlete_stats_url(league_path, year, season_type, athlete_id):
    sport, league = league_path.split("/", 1)
    return f"{CORE}/{sport}/leagues/{league}/seasons/{year}/types/{season_type}/athletes/{athlete_id}/statistics/0"


def fetch_all(urls):
    urls = sorted({url for url in urls if url})
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return dict(zip(urls, pool.map(get_json, urls)))


def find_stat(athlete_answers, name, value=None):
    """(group, stat) for a stat name in some athlete's core statistics, preferring the group whose
    number is the leader's, since baseball has strikeouts as a batter and as a pitcher."""
    found = []
    for answer in athlete_answers:
        for category in core_stat_categories(answer):
            for stat in dicts(category.get("stats")):
                if stat.get("name") == name:
                    found.append((category.get("name") or "", stat))
    if value is not None:
        for group, stat in found:
            if isinstance(stat.get("value"), (int, float)) and abs(stat["value"] - value) < 0.0011:
                return group, stat
    return found[0] if found else (None, None)


def leaders_rows(rows, league, iphone_not_shown):
    """/leaders, which both apps read for the eight leagues that have it."""
    league_path = espn_api.LEAGUES[league]
    year = season_year(league)
    if year is None:
        return f"{league}: ESPN didn't say what season it is"
    data = None
    for attempt_year in (year, year - 1):
        try:
            data = espn_api._fetch_leaders(league_path, attempt_year)
        except ApiError:
            data = None
        if data and espn_api._parse_leaders(data)["player_stats"]:
            break
    if not data:
        return f"{league}: /leaders didn't answer"
    requested = as_dict(data.get("requestedSeason"))
    season_type = as_dict(requested.get("type")).get("type") or espn_api.REGULAR_SEASON
    used_year = requested.get("year") or year
    categories = dicts(as_dict(data.get("leaders")).get("categories"))

    first_athletes = {}
    for category in categories:
        leaders = dicts(category.get("leaders"))
        athlete_id = as_dict(leaders[0].get("athlete")).get("id") if leaders else None
        if athlete_id:
            first_athletes[category.get("name")] = athlete_stats_url(league_path, used_year, season_type, athlete_id)
    answers = fetch_all(first_athletes.values())
    every_answer = [answer for answer in answers.values() if answer]

    for category in categories:
        key = category.get("name") or ""
        leaders = dicts(category.get("leaders"))
        first_value = leaders[0].get("value") if leaders else None
        own = [answers.get(first_athletes.get(key))] + every_answer
        group, stat = find_stat([a for a in own if a], key, first_value)
        if stat is None and key in LEADER_ALIASES:
            group, stat = find_stat([a for a in own if a], LEADER_ALIASES[key], first_value)
        one = {"requestedSeason": data.get("requestedSeason"), "leaders": {"categories": [category]}}
        shown = bool(espn_api._parse_leaders(one)["player_stats"])
        if key in espn_api.LEADERS_NOT_SHOWN:
            note = "filtered: no qualifying minimum in practice"
        elif not shown:
            note = "hidden this season: nobody has a number in it"
        else:
            note = ""
        shown_iphone = shown and key not in (iphone_not_shown or set())
        row = rows.add(league, PLAYER, key, key=key, group=group or "leaders",
                       display_name=category.get("displayName") or key,
                       abbreviation=category.get("abbreviation") or category.get("shortDisplayName") or "",
                       definition=as_dict(stat).get("description"), source="leaders", available=True,
                       shown_windows=shown, shown_iphone=shown_iphone,
                       low_is_good=key in espn_api.LOW_IS_GOOD_LEADERS, note=note)
        if stat is not None and group:
            row["_matches"] = {f"{group}.{stat.get('name')}".lower()}
    return every_answer, used_year


def core_leaders_rows(rows, league):
    """The core API's leaders: soccer's on both apps, and college hockey's on the iPhone."""
    league_path = espn_api.LEAGUES[league]
    sport, code = league_path.split("/", 1)
    soccer = league in SOCCER_LEAGUES
    try:
        season = espn_api.core_season(league_path)
    except ApiError:
        return [], None
    season_type = SOCCER_SEASON_TYPE if soccer else espn_api.REGULAR_SEASON
    data, used_year = None, None
    for year in range(season["year"], season["year"] - 3, -1):
        answer = get_json(f"{CORE}/{sport}/leagues/{code}/seasons/{year}/types/{season_type}/leaders",
                          {"limit": espn_api.LEADERS_LIMIT})
        if answer and core_leader_lists(answer):
            data, used_year = answer, year
            break
    if not data:
        return [], None
    categories = dicts(data.get("categories"))
    stat_refs = {}
    for category in categories:
        leaders = dicts(category.get("leaders"))
        if leaders:
            stat_refs[category.get("name")] = secure(as_dict(leaders[0].get("statistics")).get("$ref"))
    answers = fetch_all(stat_refs.values())
    every_answer = [answer for answer in answers.values() if answer]

    kept = 0
    for index, category in enumerate(categories):
        key = category.get("name") or ""
        shown_now = len(core_leader_lists({"categories": categories[:index + 1]}))
        shown, kept = shown_now > kept, shown_now
        leaders = dicts(category.get("leaders"))
        first_value = leaders[0].get("value") if leaders else None
        own = [a for a in [answers.get(stat_refs.get(key))] + every_answer if a]
        group, stat = find_stat(own, key, first_value)
        if stat is None and key in LEADER_ALIASES:
            group, stat = find_stat(own, LEADER_ALIASES[key], first_value)
        if shown:
            note = ""
        elif not any(leader.get("value") for leader in leaders):
            note = "hidden this season: nobody has a number in it"
        else:
            note = "hidden: repeats an earlier list with the same name and the same players"
        if not soccer:
            note = "; ".join(n for n in (note, "Windows has no college hockey leaders") if n)
        row = rows.add(league, PLAYER, key, key=key, group=group or "leaders",
                       display_name=category.get("displayName") or key,
                       abbreviation=category.get("abbreviation") or "",
                       definition=as_dict(stat).get("description"), source="core_leaders", available=True,
                       shown_windows=shown and soccer, shown_iphone=shown, low_is_good=False, note=note)
        if stat is not None and group:
            row["_matches"] = {f"{group}.{stat.get('name')}".lower()}
    return every_answer, used_year


def byathlete_rows(rows, league, years):
    """Every player column of statistics/byathlete, which neither app reads yet, from the first of
    `years` that has any: the season the leaders came from, then the one before. False if none."""
    data = None
    for year in dict.fromkeys(year for year in years if year):
        data = get_json(f"{WEB}/{espn_api.LEAGUES[league]}/statistics/byathlete",
                        {"region": "us", "lang": "en", "season": year, "seasontype": 2, "limit": 1})
        if dicts(as_dict(data).get("categories")):
            break
    categories = dicts(as_dict(data).get("categories"))
    for meta in categories:
        group = meta.get("name") or ""
        names = meta.get("names") or []
        titles = meta.get("displayNames") or []
        labels = meta.get("labels") or []
        descriptions = meta.get("descriptions") or []
        for index, name in enumerate(names):
            add_player_stat(rows, league, group, name, "byathlete",
                            titles[index] if index < len(titles) else name,
                            labels[index] if index < len(labels) else "",
                            descriptions[index] if index < len(descriptions) else "")
    return bool(categories)


def leader_row_for(rows, league, match):
    for row in rows.all():
        if row["league"] == league and row["kind"] == PLAYER and match.lower() in row.get("_matches", ()):
            return row
    return None


def add_player_stat(rows, league, group, name, source, title, abbreviation, description):
    """A player stat from a per-player source. One a leader category already is joins that row."""
    match = f"{group}.{name}"
    row = leader_row_for(rows, league, match)
    if row is not None:
        rows.add(league, PLAYER, row["key"], key=row["key"], group=row["group"], display_name=title,
                 abbreviation=abbreviation, definition=description, source=source)
        return
    rows.add(league, PLAYER, match, key=match, group=group, display_name=title, abbreviation=abbreviation,
             definition=description, source=source)


def core_athlete_rows(rows, league, answers):
    for answer in answers:
        for category in core_stat_categories(answer):
            for stat in dicts(category.get("stats")):
                if stat.get("name"):
                    add_player_stat(rows, league, category.get("name") or "", stat["name"], "core_athlete_stats",
                                    stat.get("displayName") or stat["name"],
                                    stat.get("abbreviation") or stat.get("shortDisplayName") or "",
                                    stat.get("description") or "")


def mlb_statsapi_rows(rows):
    """What Windows showed from the MLB Stats API until #166. Each joins the ESPN stat it is. One no
    player here has a number in (a catcher's caught stealing, say) gets ESPN's definition from the
    team stat of the same name, so this runs after the team statistics."""
    for name, group, title, espn_group, espn_stat in MLB_STATSAPI_CATEGORIES:
        match = f"{espn_group}.{espn_stat}"
        row = leader_row_for(rows, "MLB", match) or rows.get("MLB", PLAYER, match)
        if row is not None and row["available_in_current_source"]:
            rows.add("MLB", PLAYER, row["key"], key=row["key"], group=row["group"], display_name=title,
                     source="mlb_statsapi", note=f"also an MLB Stats API category ({name})")
            continue
        team = rows.get("MLB", TEAM, match) or {}
        rows.add("MLB", PLAYER, match, key=match, group=espn_group,
                 display_name=team.get("display_name") or title, abbreviation=team.get("abbreviation", ""),
                 definition=team.get("definition", ""), source="mlb_statsapi",
                 note=f"dropped in #166: Windows had it from the MLB Stats API ({name}, {group}); see #165")


# --- Team statistics ------------------------------------------------------------------------------

def team_key(section, stat, opponent=False):
    return f"{'opponent.' if opponent else ''}{section}.{stat}"


def windows_team_titles(data, sport):
    """{(category title, stat title)} that Windows' Statistics dialog has, from its own parser."""
    shown = set()
    for category in team_stats.parse_team_stats(data, sport):
        for team in category["stats"]:
            shown.update((category["category"], title) for title in team["stats"])
    return shown


def byteam_rows(rows, league, year, catalog):
    league_path = espn_api.LEAGUES[league]
    sport = sport_of(league)
    data = None
    if year is not None:
        for attempt_year in (year, year - 1):
            try:
                data = espn_api._fetch_team_stats(league_path, attempt_year)
            except ApiError:
                data = None
            if data and data.get("teams"):
                break
    if not data or not data.get("teams"):
        return None
    windows_shown = windows_team_titles(data, sport) if league in espn_api.TEAM_STAT_LEAGUES else set()
    columns = {}
    for meta in dicts(data.get("categories")):
        if meta.get("name") and meta.get("names") and meta["name"] not in columns:
            columns[meta["name"]] = meta
    splits = {}
    for team in dicts(data.get("teams")):
        for block in dicts(team.get("categories")):
            splits.setdefault((block.get("name"), str(block.get("splitId")) == team_stats.OPPONENT_SPLIT), block)
    titles = team_stats.STAT_TITLES.get(sport, {})
    sport_catalog = catalog.get(sport, {})
    for (section, opponent), block in splits.items():
        meta = columns.get(section)
        if not meta:
            continue
        names, display = meta.get("names") or [], meta.get("displayNames") or []
        labels, descriptions = meta.get("labels") or [], meta.get("descriptions") or []
        category_title = team_stats._category_title(block, section)
        # The names Windows shows, after its renames: it keeps the later of two with the same one.
        renamed = [titles.get(f"{section}.{name}", display[i] if i < len(display) else "")
                   for i, name in enumerate(names)]
        for index, name in enumerate(names):
            if name in names[index + 1:]:
                continue  # The same stat twice (NBA avgRebounds), with the same number: one row.
            title = display[index] if index < len(display) else ""
            windows_title = renamed[index]
            later = next((names[i] for i in range(index + 1, len(names))
                          if windows_title and renamed[i] == windows_title and names[i] != name), None)
            shown_windows = (category_title, windows_title) in windows_shown and not later
            listed = ("opponent" if opponent else "own", section.lower(), name) in sport_catalog
            notes = []
            if opponent:
                notes.append("what opponents did against the team")
            if windows_title != title:
                notes.append(f"Windows calls it {windows_title}")
            if later:
                notes.append(f"Windows: not shown; {section}.{later} has the same name and is shown instead")
            elif not shown_windows and league in espn_api.TEAM_STAT_LEAGUES:
                notes.append("Windows: hidden this season, no team has a number")
            if listed:
                notes.append("iPhone: league list")
            low = team_stats.low_is_good(sport, section, name, opponent)
            row = rows.add(league, TEAM, team_key(section, name, opponent), key=team_key(section, name, opponent),
                     group=f"opponent {section}" if opponent else section,
                     display_name=title or name, abbreviation=labels[index] if index < len(labels) else "",
                     definition=descriptions[index] if index < len(descriptions) else "", source="byteam",
                     available=True, shown_windows=shown_windows, shown_iphone=listed, low_is_good=low)
            for note in notes:
                Rows.note(row, note)
    return data


TEAMS_TO_ASK = 2


def team_ids(league, byteam):
    """A few teams to ask the per-team sources about. One team can leave out a stat it has nothing in."""
    teams = dicts(as_dict(byteam).get("teams"))
    if not teams:
        data = get_json(f"{SITE}/{espn_api.LEAGUES[league]}/teams", {"limit": 1000})
        sports = dicts(as_dict(data).get("sports"))
        leagues = dicts(sports[0].get("leagues")) if sports else []
        teams = dicts(leagues[0].get("teams")) if leagues else []
    ids = [str(as_dict(team.get("team")).get("id")) for team in teams]
    return [team_id for team_id in ids if team_id != "None"][:TEAMS_TO_ASK]


def add_team_stat(rows, league, section, stat, source, note, iphone=False, iphone_note=""):
    name = stat.get("name")
    if not name:
        return
    existing = rows.get(league, TEAM, team_key(section, name))
    row = rows.add(league, TEAM, team_key(section, name), key=existing["key"] if existing else team_key(section, name),
                   group=existing["group"] if existing else section,
                   display_name=stat.get("displayName") or name,
                   abbreviation=stat.get("abbreviation") or stat.get("shortDisplayName") or "",
                   definition=stat.get("description") or "", source=source, shown_iphone=iphone,
                   note="" if existing else note)
    if iphone_note:
        Rows.note(row, iphone_note)


def site_team_rows(rows, league, ids):
    """The per-team request Windows used before #152. False if no team's answer had anything."""
    # Windows asked it for every league, but only the ones with byteam now had anything there.
    windows_used = league in espn_api.TEAM_STAT_LEAGUES
    found = False
    for team_id in ids:
        data = get_json(f"{SITE}/{espn_api.LEAGUES[league]}/teams/{team_id}/statistics")
        for category in dicts(as_dict(as_dict(as_dict(data).get("results")).get("stats")).get("categories")):
            section = category.get("name") or ""
            for stat in dicts(category.get("stats")):
                found = True
                add_team_stat(rows, league, section, stat, "site_team_stats",
                              "dropped in #152: Windows had it from the per-team request; see #155" if windows_used
                              else "per-team request only; neither app reads it")
    return found


class LeagueList:
    """What the iPhone's Team Hub needs from the league's byteam list: which teams are on it, and
    which of the team's own stats it ranks (LeagueTeamStats.standing in ESPNAPIService.swift)."""

    def __init__(self, byteam):
        byteam = as_dict(byteam)
        self.team_ids = {str(as_dict(team.get("team")).get("id")) for team in dicts(byteam.get("teams"))}
        self.columns = set()
        for meta in dicts(byteam.get("categories")):
            for name in meta.get("names") or []:
                self.columns.add((str(meta.get("name")).lower(), name))

    def ranks(self, team_id, section, name):
        return team_id in self.team_ids and (section.lower(), name) in self.columns


def team_hub_shows(league, team_id, category, stat, excluded, league_list):
    """Whether the iPhone's Team Hub lists this core stat for this team, by buildTeamStatRankings:
    not Fielding, not excluded, a number other than 0, and a rank from the league list or a usable
    one of ESPN's."""
    name, display = stat.get("name"), stat.get("displayValue")
    if not category.get("displayName") or category.get("displayName") == "Fielding":
        return False
    if not name or name in excluded or not stat.get("displayName") or display in (None, "0", "0.0"):
        return False
    if league_list.ranks(team_id, category.get("name") or "", name):
        return True
    college = "college" in espn_api.LEAGUES[league]
    highest = len(league_list.team_ids) if team_id in league_list.team_ids else (400 if college else 34)
    rank, rank_text = stat.get("rank"), stat.get("rankDisplayValue")
    return (isinstance(rank, int) and rank <= highest and bool(rank_text)
            and rank_text not in ("?", "Tied-1st"))


def core_team_rows(rows, league, ids, year, excluded, byteam):
    """The core API's per-team statistics, which the iPhone's Team Hub shows for one team. A stat
    counts as shown there if it would be for any of the teams asked about. False if none answered."""
    league_path = espn_api.LEAGUES[league]
    sport, code = league_path.split("/", 1)
    season_type = SOCCER_SEASON_TYPE if league in SOCCER_LEAGUES else espn_api.REGULAR_SEASON
    league_list = LeagueList(byteam)
    seen, shown = {}, set()
    for team_id in ids:
        data = None
        for attempt_year in ((year, year - 1) if year else ()):
            data = get_json(f"{CORE}/{sport}/leagues/{code}/seasons/{attempt_year}/types/{season_type}"
                            f"/teams/{team_id}/statistics")
            if core_stat_categories(data):
                break
        for category in core_stat_categories(data):
            section = category.get("name") or ""
            for stat in dicts(category.get("stats")):
                if stat.get("name"):
                    seen.setdefault((section, stat["name"]), stat)
                    if team_hub_shows(league, team_id, category, stat, excluded, league_list):
                        shown.add((section, stat["name"]))
    for (section, name), stat in seen.items():
        hub = (section, name) in shown
        add_team_stat(rows, league, section, stat, "core_team_stats", "core per-team only: one request per team",
                      iphone=hub, iphone_note=f"iPhone: {TEAM_HUB}" if hub else
                      "iPhone: Team Hub leaves it out for the teams checked (excluded, Fielding, zero or no usable rank)")
    return bool(seen)


# --- Putting it together --------------------------------------------------------------------------

def gather(leagues):
    rows = Rows()
    problems = []
    iphone_not_shown = swift_string_set("leadersNotShown")
    if iphone_not_shown is None:
        problems.append("Couldn't read leadersNotShown from ESPNAPIService.swift; iPhone leaders assumed as Windows")
    hub_excluded = swift_team_hub_excluded()
    if hub_excluded is None:
        problems.append("Couldn't read the Team Hub's excluded set from ESPNAPIService.swift; none assumed")
        hub_excluded = set()
    catalog = iphone_catalog()
    for league in leagues:
        print(f"{league}...", file=sys.stderr)
        year = season_year(league)
        if league in espn_api.LEADER_LEAGUES:
            result = leaders_rows(rows, league, iphone_not_shown)
        else:
            result = core_leaders_rows(rows, league)
        answers, leaders_year = ([], None) if isinstance(result, str) else result
        if isinstance(result, str):
            problems.append(result)
        elif not answers and league not in ("NCAAH", "NCAAWH"):
            problems.append(f"{league}: no player leaders found")
        if not byathlete_rows(rows, league, (leaders_year, year, year and year - 1)) \
                and league in espn_api.LEADER_LEAGUES:
            problems.append(f"{league}: byathlete didn't answer")
        core_athlete_rows(rows, league, answers)
        byteam = byteam_rows(rows, league, year, catalog)
        if byteam is None and league in espn_api.TEAM_STAT_LEAGUES:
            problems.append(f"{league}: byteam didn't answer")
        ids = team_ids(league, byteam)
        if not ids:
            problems.append(f"{league}: no team to ask per-team statistics for")
        expected = league not in ("NCAAH", "NCAAWH")
        if not site_team_rows(rows, league, ids) and league in espn_api.TEAM_STAT_LEAGUES:
            problems.append(f"{league}: the old per-team statistics didn't answer, so nothing reads as dropped")
        if not core_team_rows(rows, league, ids, year, hub_excluded, byteam) and expected:
            problems.append(f"{league}: the core API's per-team statistics didn't answer")
        if league == "MLB":
            mlb_statsapi_rows(rows)
    finish(rows)
    return rows, problems


def finish(rows):
    for row in rows.all():
        sport = sport_of(row["league"])
        if row["kind"] == PLAYER and not row["available_in_current_source"]:
            sources = row["sources"]
            if "byathlete" in sources:
                why = "not a leader category; byathlete can rank every player by it"
            elif "core_athlete_stats" in sources:
                why = "not a leader category; only one player at a time"
            else:
                why = ""
            if why:
                row["notes"].insert(0, why)
        if not row["definition"]:
            written = WRITTEN_DEFINITIONS.get((sport, row["key"])) or WRITTEN_DEFINITIONS.get(("*", row["key"]))
            if written:
                row["definition"], row["definition_source"] = written, "written"


def csv_rows(rows):
    order = {league: index for index, league in enumerate(ALL_LEAGUES)}
    out = []
    for row in rows.all():
        out.append({
            "league": row["league"], "kind": row["kind"], "group": row["group"], "key": row["key"],
            "display_name": row["display_name"], "abbreviation": row["abbreviation"],
            "definition": row["definition"], "definition_source": row["definition_source"],
            "source": "; ".join(row["sources"]),
            "available_in_current_source": yes(row["available_in_current_source"]),
            "shown_windows": yes(row["shown_windows"]), "shown_iphone": yes(row["shown_iphone"]),
            "low_is_good": "" if row["low_is_good"] is None else yes(row["low_is_good"]),
            "notes": "; ".join(row["notes"]),
        })
    out.sort(key=lambda r: (order.get(r["league"], 99), r["league"], r["kind"], r["group"].lower(),
                            r["display_name"].lower(), r["key"]))
    return out


def write_csv(path, out):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(out)


def summary(out):
    """Per league and kind: rows, in the current source, shown on each app, and lost in #152 or #166."""
    lines = ["league,kind,rows,available,shown_windows,shown_iphone,dropped,espn_definitions,written_definitions"]
    seen = []
    for row in out:
        if (row["league"], row["kind"]) not in seen:
            seen.append((row["league"], row["kind"]))
    for league, kind in seen:
        group = [r for r in out if r["league"] == league and r["kind"] == kind]
        lines.append(",".join(str(v) for v in (
            league, kind, len(group),
            sum(r["available_in_current_source"] == "yes" for r in group),
            sum(r["shown_windows"] == "yes" for r in group),
            sum(r["shown_iphone"] == "yes" for r in group),
            sum("dropped in #" in r["notes"] for r in group),
            sum(r["definition_source"] == "espn" for r in group),
            sum(r["definition_source"] == "written" for r in group))))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--league", action="append", choices=ALL_LEAGUES, help="just this league (repeatable)")
    parser.add_argument("--out", default=CSV_PATH, help="where to write the CSV")
    args = parser.parse_args(argv)
    rows, problems = gather(args.league or ALL_LEAGUES)
    out = csv_rows(rows)
    write_csv(args.out, out)
    print(summary(out))
    print(f"Wrote {len(out)} rows to {args.out}")
    for problem in problems:
        print(f"WARN {problem}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
