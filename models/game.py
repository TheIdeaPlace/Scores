from typing import Dict, List
from datetime import datetime
import re

# Import timezone conversion function
try:
    from timezone_utils import convert_espn_time_to_local
    TIMEZONE_CONVERSION_AVAILABLE = True
except ImportError:
    TIMEZONE_CONVERSION_AVAILABLE = False

class GameData:
    """Data model for game information"""

    # Games that never got underway. ESPN still reports a score of "0" for both
    # sides in every one of these, so the score is noise — the record is the
    # useful thing to show. STATUS_SUSPENDED is deliberately absent: those were
    # halted after play began and their partial scores are real.
    NOT_PLAYED_STATUS_NAMES = {
        "STATUS_SCHEDULED",
        "STATUS_POSTPONED",
        "STATUS_CANCELED",
        "STATUS_CANCELLED",
    }
    NOT_PLAYED_DESCRIPTIONS = {"scheduled", "postponed", "canceled", "cancelled"}

    def __init__(self, raw_data: Dict, league: str = None):
        self.raw = raw_data or {}
        self.league = league
        self.game_id = self.raw.get("id", "")
        self.name = self.raw.get("name", "Unknown Game")
        self.start_time = self.raw.get("start_time", self.raw.get("date", ""))
        
        # Apply timezone conversion to start_time if available
        if TIMEZONE_CONVERSION_AVAILABLE and self.start_time:
            self.start_time = convert_espn_time_to_local(self.start_time)
            
        self.status = self.raw.get("status", "")
        self.status_name = self.raw.get("status_name", "")
        self.teams = self.raw.get("teams", [])

    @property
    def was_never_played(self) -> bool:
        """True for games with no score worth showing (scheduled, postponed, cancelled)."""
        if self.status_name:
            if self.status_name in self.NOT_PLAYED_STATUS_NAMES:
                return True
            # A delayed game that hasn't started reads "0 at 0" otherwise. One delayed
            # after it began has a real score, and an all-zero one is rare enough.
            return self.status_name == "STATUS_DELAYED" and all(
                str(t.get("score") or "0") == "0" for t in self.teams)
        # Older callers build GameData without status_name; fall back to the
        # display text ESPN puts in `description`.
        return bool(self.status) and self.status.lower() in self.NOT_PLAYED_DESCRIPTIONS

    def _format_football_time(self, time_str: str) -> str:
        """Format football game times to 'Thu 8/28 8:00PM' style"""
        if not time_str:
            return time_str
            
        # Handle formats like "8/28 - 5:30 PM EDT"
        if " - " in time_str and ("PM" in time_str or "AM" in time_str):
            try:
                date_part, time_part = time_str.split(" - ", 1)
                
                # Parse the date (e.g., "8/28")
                if "/" in date_part:
                    month_day = date_part.strip()
                    month, day = map(int, month_day.split("/"))
                    
                    # Smart year detection - use the most appropriate year
                    current_year = datetime.now().year
                    current_month = datetime.now().month
                    
                    # If the game month is significantly before current month, it's likely next year
                    # If the game month is after current month or close to it, use current year
                    if month < current_month - 6:  # More than 6 months ago, probably next year
                        year = current_year + 1
                    elif month < current_month - 2:  # A few months ago, might be previous year
                        year = current_year - 1  
                    else:
                        year = current_year
                    
                    # Create date and get day of week
                    game_date = datetime(year, month, day)
                    day_abbrev = game_date.strftime("%a")
                    
                    # Clean up time (remove timezone, simplify format)
                    clean_time = time_part.strip()
                    # Remove timezone abbreviations
                    clean_time = re.sub(r'\s+(EDT|EST|CDT|CST|MDT|MST|PDT|PST|ET|CT|MT|PT)$', '', clean_time)
                    
                    # Convert to simpler format (remove spaces, make PM/AM consistent)
                    clean_time = clean_time.replace(" ", "")
                    
                    return f"{day_abbrev} {month_day} {clean_time}"
                    
            except (ValueError, IndexError):
                # If parsing fails, return original
                pass
                
        return time_str

    def get_display_text(self) -> str:
        parts: List[str] = []
        
        # Build team and score display
        if self.teams:
            # Sort teams to ensure away team is first, home team is second
            away_team = None
            home_team = None
            
            for t in self.teams:
                if t.get("home_away") == "away":
                    away_team = t
                elif t.get("home_away") == "home":
                    home_team = t
            
            # Games that never happened come back from ESPN with a score of "0"
            # for both teams, which reads as nine "0 at 0" games in a row on a
            # full slate — and on a postponed game it looks like a real result.
            # Show the season record instead, or just the team name when there
            # isn't one (season openers, leagues ESPN doesn't carry records for).
            never_played = self.was_never_played

            def team_display(team: Dict) -> str:
                abbrev = team.get("name") or team.get("abbreviation", "?")
                if never_played:
                    record = team.get("record", "")
                    return f"{abbrev} ({record})" if record else abbrev
                score = team.get("score")
                return f"{abbrev}{' ' + score if score else ''}"

            # Build display with proper away @ home ordering
            if away_team and home_team:
                # Standard case: we have both home and away identified
                display_parts = [team_display(t) for t in (away_team, home_team)]
            else:
                # Fallback: home_away not available, use teams as-is
                display_parts = [team_display(t) for t in self.teams]
            
            # At a neutral site neither team is at the other's place.
            neutral = ((self.raw or {}).get("competitions") or [{}])[0].get("neutralSite")
            parts.append((" vs " if neutral else " at ").join(display_parts))
        else:
            parts.append(self.name)
        
        # Determine if this is a football game for special formatting
        is_football = self.league in ['NFL', 'NCAAF'] if self.league else \
                     any(keyword in self.name.lower() for keyword in ['ncaaf', 'nfl']) or \
                     any(keyword in str(self.raw).lower() for keyword in ['football'])
        
        # Add status and timing information
        if self.status and self.status.lower() == "in progress":
            # For live games, show the inning/quarter/period situation
            if self.start_time:
                # Check for baseball inning info
                if any(inning in self.start_time.lower() for inning in ['top', 'bot', 'end', 'mid']):
                    parts.append(f"[{self.start_time}]")
                # Check for football quarter/time info  
                elif any(quarter in self.start_time.lower() for quarter in ['1st', '2nd', '3rd', '4th', 'ot']):
                    parts.append(f"[{self.start_time}]")
                # Check for other sports time/period formats
                elif " - " in self.start_time and any(period in self.start_time.lower() for period in ['quarter', 'period', 'half']):
                    parts.append(f"[{self.start_time}]")
                else:
                    parts.append(f"[{self.status}]")
            else:
                parts.append(f"[{self.status}]")
        elif self.status and self.status.lower() == "final":
            # For final games, show final status (may include extra innings)
            if self.start_time and "final" in self.start_time.lower():
                parts.append(f"[{self.start_time}]")
            else:
                parts.append(f"[{self.status}]")
        elif self.status and self.status.lower() == "scheduled":
            # For scheduled games, show start time
            if self.start_time:
                # Clean up the time display - use enhanced football formatting
                time_display = self.start_time
                if is_football:
                    time_display = self._format_football_time(time_display)
                
                if " - " in time_display and not is_football:
                    time_part = time_display.split(" - ", 1)[1]
                    parts.append(f"({time_part})")
                else:
                    parts.append(f"({time_display})")
            else:
                parts.append(f"[{self.status}]")
        elif self.status:
            # For other statuses (Postponed, Delayed, etc.)
            parts.append(f"[{self.status}]")
        elif self.start_time:
            # Fallback: show start time for games without clear status
            time_display = self.start_time
            if is_football:
                time_display = self._format_football_time(time_display)
            parts.append(f"({time_display})")
        
        return " ".join(parts)

    def has_scores(self) -> bool:
        return any(t.get("score") for t in self.teams)
