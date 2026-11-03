"""
Venue service for managing stadium/venue data from ESPN API
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from services.api_service import ApiService
from espn_api import scoreboard_months

class VenueService:
    """Service for retrieving and managing venue data"""

    def __init__(self):
        self.venue_cache = {}
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports"
        self.leagues = {
            "nfl": "football/nfl",
            "nba": "basketball/nba", 
            "mlb": "baseball/mlb",
            "nhl": "hockey/nhl",
            "college-football": "football/college-football",
            "ncaaf": "football/college-football",  # Map NCAAF to college-football
            "mens-college-basketball": "basketball/mens-college-basketball"
        }

    def get_venues_for_league(self, league_key: str) -> Dict[str, Dict]:
        """Get all venues for a specific league"""

        if league_key in self.venue_cache:
            return self.venue_cache[league_key]

        venues = {}
        league_path = self.leagues.get(league_key)
        if not league_path:
            return venues

        # Get venues from recent games (more comprehensive than teams endpoint)
        today = datetime.now()
        start_date = today - timedelta(days=60)  # Look back 2 months
        end_date = today + timedelta(days=30)   # Look ahead 1 month

        try:
            # ESPN rejects dates=START-END ranges, so gather month by month.
            events = []
            for month in scoreboard_months(start_date, end_date):
                url = f"{self.base_url}/{league_path}/scoreboard?dates={month}&limit=100"
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    events.extend(resp.json().get('events', []))
            if events:

                for event in events:
                    competitions = event.get('competitions', [])
                    if competitions:
                        comp = competitions[0]
                        venue = comp.get('venue', {})

                        venue_id = venue.get('id')
                        if venue_id and venue_id not in venues:
                            venues[venue_id] = {
                                'id': venue_id,
                                'name': venue.get('fullName', 'Unknown'),
                                'city': venue.get('address', {}).get('city', 'Unknown'),
                                'state': venue.get('address', {}).get('state', 'Unknown'),
                                'indoor': venue.get('indoor', False),
                                'home_teams': []
                            }

                # Find home teams for each venue
                self._find_home_teams(venues, league_key)

                self.venue_cache[league_key] = venues

        except Exception as e:
            print(f"Error getting venues for {league_key}: {e}")

        return venues

    def _find_home_teams(self, venues: Dict, league_key: str):
        """Find which teams play home games at each venue"""

        # Get team data to match venues with home teams
        try:
            league_path = self.leagues.get(league_key)
            if not league_path:
                return

            url = f"{self.base_url}/{league_path}/teams"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                sports = data.get('sports', [])
                if sports:
                    leagues = sports[0].get('leagues', [])
                    if leagues:
                        teams = leagues[0].get('teams', [])

                        # Match teams to venues
                        for team_entry in teams:
                            team = team_entry.get('team', {})
                            venue = team.get('venue', {})
                            venue_id = venue.get('id')

                            if venue_id and venue_id in venues:
                                team_info = {
                                    'name': team.get('displayName', 'Unknown'),
                                    'short_name': team.get('shortDisplayName', ''),
                                    'abbreviation': team.get('abbreviation', ''),
                                    'id': team.get('id')
                                }
                                venues[venue_id]['home_teams'].append(team_info)

        except Exception:
            pass  # Skip if can't get team data

    def get_venue_details(self, venue_id: str, league_key: str) -> Dict:
        """Get comprehensive details for a specific venue"""

        venues = self.get_venues_for_league(league_key)
        venue = venues.get(venue_id)

        if not venue:
            return None

        # Create a comprehensive venue profile
        details = {
            'basic_info': {
                'name': venue.get('name'),
                'city': venue.get('city'),
                'state': venue.get('state'),
                'zip_code': venue.get('zipCode'),
                'league': league_key
            },
            'characteristics': {
                'indoor': venue.get('indoor', False),
                'grass': venue.get('grass'),
                'capacity': venue.get('capacity')
            },
            'media': {
                'images': venue.get('images', [])
            },
            'home_teams': venue.get('home_teams', [])
        }

        # Add interesting facts based on available data
        details['interesting_facts'] = self._generate_interesting_facts(venue, league_key)

        return details

    def _generate_interesting_facts(self, venue: Dict, league_key: str) -> List[str]:
        """Generate interesting facts about a venue"""

        facts = []

        # Surface type facts
        if venue.get('grass') is True:
            facts.append("Natural grass playing surface")
        elif venue.get('grass') is False:
            facts.append("Artificial turf playing surface")

        # Indoor/outdoor facts
        if venue.get('indoor'):
            facts.append("Indoor stadium with climate control")
        else:
            facts.append("Open-air stadium exposed to weather")

        # Capacity facts (if available)
        capacity = venue.get('capacity')
        if capacity:
            try:
                cap_num = int(capacity)
                if cap_num > 80000:
                    facts.append(f"Massive stadium seating {cap_num:,} fans")
                elif cap_num > 60000:
                    facts.append(f"Large stadium seating {cap_num:,} fans")
                else:
                    facts.append(f"Intimate venue seating {cap_num:,} fans")
            except (ValueError, TypeError):
                pass

        # League-specific facts. scores.py passes the league in lower case.
        league_key = (league_key or "").upper()
        if league_key == "MLB":
            facts.append("Major League Baseball venue")
            venue_name = venue.get('name') or ''
            if "Field" in venue_name:
                facts.append("Classic baseball 'Field' naming")
            elif "Park" in venue_name:
                facts.append("Traditional baseball 'Park' naming")

        elif league_key == "NFL":
            facts.append("National Football League venue")
            if venue.get('indoor'):
                facts.append("Weather never affects games here")

        elif league_key == "NBA":
            facts.append("National Basketball Association venue")

        elif league_key == "NHL":
            facts.append("National Hockey League venue")

        elif league_key in ["NCAAF", "COLLEGE-FOOTBALL"]:
            facts.append("College football venue")

        # Location facts
        city = venue.get('city', '')
        state = venue.get('state', '')
        if city and state:
            facts.append(f"Located in {city}, {state}")

        # Home team facts
        home_teams = venue.get('home_teams', [])
        if home_teams:
            if len(home_teams) == 1:
                team_name = home_teams[0].get('name', 'Unknown')
                facts.append(f"Home of the {team_name}")
            else:
                facts.append(f"Shared by {len(home_teams)} teams")

        return facts

# Global instance
venue_service = VenueService()
