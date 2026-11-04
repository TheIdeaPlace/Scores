"""
Venues and their home teams, built from a league's scoreboard.

ESPN has no list of a league's venues. /teams carries no venue at all, and a team's
franchise.venue is years out of date for some teams. A scoreboard names the venue of
every game and which team is at home there, so one month of it gives both. A game at
a neutral site is nobody's home game, so a venue used only for those is left out.
"""

import requests
from datetime import datetime
from typing import Dict, Iterator, List

from espn_api import LEAGUES, NCAAB_GROUP, _as_dict, _dicts, college_scoreboard_params
from exceptions import ApiError

# The months of a league's regular season when every team has a home game, measured
# against ESPN's scoreboards in November 2026. The other months lose teams or add
# venues nobody calls home: NBA and NHL preseason arenas in October, All-Star teams and
# the Olympic break in February, the WNBA's All-Star team and arena in July, only the
# playoff teams in MLB's October, 22 of 63 men's college hockey teams idle in December,
# and college basketball's December reaching the 1000 game limit with 20 teams still to
# play at home.
IN_SEASON_MONTHS = {
    "mlb": {4, 5, 6, 7, 8, 9},
    "nfl": {9, 11, 12},
    "nba": {11, 1, 3},
    "nhl": {11, 12, 1, 3},
    "wnba": {5, 6, 8, 9},
    "ncaaf": {10, 11},
    "ncaam": {11, 1, 2},
    "ncaawb": {11, 1, 2},
    "ncaah": {11, 1, 2},
    "ncaawh": {10, 11, 1, 2},
}

# ESPN has marked American Airlines Center as not indoors for a WNBA game. Football,
# baseball and hockey really do play outdoors, so only these leagues ignore that.
ALWAYS_INDOORS = {"nba", "wnba", "ncaam", "ncaawb"}

# In-season months to try before giving up, the latest first. Off-season, the first of
# them is already last season's. The others are only for a month ESPN won't answer.
MONTHS_TO_TRY = 3

# A month of college basketball is up to 19 MB. A year would be no better: ESPN stops
# at the first 1000 games of any query, so a year of the NBA ends in April.
SCOREBOARD_LIMIT = 1000
TIMEOUT = 15

# What the row and the details say about the league, past what its name says.
LEAGUE_FACTS = {
    "MLB": "Major League Baseball venue",
    "NFL": "National Football League venue",
    "NBA": "National Basketball Association venue",
    "NHL": "National Hockey League venue",
    "WNBA": "Women's National Basketball Association venue",
    "NCAAF": "College football venue",
    "NCAAM": "Men's college basketball venue",
    "NCAAWB": "Women's college basketball venue",
    "NCAAH": "Men's college hockey venue",
    "NCAAWH": "Women's college hockey venue",
}


def _months_back(now: datetime, in_season: set) -> Iterator[str]:
    """In-season months as YYYYMM, from the latest at or before now."""
    year, month = now.year, now.month
    while True:
        if month in in_season:
            yield f"{year}{month:02d}"
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)


def _scoreboard_query(league_key: str) -> str:
    """What gets a league's whole month of games. College football follows the coverage setting."""
    if league_key == "ncaaf":
        return "&".join(college_scoreboard_params("NCAAF"))
    if league_key in ("ncaam", "ncaawb"):
        return f"groups={NCAAB_GROUP}&limit={SCOREBOARD_LIMIT}"
    return f"limit={SCOREBOARD_LIMIT}"


def _location(city: str, state: str) -> str:
    return ", ".join(part for part in (city, state) if part)


def _home_team(competition: Dict) -> Dict:
    """The team at home in this game, or {} if ESPN doesn't name one."""
    competitor = next((c for c in _dicts(competition.get("competitors")) if c.get("homeAway") == "home"), {})
    team = _as_dict(competitor.get("team"))
    name = team.get("displayName") or team.get("name")
    if not team.get("id") or not name:
        return {}
    return {
        "id": str(team["id"]),
        "name": name,
        "short_name": team.get("shortDisplayName") or "",
        "abbreviation": team.get("abbreviation") or "",
    }


def venues_from_events(events, always_indoors: bool = False) -> Dict[str, Dict]:
    """Every venue that is some team's home in these scoreboard events, by venue id."""
    venues = {}
    for event in _dicts(events):
        competition = next(iter(_dicts(event.get("competitions"))), {})
        if competition.get("neutralSite"):
            continue
        raw = _as_dict(competition.get("venue"))
        name = raw.get("fullName") or raw.get("displayName")
        team = _home_team(competition)
        if not raw.get("id") or not name or not team:
            continue
        address = _as_dict(raw.get("address"))
        city, state = address.get("city") or "", address.get("state") or ""
        venue = venues.setdefault(str(raw["id"]), {
            "id": str(raw["id"]),
            "name": name,
            "city": city,
            "state": state,
            "location": _location(city, state),
            "home_teams": [],
        })
        # Left out when ESPN doesn't say: no answer isn't the same as outdoors.
        if raw.get("indoor") is True or (raw.get("indoor") is False and not always_indoors):
            venue["indoor"] = raw["indoor"]
        if all(known["id"] != team["id"] for known in venue["home_teams"]):
            venue["home_teams"].append(team)
    for venue in venues.values():
        venue["home_teams"].sort(key=lambda team: team["name"])
    return venues


def venue_summary(venue: Dict) -> str:
    """A venue's row in the list: Name (City, State) [Indoor] - Home Team."""
    text = venue.get("name") or "Unknown Venue"
    if venue.get("location"):
        text += f" ({venue['location']})"
    if venue.get("indoor") is not None:
        text += " [Indoor]" if venue["indoor"] else " [Outdoor]"
    teams = [team.get("name") for team in venue.get("home_teams", []) if team.get("name")]
    if teams:
        text += " - " + ", ".join(teams)
    return text


class VenueService:
    """Service for retrieving and managing venue data"""

    def __init__(self):
        self.venue_cache = {}
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports"
        self.leagues = {key: LEAGUES[key.upper()] for key in IN_SEASON_MONTHS}

    def _month_events(self, league_key: str, month: str, query: str) -> List:
        url = f"{self.base_url}/{self.leagues[league_key]}/scoreboard?dates={month}&{query}"
        resp = requests.get(url, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code} from {url}")
        return _as_dict(resp.json()).get("events")

    def get_venues_for_league(self, league_key: str) -> Dict[str, Dict]:
        """A league's venues and home teams, by venue id. Takes a request or two, so
        call it off the UI thread.

        {} means ESPN answered and had nothing. If it never answered this raises
        ApiError, because "no venues" would be untrue.
        """
        if league_key not in self.leagues:
            return {}
        query = _scoreboard_query(league_key)
        # The query is part of the key because the coverage setting can change it.
        cache_key = (league_key, query)
        if cache_key in self.venue_cache:
            return self.venue_cache[cache_key]

        months = _months_back(datetime.now(), IN_SEASON_MONTHS[league_key])
        failed = False
        for _ in range(MONTHS_TO_TRY):
            month = next(months)
            try:
                events = self._month_events(league_key, month, query)
            except Exception as e:
                print(f"Error getting venues for {league_key}, {month}: {e}")
                failed = True
                continue
            venues = venues_from_events(events, league_key in ALWAYS_INDOORS)
            if venues:
                # An older month standing in for a failed one is only for now.
                if not failed:
                    self.venue_cache[cache_key] = venues
                return venues
        if failed:
            raise ApiError("ESPN did not answer. Try again in a minute.")
        return {}

    def venue_details(self, venue: Dict, league_key: str) -> Dict:
        """What the details dialog shows for one venue from the list. No request."""
        known = {"indoor": venue["indoor"]} if venue.get("indoor") is not None else {}
        return {
            "basic_info": {
                "name": venue.get("name"),
                "location": venue.get("location") or "",
                "league": (league_key or "").upper(),
            },
            "characteristics": known,
            "home_teams": venue.get("home_teams", []),
            "interesting_facts": self._generate_interesting_facts(venue, league_key),
        }

    def _generate_interesting_facts(self, venue: Dict, league_key: str) -> List[str]:
        """Only what the scoreboard says. Capacity and playing surface aren't in it."""
        facts = []

        if venue.get("indoor"):
            facts.append("Indoor venue")
        elif venue.get("indoor") is False:
            facts.append("Open-air stadium exposed to weather")

        # scores.py passes the league in lower case.
        league_key = (league_key or "").upper()
        if league_key in LEAGUE_FACTS:
            facts.append(LEAGUE_FACTS[league_key])
        if league_key == "MLB":
            venue_name = venue.get("name") or ""
            if "Field" in venue_name:
                facts.append("Classic baseball 'Field' naming")
            elif "Park" in venue_name:
                facts.append("Traditional baseball 'Park' naming")
        elif league_key == "NFL" and venue.get("indoor"):
            facts.append("Weather never affects games here")

        if venue.get("location"):
            facts.append(f"Located in {venue['location']}")

        home_teams = venue.get("home_teams", [])
        if len(home_teams) == 1:
            team_name = home_teams[0].get("name") or "Unknown"
            facts.append(f"Home of the {team_name}")
        elif home_teams:
            facts.append(f"Shared by {len(home_teams)} teams")

        return facts


# Global instance
venue_service = VenueService()
