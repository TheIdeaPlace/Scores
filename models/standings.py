from typing import Any, Dict, List

class StandingsData:
    """Data model for team standings"""
    def __init__(self, raw_data: List[Dict]):
        self.raw_data = raw_data
        self.teams = self._parse_teams(raw_data)
        self.divisions = self._organize_by_divisions()

    def _parse_teams(self, data: List[Dict]) -> List[Dict]:
        teams: List[Dict] = []
        if not data:
            return teams
        for entry in data:
            if not isinstance(entry, dict):
                continue
            
            # Basic fields with field name normalization
            name = entry.get("team_name") or entry.get("name") or entry.get("displayName") or entry.get("abbreviation", "Unknown")
            wins = entry.get("wins") if isinstance(entry.get("wins"), (int, str)) else entry.get("record", "0-0").split("-")[0]
            losses = entry.get("losses") if isinstance(entry.get("losses"), (int, str)) else entry.get("record", "0-0").split("-")[-1]
            ties = entry.get("ties", 0)  # NFL ties
            win_pct = entry.get("win_percentage") or entry.get("win_pct") or entry.get("winPercent") or entry.get("pct") or "0.000"
            gb = entry.get("games_back") or entry.get("games_behind") or entry.get("gb") or "—"
            division = entry.get("division", "League")
            streak = entry.get("streak", "")
            
            # Build record string including ties if present
            if ties and int(ties) > 0:
                record = entry.get("record") or f"{wins}-{losses}-{ties}"
            else:
                record = entry.get("record") or f"{wins}-{losses}"
            
            # Start with the normalized basic fields
            team_data = {
                "name": name,
                "team_name": name,  # Keep both field names for compatibility
                "wins": wins,
                "losses": losses,
                "ties": ties,  # Include ties for NFL
                "win_pct": win_pct,
                "win_percentage": win_pct,  # Keep both field names for compatibility
                "games_behind": gb,
                "games_back": gb,  # Keep both field names for compatibility
                "streak": streak or "N/A",
                "record": record,
                "division": division
            }
            
            # Add all other fields from the original entry to preserve expanded data
            for key, value in entry.items():
                if key not in team_data:  # Don't overwrite our normalized fields
                    team_data[key] = value
            
            teams.append(team_data)
        return teams

    def _organize_by_divisions(self) -> Dict[str, List[Dict]]:
        def _to_int(val: Any) -> int:
            try:
                return int(val)
            except Exception:
                return -10_000
        def _to_float(val: Any) -> float:
            try:
                return float(val)
            except Exception:
                return -1.0
        divisions: Dict[str, List[Dict]] = {}
        for team in self.teams:
            division = team.get("division", "League")
            divisions.setdefault(division, []).append(team)
        for division_teams in divisions.values():
            # Soccer's table goes by ESPN's rank, which has the tiebreakers: goal difference and more.
            if all("table_rank" in team for team in division_teams):
                division_teams.sort(key=lambda x: x["table_rank"])
                continue
            # Hockey ranks by points; the percentage can put a team with fewer games first.
            division_teams.sort(key=lambda x: (_to_int(x.get("points", 0)), _to_float(x.get("win_pct")), _to_int(x.get("wins"))), reverse=True)
        return divisions
