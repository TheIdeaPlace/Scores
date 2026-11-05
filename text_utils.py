"""
Text cleaning utilities for ESPN news content.
Handles potential name replacement patterns and other text processing issues.
"""

import re
from typing import Dict, Optional


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class ESPNTextProcessor:
    """Processor for cleaning and fixing ESPN news text content"""
    
    def __init__(self):
        # Common patterns that might indicate unresolved player ID replacements
        self.placeholder_patterns = [
            r'\{\{?\w+\}?\}?',        # {{123}} or {123} or {{unknown_player}}
            r'\[\d+\]',               # [123]
            r'#\d{6,}',               # #123456 (long ID numbers)
            r'player_\d+',            # player_123
            r'athlete_\d+',           # athlete_123
            r'\b\d{6,}\b',            # Standalone long numbers (6+ digits)
            r'[\x01-\x09]',           # Control characters 1-9 (the actual ESPN issue)
            r'\\[1-9]',               # Escaped backslash patterns like \1, \2
        ]
    
    def clean_description(self, description: str, article_data: Optional[Dict] = None) -> str:
        """
        Clean article description text, fixing potential name replacement issues.
        
        Args:
            description: The raw description text from ESPN
            article_data: Optional full article data for context
            
        Returns:
            Cleaned description text
        """
        if not description:
            return description
            
        # Check for placeholder patterns
        has_placeholders = False
        for pattern in self.placeholder_patterns:
            if re.search(pattern, description, re.IGNORECASE):
                has_placeholders = True
                break
        
        if not has_placeholders:
            # No issues detected, return as-is
            return description
            
        # An article this can't make sense of keeps the words it came with, and the rest of
        # the list keeps theirs.
        try:
            # If we found placeholder patterns, try to fix them
            cleaned_text = self._attempt_placeholder_resolution(description, article_data)

            # If we couldn't resolve placeholders, provide a fallback
            if self._still_has_placeholders(cleaned_text):
                return self._create_fallback_description(description, article_data)

            return cleaned_text
        except Exception as e:
            print(f"Couldn't clean a description: {e}")
            return description
    
    def _attempt_placeholder_resolution(self, text: str, article_data: Optional[Dict]) -> str:
        """
        Attempt to resolve placeholder patterns using simple player list mapping.
        ESPN likely sends placeholders as references to a simple ordered player list.
        """
        # Get a simple ordered list of players
        player_names = self._extract_player_names_from_article(article_data) if article_data else []
        
        cleaned_text = text
        
        # Handle control characters with simple index mapping
        def replace_control_char(match):
            char = match.group(0)
            char_code = ord(char)
            # Simple mapping: \1 = player_names[0], \2 = player_names[1], etc.
            if player_names and char_code <= len(player_names):
                return player_names[char_code - 1]  # Convert 1-based to 0-based
            else:
                # Fallback to generic names
                return f'[Player {char_code}]'
        
        # Replace control characters (ASCII 1-9)
        cleaned_text = re.sub(r'[\x01-\x09]', replace_control_char, cleaned_text)
        
        # Handle escaped backslash patterns like \1, \2
        def replace_backslash_pattern(match):
            num = int(match.group(1))
            # Simple mapping: \1 = player_names[0], \2 = player_names[1], etc.
            if player_names and num <= len(player_names):
                return player_names[num - 1]  # Convert 1-based to 0-based
            else:
                # Fallback to generic names
                return f'[Player {num}]'
        
        cleaned_text = re.sub(r'\\([1-9])', replace_backslash_pattern, cleaned_text)
        
        # Handle other placeholder patterns
        remaining_patterns = [p for p in self.placeholder_patterns if p not in [r'[\x01-\x09]', r'\\[1-9]']]
        for pattern in remaining_patterns:
            cleaned_text = re.sub(pattern, '[Player Name]', cleaned_text, flags=re.IGNORECASE)
        
        return cleaned_text
    
    def _extract_player_names_from_article(self, game_data: Dict) -> list:
        """
        Extract player names in the most logical order ESPN would reference them.
        Focus on the most important/relevant players first.
        """
        player_names = []
        
        # Method 1: Get leaders first (usually the story's main players)
        game_data = _as_dict(game_data)
        leaders = _dicts(game_data.get('leaders'))
        for team_leaders in leaders:
            for category in _dicts(team_leaders.get('leaders')):
                # Prioritize key statistical categories 
                category_name = str(category.get('name') or '').lower()
                priority_categories = ['passingyards', 'rushinyards', 'receivingyards']
                
                if any(pri_cat in category_name for pri_cat in priority_categories):
                    for leader in _dicts(category.get('leaders')):
                        athlete = _as_dict(leader.get('athlete'))
                        if athlete.get('displayName'):
                            player_names.append(athlete['displayName'])
        
        # Method 2: Add key players from boxscore passing stats (QBs first)
        boxscore = _as_dict(game_data.get('boxscore'))
        players_data = _dicts(boxscore.get('players'))
        for team in players_data:
            for stat_category in _dicts(team.get('statistics')):
                if stat_category.get('name') == 'passing':  # QBs are often story leaders
                    for athlete_stat in _dicts(stat_category.get('athletes')):
                        athlete = _as_dict(athlete_stat.get('athlete'))
                        if athlete.get('displayName'):
                            player_names.append(athlete['displayName'])
        
        # Method 3: Add other key statistical performers
        for team in players_data:
            for stat_category in _dicts(team.get('statistics')):
                category_name = stat_category.get('name')
                if category_name in ['rushing', 'receiving', 'defensive']:  # Key categories
                    for athlete_stat in _dicts(stat_category.get('athletes')):
                        athlete = _as_dict(athlete_stat.get('athlete'))
                        if athlete.get('displayName'):
                            player_names.append(athlete['displayName'])
        
        # Remove duplicates while preserving order (first occurrence wins)
        seen = set()
        unique_player_names = []
        for name in player_names:
            if name not in seen:
                seen.add(name)
                unique_player_names.append(name)
        
        return unique_player_names
    

    
    def _still_has_placeholders(self, text: str) -> bool:
        """Check if text still contains unresolved placeholder patterns."""
        for pattern in self.placeholder_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _create_fallback_description(self, original_text: str, article_data: Optional[Dict]) -> str:
        """
        Create a fallback description when we can't resolve placeholders.
        """
        headline = _as_dict(article_data).get('headline', '')
        
        if headline:
            return f"Story details available in full article: {headline}"
        else:
            return "Full story details available in the complete article."


# Global instance for easy use
text_processor = ESPNTextProcessor()
