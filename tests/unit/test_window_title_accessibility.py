#!/usr/bin/env python3
"""
Test window title accessibility functionality

Tests that window titles are properly updated to reflect user location
in the application for improved screen reader accessibility.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt
    PyQt6_available = True
except ImportError:
    PyQt6_available = False


class TestWindowTitleAccessibility(unittest.TestCase):
    """Test cases for window title accessibility features"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        if not PyQt6_available:
            raise unittest.SkipTest("PyQt6 not available for testing")
        
        # Create QApplication if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()
    
    def setUp(self):
        """Set up each test"""
        # Mock the sports scores app to avoid GUI dependencies
        self.mock_app = Mock()
        self.mock_app.base_title = "Sports Scores"
        self.mock_app.current_context = []

        # Import the actual update_window_title method
        from scores import SportsScoresApp
        self.app_class = SportsScoresApp

        # Real QWidgets handed out as view parents; held so Qt doesn't collect
        # them out from under a live child view.
        self._parents = []

    def tearDown(self):
        """Release the parent widgets created for this test"""
        for parent in self._parents:
            parent.deleteLater()
        self._parents.clear()

    def make_parent_app(self, **attrs):
        """A stand-in for the main app, usable as a real view parent.

        The views subclass QWidget, and Qt's C++ constructor rejects a Mock
        outright — it needs an actual QWidget. So the parent is real and only
        the app API the views reach for is mocked onto it.
        """
        parent = QWidget()
        parent.update_window_title = Mock()
        for name, value in attrs.items():
            setattr(parent, name, value)
        self._parents.append(parent)
        return parent

    def test_update_window_title_base_case(self):
        """Test window title update with no context (home view)"""
        # Create mock app with setWindowTitle method
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        # Import and bind the method
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test base case - no context
        update_method()
        mock_app.setWindowTitle.assert_called_with("Sports Scores")
        
    def test_update_window_title_single_context(self):
        """Test window title with single context item (league view)"""
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        # Import and bind the method
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test single context - e.g., MLB league view
        update_method(["MLB"])
        mock_app.setWindowTitle.assert_called_with("MLB - Sports Scores")
        
    def test_update_window_title_multiple_context(self):
        """Test window title with multiple context items (detailed views)"""
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        # Import and bind the method
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test multiple context - e.g., MLB standings
        update_method(["Standings", "MLB"])
        mock_app.setWindowTitle.assert_called_with("MLB, Standings - Sports Scores")
        
    def test_update_window_title_game_context(self):
        """Test window title with game-specific context"""
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        # Import and bind the method
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test game context - e.g., specific game details
        update_method(["Yankees vs Red Sox", "MLB"])
        mock_app.setWindowTitle.assert_called_with("MLB, Yankees vs Red Sox - Sports Scores")
        
    def test_update_window_title_complex_context(self):
        """Test window title with complex multi-level context"""
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        # Import and bind the method
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test complex context - e.g., game statistics within a game
        update_method(["Box Score", "Yankees vs Red Sox", "MLB"])
        mock_app.setWindowTitle.assert_called_with("MLB, Yankees vs Red Sox, Box Score - Sports Scores")

    def test_window_title_pattern_compliance(self):
        """Test that titles follow the specified pattern for screen readers"""
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Test various scenarios match the expected pattern
        test_cases = [
            # (input_context, expected_title)
            (None, "Sports Scores"),
            ([], "Sports Scores"),
            (["Live Scores"], "Live Scores - Sports Scores"),
            (["MLB"], "MLB - Sports Scores"),
            (["Standings", "MLB"], "MLB, Standings - Sports Scores"),
            (["News", "NFL"], "NFL, News - Sports Scores"),
            (["Team Schedule", "Patriots", "NFL"], "NFL, Patriots, Team Schedule - Sports Scores"),
        ]
        
        for context, expected in test_cases:
            with self.subTest(context=context):
                update_method(context)
                mock_app.setWindowTitle.assert_called_with(expected)

    @patch('scores.ApiService')
    def test_home_view_title_update(self, mock_api_service):
        """Test that HomeView correctly updates window title"""
        # Mock API service to return some leagues
        mock_api_service.get_leagues.return_value = ['MLB', 'NFL', 'NBA']
        
        from scores import HomeView

        mock_parent = self.make_parent_app()

        # Create HomeView and call on_show
        home_view = HomeView(mock_parent)
        home_view.setup_ui()
        home_view.on_show()
        
        # Verify the title was updated correctly
        mock_parent.update_window_title.assert_called_with()

    def test_league_view_title_update(self):
        """Test that LeagueView correctly updates window title with league context"""
        from scores import LeagueView

        mock_parent = self.make_parent_app()

        # Create LeagueView with specific league
        with patch('scores.ApiService') as mock_api:
            mock_api.get_scores.return_value = []
            mock_api.get_news.return_value = []
            
            league_view = LeagueView(mock_parent, "MLB")
            league_view.on_show()
            
            # The title names the league, and the date shown, which isn't in the list
            label = league_view.date_label.text().removeprefix("Date: ")
            mock_parent.update_window_title.assert_called_with([label, "MLB"])

    def test_live_scores_view_title_update(self):
        """Test that LiveScoresView correctly updates window title"""
        from scores import LiveScoresView

        mock_parent = self.make_parent_app()

        # Create LiveScoresView and call on_show
        live_scores_view = LiveScoresView(mock_parent)
        live_scores_view.on_show()
        
        # Verify the title was updated correctly
        mock_parent.update_window_title.assert_called_with(["Live Scores"])

    def test_game_details_view_title_update(self):
        """Test that GameDetailsView correctly updates window title with game context"""
        from scores import GameDetailsView

        mock_parent = self.make_parent_app(config={})

        # Create GameDetailsView with specific league and game
        with patch('scores.ApiService') as mock_api:
            mock_api.get_game_details.return_value = {}
            mock_api.extract_meaningful_game_info.return_value = {
                'teams': [
                    {'name': 'Yankees', 'home_away': 'away', 'record': '90-72'},
                    {'name': 'Red Sox', 'home_away': 'home', 'record': '78-84'}
                ],
                'status': 'Final'
            }
            
            game_view = GameDetailsView(mock_parent, "MLB", "12345")
            game_view.on_show()
            
            # Should initially set generic title, then update with game info
            expected_calls = [
                unittest.mock.call(["Game Details", "MLB"]),
            ]
            mock_parent.update_window_title.assert_has_calls(expected_calls)

    def test_accessibility_benefits(self):
        """Test that the window title changes provide accessibility benefits"""
        # This test documents the accessibility improvements
        mock_app = Mock()
        mock_app.base_title = "Sports Scores"
        
        from scores import SportsScoresApp
        update_method = SportsScoresApp.update_window_title.__get__(mock_app)
        
        # Simulate user navigation through the app
        navigation_sequence = [
            # User starts at home
            (None, "Sports Scores"),
            # User selects MLB
            (["MLB"], "MLB - Sports Scores"),
            # User views standings
            (["Standings", "MLB"], "MLB, Standings - Sports Scores"),
            # User goes back to MLB, then views a game
            (["Yankees vs Red Sox", "MLB"], "MLB, Yankees vs Red Sox - Sports Scores"),
            # User views box score for that game
            (["Box Score", "Yankees vs Red Sox", "MLB"], "MLB, Yankees vs Red Sox, Box Score - Sports Scores"),
        ]
        
        # Each title change provides context to screen reader users
        for context, expected_title in navigation_sequence:
            update_method(context)
            mock_app.setWindowTitle.assert_called_with(expected_title)
            
            # Verify the title follows accessibility best practices:
            # 1. Most specific information first (for screen readers)
            # 2. Clear hierarchy of context
            # 3. Consistent base application name
            #
            # The context-free home view is the one case with no separator —
            # its title is the bare base name, not "... - Sports Scores".
            if context:
                self.assertTrue(expected_title.endswith(" - Sports Scores"))
            else:
                self.assertEqual(expected_title, "Sports Scores")
            if context and len(context) > 1:
                # Multiple contexts should be comma-separated with most general first
                context_part = expected_title.replace(" - Sports Scores", "")
                # Should start with most general context (league)
                self.assertTrue(any(league in context_part.split(", ")[0] 
                                 for league in ["MLB", "NFL", "NBA", "NHL", "Live Scores"]))


if __name__ == '__main__':
    unittest.main()