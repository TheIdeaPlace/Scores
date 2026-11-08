from typing import Any, Dict, List
import espn_api
import error_log
from exceptions import ApiError, SOMETHING_WENT_WRONG

__all__ = ["ApiService"]

class ApiService:
    """Service class to wrap espn_api functions with uniform error handling."""

    @staticmethod
    def _call(func, *args, **kwargs):
        """Every failure comes out as an ApiError in words a screen can read out. One that
        isn't already is a bug, and its own text goes to the log, not to a screen reader."""
        try:
            return func(*args, **kwargs)
        except ApiError:
            raise
        except Exception as e:
            error_log.log_handled()
            raise ApiError(SOMETHING_WENT_WRONG) from e

    @staticmethod
    def get_leagues() -> List[str]:
        return ApiService._call(espn_api.get_leagues)

    @staticmethod
    def get_scores(league: str, date=None, week=None, seasontype=None, season=None) -> List[Dict]:
        return ApiService._call(espn_api.get_scores, league, date, week, seasontype, season)

    @staticmethod
    def freshen_live_games(league: str, games: List[Dict]) -> List[Dict]:
        """A football week's games with live ones from today's fresher scoreboard."""
        return ApiService._call(espn_api.freshen_live_games, league, games)

    @staticmethod
    def get_mlb_wildcard_standings() -> Dict:
        """MLB wild card race as {"AL": [...], "NL": [...]}; {} when unavailable."""
        return ApiService._call(espn_api.get_mlb_wildcard_standings) or {}

    @staticmethod
    def get_news(league: str, limit: int = 25) -> List[Dict]:
        """Get news headlines for a league with configurable limit
        
        Args:
            league: League identifier (e.g., 'MLB', 'NFL') 
            limit: Number of articles to retrieve (default: 25, max: 50)
        """
        return ApiService._call(espn_api.get_news, league, limit)

    @staticmethod
    def get_standings(league: str) -> List[Dict]:
        return ApiService._call(espn_api.get_standings, league)

    @staticmethod
    def get_teams(league: str) -> List[Dict]:
        """Every team in a league, with its standings row where it has one."""
        return ApiService._call(espn_api.get_teams, league)

    @staticmethod
    def get_team_schedule(league: str, team_id: str, days_ahead: int = 30, days_behind: int = 30, season=None) -> List[Dict]:
        return ApiService._call(espn_api.get_team_schedule, league, team_id, days_ahead, days_behind, season)

    @staticmethod
    def get_team_schedule_and_season(league: str, team_id: str, season=None) -> tuple:
        """(schedule, the season it is from), which isn't the one asked for when it falls back."""
        return ApiService._call(espn_api.get_team_schedule_and_season, league, team_id, season=season)

    @staticmethod
    def get_favorite_card_schedule(league: str, team_id: str) -> List[Dict]:
        """A favorite team's games for its card on Home, as favorite_card.card_games."""
        return ApiService._call(espn_api.get_favorite_card_schedule, league, team_id)

    @staticmethod
    def get_available_seasons(league: str) -> List[tuple]:
        return ApiService._call(espn_api.get_available_seasons, league)

    @staticmethod
    def get_game_details(league: str, game_id: str) -> Dict:
        return ApiService._call(espn_api.get_game_details, league, game_id)

    @staticmethod
    def extract_meaningful_game_info(details: Dict) -> Dict:
        return ApiService._call(espn_api.extract_meaningful_game_info, details)

    @staticmethod
    def format_complex_data(key: str, value: Any) -> str:
        return ApiService._call(espn_api.format_complex_data, key, value)

    @staticmethod
    def get_player_statistics(league: str) -> Dict:
        """A league's player leaders. A failed request raises ApiError."""
        return ApiService._call(espn_api.get_player_statistics, league)
    
    @staticmethod
    def get_team_statistics(league: str) -> Dict:
        """Get only team statistics for a league (faster)"""
        return ApiService._call(espn_api.get_team_statistics, league)
    
    @staticmethod
    def get_stat_glossary(league: str) -> Dict:
        """ESPN's definitions of a league's statistics. A failed request raises ApiError."""
        return ApiService._call(espn_api.get_stat_glossary, league)

    @staticmethod
    def get_rankings(league: str) -> Dict:
        """Get poll/ranking data for a league"""
        return ApiService._call(espn_api.get_rankings, league)

    @staticmethod
    def get_transactions(league: str, team_id: str = None, limit: int = 50, page: int = 1):
        """Returns (list, has_more)."""
        return ApiService._call(espn_api.get_transactions, league, team_id, limit, page)

    @staticmethod
    def get_transactions_from(league: str, cursor: Dict, team_id: str = None) -> Dict:
        """One load of the Transactions screen: {"rows", "next", "oldest_year"}."""
        return ApiService._call(espn_api.get_transactions_from, league, cursor, team_id)

    @staticmethod
    def get_team_info(league: str, team_id: str) -> Dict:
        return ApiService._call(espn_api.get_team_info, league, team_id)

    @staticmethod
    def get_team_roster(league: str, team_id: str) -> List[Dict]:
        return ApiService._call(espn_api.get_team_roster, league, team_id)

    @staticmethod
    def get_team_news(league: str, team_id: str, limit: int = 25) -> List[Dict]:
        return ApiService._call(espn_api.get_team_news, league, team_id, limit)

    @staticmethod
    def get_team_transactions(league: str, team_id: str, limit: int = 25) -> List[Dict]:
        return ApiService._call(espn_api.get_team_transactions, league, team_id, limit)

    @staticmethod
    def get_draft(year: int) -> Dict:
        return ApiService._call(espn_api.get_draft, year)

    @staticmethod
    def get_draft_round(year: int, round_num: int) -> List[Dict]:
        return ApiService._call(espn_api.get_draft_round, year, round_num)

    @staticmethod
    def get_golf_leaderboard(tour: str, date: str = None, event_id: str = None) -> Dict:
        return ApiService._call(espn_api.get_golf_leaderboard, tour, date, event_id)

    @staticmethod
    def get_golf_schedule(tour: str) -> List[Dict]:
        return ApiService._call(espn_api.get_golf_schedule, tour)

    @staticmethod
    def get_world_cup_standings(league: str) -> List[Dict]:
        return ApiService._call(espn_api.get_world_cup_standings, league)

    @staticmethod
    def get_world_cup_scores_range(league: str, start_date, end_date) -> List[Dict]:
        return ApiService._call(espn_api.get_world_cup_scores_range, league, start_date, end_date)

    @staticmethod
    def get_fantasy_cheatsheet(season: int = None, max_rank: int = None) -> Dict:
        """Fantasy football draft board: {'season': int, 'players': [...]}."""
        return ApiService._call(espn_api.get_fantasy_cheatsheet, season, max_rank)
