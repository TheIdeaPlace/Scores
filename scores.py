"""
Scores - Sports Analysis Application

The version lives in version.py (imported below) so there is one copy of it for
the app, the updater and the release workflow to agree on.
"""

__author__ = "Kelly Ford"
__description__ = "Sports Analysis Application with ESPN API integration"

import csv
import sys
import webbrowser
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Union
# Add project root to sys.path if running as script
import os
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

def _resource_path(filename):
    """Resolve path to a bundled resource, works both in dev and PyInstaller onefile."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(ROOT_DIR, filename)

import settings
from version import __version__
from services import updater

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QListWidget, QPushButton, QLabel,
    QHBoxLayout, QCheckBox, QDialog, QMessageBox, QTextEdit, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QStackedWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QSpinBox, QComboBox,
    QSizePolicy, QMenu, QProgressDialog, QLineEdit, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QAction, QFont

# Windows UIA notification support
try:
    import platform
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        WINDOWS_UIA_AVAILABLE = True
    else:
        WINDOWS_UIA_AVAILABLE = False
except ImportError:
    WINDOWS_UIA_AVAILABLE = False

# New separated modules
from exceptions import ApiError, DataModelError
from services.api_service import ApiService
from services.venue_service import venue_service
from models.game import GameData
from models.news import NewsData
import live_play_format
from models.standings import StandingsData
from accessible_table import AccessibleTable, StandingsTable, WildCardTable, LeadersTable, BoxscoreTable, InjuryTable

# Text processing utilities
try:
    from text_utils import text_processor
except ImportError:
    text_processor = None
from timezone_utils import convert_espn_time_to_local
from windows_notifications import WindowsNotificationHelper

# Audio system for pitch mapping
try:
    from simple_audio_mapper import SimpleAudioPitchMapper as AudioPitchMapper
    from pitch_exploration_dialog import PitchExplorationDialog
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    AudioPitchMapper = None

# Spatial audio for basketball and hockey plays, the counterpart to the pitch
# mapper above. Separate import so a failure here cannot take baseball with it.
try:
    from play_audio_mapper import PlayAudioMapper
    PLAY_AUDIO_AVAILABLE = True
except ImportError:
    PLAY_AUDIO_AVAILABLE = False
    PlayAudioMapper = None

# Constants
DETAIL_FIELDS = ["boxscore", "plays", "drives", "leaders", "standings", "odds", "injuries", "broadcasts", "news", "gameInfo"]
BASEBALL_STAT_HEADERS = ["Player", "Position", "AB", "R", "H", "RBI", "BB", "SO", "AVG"]
STANDINGS_HEADERS = ["Rank", "Team", "Wins", "Losses", "Win %", "GB", "Streak", "Record"]
TEAM_SUMMARY_HEADERS = ["Team", "Statistic", "Value"]
INJURY_HEADERS = ["Player", "Position", "Team", "Status", "Type", "Details", "Return Date"]
LEADERS_HEADERS = ["Category/Player", "Team", "Statistic", "Value"]
FOCUS_DELAY_MS = 50


def _get_home_leagues(available_leagues):
    """Return available leagues in the user's saved order, filtered by visibility."""
    saved_order = settings.get('sport_order', [])
    visibility = settings.get('sport_visibility', {})
    ordered = [l for l in saved_order if l in available_leagues]
    ordered += [l for l in available_leagues if l not in ordered]
    return [l for l in ordered if visibility.get(l, True)]
WINDOW_WIDTH = 800  # Increased from 600 for better default size
WINDOW_HEIGHT = 600  # Increased from 400 for better default size
DIALOG_WIDTH = 800
DIALOG_HEIGHT = 600
NEWS_DIALOG_WIDTH = 700
NEWS_DIALOG_HEIGHT = 500
STANDINGS_DIALOG_WIDTH = 900
STANDINGS_DIALOG_HEIGHT = 600

def get_pitch_location(horizontal: int, vertical: int, batter_side: str = None) -> str:
    """Convert pitch coordinates to accessible location description
    
    CORRECTED SYSTEM based on ESPN's 3x3 grid (catcher's perspective):
    - ESPN uses ABSOLUTE coordinates (catcher's view)
    - Lower horizontal numbers = LEFT side of plate (X=80 is left edge)
    - Higher horizontal numbers = RIGHT side of plate  
    - Higher vertical numbers = LOWER pitches
    - No handedness adjustment - pure catcher's perspective positioning
    """
    if horizontal is None or vertical is None:
        return ""
    
    # Determine vertical location (height) - adjusted thresholds
    if vertical > 180:  # Lowered threshold for "low"
        height_desc = "Low"
    elif vertical < 140:  # Raised threshold for "high"
        height_desc = "High" 
    else:
        height_desc = "Middle"
    
    # Determine horizontal location (absolute positioning)
    # CORRECTED: Based on ESPN coordinate system from catcher's perspective
    # Lower X values = LEFT side, Higher X values = RIGHT side
    # Left edge of strike zone is at X=80 (based on user analysis)
    # If X=86 is "lower left" section, strike zone might be wider than initially thought
    if 90 <= horizontal <= 170:  # Strike zone center (narrower definition)
        if vertical > 180:  # Adjusted to match above
            return "Low Strike Zone"
        elif vertical < 140:  # Adjusted to match above
            return "High Strike Zone"
        else:
            return "Strike Zone Center"
    
    # No batter handedness adjustment - pure catcher's perspective
    # Lower numbers = LEFT side, Higher numbers = RIGHT side
    if horizontal < 50:
        location = "Far Left"
    elif horizontal < 90:  # Include X=86 as "Left Side"
        location = "Left Side"
    elif horizontal > 220:
        location = "Far Right"
    elif horizontal > 170:
        location = "Right Side"
    else:
        location = "Strike Zone"  # This should have been caught above, but safety net
    
    # Combine height and location
    if "Strike Zone" in location:
        return location  # Already includes height
    else:
        return f"{height_desc} {location}"

class AudioOnFocusAction(QAction):
    """Custom QAction that plays audio when highlighted in menu (for strike zone exploration)"""
    
    def __init__(self, text, parent, audio_callback, zone_id):
        super().__init__(text, parent)
        self.audio_callback = audio_callback
        self.zone_id = zone_id

class StrikeZoneMenu(QMenu):
    """Custom QMenu that plays audio when actions are highlighted"""
    
    def __init__(self, title, parent, audio_callback):
        super().__init__(title, parent)
        self.audio_callback = audio_callback
        self._last_highlighted = None
        self.setToolTipsVisible(True)
        
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # Get the action under the mouse
        action = self.actionAt(event.pos())
        if action and hasattr(action, 'zone_id') and action != self._last_highlighted:
            self._last_highlighted = action
            # Play audio for this zone with a small delay to avoid rapid-fire
            QTimer.singleShot(100, lambda: self.audio_callback(action.zone_id))
    
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        # Handle arrow key navigation
        if event.key() in [Qt.Key.Key_Up, Qt.Key.Key_Down]:
            QTimer.singleShot(50, self._play_highlighted_action_audio)
    
    def _play_highlighted_action_audio(self):
        """Play audio for currently highlighted action"""
        highlighted = self.activeAction()
        if highlighted and hasattr(highlighted, 'zone_id'):
            self.audio_callback(highlighted.zone_id)

class ConfigDialog(QDialog):
    def __init__(self, details, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Game Details")
        layout = QVBoxLayout()
        self.checkboxes = {}
        for d in details:
            cb = QCheckBox(d)
            cb.setChecked(d in selected)
            layout.addWidget(cb)
            self.checkboxes[d] = cb
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)
        self.setLayout(layout)
    def get_selected(self):
        return [d for d, cb in self.checkboxes.items() if cb.isChecked()]

class HomeSettingsDialog(QDialog):
    """Configure home page sport order and visibility."""

    def __init__(self, available_leagues, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Home Page Settings - Sports Scores")
        self.available_leagues = available_leagues
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Check sports to show on the home page. Select an item and use Up/Down to reorder."))

        saved_order = settings.get('sport_order', [])
        visibility = settings.get('sport_visibility', {})
        ordered = [l for l in saved_order if l in available_leagues]
        ordered += [l for l in available_leagues if l not in ordered]

        self.list_widget = QListWidget()
        self.list_widget.setAccessibleName("Sport List")
        self.list_widget.setAccessibleDescription("List of sports. Check or uncheck to show or hide. Select and use Up or Down buttons to reorder.")
        for league in ordered:
            item = QListWidgetItem(league)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = Qt.CheckState.Checked if visibility.get(league, True) else Qt.CheckState.Unchecked
            item.setCheckState(checked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        move_layout = QHBoxLayout()
        up_btn = QPushButton("Move Up")
        up_btn.setAccessibleName("Move selected sport up")
        up_btn.clicked.connect(self._move_up)
        down_btn = QPushButton("Move Down")
        down_btn.setAccessibleName("Move selected sport down")
        down_btn.clicked.connect(self._move_down)
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset)
        move_layout.addWidget(up_btn)
        move_layout.addWidget(down_btn)
        move_layout.addStretch()
        move_layout.addWidget(reset_btn)
        layout.addLayout(move_layout)

        # College football coverage. ESPN serves the two divisions separately, and
        # asking only for FBS hides most of opening weekend, which is largely FCS.
        cfb_layout = QHBoxLayout()
        cfb_layout.addWidget(QLabel("College football games shown:"))
        self.ncaaf_coverage_combo = QComboBox()
        self._ncaaf_coverage_options = [
            ("All Division I (FBS and FCS)", 'all_d1'),
            ("FBS only", 'fbs'),
        ]
        self.ncaaf_coverage_combo.addItems([label for label, _ in self._ncaaf_coverage_options])
        saved_coverage = settings.get('ncaaf_coverage', 'all_d1')
        for i, (_, value) in enumerate(self._ncaaf_coverage_options):
            if value == saved_coverage:
                self.ncaaf_coverage_combo.setCurrentIndex(i)
                break
        self.ncaaf_coverage_combo.setAccessibleName("College football games shown")
        self.ncaaf_coverage_combo.setAccessibleDescription(
            "All Division I shows FBS and FCS together, around 200 games a week, and is the only "
            "setting that shows opening weekend in full. FBS only shows about 100 games a week.")
        cfb_layout.addWidget(self.ncaaf_coverage_combo)
        cfb_layout.addStretch()
        layout.addLayout(cfb_layout)

        self.auto_update_check = QCheckBox("Automatically check for updates at startup")
        self.auto_update_check.setAccessibleDescription(
            "When checked, Scores looks for a newer version each time it starts. "
            "You can always check manually from the home page.")
        self.auto_update_check.setChecked(settings.get('auto_check_updates', True))
        layout.addWidget(self.auto_update_check)

        ok_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._save_and_accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_layout.addStretch()
        ok_layout.addWidget(ok_btn)
        ok_layout.addWidget(cancel_btn)
        layout.addLayout(ok_layout)

        self.setLayout(layout)

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    def _reset(self):
        self.list_widget.clear()
        for league in self.available_leagues:
            item = QListWidgetItem(league)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)

    def _save_and_accept(self):
        order = []
        visibility = {}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            order.append(item.text())
            visibility[item.text()] = (item.checkState() == Qt.CheckState.Checked)
        settings.set('sport_order', order)
        settings.set('sport_visibility', visibility)
        settings.set('auto_check_updates', self.auto_update_check.isChecked())
        settings.set('ncaaf_coverage',
                     self._ncaaf_coverage_options[self.ncaaf_coverage_combo.currentIndex()][1])
        self.accept()


class DatePickerDialog(QDialog):
    """Dialog for selecting a specific date to view scores"""
    
    def __init__(self, current_date, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go to Date")
        self.setModal(True)
        self.selected_date = current_date
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        layout.addWidget(QLabel("Select a date to view scores:"))
        
        # Date controls in a horizontal layout
        date_layout = QHBoxLayout()
        
        # Month selection
        date_layout.addWidget(QLabel("Month:"))
        self.month_combo = QComboBox()
        self.month_combo.setEditable(True)  # Allow typing
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.month_combo.addItems(months)
        self.month_combo.setCurrentIndex(self.selected_date.month - 1)
        date_layout.addWidget(self.month_combo)
        
        # Day selection
        date_layout.addWidget(QLabel("Day:"))
        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 31)
        self.day_spin.setValue(self.selected_date.day)
        self.day_spin.setKeyboardTracking(True)  # Allow typing numbers
        date_layout.addWidget(self.day_spin)
        
        # Year selection
        date_layout.addWidget(QLabel("Year:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(1900, 2030)  # ESPN accepts dates back to 1900 (data available from ~1993)
        self.year_spin.setValue(self.selected_date.year)
        self.year_spin.setKeyboardTracking(True)  # Allow typing numbers
        date_layout.addWidget(self.year_spin)
        
        layout.addLayout(date_layout)
        
        # Update day range when month/year changes
        self.month_combo.currentIndexChanged.connect(self.update_day_range)
        self.year_spin.valueChanged.connect(self.update_day_range)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        ok_btn = QPushButton("Go to Date")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # Set focus to month combo
        self.month_combo.setFocus()
    
    def update_day_range(self):
        """Update the valid day range based on selected month and year"""
        import calendar
        
        month = self.month_combo.currentIndex() + 1
        year = self.year_spin.value()
        
        # Get the number of days in the selected month
        max_days = calendar.monthrange(year, month)[1]
        
        # Update the day spinner range
        current_day = self.day_spin.value()
        self.day_spin.setRange(1, max_days)
        
        # If current day is now invalid, set to max valid day
        if current_day > max_days:
            self.day_spin.setValue(max_days)
    
    def get_selected_date(self):
        """Get the selected date as a datetime.date object"""
        from datetime import date
        
        month = self.month_combo.currentIndex() + 1
        day = self.day_spin.value()
        year = self.year_spin.value()
        
        try:
            return date(year, month, day)
        except ValueError:
            # Invalid date, return current date
            return self.selected_date
    
    def keyPressEvent(self, event):
        """Handle Escape key to close dialog"""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

class BaseView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
    
    def keyPressEvent(self, event):
        """Handle key press events for all views"""
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
        elif event.key() == Qt.Key.Key_Escape:
            # Escape key goes back to previous level
            if self.parent_app and hasattr(self.parent_app, 'go_back'):
                self.parent_app.go_back()
        else:
            super().keyPressEvent(event)
    
    def setup_ui(self):
        pass
    
    def on_show(self):
        pass
    
    def refresh(self):
        """Override in subclasses to implement refresh functionality"""
        pass
    
    def set_focus_with_delay(self, w):
        QTimer.singleShot(FOCUS_DELAY_MS, lambda: w.setFocus())
    
    def set_focus_and_select_first(self, list_widget):
        """Set focus to list widget and select the first item"""
        def focus_and_select():
            list_widget.setFocus()
            if list_widget.count() > 0:
                list_widget.setCurrentRow(0)
        QTimer.singleShot(FOCUS_DELAY_MS, focus_and_select)

class HomeView(BaseView):
    """Home view showing league selection"""
    
    def keyPressEvent(self, event):
        """Handle key press events - but don't handle Escape for home view"""
        if event.key() == Qt.Key.Key_F5:
            self.refresh()
        else:
            super(BaseView, self).keyPressEvent(event)  # Skip BaseView's Escape handling
    
    def setup_ui(self):
        self._fav_loaders = []
        self._build_favorites_container()
        self._rebuild_favorites()

        self.layout.addWidget(QLabel("Select a League:"))

        self.league_list = QListWidget()
        self.league_list.setAccessibleName("League Selection List")
        self.league_list.setAccessibleDescription("List of available sports leagues and live scores")
        
        # Add Live Scores as the first item
        live_scores_item = QListWidgetItem("Live Scores - All Sports")
        live_scores_item.setData(Qt.ItemDataRole.UserRole, "__live_scores__")
        self.league_list.addItem(live_scores_item)
        
        # Add separator
        separator_item = QListWidgetItem("─" * 30)
        separator_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
        self.league_list.addItem(separator_item)
        
        # Load leagues with error handling
        leagues = ApiService.get_leagues()
        if not leagues:
            self._show_api_error("Failed to load leagues")
            return

        for league in _get_home_leagues(leagues):
            self.league_list.addItem(league)

        self._append_footer_items()

        self.league_list.itemActivated.connect(self._on_league_selected)
        self.layout.addWidget(self.league_list)

        # Navigation buttons
        self._add_nav_buttons()
    
    def _on_league_selected(self, item):
        league = item.text()
        user_data = item.data(Qt.ItemDataRole.UserRole)
        
        if user_data == "__live_scores__":
            # Open Live Scores view
            if self.parent_app:
                self.parent_app.open_live_scores()
            return

        if user_data == "__user_guide__":
            guide_path = _resource_path("user_guide.html")
            webbrowser.open(f"file:///{guide_path.replace(os.sep, '/')}")
            return

        if user_data == "__check_updates__":
            if self.parent_app:
                self.parent_app.check_for_updates(manual=True)
            return

        # Golf tours open a dedicated tournament dialog instead of a standard league view
        if league in ("PGA", "LPGA"):
            tour_name = "PGA Tour" if league == "PGA" else "LPGA Tour"
            if self.parent_app:
                self.parent_app.update_window_title([tour_name])
            dialog = GolfTournamentDialog(league, self)
            dialog.exec()
            if self.parent_app:
                self.parent_app.update_window_title()
            return

        # World Cup hubs open their dedicated dialog
        if league in ("WC2026", "WWC2027"):
            display = _WC_DISPLAY_NAMES.get(league, league)
            if self.parent_app:
                self.parent_app.update_window_title([display])
            dialog = WorldCupDialog(league, self)
            dialog.exec()
            if self.parent_app:
                self.parent_app.update_window_title()
            return

        # NFL/NCAAF resolve their own current week from the season calendar, so
        # this no longer pre-computes one. It used to pass a bare week number,
        # which the view could only read as a regular-season week — the reason
        # opening NFL in August landed on the September opener instead of the
        # preseason games being played that day.
        if self.parent_app:
            self.parent_app.open_league(league)
    
    def _add_nav_buttons(self):
        btn_layout = QHBoxLayout()
        settings_btn = QPushButton("Settings")
        settings_btn.setAccessibleName("Home Page Settings")
        settings_btn.setAccessibleDescription("Configure which sports appear on the home page and their order")
        settings_btn.clicked.connect(self._open_settings)
        btn_layout.addWidget(settings_btn)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)

    def _open_settings(self):
        available = ApiService.get_leagues()
        dialog = HomeSettingsDialog(available, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
    
    def _show_api_error(self, message: str):
        """Show API error message to user"""
        error_label = QLabel(f"Error: {message}")
        error_label.setStyleSheet("color: red; font-weight: bold;")
        self.layout.addWidget(error_label)
    
    def on_show(self):
        self.set_focus_and_select_first(self.league_list)
        # Update window title for home view
        if self.parent_app:
            self.parent_app.update_window_title()
    
    def refresh(self):
        """Refresh the league list and favorites section."""
        self._rebuild_favorites()

        self.league_list.clear()

        live_scores_item = QListWidgetItem("Live Scores - All Sports")
        live_scores_item.setData(Qt.ItemDataRole.UserRole, "__live_scores__")
        self.league_list.addItem(live_scores_item)

        separator_item = QListWidgetItem("─" * 30)
        separator_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.league_list.addItem(separator_item)

        leagues = ApiService.get_leagues()
        if not leagues:
            self._show_api_error("Failed to load leagues")
            return

        for league in _get_home_leagues(leagues):
            self.league_list.addItem(league)

        self._append_footer_items()

        self.set_focus_and_select_first(self.league_list)

    def _append_footer_items(self):
        """Add the non-league entries that close the home list.

        Called from both setup_ui and refresh so the two paths cannot drift.
        """
        footer_sep = QListWidgetItem("─" * 30)
        footer_sep.setFlags(Qt.ItemFlag.NoItemFlags)
        self.league_list.addItem(footer_sep)

        guide_item = QListWidgetItem("User Guide")
        guide_item.setData(Qt.ItemDataRole.UserRole, "__user_guide__")
        self.league_list.addItem(guide_item)

        update_item = QListWidgetItem("Check for Updates")
        update_item.setData(Qt.ItemDataRole.UserRole, "__check_updates__")
        self.league_list.addItem(update_item)

    # ---------------------------------------------------------------- favorites

    def _build_favorites_container(self):
        """Create the persistent favorites section (shown/hidden based on data)."""
        self.favorites_container = QWidget()
        fav_layout = QVBoxLayout(self.favorites_container)
        fav_layout.setContentsMargins(0, 0, 0, 4)

        fav_layout.addWidget(QLabel("Favorite Teams:"))

        self.favorites_list = QListWidget()
        self.favorites_list.setMaximumHeight(200)
        self.favorites_list.setAccessibleName("Favorite Teams")
        self.favorites_list.setAccessibleDescription(
            "Your favorite teams. Press Enter to view team details.")
        self.favorites_list.itemActivated.connect(self._on_favorite_activated)
        fav_layout.addWidget(self.favorites_list)

        btn_row = QHBoxLayout()
        up_btn = QPushButton("Move Up")
        up_btn.setAccessibleName("Move selected favorite team up")
        up_btn.clicked.connect(self._move_fav_up)
        down_btn = QPushButton("Move Down")
        down_btn.setAccessibleName("Move selected favorite team down")
        down_btn.clicked.connect(self._move_fav_down)
        remove_btn = QPushButton("Remove from Favorites")
        remove_btn.clicked.connect(self._remove_favorite)
        btn_row.addWidget(up_btn)
        btn_row.addWidget(down_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        fav_layout.addLayout(btn_row)

        self.layout.addWidget(self.favorites_container)
        self.favorites_container.hide()

    def _rebuild_favorites(self):
        """Populate or hide the favorites section."""
        favorites = settings.get_favorites()
        if not favorites:
            self.favorites_container.hide()
            return

        self.favorites_container.show()
        self.favorites_list.clear()
        self._fav_loaders = []

        for fav in favorites:
            item = QListWidgetItem(f"★ {fav['team_name']}  [{fav['league']}]")
            item.setData(Qt.ItemDataRole.UserRole, fav)
            self.favorites_list.addItem(item)
            loader = FavoriteCardLoader(
                fav['team_id'], fav['team_name'],
                fav['league'], fav.get('abbreviation', ''))
            loader.card_ready.connect(self._on_card_ready)
            self._fav_loaders.append(loader)
            # Rebuilds and leaving Home drop _fav_loaders while cards still load.
            _start_detached_thread(loader)

    def _on_card_ready(self, team_id, league, summary, news_lines):
        for i in range(self.favorites_list.count()):
            item = self.favorites_list.item(i)
            fav = item.data(Qt.ItemDataRole.UserRole)
            if fav and fav.get('team_id') == team_id and fav.get('league') == league:
                lines = [f"★ {fav['team_name']}  [{league}]"]
                if summary:
                    lines.append(f"  {summary}")
                for h in news_lines:
                    lines.append(f"  {h}")
                item.setText("\n".join(lines))
                break

    def _on_favorite_activated(self, item):
        fav = item.data(Qt.ItemDataRole.UserRole)
        if not fav:
            return
        try:
            team_data = {
                'team_id': fav['team_id'],
                'team_name': fav['team_name'],
                'abbreviation': fav.get('abbreviation', ''),
                'wins': '', 'losses': '',
            }
            dialog = TeamHubDialog(team_data, fav['league'], self)
            dialog.exec()
            self._rebuild_favorites()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open team: {e}")

    def _move_fav_up(self):
        row = self.favorites_list.currentRow()
        if row <= 0:
            return
        favs = settings.get_favorites()
        favs[row - 1], favs[row] = favs[row], favs[row - 1]
        settings.save_favorites(favs)
        self._rebuild_favorites()
        self.favorites_list.setCurrentRow(row - 1)

    def _move_fav_down(self):
        row = self.favorites_list.currentRow()
        favs = settings.get_favorites()
        if row < 0 or row >= len(favs) - 1:
            return
        favs[row], favs[row + 1] = favs[row + 1], favs[row]
        settings.save_favorites(favs)
        self._rebuild_favorites()
        self.favorites_list.setCurrentRow(row + 1)

    def _remove_favorite(self):
        row = self.favorites_list.currentRow()
        if row < 0:
            return
        favs = settings.get_favorites()
        if row < len(favs):
            del favs[row]
            settings.save_favorites(favs)
            self._rebuild_favorites()


class LiveScoresView(BaseView):
    """View showing live games from all sports"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.monitored_games = set()  # Track games being monitored for notifications
        self.game_data = {}  # Store complete game data for notifications
        self.current_time = datetime.now()
        
        # Initialize Windows UIA notification helper
        self.notification_helper = WindowsNotificationHelper()
        
        # Refresh frequency options (in milliseconds)
        self.refresh_intervals = {
            "30 seconds": 30000,
            "1 minute": 60000,
            "2 minutes": 120000,
            "Manual (F5 only)": 0
        }
        _saved_text = settings.get('auto_refresh_interval', '1 minute')
        self.current_refresh_interval = self.refresh_intervals.get(_saved_text, 60000)

        self._loader = None          # LiveScoresLoader while a load is running
        self._pending_old_scores = {}  # monitored scores captured when a refresh began

        self.setup_ui()
        
        # Setup auto-refresh timer for live updates. Parented to the view so it
        # stops when the view is replaced, instead of refreshing a dead view.
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_live_scores)
        self._update_refresh_timer()
    
    def setup_ui(self):
        # Header with current time
        self.time_label = QLabel()
        self.layout.addWidget(self.time_label)
        
        self.layout.addWidget(QLabel("Live Scores - All Sports:"))
        
        # Refresh frequency control
        refresh_layout = QHBoxLayout()
        refresh_layout.addWidget(QLabel("Update frequency:"))
        
        self.refresh_combo = QComboBox()
        self.refresh_combo.addItems(list(self.refresh_intervals.keys()))
        self.refresh_combo.setCurrentText(settings.get('auto_refresh_interval', '1 minute'))
        self.refresh_combo.currentTextChanged.connect(self._on_refresh_frequency_changed)
        self.refresh_combo.setAccessibleName("Refresh Frequency")
        self.refresh_combo.setAccessibleDescription("Select how often live scores should update automatically")
        refresh_layout.addWidget(self.refresh_combo)
        
        refresh_layout.addStretch()  # Push combo to the left
        self.layout.addLayout(refresh_layout)
        
        # Instructions for manual refresh
        info_label = QLabel("Press 'F5' to refresh manually")
        info_label.setStyleSheet("color: #666; font-style: italic;")
        self.layout.addWidget(info_label)
        
        self.live_scores_list = QListWidget()
        self.live_scores_list.setAccessibleName("Live Scores List")
        self.live_scores_list.setAccessibleDescription("List of currently live games from all sports. Press Alt+M to monitor a game for notifications.")
        self.live_scores_list.itemActivated.connect(self._on_game_selected)
        self.layout.addWidget(self.live_scores_list)
        
        self._add_nav_buttons()
        self.load_live_scores()
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.modifiers() == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_M:
            self._toggle_monitoring()
        elif event.key() == Qt.Key.Key_F5:
            # Provide feedback for manual refresh
            if hasattr(self, 'refresh_combo') and self.refresh_combo.currentText() == "Manual (F5 only)":
                self.notification_helper.announce("Refreshing live scores manually")
            self.refresh_live_scores()
        else:
            super().keyPressEvent(event)
    
    def _toggle_monitoring(self):
        """Toggle monitoring for the currently selected game"""
        current_item = self.live_scores_list.currentItem()
        if not current_item:
            return
            
        game_data = current_item.data(Qt.ItemDataRole.UserRole)
        if not game_data or not isinstance(game_data, dict):
            return
            
        game_id = game_data.get("id", "")
        if not game_id:
            return
        
        if game_id in self.monitored_games:
            self.monitored_games.remove(game_id)
            # Update display to remove monitoring indicator
            text = current_item.text()
            if text.endswith(" - monitoring"):
                current_item.setText(text[:-12])  # Remove " - monitoring"
            self._announce_monitoring(False, game_data)
        else:
            self.monitored_games.add(game_id)
            # Update display to show monitoring indicator
            text = current_item.text()
            if not text.endswith(" - monitoring"):
                current_item.setText(text + " - monitoring")
            self._announce_monitoring(True, game_data)
    
    def _announce_monitoring(self, monitoring: bool, game_data: dict):
        """Announce monitoring status change for accessibility"""
        game_name = game_data.get("name", "Selected game")
        
        # Use Windows UIA notifications for better accessibility
        self.notification_helper.announce_monitoring_change(game_name, monitoring)
        
        # Also update the UI
        status = "now monitoring" if monitoring else "no longer monitoring"
        message = f"{status} {game_name} for score updates"
        self.time_label.setText(f"Live Scores - {message}")
        QTimer.singleShot(3000, self._update_time_label)  # Reset after 3 seconds
    
    def _update_time_label(self):
        """Update the time label with current time"""
        self.current_time = datetime.now()
        time_str = self.current_time.strftime("%I:%M %p")
        refresh_mode = self.refresh_combo.currentText() if hasattr(self, 'refresh_combo') else "30 seconds"
        self.time_label.setText(f"Live Scores - Last updated: {time_str} (Refresh: {refresh_mode})")
    
    def _on_refresh_frequency_changed(self, frequency_text):
        """Handle refresh frequency change"""
        self.current_refresh_interval = self.refresh_intervals[frequency_text]
        settings.set('auto_refresh_interval', frequency_text)
        self._update_refresh_timer()
        
        # Announce the change for accessibility
        if frequency_text == "Manual (F5 only)":
            message = "Automatic refresh disabled. Press F5 to refresh manually."
        else:
            message = f"Refresh frequency set to {frequency_text}"
        
        self.notification_helper.announce(message)
        self._update_time_label()  # Update the display immediately
    
    def _update_refresh_timer(self):
        """Update the refresh timer based on current interval"""
        self.refresh_timer.stop()
        
        if self.current_refresh_interval > 0:
            self.refresh_timer.start(self.current_refresh_interval)
        # If interval is 0 (manual mode), timer stays stopped
    
    def _on_game_selected(self, item):
        """Handle game selection - open game details"""
        game_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(game_data, dict) and game_data.get("golf_tour"):
            tour = game_data["golf_tour"]
            if self.parent_app:
                self.parent_app.update_window_title([game_data.get("tour_name", tour)])
            GolfTournamentDialog(tour, self).exec()
            if self.parent_app:
                self.parent_app.update_window_title(["Live Scores"])
            return
        if game_data and isinstance(game_data, dict):
            game_id = game_data.get("id")
            league = game_data.get("league")
            if game_id and league and self.parent_app:
                # Set the current league for proper navigation
                self.parent_app.current_league = league
                self.parent_app.open_game_details(game_id, from_live_scores=True)
    
    def load_live_scores(self):
        """Start loading live, upcoming, and completed games from all sports.

        The fetch runs on a LiveScoresLoader thread. On a busy college football
        Saturday it is dozens of requests and can take longer than the refresh
        interval; done on the UI thread, that froze the window for good. A load
        already in progress is left to finish rather than started again.
        """
        if self._loader is not None and self._loader.isRunning():
            return
        if self.live_scores_list.count() == 0:
            self.live_scores_list.addItem("Loading live scores...")
        loader = LiveScoresLoader(self._fetch_live_scores)
        loader.data_loaded.connect(self._on_live_scores_loaded)
        loader.error_occurred.connect(self._on_live_scores_error)
        self._loader = loader
        _start_detached_thread(loader)

    def _on_live_scores_error(self, message: str):
        self._show_api_error(f"Failed to load live scores: {message}")
        self._pending_old_scores = {}

    def _on_live_scores_loaded(self, live_games: list, current_date_games: list, golf: list):
        """Show freshly loaded games, keeping the user's place in the list."""
        # An exception escaping a slot aborts the app under PyQt6.
        try:
            self._show_loaded_live_scores(live_games, current_date_games, golf)
        except Exception as e:
            self._show_api_error(f"Failed to load live scores: {e}")
        self._pending_old_scores = {}

    def _show_loaded_live_scores(self, live_games, current_date_games, golf=()):
        current = self.live_scores_list.currentItem()
        current_data = current.data(Qt.ItemDataRole.UserRole) if current else None
        selected_id = current_data.get("id") if isinstance(current_data, dict) else None
        selected_row = self.live_scores_list.currentRow()

        self._render_live_scores(live_games, current_date_games, golf)

        restored = False
        if selected_id:
            for row in range(self.live_scores_list.count()):
                data = self.live_scores_list.item(row).data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("id") == selected_id:
                    self.live_scores_list.setCurrentRow(row)
                    restored = True
                    break
        if not restored and 0 <= selected_row < self.live_scores_list.count():
            self.live_scores_list.setCurrentRow(selected_row)

        self._check_monitored_scores(self._pending_old_scores)

    def _render_live_scores(self, live_games, current_date_games, golf=()):
        """Fill the list from already-fetched games. No network access."""
        from datetime import datetime

        self.live_scores_list.clear()
        self.game_data.clear()
        self._update_time_label()

        try:
            today = datetime.now().date()

            # Categorize games
            live_games_dict = {game.get('id', ''): game for game in live_games}
            upcoming_games = []
            completed_games = []

            for game in current_date_games:
                game_id = game.get('game_id', '')
                if game_id not in live_games_dict:
                    # Check if game is upcoming or completed
                    state = game.get('state', '')
                    if state == 'upcoming':
                        upcoming_games.append(game)
                    elif state == 'completed':
                        completed_games.append(game)

            # Sort upcoming games by start time (closest first)
            upcoming_games.sort(key=lambda g: g.get('start_time', ''))
            
            if golf:
                section_header = QListWidgetItem("=== GOLF LIVE ===")
                section_header.setBackground(QColor(200, 255, 200))
                self.live_scores_list.addItem(section_header)
                for t in golf:
                    leaders = "; ".join(f"{pos}. {name}, {score}" for pos, name, score in t["leaders"])
                    text = f"{t['tour_name']}: {t['name']}, {t['status']}"
                    if leaders:
                        text += f". Leaders: {leaders}"
                    item = QListWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole,
                                 {"golf_tour": t["tour"], "tour_name": t["tour_name"]})
                    self.live_scores_list.addItem(item)
                self.live_scores_list.addItem("")

            total_games = len(live_games) + len(upcoming_games) + len(completed_games) + len(golf)
            if total_games == 0:
                self.live_scores_list.addItem(f"No games on {today.strftime('%B %d, %Y')}.")
                return

            # Section 1: Live Games
            if live_games:
                section_header = QListWidgetItem("=== LIVE GAMES ===")
                section_header.setBackground(QColor(200, 255, 200))  # Light green background
                self.live_scores_list.addItem(section_header)
                
                # Group live games by league for better organization
                games_by_league = {}
                for game in live_games:
                    league = game.get("league", "Unknown")
                    if league not in games_by_league:
                        games_by_league[league] = []
                    games_by_league[league].append(game)
                
                for league in sorted(games_by_league.keys()):
                    # Add league header
                    league_item = QListWidgetItem(f"--- {league} ---")
                    league_item.setBackground(QColor(240, 240, 240))
                    self.live_scores_list.addItem(league_item)
                    
                    for game in games_by_league[league]:
                        game_id = game.get("id", "")
                        game_name = game.get("name", "Unknown Game")
                        status = game.get("status", "")
                        teams = game.get("teams", [])
                        recent_play = game.get("recent_play", "")
                        game_league = game.get("league", "")
                        
                        # Build display text
                        display_text = f"{game_name}"
                        if teams and len(teams) >= 2:
                            # game_name reads "Away at Home"; ESPN lists home first.
                            team1, team2 = live_play_format.away_then_home(teams)
                            score1 = team1.get("score", "")
                            score2 = team2.get("score", "")
                            if score1 and score2:
                                display_text += f" - {score1}-{score2}"
                        
                        if status and game_league not in ["NFL", "NCAAF"]:
                            display_text += f" ({status})"
                        
                        # Enhanced display for different sports. recent_play is
                        # the status itself when the scoreboard had no play.
                        if recent_play and len(recent_play.strip()) > len((status or "").strip()):
                            display_text = live_play_format.format_live_game(
                                game_league, teams, status, recent_play, display_text)
                        elif status and game_league in ["NFL", "NCAAF"]:
                            # Other leagues already have the status above.
                            display_text += f" ({status})"
                        
                        item = QListWidgetItem(display_text)
                        item.setData(Qt.ItemDataRole.UserRole, game)
                        self.live_scores_list.addItem(item)
                        
                        if game_id:
                            self.game_data[game_id] = game
                
                self.live_scores_list.addItem("")

            # Section 2: Upcoming Games
            if upcoming_games:
                section_header = QListWidgetItem("=== UPCOMING GAMES ===")
                section_header.setBackground(QColor(255, 255, 200))  # Light yellow background
                self.live_scores_list.addItem(section_header)
                
                # Group upcoming games by league
                upcoming_by_league = {}
                for game in upcoming_games:
                    league = game.get('league', 'Unknown')
                    if league not in upcoming_by_league:
                        upcoming_by_league[league] = []
                    upcoming_by_league[league].append(game)
                
                for league in sorted(upcoming_by_league.keys()):
                    league_item = QListWidgetItem(f"--- {league} ---")
                    league_item.setBackground(QColor(240, 240, 240))
                    self.live_scores_list.addItem(league_item)
                    
                    for game in upcoming_by_league[league]:
                        display_text = self._format_game_display(game)
                        item = QListWidgetItem(display_text)
                        # Prepare game data in format expected by _on_game_selected
                        game_data = game.get('raw_data', game)
                        if 'game_id' in game and 'id' not in game_data:
                            game_data = dict(game_data) if isinstance(game_data, dict) else {}
                            game_data['id'] = game.get('game_id')
                            game_data['league'] = game.get('league')
                        item.setData(Qt.ItemDataRole.UserRole, game_data)
                        self.live_scores_list.addItem(item)
                
                self.live_scores_list.addItem("")

                self.live_scores_list.addItem("")

            # Section 3: Completed Games
            if completed_games:
                section_header = QListWidgetItem("=== COMPLETED GAMES ===")
                section_header.setBackground(QColor(220, 220, 220))  # Light gray background
                self.live_scores_list.addItem(section_header)
                
                # Group completed games by league
                completed_by_league = {}
                for game in completed_games:
                    league = game.get('league', 'Unknown')
                    if league not in completed_by_league:
                        completed_by_league[league] = []
                    completed_by_league[league].append(game)
                
                for league in sorted(completed_by_league.keys()):
                    league_item = QListWidgetItem(f"--- {league} ---")
                    league_item.setBackground(QColor(240, 240, 240))
                    self.live_scores_list.addItem(league_item)
                    
                    for game in completed_by_league[league]:
                        display_text = self._format_game_display(game)
                        item = QListWidgetItem(display_text)
                        # Prepare game data in format expected by _on_game_selected
                        game_data = game.get('raw_data', game)
                        if 'game_id' in game and 'id' not in game_data:
                            game_data = dict(game_data) if isinstance(game_data, dict) else {}
                            game_data['id'] = game.get('game_id')
                            game_data['league'] = game.get('league')
                        item.setData(Qt.ItemDataRole.UserRole, game_data)
                        self.live_scores_list.addItem(item)

                self.live_scores_list.addItem("")
        except Exception as e:
            self._show_api_error(f"Failed to load live scores: {str(e)}")
    
    def refresh_live_scores(self):
        """Refresh live scores and check for changes in monitored games"""
        old_scores = {}
        
        # Capture current scores for monitored games
        for game_id in self.monitored_games:
            if game_id in self.game_data:
                game = self.game_data[game_id]
                teams = game.get("teams", [])
                if len(teams) >= 2:
                    old_scores[game_id] = (
                        teams[0].get("score", ""),
                        teams[1].get("score", "")
                    )
        
        if self._loader is not None and self._loader.isRunning():
            return  # the load in flight will bring the latest scores
        self._pending_old_scores = old_scores
        self.load_live_scores()

    def _check_monitored_scores(self, old_scores):
        """Announce score changes in monitored games since old_scores was taken."""
        for game_id in self.monitored_games:
            if game_id in self.game_data and game_id in old_scores:
                game = self.game_data[game_id]
                teams = game.get("teams", [])
                if len(teams) >= 2:
                    new_scores = (
                        teams[0].get("score", ""),
                        teams[1].get("score", "")
                    )
                    old_score = old_scores[game_id]
                    
                    if new_scores != old_score:
                        self._notify_score_change(game, old_score, new_scores)
    
    def _notify_score_change(self, game, old_scores, new_scores):
        """Notify about score changes in monitored games"""
        game_name = game.get("name", "Game")
        teams = game.get("teams", [])
        
        if len(teams) >= 2:
            team1_name = teams[0].get("name", "Team 1") 
            team2_name = teams[1].get("name", "Team 2")
            score_text = f"{team1_name} {new_scores[0]} - {team2_name} {new_scores[1]}"
            
            # Use Windows UIA notifications for accessibility
            self.notification_helper.notify_score_change(game_name, score_text)
            
            # Also update the UI
            self.time_label.setText(f"SCORE UPDATE: {game_name} - {score_text}")
            QTimer.singleShot(5000, self._update_time_label)  # Reset after 5 seconds
    
    def _add_nav_buttons(self):
        """Add navigation buttons"""
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh (F5)")
        refresh_btn.clicked.connect(self.refresh_live_scores)
        btn_layout.addWidget(refresh_btn)
        
        back_btn = QPushButton("Back to Home")
        back_btn.clicked.connect(lambda: self.parent_app.show_home() if self.parent_app else None)
        btn_layout.addWidget(back_btn)
        
        self.layout.addLayout(btn_layout)
    
    def on_show(self):
        """Called when view is shown"""
        self.set_focus_and_select_first(self.live_scores_list)
        # Update window title for live scores view
        if self.parent_app:
            self.parent_app.update_window_title(["Live Scores"])
    
    def _show_api_error(self, message: str):
        """Show API error message to user"""
        error_label = QLabel(f"Error: {message}")
        error_label.setStyleSheet("color: red; font-weight: bold;")
        self.layout.addWidget(error_label)
    
    @staticmethod
    def _fetch_live_scores():
        """Everything Live Scores shows: (live games, today's games, golf).

        Works the way the iOS app does: one scoreboard request per league for
        today, all in parallel, with live games and their latest plays read
        from those same scoreboards. It used to fetch every scoreboard twice
        and a full game summary per live game on top, 85 requests and over a
        minute on a busy Saturday. Golf tournaments come from their own
        scoreboards, since they list golfers rather than two teams.

        Runs on the LiveScoresLoader thread, so it must not touch widgets.
        """
        import espn_api
        from concurrent.futures import ThreadPoolExecutor

        def golf(tour):
            try:
                return espn_api.get_live_golf_tournament(tour)
            except Exception as e:
                print(f"Error fetching {tour} tournament: {e}")
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            golf_future = list(pool.map(golf, espn_api.GOLF_TOURS))
            today_games = LiveScoresView._get_today_games_all_sports()

        live_games = []
        for game in today_games:
            if game.get('state') != 'live':
                continue
            raw = game['raw_data']
            comp = (raw.get('competitions') or [{}])[0]
            status = raw.get('start_time') or raw.get('status') or "In Progress"
            live_games.append({
                "id": game['game_id'],
                "name": raw.get('name', game.get('name', '')),
                "league": game['league'],
                "status": status,
                "teams": [{"name": t.get("name", ""), "score": str(t.get("score", "")),
                           "home_away": t.get("home_away", "")}
                          for t in raw.get('teams', [])],
                "recent_play": espn_api.scoreboard_live_detail(game['league'], comp) or status,
            })
        return live_games, today_games, [g for g in golf_future if g]

    @staticmethod
    def _get_today_games_all_sports():
        """Get all games for the current date from every team sport.

        Golf is left out: its scoreboards list golfers, which read here as
        "Unknown at Unknown". _fetch_live_scores fetches it separately.
        Runs on the LiveScoresLoader thread, so it must not touch widgets.
        """
        from models.game import GameData
        from datetime import datetime
        from espn_api import GOLF_TOURS

        all_games = []
        today = datetime.now().date()

        leagues = [lg for lg in ApiService.get_leagues() if lg not in GOLF_TOURS]

        def fetch(league):
            try:
                return ApiService.get_scores(league, today) or []
            except Exception as e:
                print(f"Error fetching {league} games: {e}")
                return []

        # One scoreboard per league, all in parallel.
        from concurrent.futures import ThreadPoolExecutor
        from espn_api import LIVE_FETCH_WORKERS
        with ThreadPoolExecutor(max_workers=LIVE_FETCH_WORKERS) as pool:
            scoreboards = list(pool.map(fetch, leagues))

        for league, scores_data in zip(leagues, scoreboards):
            try:
                for game_raw in scores_data:
                    # Create GameData object for consistent formatting
                    game = GameData(game_raw, league)
                    # Convert to format expected by live scores view
                    game_dict = {
                        'game_id': game_raw.get('id', ''),
                        'league': league,
                        'name': game.name,
                        'teams': game.teams,
                        'status': game.status,
                        'start_time': game.start_time,
                        'display_text': game.get_display_text(),
                        'raw_data': game_raw,
                        'game_data': game  # Keep reference to GameData object
                    }

                    # Determine game state using ESPN's authoritative state field
                    # from the raw competition data (in/post/pre), then fall back to
                    # string matching on the status description.
                    competitions_raw = game_raw.get('competitions', [])
                    comp_state = ''
                    if competitions_raw:
                        comp_state = (
                            competitions_raw[0]
                            .get('status', {})
                            .get('type', {})
                            .get('state', '')
                            .lower()
                        )

                    if comp_state == 'in':
                        game_dict['state'] = 'live'
                    elif comp_state == 'post':
                        game_dict['state'] = 'completed'
                    elif comp_state == 'pre':
                        game_dict['state'] = 'upcoming'
                    else:
                        # Fallback: match on the human-readable description string
                        status_lower = game.status.lower() if game.status else ''
                        if 'progress' in status_lower or status_lower in ('live', 'halftime'):
                            game_dict['state'] = 'live'
                        elif status_lower.startswith('final') or status_lower == 'completed':
                            game_dict['state'] = 'completed'
                        elif status_lower in ('scheduled', 'upcoming'):
                            game_dict['state'] = 'upcoming'
                        else:
                            # Unknown — default to upcoming so it still appears
                            game_dict['state'] = 'upcoming'
                    
                    all_games.append(game_dict)
            except Exception as e:
                print(f"Error fetching {league} games: {e}")
                continue

        return all_games

    def _format_game_display(self, game):
        """Format a game for display in the list using GameData if available"""
        try:
            # Use the pre-formatted display text if available
            if 'display_text' in game and game['display_text']:
                return game['display_text']

            # Use GameData object if available
            if 'game_data' in game and game['game_data']:
                return game['game_data'].get_display_text()
            
            # Fallback to manual formatting
            home_team = game.get('home_team', {})
            away_team = game.get('away_team', {})
            home_score = game.get('home_score', '')
            away_score = game.get('away_score', '')
            status = game.get('status', '')
            
            # Build team display
            home_name = home_team.get('name', home_team.get('abbreviation', 'TBD'))
            away_name = away_team.get('name', away_team.get('abbreviation', 'TBD'))
            
            # Format scores if available
            if home_score and away_score:
                team_display = f"{away_name} {away_score} at {home_name} {home_score}"
            else:
                team_display = f"{away_name} at {home_name}"
            
            # Add status info
            if status:
                return f"{team_display} ({status})"
            else:
                return team_display
        except Exception as e:
            print(f"Error formatting game display: {e}")
            return game.get('name', 'Unknown Game')
    
    def refresh(self):
        """Refresh the live scores"""
        self.refresh_live_scores()

class LeagueView(BaseView):
    """View showing scores for a specific league"""
    
    def __init__(self, parent=None, league=None, week=None, season_type=None):
        super().__init__(parent)
        self.league = league
        self.news_headlines = []

        # Bumped by every load_scores, so a slow load that finishes after a
        # newer one (stepping weeks quickly) is dropped instead of shown.
        self._scores_generation = 0
        # (generation, UserRole) of the row a refresh should land on; tied to
        # its load so it can't carry over to another day, week or failed load.
        self._reselect = None
        # Dialogs whose data is being fetched by _fetch_then, by title.
        self._background_fetches = {}

        # For football leagues, the season (and, unless one was asked for, the
        # week) comes from ESPN's calendar. That is a network request, so the
        # first load fetches it on its thread; until then these are placeholders.
        if self.is_football_league():
            self._calendar_pending = True
            self._requested_week = week
            self._requested_season_type = season_type
            self.current_season = datetime.now().year
            self.current_week = week if week is not None else 1
            self.current_season_type = season_type or 2
            self.current_date = None
        else:
            self._calendar_pending = False
            self.current_season = None
            self.current_week = None
            self.current_season_type = None
            self.current_date = datetime.now().date()

        self.setup_ui()

    def is_football_league(self):
        return self.league in ["NFL", "NCAAF"]
    
    def setup_ui(self):
        # Navigation label (date or week)
        self.date_label = QLabel()
        self.date_label.setAccessibleName(
            "Week shown" if self.is_football_league() else "Date shown")
        self.layout.addWidget(self.date_label)

        self.layout.addWidget(QLabel(f"Scores for {self.league}:"))

        self.scores_list = QListWidget()
        self.scores_list.setAccessibleName("Scores List")
        self.scores_list.setAccessibleDescription("List of games and scores for the selected date or week")
        self.scores_list.itemActivated.connect(self._on_score_item_selected)
        self.layout.addWidget(self.scores_list)

        self._add_nav_buttons()
        self.load_scores()
    
    def _on_score_item_selected(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data == "__news__":
            self._show_news_dialog(); return
        if data == "__standings__":
            self._show_standings_dialog(); return
        if data == "__polls__":
            self._show_polls_dialog(); return
        if data == "__statistics__":
            self._show_statistics_dialog(); return
        if data == "__teams__":
            self._show_teams_dialog(); return
        if data == "__transactions__":
            self._show_transactions_dialog(); return
        if data == "__draft__":
            self._show_draft_dialog(); return
        if data == "__fantasy__":
            self._show_fantasy_cheatsheet(); return
        if data == "__venues__":
            self._show_venues_dialog(); return
        if data == "__bowls__":
            self._show_bowls_and_playoffs(); return
        if data and isinstance(data, str) and self.parent_app:
            self.parent_app.open_game_details(data)

    def load_scores(self, reselect=None):
        """Start loading scores for the current date or week.

        `reselect` is the UserRole of the row to land on once loaded (a
        refresh's selected game); otherwise the first row.

        The scoreboard, the news and, the first time, the football calendar
        are fetched on a LeagueScoresLoader thread. On a college football
        Saturday the scoreboard alone is several MB; fetched here it froze the
        window on every open, every week step and every Back from a game.
        """
        self._scores_generation += 1
        self._reselect = (self._scores_generation, reselect) if reselect is not None else None
        football = self.is_football_league()
        if football and self._calendar_pending:
            self.date_label.setText("Finding the current week...")
        elif football:
            self.date_label.setText(self._week_label())
        else:
            self.date_label.setText(f"Date: {self.current_date.strftime('%A, %B %d, %Y')}")

        self.scores_list.clear()
        self.scores_list.addItem("Loading scores...")
        self.scores_list.setCurrentRow(0)

        if football:
            request = dict(week=self.current_week, season=self.current_season,
                           seasontype=self.current_season_type)
        else:
            request = dict(date=self.current_date)
        loader = LeagueScoresLoader(
            self._scores_generation, self.league, request,
            resolve_calendar=football and self._calendar_pending,
            requested_week=getattr(self, '_requested_week', None),
            requested_season_type=getattr(self, '_requested_season_type', None))
        loader.data_loaded.connect(self._on_scores_loaded)
        loader.error_occurred.connect(self._on_scores_error)
        _start_detached_thread(loader)

    def _on_scores_error(self, generation: int, message: str):
        if generation == self._scores_generation:
            self._show_api_error(f"Failed to load scores: {message}")

    def _on_scores_loaded(self, generation: int, calendar, scores_data: list, news: list):
        if generation != self._scores_generation:
            return  # a newer load has started since
        # An exception escaping a slot aborts the app under PyQt6, so a bad game
        # record must end here as an error message, as it did before.
        try:
            self._show_loaded_scores(calendar, scores_data, news)
        except Exception as e:
            self._show_api_error(f"Failed to load scores: {e}")

    def _show_loaded_scores(self, calendar, scores_data, news):
        if calendar is not None:
            self.current_season, self.current_season_type, self.current_week = calendar
            self._calendar_pending = False
        if self.is_football_league():
            self.date_label.setText(self._week_label())

        had_focus = self.scores_list.hasFocus()
        self.news_headlines = news
        self.scores_list.clear()
        if not scores_data:
            self.scores_list.addItem(
                "No games found for this week." if self.is_football_league()
                else "No games found for this date.")
        else:
            self._add_game_sections(scores_data)
        if self.news_headlines:
            self.scores_list.addItem("--- News Headlines ---")
            news_item = self.scores_list.item(self.scores_list.count()-1)
            news_item.setData(Qt.ItemDataRole.UserRole, "__news__")
        self._add_common_sections()
        # The list was showing "Loading scores..."; land on the first row so a
        # screen reader announces what replaced it. A refresh (F5) lands on the
        # game that was selected instead, so someone following a live game
        # doesn't lose it.
        row = 0
        pending, self._reselect = self._reselect, None
        reselect = pending[1] if pending and pending[0] == self._scores_generation else None
        if reselect is not None:
            for i in range(self.scores_list.count()):
                if self.scores_list.item(i).data(Qt.ItemDataRole.UserRole) == reselect:
                    row = i
                    break
        self.scores_list.setCurrentRow(row)
        if had_focus:
            self.scores_list.setFocus()

    def _add_game_sections(self, scores_data):
        """Add games under In Progress / Upcoming / Completed / Postponed headers.

        get_scores already returns games in section order. Each header is a
        plain list row with no data, so arrow keys stop on it and the screen
        reader reads it, but activating it does nothing. The count lets a
        user tell at a glance whether a section is worth entering.
        """
        from espn_api import SCORE_SECTIONS, game_section
        by_section = {}
        for game_raw in scores_data:
            by_section.setdefault(game_section(game_raw), []).append(game_raw)
        for key, title in SCORE_SECTIONS:
            games = by_section.get(key)
            if not games:
                continue
            count = len(games)
            self.scores_list.addItem(f"{title}, {count} {'game' if count == 1 else 'games'}")
            for game_raw in games:
                text = (self._live_game_text(game_raw) if key == "in_progress" else None)
                item = QListWidgetItem(text or GameData(game_raw, self.league).get_display_text())
                item.setData(Qt.ItemDataRole.UserRole, game_raw.get("id"))
                self.scores_list.addItem(item)

    def _live_game_text(self, game_raw):
        """A live game's text with its current play, laid out as Live Scores
        lays it out, or None when the scoreboard has no play to add.

        The play comes from the scoreboard entry already loaded, so this costs
        no request.
        """
        from espn_api import scoreboard_live_detail
        comp = (game_raw.get("competitions") or [{}])[0] or {}
        play = scoreboard_live_detail(self.league, comp)
        game = GameData(game_raw, self.league)
        status = game.start_time or game.status
        if not play or len(play.strip()) <= len((status or "").strip()):
            return None
        text = live_play_format.format_live_game(
            self.league, game.teams, status, play, game.get_display_text())
        # Live Scores names teams in full; this list uses short names for
        # NFL and MLB, and type-ahead should find a live game the same way.
        return live_play_format.use_list_team_names(
            text, live_play_format.list_team_names(game_raw, game.teams))

    def _add_common_sections(self):
        if self.league in ["MLB", "NFL", "NBA", "NHL", "NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"]:
            self.scores_list.addItem("--- Standings ---")
            standings_item = self.scores_list.item(self.scores_list.count()-1)
            standings_item.setData(Qt.ItemDataRole.UserRole, "__standings__")
            
            # Add Polls for NCAA sports (have ranking data)
            if self.league in ["NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"]:
                self.scores_list.addItem("--- Polls ---")
                polls_item = self.scores_list.item(self.scores_list.count()-1)
                polls_item.setData(Qt.ItemDataRole.UserRole, "__polls__")
            
            self.scores_list.addItem("--- Statistics ---")
            statistics_item = self.scores_list.item(self.scores_list.count()-1)
            statistics_item.setData(Qt.ItemDataRole.UserRole, "__statistics__")
            self.scores_list.addItem("--- Teams ---")
            teams_item = self.scores_list.item(self.scores_list.count()-1)
            teams_item.setData(Qt.ItemDataRole.UserRole, "__teams__")
            self.scores_list.addItem("--- Transactions ---")
            transactions_item = self.scores_list.item(self.scores_list.count()-1)
            transactions_item.setData(Qt.ItemDataRole.UserRole, "__transactions__")
            self.scores_list.addItem("--- Venues ---")
            venues_item = self.scores_list.item(self.scores_list.count()-1)
            venues_item.setData(Qt.ItemDataRole.UserRole, "__venues__")

            if self.league == "NFL":
                self.scores_list.addItem("--- NFL Draft ---")
                draft_item = self.scores_list.item(self.scores_list.count()-1)
                draft_item.setData(Qt.ItemDataRole.UserRole, "__draft__")

                self.scores_list.addItem("--- Fantasy Cheatsheet ---")
                cheatsheet_item = self.scores_list.item(self.scores_list.count()-1)
                cheatsheet_item.setData(Qt.ItemDataRole.UserRole, "__fantasy__")

            # Add Bowls & Playoffs for NCAAF
            if self.league == "NCAAF":
                self.scores_list.addItem("--- Bowls & Playoffs ---")
                bowls_item = self.scores_list.item(self.scores_list.count()-1)
                bowls_item.setData(Qt.ItemDataRole.UserRole, "__bowls__")

    def _show_news_dialog(self):
        """Show news dialog"""
        try:
            # Update window title to show we're viewing news
            if self.parent_app:
                self.parent_app.update_window_title(["News", self.league])
            
            dialog = NewsDialog(self.news_headlines, self.league, self)
            dialog.exec()
            
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show news: {str(e)}")
            # Restore original title on error
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
    
    def _show_standings_dialog(self):
        """Show standings dialog with caching and fast background loading"""
        try:
            # Update window title to show we're viewing standings
            if self.parent_app:
                self.parent_app.update_window_title(["Standings", self.league])
            
            # Check cache first
            cache = DataCache()
            cached_data = cache.get_standings(self.league)
            
            if cached_data:
                # Use cached data immediately
                dialog = StandingsDialog(cached_data, self.league, self)
                dialog.exec()
                # Restore original title when dialog closes
                if self.parent_app:
                    self.parent_app.update_window_title([self.league])
            else:
                # Load in background (now fast enough to not need loading dialog)
                self.standings_loader = StandingsLoader(self.league)
                self.standings_loader.data_loaded.connect(self._on_standings_data_loaded)
                self.standings_loader.error_occurred.connect(self._on_standings_data_error)
                # A second press, or leaving the view, replaces this reference mid-load.
                _start_detached_thread(self.standings_loader)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show standings: {str(e)}")
    
    def _on_standings_progress(self, message: str):
        """Update standings loading progress (no longer used)"""
        pass
    
    def _on_standings_data_loaded(self, standings_data):
        """Handle standings data loaded from background thread"""
        try:
            # Cache the data
            cache = DataCache()
            cache.set_standings(self.league, standings_data)
            
            # Show the dialog immediately (no loading dialog to close)
            dialog = StandingsDialog(standings_data, self.league, self)
            dialog.exec()
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to display standings: {str(e)}")
    
    def _show_polls_dialog(self):
        """Show polls/rankings dialog"""
        try:
            # Update window title to show we're viewing polls
            if self.parent_app:
                self.parent_app.update_window_title(["Polls", self.league])
            
            self._fetch_then("Polls", lambda: ApiService.get_rankings(self.league),
                             self._open_polls_dialog)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show polls: {str(e)}")
            if self.parent_app:
                self.parent_app.update_window_title([self.league])

    def _open_polls_dialog(self, polls_data):
        try:
            if not polls_data or not polls_data.get('polls'):
                QMessageBox.information(self, "Polls", 
                                      f"No poll data available for {self.league}.")
                # Restore original title
                if self.parent_app:
                    self.parent_app.update_window_title([self.league])
                return
            
            dialog = PollsDialog(polls_data, self.league, self)
            dialog.exec()
            
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show polls: {str(e)}")
            # Restore original title on error
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
    
    def _show_statistics_dialog(self):
        """Show statistics dialog with new flow: choose team/player → select stat → view results"""
        try:
            print(f"DEBUG: Starting _show_statistics_dialog for league: {self.league}")
            
            # Update window title to show we're viewing statistics
            if self.parent_app:
                self.parent_app.update_window_title(["Statistics", self.league])
            
            # Loop to allow returning to choice dialog
            while True:
                # First dialog: Choose between Team or Player statistics
                choice_dialog = StatisticsChoiceDialog(self.league, self)
                print(f"DEBUG: Created StatisticsChoiceDialog")
                
                if choice_dialog.exec() == QDialog.DialogCode.Accepted:
                    print(f"DEBUG: StatisticsChoiceDialog accepted")
                    choice = choice_dialog.get_choice()
                    print(f"DEBUG: Got choice: {choice}")
                    
                    if choice:
                        # Second dialog: Select specific statistic and view results
                        print(f"DEBUG: Creating StatisticsViewDialog with league={self.league}, choice={choice}")
                        stats_dialog = StatisticsViewDialog(self.league, choice, self)
                        print(f"DEBUG: About to show StatisticsViewDialog")
                        result = stats_dialog.exec()
                        print(f"DEBUG: StatisticsViewDialog returned with result: {result}")
                        
                        # If the user clicked OK or closed normally, exit the loop
                        # If they pressed Escape (result == 0), continue the loop to show choice again
                        if result == QDialog.DialogCode.Accepted:
                            break  # Exit statistics completely
                        # If result == QDialog.DialogCode.Rejected (Escape), loop continues
                    else:
                        print(f"DEBUG: No choice received from StatisticsChoiceDialog")
                        break  # Exit if no choice
                else:
                    print(f"DEBUG: StatisticsChoiceDialog was not accepted")
                    break  # Exit if choice dialog was cancelled
            
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
                    
        except Exception as e:
            print(f"DEBUG: Exception in _show_statistics_dialog: {str(e)}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to display statistics: {str(e)}")
            # Restore original title on error
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
    
    def _on_standings_data_error(self, error_message):
        """Handle standings data loading error"""
        QMessageBox.warning(self, "Standings", error_message)
    
    def _show_teams_dialog(self):
        """Show teams dialog with simple tabbed interface"""
        try:
            # Update window title to show we're viewing teams
            if self.parent_app:
                self.parent_app.update_window_title(["Teams", self.league])
            
            self._fetch_then("Teams", lambda: ApiService.get_standings(self.league),
                             self._open_teams_dialog)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show teams: {str(e)}")
            if self.parent_app:
                self.parent_app.update_window_title([self.league])

    def _open_teams_dialog(self, standings_data):
        try:
            if not standings_data:
                QMessageBox.information(self, "Teams", 
                                      f"No teams data available for {self.league}.")
                # Restore original title
                if self.parent_app:
                    self.parent_app.update_window_title([self.league])
                return
            
            # Filter data by league to avoid MLB/NFL mixing
            filtered_data = [team for team in standings_data 
                           if self._is_team_for_league(team, self.league)]
            
            dialog = SimpleTeamsDialog(filtered_data, self.league, self)
            dialog.exec()
            
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show teams: {str(e)}")
            # Restore original title on error
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
    
    def _show_transactions_dialog(self):
        try:
            if self.parent_app:
                self.parent_app.update_window_title(["Transactions", self.league])
            dialog = TransactionsDialog(self.league, self)
            dialog.exec()
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show transactions: {e}")
            if self.parent_app:
                self.parent_app.update_window_title([self.league])

    def _show_draft_dialog(self):
        try:
            if self.parent_app:
                self.parent_app.update_window_title(["NFL Draft", "NFL"])
            dialog = NFLDraftDialog(self)
            dialog.exec()
        finally:
            if self.parent_app:
                self.parent_app.update_window_title(["NFL"])

    def _show_fantasy_cheatsheet(self):
        try:
            if self.parent_app:
                self.parent_app.update_window_title(["Fantasy Cheatsheet", "NFL"])
            dialog = FantasyCheatsheetDialog(self)
            dialog.exec()
            # Parented to this view, so Qt would otherwise keep it alive for the
            # life of the session. Each corpse holds a table of ~9,000 cells plus
            # two full list views — about 8 MB per open, and a draft-day user
            # opens this board many times.
            dialog.deleteLater()
        finally:
            if self.parent_app:
                self.parent_app.update_window_title(["NFL"])

    def _show_venues_dialog(self):
        """Show venues dialog for the current league"""
        try:
            # Update window title to show we're viewing venues
            if self.parent_app:
                self.parent_app.update_window_title(["Venues", self.league])
            
            # Convert league to lowercase for venue service
            league_key = self.league.lower()
            self._fetch_then("Venues", lambda: venue_service.get_venues_for_league(league_key),
                             self._open_venues_dialog)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show venues: {str(e)}")
            if self.parent_app:
                self.parent_app.update_window_title([self.league])

    def _open_venues_dialog(self, venues_data):
        try:
            if not venues_data:
                QMessageBox.information(self, "Venues", 
                                      f"No venue data available for {self.league}.")
                # Restore original title
                if self.parent_app:
                    self.parent_app.update_window_title([self.league])
                return
            
            dialog = VenuesDialog(venues_data, self.league, self)
            dialog.exec()
            
            # Restore original title when dialog closes
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show venues: {str(e)}")
            # Restore original title on error
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
    
    def _fetch_then(self, title, fetch, show):
        """Run fetch() on a thread, then show(result) here.

        Polls, Teams and Venues used to download before their dialog opened, on
        the UI thread; Venues alone could freeze the window for 20 seconds. The
        activated row says "(loading...)" until the dialog opens, and a second
        Enter while it loads does nothing.
        """
        if title in self._background_fetches:
            return
        item = self.scores_list.currentItem()
        original = item.text() if item else None
        if item:
            item.setText(f"{original} (loading...)")

        def finish():
            self._background_fetches.pop(title, None)
            try:
                if item is not None and original is not None:
                    item.setText(original)
            except RuntimeError:
                pass  # the list was reloaded meanwhile and the row is gone

        def failed(message):
            finish()
            QMessageBox.critical(self, "Error", f"Failed to show {title.lower()}: {message}")
            if self.parent_app:
                self.parent_app.update_window_title([self.league])

        def loaded(result):
            finish()
            # An exception escaping a slot aborts the app under PyQt6.
            try:
                show(result)
            except Exception as e:
                failed(str(e))

        loader = CallLoader(fetch)
        loader.data_loaded.connect(loaded)
        loader.error_occurred.connect(failed)
        self._background_fetches[title] = loader
        _start_detached_thread(loader)

    def _show_bowls_and_playoffs(self):
        """Show Bowls & Playoffs view for NCAAF"""
        try:
            # Update window title
            if self.parent_app:
                self.parent_app.update_window_title(["Bowls & Playoffs", self.league])
            
            dialog = BowlsAndPlayoffsDialog(self.league, self)
            dialog.exec()
            
            # Restore original title
            if self.parent_app:
                self.parent_app.update_window_title([self.league])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show bowls & playoffs: {str(e)}")

    def _is_team_for_league(self, team_data: Dict, league: str) -> bool:
        """Check if team belongs to the specified league"""
        team_name = team_data.get('team_name', '')
        logo_url = team_data.get('logo', '')
        
        if league == "MLB":
            return '/mlb/' in logo_url
        elif league == "NFL":
            return '/nfl/' in logo_url
        return True  # Default to include if uncertain
    
    def previous_day(self):
        """Navigate to previous day"""
        self.current_date -= timedelta(days=1)
        self.load_scores()
        self.set_focus_and_select_first(self.scores_list)
    
    def next_day(self):
        """Navigate to next day"""
        self.current_date += timedelta(days=1)
        self.load_scores()
        self.set_focus_and_select_first(self.scores_list)
    
    def go_to_date(self):
        """Show date picker dialog and navigate to selected date"""
        if self.current_date is None:
            return  # Week-based leagues (NFL/NCAAF) don't use date navigation
        try:
            dialog = DatePickerDialog(self.current_date, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_date = dialog.get_selected_date()
                if new_date != self.current_date:
                    self.current_date = new_date
                    self.load_scores()
                    self.set_focus_and_select_first(self.scores_list)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to change date: {str(e)}")
    
    def refresh(self):
        """Refresh the current view, staying on the selected game."""
        current = self.scores_list.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current else None
        # A second F5 before the first load lands is on "Loading scores...";
        # keep aiming for the game the first one was on.
        if selected is None and self._reselect and self._reselect[0] == self._scores_generation:
            selected = self._reselect[1]
        self.load_scores(reselect=selected)
        # Focus only: the row is chosen when the scores arrive.
        self.scores_list.setFocus()
    
    def _add_nav_buttons(self):
        btn_layout = QHBoxLayout()

        back_btn = QPushButton("Back (Alt+B)")
        back_btn.setShortcut("Alt+B")
        back_btn.clicked.connect(lambda: self.parent_app.go_back() if self.parent_app else None)
        btn_layout.addWidget(back_btn)

        if self.is_football_league():
            prev_week_btn = QPushButton("Previous Week (Alt+P)")
            prev_week_btn.setShortcut("Alt+P")
            prev_week_btn.clicked.connect(self.previous_week)
            btn_layout.addWidget(prev_week_btn)

            next_week_btn = QPushButton("Next Week (Alt+N)")
            next_week_btn.setShortcut("Alt+N")
            next_week_btn.clicked.connect(self.next_week)
            btn_layout.addWidget(next_week_btn)

        else:
            prev_btn = QPushButton("Previous Day (Alt+P)")
            prev_btn.setShortcut("Alt+P")
            prev_btn.clicked.connect(self.previous_day)
            btn_layout.addWidget(prev_btn)

            next_btn = QPushButton("Next Day (Alt+N)")
            next_btn.setShortcut("Alt+N")
            next_btn.clicked.connect(self.next_day)
            btn_layout.addWidget(next_btn)

            go_to_date_btn = QPushButton("Go to Date (Ctrl+G)")
            go_to_date_btn.setShortcut("Ctrl+G")
            go_to_date_btn.clicked.connect(self.go_to_date)
            btn_layout.addWidget(go_to_date_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(refresh_btn)

        self.layout.addLayout(btn_layout)

    def _week_label(self, suffix: str = ""):
        """Label for the current week, e.g. 'Week: Preseason Week 1'.

        ESPN's week numbers restart in each season type, so a bare "Week 1" is
        genuinely ambiguous in August — the calendar label is what tells a
        preseason game apart from the September opener. Prefixed like the
        non-football "Date: …" label so a screen reader hearing the window
        knows what the value refers to.
        """
        try:
            from services.football_calendar import get_week_label
            label = get_week_label(self.league, self.current_season,
                                   self.current_season_type, self.current_week)
        except Exception:
            label = f"Week {self.current_week}"
        # ESPN's labels are a mix: "Week 1" and "Preseason Week 1" already say
        # what they are, "Hall of Fame Weekend" and "Wild Card" do not.
        if "week" not in label.lower():
            label = f"Week: {label}"
        return f"{label}{suffix}"

    def _step_week(self, delta: int):
        """Move one week, rolling over between preseason, regular and postseason."""
        try:
            from services.football_calendar import step_week
            season_type, week = step_week(
                self.league, self.current_season,
                self.current_season_type, self.current_week, delta)
        except Exception:
            season_type, week = self.current_season_type, max(1, self.current_week + delta)

        if (season_type, week) == (self.current_season_type, self.current_week):
            # Already at one end of the season. Say so rather than doing nothing:
            # the default view in August *is* the first week, so a silent no-op
            # here reads as the app having frozen. Focus still moves, so the key
            # press produces an audible result either way.
            edge = "first" if delta < 0 else "last"
            self.date_label.setText(self._week_label(f" — {edge} week of the season"))
            self.set_focus_and_select_first(self.scores_list)
            return
        self.current_season_type, self.current_week = season_type, week
        self.load_scores()
        self.set_focus_and_select_first(self.scores_list)

    def previous_week(self):
        # Until the calendar arrives the week is a placeholder to step from.
        if self.current_week and not self._calendar_pending:
            self._step_week(-1)

    def next_week(self):
        if self.current_week and not self._calendar_pending:
            self._step_week(+1)
    
    def _show_api_error(self, message: str):
        """Show API error message"""
        self.scores_list.clear()
        error_item = self.scores_list.addItem(f"Error: {message}")
        QMessageBox.warning(self, "API Error", message)
    
    def keyPressEvent(self, event):
        """Handle key press events for league view"""
        if event.key() == Qt.Key.Key_G and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if not self.is_football_league():
                self.go_to_date()
        else:
            # Call parent to handle F5, Escape, etc.
            super().keyPressEvent(event)
    
    def on_show(self):
        self.set_focus_and_select_first(self.scores_list)
        # Update window title for league view
        if self.parent_app and self.league:
            self.parent_app.update_window_title([self.league])

class GameDetailsView(BaseView):
    """View showing detailed information for a specific game"""
    
    def __init__(self, parent=None, league=None, game_id=None, original_game_data=None):
        super().__init__(parent)
        self.league = league
        self.game_id = game_id
        self.original_game_data = original_game_data  # Store original game data with team IDs
        self.config = parent.config if parent else {}
        self.raw_game_data = None  # Store raw data for drill-down access
        self.current_raw_details = None  # the game summary, once loaded
        self._details_generation = 0  # newest load_game_details; older results are dropped
        
        # Initialize audio pitch mapper
        self.audio_mapper = None
        if AUDIO_AVAILABLE:
            try:
                self.audio_mapper = AudioPitchMapper(self)
                self.audio_mapper.audio_generated.connect(self._on_audio_feedback)
                self.audio_mapper.audio_error.connect(self._on_audio_error)
            except Exception as e:
                print(f"Audio initialization failed: {e}")
                self.audio_mapper = None

        # Basketball and hockey play audio
        self.play_audio_mapper = None
        if PLAY_AUDIO_AVAILABLE:
            try:
                self.play_audio_mapper = PlayAudioMapper(self)
                self.play_audio_mapper.audio_error.connect(self._on_play_audio_error)
            except Exception as e:
                print(f"Play audio initialization failed: {e}")
                self.play_audio_mapper = None

        self.setup_ui()
    
    def setup_ui(self):
        self.layout.addWidget(QLabel("Game Details:"))
        
        self.details_list = QListWidget()
        self.details_list.setAccessibleName("Game Details List")
        self.details_list.setAccessibleDescription("List of detailed information about the selected game")
        self.details_list.itemActivated.connect(self._on_detail_item_selected)
        self.layout.addWidget(self.details_list)
        
        self._add_nav_buttons()
        self.load_game_details()
    
    def _on_audio_feedback(self, message):
        """Handle audio generation feedback"""
        # Provide accessible feedback about audio generation
        if hasattr(self, 'details_list'):
            self.details_list.setAccessibleDescription(f"Audio: {message}")
    
    def _on_audio_error(self, error_message):
        """Handle audio errors"""
        print(f"Audio error: {error_message}")
        # Could show a non-intrusive error message if needed

    def _on_play_audio_error(self, error_message):
        """Basketball and hockey playback failed.

        Successful playback says nothing, so a failure has to be spoken or it
        sounds the same as a tone that played. The mapper reports once per run.
        """
        self._on_audio_error(error_message)
        self._announce_play_audio("Couldn't play the sound")
    
    def keyPressEvent(self, event):
        """Handle key press events for game details view"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # If details list has focus and an item is selected, activate it
            if self.details_list.hasFocus():
                current_item = self.details_list.currentItem()
                if current_item:
                    self._on_detail_item_selected(current_item)
                    return
        
        # Call parent to handle other keys (F5, Escape, etc.)
        super().keyPressEvent(event)
    
    def _on_detail_item_selected(self, item):
        """Handle selection of detailed data items"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        field_name = data.get("field")
        field_data = data.get("data")
        
        if not field_name or not field_data:
            return
        
        try:
            self._show_detail_dialog(field_name, field_data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show {field_name} details: {str(e)}")
    
    def _show_detail_dialog(self, field_name: str, field_data: Any):
        """Show detailed data in a dialog"""
        if field_name == "standings":
            # Convert game details standings format to list format if needed
            if isinstance(field_data, dict) and "groups" in field_data:
                # Game details format - convert to list format
                standings_list = []
                for group in field_data.get("groups", []):
                    standings = group.get("standings", {})
                    entries = standings.get("entries", [])
                    for entry in entries:
                        standings_list.append(entry)
                dlg = StandingsDetailDialog(standings_list, self.league, self)
            elif isinstance(field_data, list):
                # Already in list format (from main standings)
                dlg = StandingsDetailDialog(field_data, self.league, self)
            else:
                QMessageBox.information(self, "Standings", "No standings data available.")
                return
            dlg.exec()
            return
        
        if field_name == "team_schedule":
            # Handle team schedule navigation
            if not isinstance(field_data, dict):
                QMessageBox.warning(self, "Error", "Invalid team data.")
                return
                
            team_name = field_data.get("team_name", "Unknown Team")
            team_id = field_data.get("team_id")

            if team_id:
                self._open_team_schedule(team_name, team_id, field_data)
            else:
                # No ID in the summary. Looking one up fetches the league's
                # standings, so do that off the UI thread.
                loader = CallLoader(lambda: self._find_team_id_alternative(team_name))
                loader.data_loaded.connect(
                    lambda found: self._open_team_schedule(team_name, found, field_data))
                loader.error_occurred.connect(
                    lambda _e: self._open_team_schedule(team_name, None, field_data))
                _start_detached_thread(loader)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{field_name.title()} Details")
        dlg.resize(DIALOG_WIDTH, DIALOG_HEIGHT)
        layout = QVBoxLayout()        # Store reference to tab widget for F6 handling
        tab_widget_ref = None
        
        if field_name == "leaders" and isinstance(field_data, (list, dict)):
            try:
                self._add_leaders_data_to_layout(layout, field_data)
                # Find the tab widget that was just added for F6 handling
                for child in layout.children():
                    if hasattr(child, 'widget') and isinstance(child.widget(), QTabWidget):
                        tab_widget_ref = child.widget()
                        break
            except Exception as e:
                error_label = QLabel(f"Leaders display error: {str(e)}")
                layout.addWidget(error_label)
        elif field_name == "boxscore" and isinstance(field_data, dict):
            self._add_boxscore_data_to_layout(layout, field_data)
            # Find the tab widget that was just added
            for child in layout.children():
                if hasattr(child, 'widget') and isinstance(child.widget(), QTabWidget):
                    tab_widget_ref = child.widget()
                    break
        elif field_name == "plays" and isinstance(field_data, list):
            self._add_plays_list_to_layout(layout, field_data)
            # A period of play audio runs half a minute; don't let it outlive
            # the dialog it belongs to.
            if self.play_audio_mapper:
                dlg.finished.connect(lambda _result: self.play_audio_mapper.stop())
        elif field_name == "drives" and isinstance(field_data, dict):
            self._add_drives_list_to_layout(layout, field_data)
        elif field_name == "officials" and isinstance(field_data, list):
            self._add_officials_list_to_layout(layout, field_data)
        elif field_name == "injuries" and isinstance(field_data, list):
            self._add_injuries_list_to_layout(layout, field_data)
        elif field_name == "news" and isinstance(field_data, (list, dict)):
            self._add_news_list_to_layout(layout, field_data)
        elif field_name == "game_wrap_up":
            # Generate and display comprehensive game wrap-up
            self._generate_and_display_game_wrap_up(field_data)
            return  # Don't continue with dialog creation
        else:
            # Fallback to formatted text
            text_widget = QTextEdit()
            try:
                formatted_data = ApiService.format_complex_data(field_name, field_data)
                text_widget.setPlainText(formatted_data)
            except ApiError:
                text_widget.setPlainText("Error formatting data")
            text_widget.setReadOnly(True)
            layout.addWidget(text_widget)
        
        # Add close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        
        dlg.setLayout(layout)
        
        # Add F5 refresh support for all dialogs
        original_keyPressEvent = dlg.keyPressEvent
        focus_state = {"current": "tab_bar"}  # Track current focus state for F6 navigation
        
        def custom_keyPressEvent(event):
            if event.key() == Qt.Key.Key_F5:
                # Refresh the dialog by reloading the data
                # Close, reload in the background, and reshow when it lands.
                dlg.accept()
                loader = GameDetailsLoader(0, self.league, self.game_id)
                loader.data_loaded.connect(
                    lambda _gen, raw, _details: self._reshow_detail_dialog(field_name, raw))
                loader.error_occurred.connect(
                    lambda _gen, e: QMessageBox.critical(
                        self, "Refresh Error", f"Failed to refresh {field_name}: {e}"))
                _start_detached_thread(loader)
                return
            elif event.key() == Qt.Key.Key_Escape:
                # Escape closes the dialog
                dlg.reject()
                return
            
            # Handle F6 for tabbed dialogs (boxscore and leaders)
            if event.key() == Qt.Key.Key_F6 and field_name in ["boxscore", "leaders"] and tab_widget_ref:
                # Cycle through: tab_bar -> first_table -> other_tables -> next_tab -> repeat
                current_tab_index = tab_widget_ref.currentIndex()
                current_widget = tab_widget_ref.widget(current_tab_index)
                
                if current_widget:
                    # Find tables based on field type
                    if field_name == "boxscore":
                        tables = current_widget.findChildren(BoxscoreTable)
                    else:  # leaders
                        tables = current_widget.findChildren(LeadersTable)
                    
                    if focus_state["current"] == "tab_bar":
                        # Move from tab bar to first table in current tab
                        if tables and tables[0].rowCount() > 0:
                            tables[0].setFocus()
                            tables[0].setCurrentCell(0, 0)
                            focus_state["current"] = f"table_0"
                        event.accept()
                        return
                        
                    elif focus_state["current"].startswith("table_"):
                        # Currently on a table, move to next table or next tab
                        try:
                            current_table_idx = int(focus_state["current"].split("_")[1])
                            next_table_idx = current_table_idx + 1
                            
                            if next_table_idx < len(tables) and tables[next_table_idx].rowCount() > 0:
                                # Move to next table in same tab
                                tables[next_table_idx].setFocus()
                                tables[next_table_idx].setCurrentCell(0, 0)
                                focus_state["current"] = f"table_{next_table_idx}"
                            else:
                                # Move to next tab
                                next_tab_index = (current_tab_index + 1) % tab_widget_ref.count()
                                tab_widget_ref.setCurrentIndex(next_tab_index)
                                tab_widget_ref.tabBar().setFocus()
                                focus_state["current"] = "tab_bar"
                        except:
                            # Fallback to tab bar
                            tab_widget_ref.tabBar().setFocus()
                            focus_state["current"] = "tab_bar"
                        
                        event.accept()
                        return
                
                # Fallback: just go to tab bar
                tab_widget_ref.tabBar().setFocus()
                focus_state["current"] = "tab_bar"
                event.accept()
                return
                
            original_keyPressEvent(event)
            
        dlg.keyPressEvent = custom_keyPressEvent
        
        # Set focus to first table after dialog is shown (for tabbed dialogs)
        if field_name in ["boxscore", "leaders"]:
            def set_focus_to_table():
                # Find the tab widget in the dialog
                tab_widgets = dlg.findChildren(QTabWidget)
                if tab_widgets:
                    tab_widget = tab_widgets[0]
                    tab_widget.setFocus()
                    # Set focus to first table in first tab
                    first_widget = tab_widget.widget(0)
                    if first_widget:
                        if field_name == "boxscore":
                            tables = first_widget.findChildren(BoxscoreTable)
                        else:  # leaders
                            tables = first_widget.findChildren(LeadersTable)
                        if tables and tables[0].rowCount() > 0:
                            QTimer.singleShot(100, lambda: tables[0].setFocus())
                            QTimer.singleShot(100, lambda: tables[0].setCurrentCell(0, 0))
            
            QTimer.singleShot(FOCUS_DELAY_MS, set_focus_to_table)
        
        dlg.exec()
    
    def load_game_details(self):
        """Start loading detailed game information.

        The summary is fetched on a GameDetailsLoader thread; hockey also
        scrapes the espn.com game page. Fetched here it froze the window on
        every game opened and every refresh.
        """
        self._details_generation += 1
        self.details_list.clear()
        self.details_list.addItem("Loading game details...")
        self.details_list.setCurrentRow(0)
        loader = GameDetailsLoader(self._details_generation, self.league, self.game_id)
        loader.data_loaded.connect(self._on_game_details_loaded)
        loader.error_occurred.connect(self._on_game_details_error)
        _start_detached_thread(loader)

    def _on_game_details_error(self, generation: int, message: str):
        if generation == self._details_generation:
            self._show_api_error(f"Failed to load game details: {message}")

    def _on_game_details_loaded(self, generation: int, raw_details: dict, details: dict):
        if generation != self._details_generation:
            return
        had_focus = self.details_list.hasFocus()
        self.details_list.clear()

        # An exception escaping a slot aborts the app under PyQt6.
        try:
            # Store raw details for export functionality
            self.current_raw_details = raw_details

            # Display basic game information
            self._add_basic_game_info(details)
            
            # Show configurable details
            self._add_configurable_details(raw_details)
            
            # Add Game Wrap Up option at the end
            self._add_game_wrap_up_option()

        except Exception as e:
            self._show_api_error(f"Failed to load game details: {str(e)}")
            return
        # The list was showing "Loading game details..."; land on the first
        # row so a screen reader announces what replaced it.
        self.details_list.setCurrentRow(0)
        if had_focus:
            self.details_list.setFocus()

    def _get_team_id_from_original_data(self, team_name: str) -> str:
        """Get team ID from original game data (infrastructure-level solution)"""
        if not self.original_game_data:
            return ""
            
        # Look for team ID in the original game data structure
        competitors = []
        if 'competitions' in self.original_game_data:
            competitions = self.original_game_data.get('competitions', [])
            if competitions:
                competitors = competitions[0].get('competitors', [])
        elif 'competitors' in self.original_game_data:
            competitors = self.original_game_data.get('competitors', [])
            
        # Try to match team by name and get ID
        for competitor in competitors:
            team = competitor.get('team', {})
            team_names = [
                team.get('name', ''),
                team.get('displayName', ''),
                team.get('shortDisplayName', ''),
                team.get('location', ''),
                team.get('nickname', '')
            ]
            
            # Check for exact matches first
            for name in team_names:
                if name and name == team_name:
                    return str(team.get('id', ''))
                    
            # Check for partial matches (handles "Wisconsin Badgers" vs "Badgers")
            for name in team_names:
                if name and (team_name in name or name in team_name):
                    return str(team.get('id', ''))
                    
        return ""

    def _open_team_schedule(self, team_name, team_id, field_data):
        """Open a team's schedule from game details, once its ID is known."""
        if not team_id:
            # Still no team ID - gracefully handle this
            QMessageBox.information(self, "Team Schedule", 
                f"Schedule for {team_name} is temporarily unavailable.\n\n"
                "You can access team schedules from the main league standings.")
            return

        # Create team data structure for TeamScheduleDialog
        team_data = {
            'team_id': team_id,
            'team_name': team_name,
            'wins': '',  # TeamScheduleDialog will load this
            'losses': '',
            'record': field_data.get('record', '')
        }

        try:
            dlg = TeamScheduleDialog(team_data, field_data.get('league', self.league), self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                f"Failed to load {team_name} schedule: {str(e)}\n\n"
                "You can try accessing the team schedule from the main league standings.")

    def _find_team_id_alternative(self, team_name: str) -> str:
        """Alternative method to find team ID when standard extraction fails"""
        # Known team ID mappings for major teams (interim solution)
        team_id_map = {
            'college-football': {
                'Wisconsin Badgers': '275',
                'Badgers': '275',
                'Wisconsin': '275',
                'Michigan Wolverines': '130',
                'Wolverines': '130',
                'Michigan': '130',
                'Ohio State Buckeyes': '194',
                'Buckeyes': '194',
                'Ohio State': '194',
                'Alabama Crimson Tide': '333',
                'Alabama': '333',
                'Crimson Tide': '333',
                # Add more as needed
            }
        }
        
        # Check hardcoded mappings first
        league_map = team_id_map.get(self.league, {})
        for known_name, team_id in league_map.items():
            if known_name.lower() == team_name.lower() or team_name.lower() in known_name.lower() or known_name.lower() in team_name.lower():
                return team_id
        
        try:
            # Try to get current league standings which contain team IDs
            standings_data = ApiService.get_standings(self.league)
            
            if standings_data:
                # Handle both dict format (with groups) and list format
                entries_to_check = []
                
                if isinstance(standings_data, dict):
                    # Look through standings for the team
                    for group in standings_data.get('groups', []):
                        standings = group.get('standings', {})
                        entries_to_check.extend(standings.get('entries', []))
                elif isinstance(standings_data, list):
                    # Direct list format
                    entries_to_check = standings_data
                
                for entry in entries_to_check:
                    team = entry.get('team', {})
                    team_names = [
                        team.get('name', ''),
                        team.get('displayName', ''),
                        team.get('shortDisplayName', ''),
                        team.get('location', ''),
                        team.get('nickname', '')
                    ]
                    
                    # Check for matches
                    for name in team_names:
                        if name and (name == team_name or team_name in name or name in team_name):
                            return str(team.get('id', ''))
        except Exception as e:
            pass  # Silently handle API errors
            
        return ""

    def _extract_team_id(self, team_info: Dict, raw_details: Dict) -> str:
        """Extract team ID from game details data"""
        if not raw_details:
            return ""
            
        # Look for team ID in the header.competitions.competitors
        header = raw_details.get('header', {})
        competitions = header.get('competitions', [])
        if not competitions:
            return ""
            
        competition = competitions[0]
        competitors = competition.get('competitors', [])
        
        # Get the team name we're looking for (from processed game info)
        team_name = team_info.get('name', '')
        
        # Try exact matches with all possible name fields
        for competitor in competitors:
            comp_team = competitor.get('team', {})
            comp_names = [
                comp_team.get('name', ''),
                comp_team.get('displayName', ''),
                comp_team.get('shortDisplayName', ''),
                comp_team.get('alternateDisplayName', '')
            ]
            
            for comp_name in comp_names:
                if comp_name and comp_name == team_name:
                    return str(comp_team.get('id', ''))
        
        # Enhanced fallback: try partial matches since processed names might be different from raw names
        for competitor in competitors:
            comp_team = competitor.get('team', {})
            comp_abbrev = comp_team.get('abbreviation', '')
            comp_location = comp_team.get('location', '')
            comp_nickname = comp_team.get('nickname', '')
            comp_name = comp_team.get('name', '')
            comp_display = comp_team.get('displayName', '')
            
            # Check if abbreviation matches
            if comp_abbrev and comp_abbrev in team_name:
                return str(comp_team.get('id', ''))
                
            # Check if any part of the processed name matches the raw name components
            if comp_location and comp_location in team_name:
                return str(comp_team.get('id', ''))
            if comp_nickname and comp_nickname in team_name:
                return str(comp_team.get('id', ''))
            if comp_name and comp_name in team_name:
                return str(comp_team.get('id', ''))
                
            # Reverse check: see if raw display name contains our processed name parts
            team_words = team_name.split()
            for word in team_words:
                if len(word) > 3:  # Skip short words like "at", "vs", etc.
                    if word in comp_display or word in comp_name or word in comp_location:
                        return str(comp_team.get('id', ''))
                
        return ""

    def _add_basic_game_info(self, details: Dict, raw_details: Dict = None):
        """Add basic game information to the details list"""
        # Extract game information for window title
        game_title_parts = []
        
        # Display teams and records with interactive team names
        if 'teams' in details:
            team_names = []
            for team in details['teams']:
                team_names.append(team['name'])
                home_away = " (Home)" if team['home_away'] == 'home' else " (Away)"
                
                # Use team_id directly from processed details (infrastructure fix)
                team_id = team.get('team_id', '')
                
                # Only use complex extraction if team_id is missing
                if not team_id:
                    # Infrastructure-level team ID resolution (fallback methods)
                    team_id = self._get_team_id_from_original_data(team['name'])
                    if not team_id:
                        team_id = self._extract_team_id(team, raw_details)
                
                # Create interactive team item  
                team_display = f"{team['name']}{home_away}"
                team_item = QListWidgetItem(team_display)
                team_item.setData(Qt.ItemDataRole.UserRole, {
                    "field": "team_schedule",
                    "data": {
                        "team_name": team['name'],
                        "team_id": team_id,
                        "league": self.league,
                        "record": team['record'],
                        "from_game_details": True  # Flag to indicate navigation source
                    }
                })
                self.details_list.addItem(team_item)
                self.details_list.addItem(f"  Record: {team['record']}")
            
            # Build game title with team names - ensure away team first, home team second
            sorted_teams = sorted(details['teams'], key=lambda t: 0 if t['home_away'] == 'away' else 1)
            sorted_names = [t['name'] for t in sorted_teams]
            
            if len(sorted_names) >= 2:
                game_title_parts.append(f"{sorted_names[0]} at {sorted_names[1]}")
            elif len(sorted_names) == 1:
                game_title_parts.append(sorted_names[0])
        
        # Add date/status information to title if available
        if 'status' in details and details['status']:
            # Only add non-generic status info
            status = details['status']
            if status not in ['Final', 'Scheduled', 'In Progress']:
                game_title_parts.append(status)
        
        # Update window title with game-specific information
        if self.parent_app and self.league:
            title_context = game_title_parts + [self.league] if game_title_parts else ["Game Details", self.league]
            self.parent_app.update_window_title(title_context)
        
        # Game status and timing
        if 'status' in details:
            self.details_list.addItem(f"Status: {details['status']}")
        
        # Score information
        if 'scores' in details and details['scores']:
            score_display = " - ".join(details['scores'])
            self.details_list.addItem(f"Score: {score_display}")
        
        if 'detailed_status' in details and details['detailed_status'] != 'N/A':
            self.details_list.addItem(f"Game Time: {details['detailed_status']}")
        
        # Venue information
        if 'venue' in details:
            venue_info = details['venue']
            if 'venue_city' in details and details['venue_city'] != 'Unknown':
                venue_info += f" ({details['venue_city']}"
                if 'venue_state' in details and details['venue_state']:
                    venue_info += f", {details['venue_state']}"
                venue_info += ")"
            self.details_list.addItem(f"Venue: {venue_info}")
        
        if 'weather' in details:
            weather_display = details['weather']
            if 'temperature' in details and details['temperature'] not in weather_display:
                weather_display += f", {details['temperature']}"
            self.details_list.addItem(f"Weather: {weather_display}")
        
        # Officials - make interactive if available
        if raw_details and 'gameInfo' in raw_details:
            game_info = raw_details['gameInfo']
            if 'officials' in game_info and isinstance(game_info['officials'], list):
                officials = game_info['officials']
                if officials:
                    officials_item = QListWidgetItem(f"Officials: {len(officials)} assigned (Press Enter for details)")
                    officials_item.setData(Qt.ItemDataRole.UserRole, {
                        "field": "officials",
                        "data": officials
                    })
                    self.details_list.addItem(officials_item)
        
        # Betting information
        if 'betting_line' in details:
            self.details_list.addItem(f"Betting Line: {details['betting_line']}")
        if 'over_under' in details:
            self.details_list.addItem(f"Over/Under: {details['over_under']}")
        
        # Broadcast info
        if 'broadcast' in details:
            self.details_list.addItem(f"TV: {details['broadcast']}")
        
        # Injuries
        if 'injuries' in details:
            self.details_list.addItem(f"Injuries: {details['injuries']}")
    
    def _add_game_wrap_up_option(self):
        """Add Game Wrap Up option at the end of the details list"""
        if hasattr(self, 'current_raw_details') and self.current_raw_details:
            # Check if this is a completed game that might have wrap-up content
            header = self.current_raw_details.get('header', {})
            competitions = header.get('competitions', [])
            
            if competitions:
                competition = competitions[0]
                status = competition.get('status', {})
                status_type = status.get('type', {})
                
                # Only add wrap-up for completed games
                state = status_type.get('state', '').lower()
                if state in ['post', 'final']:
                    # Add only the wrap-up item, no heading
                    wrap_up_item = QListWidgetItem("🚧 Game Wrap Up")
                    wrap_up_item.setData(Qt.ItemDataRole.UserRole, {
                        "field": "game_wrap_up",
                        "data": self.current_raw_details
                    })
                    self.details_list.addItem(wrap_up_item)

    def _add_configurable_details(self, raw_details: Dict):
        """Add all available detail fields (no longer configurable - show everything)"""
        # Show all available detail fields - be more permissive than before
        all_available_fields = []
        
        # Include ALL detail fields that have any data (even empty lists/dicts) 
        for field in DETAIL_FIELDS:
            value = raw_details.get(field)
            if value is not None:  # Include if field exists, even if empty
                all_available_fields.append(field)
        
        # Always include plays if available (even if empty, for consistency)
        if raw_details.get("plays") is not None and "plays" not in all_available_fields:
            all_available_fields.append("plays")
        
        if all_available_fields:
            self.details_list.addItem("--- Additional Details ---")
            for field in all_available_fields:
                value = raw_details.get(field, "N/A")
                if value == "N/A" or not value:
                    self.details_list.addItem(f"{field}: No data available")
                else:
                    self._add_configurable_field(field, value)
    
    def _add_configurable_field(self, field: str, value: Any):
        """Add a configurable field to the details list"""
        navigable_fields = ["standings", "leaders", "boxscore", "plays", "drives", "injuries", "news"]
        
        if field in navigable_fields:
            has_data = self._check_field_has_data(field, value)
            
            if has_data:
                item_text = f"{field.title()}"
                self.details_list.addItem(item_text)
                list_item_widget = self.details_list.item(self.details_list.count() - 1)
                if list_item_widget:
                    # For news field, pass full raw details to enable game-specific article detection
                    if field == "news" and hasattr(self, 'current_raw_details'):
                        list_item_widget.setData(Qt.ItemDataRole.UserRole, {"field": field, "data": self.current_raw_details})
                    else:
                        list_item_widget.setData(Qt.ItemDataRole.UserRole, {"field": field, "data": value})
            else:
                try:
                    formatted_value = ApiService.format_complex_data(field, value)
                    self.details_list.addItem(f"{field}: {formatted_value}")
                except ApiError:
                    self.details_list.addItem(f"{field}: Error formatting data")
        else:
            # Use enhanced formatting for simple data
            try:
                formatted_value = ApiService.format_complex_data(field, value)
                if '\n' in formatted_value:
                    self.details_list.addItem(f"{field}:")
                    for line in formatted_value.split('\n'):
                        if line.strip():
                            self.details_list.addItem(f"  {line}")
                else:
                    self.details_list.addItem(f"{field}: {formatted_value}")
            except ApiError:
                self.details_list.addItem(f"{field}: Error formatting data")
    
    def _check_field_has_data(self, field: str, value: Any) -> bool:
        """Check if a field has navigable data"""
        if field == "standings" and isinstance(value, (list, dict)):
            if isinstance(value, list):
                return len(value) > 0
            elif isinstance(value, dict):
                # Check for game details standings format (groups with standings.entries)
                groups = value.get("groups", [])
                return any(group.get("standings", {}).get("entries") for group in groups)
        elif field == "leaders":
            # ESPN leaders data is a list of teams with leader categories
            if isinstance(value, list):
                return len(value) > 0 and any(
                    isinstance(team, dict) and team.get("leaders") 
                    for team in value
                )
            elif isinstance(value, dict):
                return len(value) > 0
            return False
        elif field == "boxscore" and isinstance(value, dict):
            return bool(value.get("teams") or value.get("players"))
        elif field == "plays" and isinstance(value, list):
            return len(value) > 0
        elif field == "drives" and isinstance(value, dict):
            # NFL/NCAAF drives data - check for current drive or previous drives
            current = value.get("current")
            previous = value.get("previous", [])
            return bool(current) or len(previous) > 0
        elif field == "injuries" and isinstance(value, list):
            return len(value) > 0
        elif field == "news" and isinstance(value, (list, dict)):
            return len(value) > 0 if isinstance(value, list) else bool(value.get("articles"))
        return False
    
    def _reshow_detail_dialog(self, field_name, raw_details):
        """Reopen a detail dialog with freshly loaded data (F5 inside it)."""
        try:
            updated_field_data = raw_details.get(field_name)
            if updated_field_data:
                self._show_detail_dialog(field_name, updated_field_data)
        except Exception as e:
            QMessageBox.critical(self, "Refresh Error", f"Failed to refresh {field_name}: {e}")

    def refresh(self):
        """Refresh the game details"""
        self.load_game_details()
        self.set_focus_and_select_first(self.details_list)
    
    def _add_nav_buttons(self):
        btn_layout = QHBoxLayout()
        
        back_btn = QPushButton("Back (Alt+B)")
        back_btn.setShortcut("Alt+B")
        back_btn.clicked.connect(lambda: self.parent_app.go_back() if self.parent_app else None)
        btn_layout.addWidget(back_btn)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(refresh_btn)
        
        self.layout.addLayout(btn_layout)
    
    def _show_api_error(self, message: str):
        """Show API error message"""
        self.details_list.clear()
        error_item = self.details_list.addItem(f"Error: {message}")
        QMessageBox.warning(self, "API Error", message)
    
    def on_show(self):
        self.set_focus_and_select_first(self.details_list)
        # Update window title with game context (will be set after game data loads)
        if self.parent_app and self.league:
            # Initial title while loading
            self.parent_app.update_window_title(["Game Details", self.league])
    
    def _add_standings_table_to_layout(self, layout, data):
        """Add standings table to layout"""
        standings_data = StandingsData(data)
        if not standings_data.teams:
            layout.addWidget(QLabel("No standings data available."))
            return
        
        # Check if we have division data for MLB
        has_divisions = len(standings_data.divisions) > 1 or any(
            div != "League" for div in standings_data.divisions.keys()
        )
        
        if has_divisions and hasattr(self, 'league') and self.league == "MLB":
            # Create tabbed view for divisions
            tab_widget = QTabWidget()
            tab_widget.setAccessibleName("Division Standings")
            tab_widget.setAccessibleDescription("Baseball divisions, use arrow keys to navigate between divisions")
            
            # Sort divisions for consistent ordering
            division_order = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West", "League"]
            sorted_divisions = []
            
            for div_name in division_order:
                if div_name in standings_data.divisions:
                    sorted_divisions.append((div_name, standings_data.divisions[div_name]))
            
            # Add any divisions not in our predefined order
            for div_name, teams in standings_data.divisions.items():
                if div_name not in division_order:
                    sorted_divisions.append((div_name, teams))
            
            for div_name, teams in sorted_divisions:
                if teams:  # Only create tab if there are teams
                    # Create table for this division
                    table = QTableWidget()
                    table.setColumnCount(len(STANDINGS_HEADERS))
                    table.setHorizontalHeaderLabels(STANDINGS_HEADERS)
                    table.setRowCount(len(teams))
                    
                    # Populate table with division ranking
                    for row, team_data in enumerate(teams):
                        rank = str(row + 1)  # Rank within division
                        items_data = [
                            rank,
                            team_data["name"],
                            team_data["wins"],
                            team_data["losses"],
                            team_data["win_pct"],
                            team_data["games_behind"],
                            team_data.get("streak", "N/A"),
                            team_data["record"]
                        ]
                        
                        for col, value in enumerate(items_data):
                            item = QTableWidgetItem(str(value))
                            table.setItem(row, col, item)
                    
                    # Configure table
                    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                    table.setAlternatingRowColors(True)
                    table.verticalHeader().setVisible(False)
                    
                    # Auto-resize columns
                    header = table.horizontalHeader()
                    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Team name stretches
                    
                    # Add table to tab
                    tab_widget.addTab(table, div_name)
            
            layout.addWidget(tab_widget)
        else:
            # Create single table for non-divisional leagues
            table = QTableWidget()
            table.setColumnCount(len(STANDINGS_HEADERS))
            table.setHorizontalHeaderLabels(STANDINGS_HEADERS)
            table.setRowCount(len(standings_data.teams))
            
            # Populate table
            for row, team_data in enumerate(standings_data.teams):
                rank = str(row + 1)
                items_data = [
                    rank,
                    team_data["name"],
                    team_data["wins"],
                    team_data["losses"],
                    team_data["win_pct"],
                    team_data["games_behind"],
                    team_data.get("streak", "N/A"),
                    team_data["record"]
                ]
                
                for col, value in enumerate(items_data):
                    item = QTableWidgetItem(str(value))
                    table.setItem(row, col, item)
            
            # Configure table
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            
            # Auto-resize columns
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Team name stretches
            
            layout.addWidget(table)
    
    def _add_leaders_data_to_layout(self, layout, data):
        """Add leaders data to layout using tabbed interface with one tab per team"""
        if not data:
            layout.addWidget(QLabel("No leaders data available."))
            return
        
        # Handle both list and dict formats for ESPN leaders data
        if isinstance(data, dict):
            # Convert dict format to list format for consistent processing
            if "teams" in data:
                data = data["teams"]
            elif isinstance(data, dict) and all(isinstance(v, (dict, list)) for v in data.values()):
                # Legacy dict format - convert to list structure
                data = [{"team": {"displayName": "Team"}, "leaders": [{"displayName": k, "leaders": [v] if isinstance(v, dict) else v} for k, v in data.items()]}]
        
        if not isinstance(data, list):
            layout.addWidget(QLabel("Leaders data format not recognized."))
            return
        
        # Filter out teams with no data
        valid_teams = []
        for team_data in data:
            if isinstance(team_data, dict) and team_data.get("leaders"):
                valid_teams.append(team_data)
        
        if not valid_teams:
            layout.addWidget(QLabel("No statistical leaders found in data."))
            return
        
        # Create tab widget for teams
        tab_widget = QTabWidget()
        tab_widget.setAccessibleName("Team Leaders")
        tab_widget.setAccessibleDescription("Statistical leaders by team. Use arrow keys to navigate between teams, Tab to enter table.")
        
        # Create a tab for each team
        for team_data in valid_teams:
            team_info = team_data.get("team", {})
            team_name = team_info.get("displayName", team_info.get("abbreviation", "Unknown Team"))
            
            # Create widget for this team's tab
            team_widget = QWidget()
            team_layout = QVBoxLayout()
            
            # Create leaders table for this team
            leaders_table = LeadersTable(parent=self)
            
            # Parse this team's statistical leaders
            team_leaders = team_data.get("leaders", [])
            rows = []
            
            for category_data in team_leaders:
                if not isinstance(category_data, dict):
                    continue
                    
                category_name = category_data.get("displayName", category_data.get("name", "Unknown Category"))
                category_leaders = category_data.get("leaders", [])
                
                # Add each leader in this category
                for leader in category_leaders:
                    if not isinstance(leader, dict):
                        continue
                        
                    athlete_info = leader.get("athlete", {})
                    player_name = athlete_info.get("displayName", athlete_info.get("fullName", "Unknown Player"))
                    display_value = leader.get("displayValue", "N/A")
                    
                    rows.append([
                        category_name,
                        player_name,
                        display_value
                    ])
            
            if rows:
                # Use custom headers for individual team view (no team column needed)
                leaders_table.setColumnCount(3)
                leaders_table.setHorizontalHeaderLabels(["Category", "Player", "Value"])
                leaders_table.setRowCount(len(rows))
                
                for row, data_row in enumerate(rows):
                    for col, value in enumerate(data_row):
                        item = QTableWidgetItem(str(value))
                        leaders_table.setItem(row, col, item)
                
                # Configure table appearance
                leaders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                leaders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                leaders_table.setAlternatingRowColors(True)
                leaders_table.verticalHeader().setVisible(False)
                
                # Resize columns
                header = leaders_table.horizontalHeader()
                header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Player name stretches
                
                # Set accessibility
                leaders_table.setAccessibleName(f"{team_name} Statistical Leaders")
                leaders_table.setAccessibleDescription(f"Statistical leaders for {team_name}. Use arrow keys to navigate.")
                
                team_layout.addWidget(leaders_table)
            else:
                team_layout.addWidget(QLabel(f"No statistical leaders available for {team_name}."))
            
            team_widget.setLayout(team_layout)
            tab_widget.addTab(team_widget, team_name)
        
        # Add tab widget to main layout
        layout.addWidget(tab_widget)
        
        # Set focus to first tab initially
        if tab_widget.count() > 0:
            tab_widget.setCurrentIndex(0)
    
    def _add_boxscore_data_to_layout(self, layout, data):
        """Add boxscore data to layout using accessible tables with proper keyboard navigation"""
        if not data:
            layout.addWidget(QLabel("No boxscore data available."))
            return
        
        # Check if data has the expected ESPN API structure
        has_teams = isinstance(data, dict) and "teams" in data and data["teams"]
        has_players = isinstance(data, dict) and "players" in data and data["players"]
        
        if not has_teams and not has_players:
            info_label = QLabel("Boxscore data is not available for this game.\n\n"
                               "This can happen for several reasons:\n"
                               "• Game is too old (ESPN may not provide detailed statistics for older games)\n"
                               "• Game was postponed or cancelled\n"
                               "• Game has not yet started\n"
                               "• Data is temporarily unavailable from ESPN\n\n"
                               "Try checking recent games or games currently in progress for boxscore data.")
            info_label.setWordWrap(True)
            info_label.setStyleSheet("padding: 10px; color: #666; font-size: 12px;")
            layout.addWidget(info_label)
            return
        
        # Create tab widget for organized boxscore display
        tab_widget = QTabWidget()
        tab_widget.setAccessibleName("Boxscore Tabs")
        tab_widget.setAccessibleDescription("Tabbed view of team and player statistics. Use Left/Right arrow keys to navigate tabs, Tab to enter tables.")
        tab_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Process each team separately - create tabs for each team
        if has_teams or has_players:
            # Determine team names first
            team_names = []
            if has_teams:
                for team_data in data["teams"]:
                    team_name = team_data.get("team", {}).get("displayName", "Unknown Team")
                    team_names.append(team_name)
            elif has_players:
                for team_players in data["players"]:
                    team_name = team_players.get("team", {}).get("displayName", "Unknown Team")
                    team_names.append(team_name)
            
            # Create tabs for each team
            for team_idx in range(len(team_names)):
                team_name = team_names[team_idx]
                
                # Team Statistics Tab
                if has_teams and team_idx < len(data["teams"]):
                    team_data = data["teams"][team_idx]
                    team_stats = team_data.get("statistics", [])
                    
                    if team_stats:
                        team_widget = QWidget()
                        team_layout = QVBoxLayout()
                        
                        # Create team header
                        team_label = QLabel(f"=== {team_name} Team Statistics ===")
                        team_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
                        team_layout.addWidget(team_label)
                        
                        first_team_table = None  # Track first table for focus
                        
                        for stat_group in team_stats:
                            stat_type = stat_group.get("displayName", stat_group.get("name", "Team Stats"))
                            stats_array = stat_group.get("stats", [])
                            
                            if stats_array:
                                # Create team statistics table
                                team_table = BoxscoreTable(title=f"{team_name} {stat_type}")
                                team_table.setup_columns(["Statistic", "Value"])
                                
                                # Prioritize important stats by putting them first
                                important_stats = ['runs', 'hits', 'errors', 'homeRuns', 'runsBattedIn']
                                if stat_type.lower() == 'pitching':
                                    important_stats = ['earnedRuns', 'runs', 'hits', 'strikeouts', 'walks', 'homeRuns']
                                
                                stats_data = []
                                remaining_stats = []
                                
                                # First pass: find important stats
                                for stat in stats_array:
                                    stat_name = stat.get("displayName", stat.get("name", "Unknown"))
                                    stat_value = stat.get("displayValue", str(stat.get("value", "N/A")))
                                    stat_key = stat.get("name", "").lower()
                                    
                                    if any(important in stat_key for important in important_stats):
                                        stats_data.append([stat_name, stat_value])
                                    else:
                                        remaining_stats.append([stat_name, stat_value])
                                
                                # Add a separator if we have both important and remaining stats
                                if stats_data and remaining_stats:
                                    stats_data.append(["--- Other Stats ---", ""])
                                
                                # Add remaining stats
                                stats_data.extend(remaining_stats)
                                
                                # Set focus on first table created
                                should_focus = first_team_table is None
                                if should_focus:
                                    first_team_table = team_table
                                
                                team_table.populate_data(stats_data, set_focus=should_focus)
                                team_layout.addWidget(team_table)
                        
                        team_widget.setLayout(team_layout)
                        tab_widget.addTab(team_widget, f"{team_name} Stats")
                
                # Player Statistics Tabs for this team
                if has_players and team_idx < len(data["players"]):
                    team_players = data["players"][team_idx]
                    player_stats_groups = team_players.get("statistics", [])
                    
                    for stat_group in player_stats_groups:
                        stat_type = stat_group.get("type", "Unknown")
                        stat_names = stat_group.get("names", [])
                        athletes = stat_group.get("athletes", [])
                        
                        if not athletes or not stat_names:
                            continue
                        
                        # Create widget for this stat type (batting/pitching)
                        stat_widget = QWidget()
                        stat_layout = QVBoxLayout()
                        
                        # Create team header
                        team_label = QLabel(f"=== {team_name} {stat_type.title()} ===")
                        team_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
                        stat_layout.addWidget(team_label)
                        
                        # Create player statistics table
                        stat_table = BoxscoreTable(title=f"{team_name} {stat_type.title()}")
                        
                        # Build headers - Player name + position + stat names
                        headers = ["Player", "Pos"] + stat_names
                        stat_table.setup_columns(headers, stretch_column=0)
                        
                        # Build player data
                        player_data = []
                        for athlete in athletes:
                            if not athlete.get("active", True):
                                continue
                                
                            player_info = athlete.get("athlete", {})
                            player_name = player_info.get("displayName", "Unknown")
                            position = player_info.get("position", {}).get("abbreviation", "")
                            stats = athlete.get("stats", [])
                            
                            # Build row data
                            row = [player_name, position]
                            row.extend(stats)
                            player_data.append(row)
                        
                        # Set focus for first tab created
                        should_focus = tab_widget.count() == 0
                        stat_table.populate_data(player_data, set_focus=should_focus)
                        stat_layout.addWidget(stat_table)
                        
                        stat_widget.setLayout(stat_layout)
                        tab_widget.addTab(stat_widget, f"{team_name} {stat_type.title()}")
        
        # Add the tab widget to the main layout
        layout.addWidget(tab_widget)
        
        # Configure custom keyboard navigation for tab widget
        original_keyPressEvent = tab_widget.keyPressEvent
        
        def custom_keyPressEvent(event):
            key = event.key()
            
            # Handle arrow keys for tab navigation when focus is on tab bar
            if tab_widget.tabBar().hasFocus():
                if key == Qt.Key.Key_Left:
                    current = tab_widget.currentIndex()
                    new_index = (current - 1) % tab_widget.count()
                    tab_widget.setCurrentIndex(new_index)
                    event.accept()
                    return
                elif key == Qt.Key.Key_Right:
                    current = tab_widget.currentIndex()
                    new_index = (current + 1) % tab_widget.count()
                    tab_widget.setCurrentIndex(new_index)
                    event.accept()
                    return
                elif key == Qt.Key.Key_Tab:
                    # Tab from tab bar into first table of current tab
                    current_widget = tab_widget.currentWidget()
                    if current_widget:
                        tables = current_widget.findChildren(BoxscoreTable)
                        if tables:
                            tables[0].setFocus()
                            if tables[0].rowCount() > 0:
                                tables[0].setCurrentCell(0, 0)
                    event.accept()
                    return
            
            # Default handling
            original_keyPressEvent(event)
        
        tab_widget.keyPressEvent = custom_keyPressEvent
        
        # Set up initial tab focus
        if tab_widget.count() > 0:
            tab_widget.setCurrentIndex(0)
            # Focus on the tab bar initially so arrows can navigate tabs
            QTimer.singleShot(50, lambda: tab_widget.tabBar().setFocus())

    def _add_plays_list_to_layout(self, layout, data):
        """Add hierarchical play-by-play tree to layout"""
        if not data:
            layout.addWidget(QLabel("No play-by-play data available."))
            return
        
        # Store plays data for export functionality
        self.current_plays_data = data
        
        # Detect sport type from data structure or current league
        sport_type = self._detect_sport_type(data)
        # The tree builders take only (tree, data), so stash the league here for
        # the ones that tag their items for play audio.
        self._plays_sport_type = sport_type

        # Add header info with export button
        header_layout = QHBoxLayout()
        info_label = QLabel(f"Play-by-Play ({len(data)} plays)")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
        header_layout.addWidget(info_label)

        if sport_type in ["NHL", "NCAAH", "NCAAWH"]:
            hockey_note = QLabel("Note: ESPN hockey feeds may provide key events only (goals/penalties), not every shift-level action.")
            hockey_note.setStyleSheet("font-size: 11px; color: #666; margin-left: 8px;")
            hockey_note.setWordWrap(True)
            header_layout.addWidget(hockey_note)
        
        # Add Export Game Log button
        export_btn = QPushButton("Export Game Log")
        export_btn.setAccessibleName("Export Game Log Button")
        export_btn.setAccessibleDescription("Export the complete game log as an HTML file")
        export_btn.clicked.connect(self._export_game_log)
        export_btn.setMaximumWidth(150)
        header_layout.addWidget(export_btn)
        
        # Add Pitch Audio button for baseball games. _detect_sport_type returns a
        # league key, so this is "MLB" — it used to read 'baseball', which the
        # detector never returns, so the button never appeared.
        if sport_type == "MLB":
            pitch_audio_btn = QPushButton("Pitch Audio")
            pitch_audio_btn.setAccessibleName("Pitch Audio Button")
            pitch_audio_btn.setAccessibleDescription("Play audio for the currently selected pitch (Alt+P)")
            pitch_audio_btn.clicked.connect(lambda: self._play_current_pitch_audio(plays_tree))
            pitch_audio_btn.setMaximumWidth(120)
            header_layout.addWidget(pitch_audio_btn)

        # The same thing for the sports whose plays carry court/rink coordinates.
        if self.play_audio_mapper and self.play_audio_mapper.supports(sport_type):
            play_audio_btn = QPushButton("Play Audio")
            play_audio_btn.setAccessibleName("Play Audio Button")
            play_audio_btn.setAccessibleDescription(
                "Play spatial audio for the currently selected play (Alt+P). "
                "Alt+S plays every located play in the period."
            )
            play_audio_btn.clicked.connect(lambda: self._play_current_play_audio(plays_tree))
            play_audio_btn.setMaximumWidth(120)
            header_layout.addWidget(play_audio_btn)

        header_layout.addStretch()  # Push buttons to the left
        
        layout.addLayout(header_layout)
        
        # Create tree widget for hierarchical view
        plays_tree = QTreeWidget()
        plays_tree.setAccessibleName("Play-by-Play Tree")
        plays_tree.setAccessibleDescription("Hierarchical view of game plays organized by period and drive/inning. Use up/down arrows to navigate, left/right to expand/collapse.")
        plays_tree.setHeaderLabels(["Play Description"])
        
        # Add custom event handling for better accessibility
        def on_item_expanded(item):
            # Provide accessibility feedback for expansions
            item_text = item.text(0)
            plays_tree.setAccessibleDescription(f"Expanded {item_text}. Use arrow keys to navigate children.")
        
        def on_item_collapsed(item):
            # Provide accessibility feedback for collapses
            item_text = item.text(0)
            plays_tree.setAccessibleDescription(f"Collapsed {item_text}. Use right arrow to expand.")
        
        plays_tree.itemExpanded.connect(on_item_expanded)
        plays_tree.itemCollapsed.connect(on_item_collapsed)
        
        # Add context menu for pitch audio options
        def show_context_menu(position):
            current_item = plays_tree.itemAt(position)
            if current_item:
                self._show_pitch_context_menu(current_item, plays_tree.mapToGlobal(position))
        
        def on_key_press(event):
            current_item = plays_tree.currentItem()
            
            if event.key() == Qt.Key.Key_F10 and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                # Shift+F10 for context menu (works on any item)
                if current_item:
                    item_rect = plays_tree.visualItemRect(current_item)
                    self._show_pitch_context_menu(current_item, plays_tree.mapToGlobal(item_rect.center()))
                    event.accept()
                    return
            elif current_item and self._handle_plays_audio_key(
                current_item, event.key(), event.modifiers()
            ):
                event.accept()
                return
            # Fall back to default behavior
            plays_tree.__class__.keyPressEvent(plays_tree, event)
        
        # Enable context menu
        plays_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        plays_tree.customContextMenuRequested.connect(show_context_menu)
        plays_tree.keyPressEvent = on_key_press
        
        # Store reference for strike zone audio context
        self.current_tree_widget = plays_tree
        
        basketball_leagues = {"NBA", "WNBA", "NCAAM", "NCAAWB", "NCAAW"}
        football_leagues = {"NFL", "NCAAF"}

        if sport_type == "MLB":
            self._build_baseball_tree(plays_tree, data)
        elif sport_type in football_leagues:
            self._build_football_tree(plays_tree, data)
        elif sport_type in basketball_leagues:
            self._build_basketball_tree(plays_tree, data)
        else:
            # Default to generic organization
            self._build_generic_tree(plays_tree, data)
        
        layout.addWidget(plays_tree)
        
        # Set focus to the tree for better accessibility
        QTimer.singleShot(100, lambda: plays_tree.setFocus())
    
    def _add_drives_list_to_layout(self, layout, drives_data):
        """Add NFL/NCAAF drives data to layout (Football-specific method)"""
        
        def get_drive_result_info(drive):
            """Get scoring drive information with accessibility-compliant colors"""
            result = drive.get('result', '').upper()
            
            # WCAG AA compliant colors (4.5:1 contrast ratio minimum)
            if result == 'TD':
                return {
                    'icon': '🏈', 
                    'badge': 'TD 7pts', 
                    'color': QColor(0, 100, 0, 80),      # Dark green background
                    'accessible_text': 'Touchdown scoring drive'
                }
            elif result == 'FG':
                return {
                    'icon': '🥅', 
                    'badge': 'FG 3pts', 
                    'color': QColor(0, 0, 139, 60),      # Dark blue background
                    'accessible_text': 'Field goal scoring drive'
                }
            elif result == 'MISSED FG':
                return {
                    'icon': '❌', 
                    'badge': 'MISSED FG', 
                    'color': QColor(139, 0, 0, 60),      # Dark red background
                    'accessible_text': 'Missed field goal attempt'
                }
            elif result in ['FUMBLE', 'INT', 'INTERCEPTION', 'TURNOVER']:
                return {
                    'icon': '🔄', 
                    'badge': 'TURNOVER', 
                    'color': QColor(255, 140, 0, 60),    # Dark orange background
                    'accessible_text': 'Turnover drive'
                }
            elif result == 'DOWNS':
                return {
                    'icon': '🛑', 
                    'badge': '4TH DOWN', 
                    'color': QColor(255, 140, 0, 60),    # Dark orange background
                    'accessible_text': 'Turnover on downs'
                }
            elif result == 'PUNT':
                return {
                    'icon': '⚡', 
                    'badge': 'PUNT', 
                    'color': QColor(128, 128, 128, 40),  # Light gray background
                    'accessible_text': 'Punt drive'
                }
            elif result in ['END OF HALF', 'END OF GAME']:
                return {
                    'icon': '⏰', 
                    'badge': 'CLOCK', 
                    'color': QColor(128, 128, 128, 40),  # Light gray background
                    'accessible_text': 'Clock expiration drive'
                }
            elif result == 'SAFETY':
                return {
                    'icon': '🛡️', 
                    'badge': 'SAFETY 2pts', 
                    'color': QColor(128, 0, 128, 60),    # Purple background
                    'accessible_text': 'Safety scoring drive'
                }
            else:
                return {
                    'icon': '📌', 
                    'badge': result if result else 'DRIVE', 
                    'color': QColor(255, 255, 255, 0),   # No background
                    'accessible_text': 'Non-scoring drive'
                }
        
        if not drives_data:
            layout.addWidget(QLabel("No drives data available."))
            return
        
        # Handle both current drive and drive history
        all_drives = []
        
        # Add current drive if available
        current_drive = drives_data.get("current")
        if current_drive:
            all_drives.append(("Current Drive", current_drive))
        
        # Add previous drives if available
        previous_drives = drives_data.get("previous", [])
        for i, drive in enumerate(previous_drives):
            drive_num = len(previous_drives) - i  # Number drives in reverse order
            all_drives.append((f"Drive {drive_num}", drive))
        
        if not all_drives:
            layout.addWidget(QLabel("No drive data available."))
            return
        
        # Store drives data for export functionality
        self.current_drives_data = drives_data
        
        # Add header info with export button
        header_layout = QHBoxLayout()
        total_drives = len(all_drives)
        info_label = QLabel(f"Drive-by-Drive Summary ({total_drives} drives)")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
        header_layout.addWidget(info_label)
        
        # Add Export Game Log button
        export_btn = QPushButton("Export Game Log")
        export_btn.setAccessibleName("Export Game Log Button")
        export_btn.setAccessibleDescription("Export the complete game log as an HTML file")
        export_btn.clicked.connect(self._export_game_log)
        export_btn.setMaximumWidth(150)
        header_layout.addWidget(export_btn)
        header_layout.addStretch()  # Push button to the left
        
        layout.addLayout(header_layout)
        
        # Create tree widget for drives
        drives_tree = QTreeWidget()
        sport_name = "NFL/NCAAF" if self.league in ["NFL", "NCAAF"] else "Football"
        drives_tree.setAccessibleName(f"{sport_name} Drives Tree")
        drives_tree.setAccessibleDescription(f"Hierarchical view of {sport_name} drives organized by quarter. Use up/down arrows to navigate, left/right to expand/collapse.")
        drives_tree.setHeaderLabels(["Drive Summary"])
        
        # Group drives by quarter for better organization
        quarter_groups = {}
        
        for drive_label, drive in all_drives:
            if not drive or not isinstance(drive, dict):
                continue
                
            # Get drive info
            description = drive.get("description", "Unknown drive")
            team_info = drive.get("team", {})
            team_name = team_info.get("displayName", "Unknown Team")
            
            # Determine quarter from plays
            plays = drive.get("plays", [])
            quarter = "Unknown Quarter"
            if plays and len(plays) > 0:
                first_play = plays[0]
                period_info = first_play.get("period", {})
                quarter_num = period_info.get("number", "?")
                quarter = f"Quarter {quarter_num}"
            
            # Separate kickoffs from regular drive plays
            drive_plays = []
            kickoff_plays = []
            
            for play in plays:
                play_type = play.get("type", {})
                play_type_text = play_type.get("text", "").lower()
                
                if "kickoff" in play_type_text:
                    kickoff_plays.append(play)
                else:
                    drive_plays.append(play)
            
            # Group by quarter
            if quarter not in quarter_groups:
                quarter_groups[quarter] = []
            
            # Add kickoffs as separate entries
            for kickoff in kickoff_plays:
                quarter_groups[quarter].append(("Kickoff", {"plays": [kickoff]}, "Special Teams", "Kickoff", True))
            
            # Add regular drive if it has non-kickoff plays
            if drive_plays:
                modified_drive = drive.copy()
                modified_drive["plays"] = drive_plays
                quarter_groups[quarter].append((drive_label, modified_drive, team_name, description, False))
        
        # Build tree structure by quarter
        for quarter in sorted(quarter_groups.keys()):
            quarter_item = QTreeWidgetItem([quarter])
            quarter_item.setExpanded(True)
            drives_tree.addTopLevelItem(quarter_item)
            
            drives_in_quarter = quarter_groups[quarter]
            for drive_label, drive, team_name, description, is_kickoff in drives_in_quarter:
                if is_kickoff:
                    # Create kickoff item directly under quarter
                    kickoff_item = QTreeWidgetItem(["⚡ Kickoff"])
                    kickoff_item.setBackground(0, QColor(240, 240, 255))  # Light blue
                    kickoff_item.setExpanded(False)
                    quarter_item.addChild(kickoff_item)
                    
                    # Add the kickoff play
                    plays = drive.get("plays", [])
                    for play in plays:
                        play_text = play.get("text", "Unknown play")
                        
                        # Add clock context
                        clock = play.get("clock", {})
                        if clock:
                            clock_display = clock.get("displayValue", "")
                            if clock_display:
                                play_text = f"[{clock_display}] {play_text}"
                        
                        play_item = QTreeWidgetItem([play_text])
                        kickoff_item.addChild(play_item)
                else:
                    # Create enhanced drive summary node with scoring information
                    result_info = get_drive_result_info(drive)
                    
                    # Build enhanced drive summary with scoring indicators
                    enhanced_summary = f"{result_info['icon']} [{result_info['badge']}] {team_name}: {description}"
                    
                    drive_item = QTreeWidgetItem([enhanced_summary])
                    drive_item.setExpanded(False)  # Collapsed by default
                    
                    # Apply accessibility-compliant background color
                    drive_item.setBackground(0, result_info['color'])
                    
                    # Add accessible description for screen readers
                    drive_item.setToolTip(0, f"{result_info['accessible_text']}: {team_name} - {description}")
                    
                    quarter_item.addChild(drive_item)
                    
                    # Add individual plays under the drive (already filtered to exclude kickoffs)
                    plays = drive.get("plays", [])
                    for play in plays:
                        play_text = play.get("text", "Unknown play")
                        
                        # Add down and distance information for NFL plays
                        down_distance_prefix = ""
                        start = play.get("start", {})
                        
                        # For display, we want to show the situation at the START of the play
                        down = start.get("down", 0)
                        distance = start.get("distance", 0)
                        possession_text = start.get("possessionText", "")
                        yards_to_endzone = start.get("yardsToEndzone", 0)
                        
                        # Get additional NFL-specific data
                        stat_yardage = play.get("statYardage", 0)
                        play_type = play.get("type", {})
                        play_type_text = play_type.get("text", "")
                        
                        # Build enhanced play description
                        enhanced_text = play_text
                        
                        # Add yardage information if available
                        if stat_yardage != 0:
                            yardage_display = f"(+{stat_yardage} yards)" if stat_yardage > 0 else f"({stat_yardage} yards)"
                            enhanced_text = f"{yardage_display} {enhanced_text}"
                        
                        # Add play type for clarity (accessible text)
                        if play_type_text and play_type_text.lower() not in enhanced_text.lower():
                            if "pass" in play_type_text.lower():
                                enhanced_text = f"PASS: {enhanced_text}"
                            elif "rush" in play_type_text.lower():
                                enhanced_text = f"RUSH: {enhanced_text}"
                            elif "sack" in play_type_text.lower():
                                enhanced_text = f"SACK: {enhanced_text}"
                            elif "penalty" in play_type_text.lower():
                                enhanced_text = f"PENALTY: {enhanced_text}"
                            elif "punt" in play_type_text.lower():
                                enhanced_text = f"PUNT: {enhanced_text}"
                            elif "field goal" in play_type_text.lower():
                                enhanced_text = f"FIELD GOAL: {enhanced_text}"
                        
                        # Add situational context
                        situation_prefix = ""
                        if yards_to_endzone <= 5:
                            situation_prefix = "GOAL LINE "
                        elif yards_to_endzone <= 20:
                            situation_prefix = "RED ZONE "
                        elif down == 4:
                            situation_prefix = "4TH DOWN "
                        
                        # Use start data for down/distance display (not end!)
                        if down > 0:  # Regular downs
                            if possession_text:
                                if situation_prefix:
                                    down_distance_prefix = f"[{situation_prefix}{down} & {distance} from {possession_text}] "
                                else:
                                    down_distance_prefix = f"[{down} & {distance} from {possession_text}] "
                            else:
                                down_distance_prefix = f"[{situation_prefix}{down} & {distance}] "
                        
                        # Add extra context for key plays
                        if play.get("scoringPlay"):
                            away_score = play.get("awayScore", 0)
                            home_score = play.get("homeScore", 0)
                            play_text = f"TOUCHDOWN: {down_distance_prefix}{enhanced_text} ({away_score}-{home_score})"
                        else:
                            play_text = f"{down_distance_prefix}{enhanced_text}"
                        
                        # Add clock context
                        clock = play.get("clock", {})
                        if clock:
                            clock_display = clock.get("displayValue", "")
                            if clock_display:
                                play_text = f"[{clock_display}] {play_text}"
                        
                        play_item = QTreeWidgetItem([play_text])
                        
                        # Highlight scoring plays
                        if play.get("scoringPlay"):
                            play_item.setBackground(0, QColor(255, 255, 150))  # Light yellow
                        # Highlight goal line plays
                        elif yards_to_endzone <= 5:
                            play_item.setBackground(0, QColor(255, 240, 240))  # Light red
                        # Highlight red zone plays  
                        elif yards_to_endzone <= 20:
                            play_item.setBackground(0, QColor(255, 250, 240))  # Light orange
                        
                        drive_item.addChild(play_item)
        
        layout.addWidget(drives_tree)
    
    def _detect_sport_type(self, data):
        """Detect sport type from play data or current league"""
        if hasattr(self, 'league') and self.league:
            return self.league
        
        # Try to detect from data structure
        if data and len(data) > 0:
            sample_play = data[0]
            period = sample_play.get("period", {})
            period_display = period.get("displayValue", "")
            
            if "inning" in period_display.lower():
                return "MLB"
            elif "quarter" in period_display.lower():
                # Need to differentiate between football and basketball quarters
                # Check for football-specific indicators
                if any(key in sample_play for key in ["driveNumber", "down", "distance", "yardsToEndzone"]):
                    return "NFL"
                else:
                    return "NBA"  # Default basketball for quarters without football indicators
            elif "period" in period_display.lower():
                return "NHL"
            elif "half" in period_display.lower() or "time" in period_display.lower():
                return "Soccer"
        
        return "Generic"
    
    def _build_baseball_tree(self, plays_tree, data):
        """Build baseball-specific hierarchical tree: Inning → Half → At-bat → Pitches"""
        if not data:
            return

        away_label, home_label = self._get_basketball_team_labels()

        # Group plays by inning number (int), preserving encounter order
        inning_order = []
        inning_halves = {}  # inning_num -> {"top": [], "bottom": [], "label": str}

        for play in data:
            period_info = play.get("period", {}) or {}
            period_number = period_info.get("number", 0)
            period_type = period_info.get("type", "").lower()
            period_display = period_info.get("displayValue", f"Inning {period_number}")

            if period_number not in inning_halves:
                inning_order.append(period_number)
                inning_halves[period_number] = {"top": [], "bottom": [], "label": period_display}

            if period_type == "bottom":
                inning_halves[period_number]["bottom"].append(play)
            else:
                inning_halves[period_number]["top"].append(play)

        for inning_num in inning_order:
            inning_data = inning_halves[inning_num]
            top_plays = inning_data["top"]
            bottom_plays = inning_data["bottom"]
            inning_label = inning_data["label"]

            # Runs scored each half — use score deltas (awayScore/homeScore only go up)
            # Summing scoreValue is unreliable; ESPN sets it on non-scoring plays too.
            top_runs = self._runs_in_half(top_plays, "awayScore")
            bottom_runs = self._runs_in_half(bottom_plays, "homeScore")
            total_runs = top_runs + bottom_runs

            # Final score after inning from last play that carries score data
            final_score_text = ""
            for play in reversed(top_plays + bottom_plays):
                away = self._safe_int(play.get("awayScore"))
                home = self._safe_int(play.get("homeScore"))
                if away is not None and home is not None:
                    final_score_text = f"  [{away_label} {away} - {home_label} {home}]"
                    break

            # Build inning header: "3rd Inning — NYM 2R, MIL 1R  [NYM 3 - MIL 2]"
            runs_parts = []
            if top_runs > 0:
                runs_parts.append(f"{away_label} {top_runs}R")
            if bottom_runs > 0:
                runs_parts.append(f"{home_label} {bottom_runs}R")

            if runs_parts:
                inning_header = f"{inning_label} — {', '.join(runs_parts)}{final_score_text}"
            else:
                inning_header = f"{inning_label}{final_score_text}"

            inning_item = QTreeWidgetItem([inning_header])
            inning_item.setExpanded(True)
            if total_runs > 0:
                inning_item.setBackground(0, QColor(230, 255, 230))  # light green for scoring innings
            plays_tree.addTopLevelItem(inning_item)

            # Top half
            if top_plays:
                ab_count = self._count_at_bats_in_plays(top_plays)
                runs_badge = f"  {top_runs}R" if top_runs > 0 else f"  {ab_count} AB"
                top_label = f"Top — {away_label} Batting{runs_badge}"
                top_item = QTreeWidgetItem([top_label])
                top_item.setExpanded(True)
                if top_runs > 0:
                    top_item.setBackground(0, QColor(200, 255, 200))
                inning_item.addChild(top_item)
                self._add_baseball_plays_to_tree_group(top_item, top_plays, away_label, home_label)

            # Bottom half
            if bottom_plays:
                ab_count = self._count_at_bats_in_plays(bottom_plays)
                runs_badge = f"  {bottom_runs}R" if bottom_runs > 0 else f"  {ab_count} AB"
                bottom_label = f"Bottom — {home_label} Batting{runs_badge}"
                bottom_item = QTreeWidgetItem([bottom_label])
                bottom_item.setExpanded(True)
                if bottom_runs > 0:
                    bottom_item.setBackground(0, QColor(200, 255, 200))
                inning_item.addChild(bottom_item)
                self._add_baseball_plays_to_tree_group(bottom_item, bottom_plays, away_label, home_label)

    def _count_at_bats_in_plays(self, plays):
        """Count distinct at-bats in a list of plays (for half-inning badge)"""
        seen = set()
        count = 0
        for play in plays:
            ab_id = play.get("atBatId")
            st = play.get("summaryType", "")
            if ab_id:
                if ab_id not in seen and st == "A":
                    seen.add(ab_id)
                    count += 1
            elif " pitches to " in play.get("text", ""):
                count += 1
        return max(count, 1)

    def _runs_in_half(self, plays, score_key):
        """Return runs scored in a half-inning.

        Primary: sum scoreValue from summaryType='S' plays only. ESPN sets
        scoreValue on both announcement ('A') and result ('S') plays for the
        same at-bat, so summing all plays double-counts. Using only 'S' plays
        avoids this.
        Fallback: last-minus-first score delta for data that lacks summaryType.
        """
        s_plays = [p for p in plays if p.get("summaryType") == "S"]
        if s_plays:
            return sum(max(0, int(p.get("scoreValue") or 0)) for p in s_plays)
        # Fallback: use score on the last play minus score on the first play
        scores = [int(p[score_key]) for p in plays if p.get(score_key) is not None]
        return max(0, scores[-1] - scores[0]) if len(scores) >= 2 else 0

    def _build_football_tree(self, plays_tree, data):
        """Build NFL/NCAAF hierarchical tree: Quarter → Drive → Plays"""
        away_label, home_label = self._get_basketball_team_labels()

        # Group plays into quarters, preserving drive order within each quarter
        quarter_order = []
        quarter_data = {}  # period_display -> {"drive_order": [], "drives": {key: []}, "team_names": {key: str}}

        for play in data:
            period_info = play.get("period", {}) or {}
            period_num = period_info.get("number", 1)
            period_display = period_info.get("displayValue", f"Q{period_num}")

            drive_number = play.get("driveNumber") or ""
            team_obj = play.get("team", {}) or {}
            team_abbr = (team_obj.get("abbreviation")
                         or team_obj.get("shortDisplayName")
                         or team_obj.get("displayName")
                         or "")
            drive_key = str(drive_number)

            if period_display not in quarter_data:
                quarter_order.append(period_display)
                quarter_data[period_display] = {"drive_order": [], "drives": {}, "team_names": {}}

            qd = quarter_data[period_display]
            if drive_key not in qd["drives"]:
                qd["drive_order"].append(drive_key)
                qd["drives"][drive_key] = []
                qd["team_names"][drive_key] = team_abbr
            elif team_abbr and not qd["team_names"][drive_key]:
                qd["team_names"][drive_key] = team_abbr

            qd["drives"][drive_key].append(play)

        for period_display in quarter_order:
            qd = quarter_data[period_display]

            # Score at end of quarter from last play with score data
            quarter_score = ""
            for dk in reversed(qd["drive_order"]):
                for play in reversed(qd["drives"][dk]):
                    away = self._safe_int(play.get("awayScore"))
                    home = self._safe_int(play.get("homeScore"))
                    if away is not None and home is not None:
                        quarter_score = f"  [{away_label} {away} - {home_label} {home}]"
                        break
                if quarter_score:
                    break

            quarter_item = QTreeWidgetItem([f"{period_display}{quarter_score}"])
            quarter_item.setExpanded(True)
            plays_tree.addTopLevelItem(quarter_item)

            for drive_key in qd["drive_order"]:
                drive_plays = qd["drives"][drive_key]
                if not drive_plays:
                    continue

                team_abbr = qd["team_names"][drive_key]
                drive_result = self._determine_drive_result(drive_plays)

                # Score at end of drive
                drive_score = ""
                for play in reversed(drive_plays):
                    away = self._safe_int(play.get("awayScore"))
                    home = self._safe_int(play.get("homeScore"))
                    if away is not None and home is not None:
                        drive_score = f"  ({away}-{home})"
                        break

                play_count = len(drive_plays)
                team_prefix = f"{team_abbr}: " if team_abbr else "Drive: "
                drive_header = f"{team_prefix}{drive_result}{drive_score}  ({play_count} plays)"

                drive_item = QTreeWidgetItem([drive_header])
                drive_item.setExpanded(False)
                if any(s in drive_result.lower() for s in ("touchdown", "field goal", "safety")):
                    drive_item.setBackground(0, QColor(220, 255, 220))

                quarter_item.addChild(drive_item)
                self._add_football_plays_to_drive(drive_item, drive_plays)
    
    def _build_generic_tree(self, plays_tree, data):
        """Build generic hierarchical tree — used for NHL, Soccer, and unknown sports"""
        away_label, home_label = self._get_basketball_team_labels()

        period_order = []
        period_groups = {}  # key -> {"plays": [], "label": str}

        for play in data:
            period_info = play.get("period", {}) or {}
            period_num = period_info.get("number", 1)
            period_display = period_info.get("displayValue", f"Period {period_num}")
            key = f"{period_num}:{period_display}"

            if key not in period_groups:
                period_order.append(key)
                period_groups[key] = {"plays": [], "label": period_display}
            period_groups[key]["plays"].append(play)

        for key in period_order:
            pg = period_groups[key]
            plays_in_period = pg["plays"]
            period_label = pg["label"]

            # Score at end of period + goal/score count
            period_score = ""
            goals_this_period = sum(max(0, p.get("scoreValue", 0) or 0) for p in plays_in_period)
            for play in reversed(plays_in_period):
                away = self._safe_int(play.get("awayScore"))
                home = self._safe_int(play.get("homeScore"))
                if away is not None and home is not None:
                    period_score = f"  [{away_label} {away} - {home_label} {home}]"
                    break

            if goals_this_period > 0:
                g = goals_this_period
                period_header = f"{period_label}  ({g} goal{'s' if g != 1 else ''}){period_score}"
            else:
                period_header = f"{period_label}{period_score}"

            period_item = QTreeWidgetItem([period_header])
            period_item.setExpanded(True)
            plays_tree.addTopLevelItem(period_item)
            self._label_period_for_audio(period_item, plays_in_period)

            for play in plays_in_period:
                play_text = play.get("text", "Unknown play")
                clock_time = self._extract_play_clock_display(play)
                score_info = self._extract_basketball_score_info(play)

                if clock_time not in ("--:--", ""):
                    formatted_text = self._format_clock_play_entry(play_text, clock_time, score_info)
                else:
                    formatted_text = play_text

                play_item = QTreeWidgetItem([formatted_text])
                if play.get("scoringPlay", False) or (play.get("scoreValue", 0) or 0) > 0:
                    play_item.setBackground(0, QColor(220, 255, 220))
                self._tag_play_for_audio(play_item, play)
                period_item.addChild(play_item)

    def _build_basketball_tree(self, plays_tree, data):
        """Build basketball-specific tree: Period → Plays with clock + score"""
        away_label, home_label = self._get_basketball_team_labels()

        period_order = []
        period_groups = {}  # period_num -> {"plays": [], "label": str}

        for play in data:
            period_info = play.get("period", {}) or {}
            period_num = period_info.get("number", 1)
            period_display = period_info.get("displayValue", str(period_num))

            if period_num not in period_groups:
                period_order.append(period_num)
                period_groups[period_num] = {"plays": [], "label": period_display}
            period_groups[period_num]["plays"].append(play)

        for period_num in period_order:
            pg = period_groups[period_num]
            plays_in_period = pg["plays"]
            period_label = self._ordinal_period_label(period_num, pg["label"])

            # Score at end of period
            period_score = ""
            for play in reversed(plays_in_period):
                away = self._safe_int(play.get("awayScore"))
                home = self._safe_int(play.get("homeScore"))
                if away is not None and home is not None:
                    period_score = f"  [{away_label} {away} - {home_label} {home}]"
                    break

            period_item = QTreeWidgetItem([f"{period_label}{period_score}"])
            period_item.setExpanded(True)
            plays_tree.addTopLevelItem(period_item)
            self._label_period_for_audio(period_item, plays_in_period)

            period_plays = sorted(
                plays_in_period,
                key=lambda p: self._parse_basketball_clock(p.get("clock", "00:00")),
                reverse=True,
            )

            for play in period_plays:
                action_text = play.get("text", "Unknown play")
                score_info = self._extract_basketball_score_info(play)
                clock_time = play.get("clock", "00:00")
                formatted_play = self._format_basketball_play_entry(
                    action_text, score_info, clock_time
                )

                play_item = QTreeWidgetItem([formatted_play])
                self._apply_basketball_play_styling(play_item, play)
                self._tag_play_for_audio(play_item, play)
                period_item.addChild(play_item)

    def _ordinal_period_label(self, period_num, fallback_display=""):
        """Convert period number to a readable label (1st Quarter, OT, etc.)"""
        fb_lower = fallback_display.lower()
        if "ot" in fb_lower or "overtime" in fb_lower or "extra" in fb_lower:
            ot_num = period_num - 4
            return f"OT{ot_num if ot_num > 1 else ''}"
        ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
        if period_num in ordinals:
            return f"{ordinals[period_num]} Quarter"
        if period_num > 4:
            ot_num = period_num - 4
            return f"OT{ot_num if ot_num > 1 else ''}"
        return fallback_display or f"Period {period_num}"

    def _parse_basketball_clock(self, clock_str):
        """Parse basketball clock value into seconds for sorting"""
        try:
            clock_display = self._extract_basketball_clock_display(clock_str)
            if ":" in clock_display:
                minutes, seconds = clock_display.split(":")
                return int(minutes) * 60 + int(seconds)
            return 0
        except Exception:
            return 0

    def _extract_play_clock_display(self, play):
        """Extract readable clock value from a play payload"""
        if not isinstance(play, dict):
            return "--:--"
        return self._extract_basketball_clock_display(play.get("clock", "--:--"))

    def _extract_basketball_clock_display(self, clock_value):
        """Extract a readable MM:SS clock from ESPN clock payload variants"""
        if isinstance(clock_value, str):
            return clock_value

        if isinstance(clock_value, dict):
            return (
                clock_value.get("displayValue")
                or clock_value.get("value")
                or clock_value.get("text")
                or "--:--"
            )

        if isinstance(clock_value, list) and clock_value:
            first_entry = clock_value[0]
            if isinstance(first_entry, dict):
                return (
                    first_entry.get("displayValue")
                    or first_entry.get("value")
                    or first_entry.get("text")
                    or "--:--"
                )
            return str(first_entry)

        return "--:--"

    def _extract_basketball_score_info(self, play):
        """Extract score information from basketball play data"""
        away_raw = play.get("awayScore")
        home_raw = play.get("homeScore")

        away_score = self._safe_int(away_raw)
        home_score = self._safe_int(home_raw)

        has_score = away_score is not None and home_score is not None

        return {
            "away": away_score,
            "home": home_score,
            "has_score": has_score,
            "is_scoring": play.get("scoringPlay", False),
        }

    def _safe_int(self, value):
        """Convert score-like values to int when possible"""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _get_basketball_team_labels(self):
        """Resolve away/home display labels from available game context"""
        away_label = "Away"
        home_label = "Home"

        sources = [
            getattr(self, "current_raw_details", None),
            getattr(self, "original_game_data", None),
            getattr(self, "raw_game_data", None),
        ]

        for source in sources:
            if not isinstance(source, dict):
                continue

            # Scoreboard-like shape
            home_team = source.get("home_team")
            away_team = source.get("away_team")
            if isinstance(home_team, dict) and isinstance(away_team, dict):
                home_label = home_team.get("abbreviation") or home_team.get("name") or home_label
                away_label = away_team.get("abbreviation") or away_team.get("name") or away_label
                return away_label, home_label

            # Game-details shape (competitions/competitors)
            containers = [source]
            header = source.get("header")
            if isinstance(header, dict):
                containers.append(header)

            for container in containers:
                competitions = container.get("competitions", [])
                if not competitions:
                    continue

                competitors = competitions[0].get("competitors", [])
                for competitor in competitors:
                    team = competitor.get("team", {}) if isinstance(competitor, dict) else {}
                    label = (
                        team.get("abbreviation")
                        or team.get("shortDisplayName")
                        or team.get("displayName")
                        or team.get("name")
                    )
                    if not label:
                        continue

                    home_away = competitor.get("homeAway", "").lower()
                    if home_away == "away":
                        away_label = label
                    elif home_away == "home":
                        home_label = label

                if away_label != "Away" or home_label != "Home":
                    return away_label, home_label

        return away_label, home_label

    def _format_basketball_play_entry(self, action_text, score_info, clock_time):
        """Format basketball play entry with action, score, and time"""
        time_part = self._extract_basketball_clock_display(clock_time)
        return self._format_clock_play_entry(action_text, time_part, score_info)

    def _format_clock_play_entry(self, action_text, clock_time, score_info):
        """Format a clock-based play as Action - Time - Team-labeled score"""
        clean_action = self._clean_basketball_action_text(action_text)
        away_label, home_label = self._get_basketball_team_labels()

        if score_info.get("has_score"):
            score_part = f"{away_label} {score_info['away']}, {home_label} {score_info['home']}"
            return f"{clean_action} - {clock_time} ({score_part})"

        if score_info.get("is_scoring"):
            return f"{clean_action} - {clock_time} (Scoring play)"

        return f"{clean_action} - {clock_time}"

    def _clean_basketball_action_text(self, action_text):
        """Clean basketball action text for readability"""
        if not action_text:
            return "Unknown play"
        return " ".join(action_text.split())

    def _apply_basketball_play_styling(self, play_item, play):
        """Apply visual styling to basketball play items based on play type"""
        action_text = play.get("text", "").lower()
        from PyQt6.QtGui import QBrush

        if any(word in action_text for word in ["makes", "made"]) and any(word in action_text for word in ["three", "3-pt"]):
            play_item.setBackground(0, QBrush(QColor(173, 216, 230, 50)))
        elif any(word in action_text for word in ["makes", "made"]) and any(word in action_text for word in ["layup", "dunk", "tip"]):
            play_item.setBackground(0, QBrush(QColor(144, 238, 144, 50)))
        elif any(word in action_text for word in ["makes", "made"]) and "free throw" in action_text:
            play_item.setBackground(0, QBrush(QColor(255, 255, 224, 50)))
        elif "misses" in action_text and any(word in action_text for word in ["three", "3-pt"]):
            play_item.setBackground(0, QBrush(QColor(255, 182, 193, 50)))
        elif "foul" in action_text and "technical" not in action_text:
            play_item.setBackground(0, QBrush(QColor(255, 200, 150, 50)))
        elif any(word in action_text for word in ["technical foul", "flagrant"]):
            play_item.setBackground(0, QBrush(QColor(255, 165, 0, 30)))
        elif "timeout" in action_text:
            play_item.setBackground(0, QBrush(QColor(211, 211, 211, 50)))
        elif "substitution" in action_text:
            play_item.setBackground(0, QBrush(QColor(230, 230, 250, 50)))
        elif play.get("scoringPlay", False):
            play_item.setBackground(0, QBrush(QColor(176, 224, 230, 50)))
    
    def _add_baseball_plays_to_tree_group(self, parent_item, plays, away_label="Away", home_label="Home"):
        """Add plays to a tree group, organizing by at-bat with result as main node.

        Uses ESPN's atBatId + summaryType when available (preferred), otherwise
        falls back to text-pattern matching for older API responses.
        """
        has_at_bat_ids = any(p.get("atBatId") for p in plays)
        if has_at_bat_ids:
            self._add_baseball_plays_by_at_bat_id(parent_item, plays, away_label, home_label)
        else:
            self._add_baseball_plays_by_text_pattern(parent_item, plays)

    def _is_substitution_play(self, play):
        """Return True if this play is a player substitution/change.

        ESPN usually sets summaryType='C' but sometimes omits it for pinch
        hitters/runners.  Fall back to type field and text-pattern detection.
        """
        if play.get("summaryType") == "C":
            return True
        type_text = (play.get("type") or {}).get("text", "").lower()
        if "substitut" in type_text or "line change" in type_text:
            return True
        text = play.get("text", "").lower()
        # "Perkins hit for Jones", "Smith ran for Doe", "entered for"
        if " hit for " in text or " ran for " in text or " entered for " in text:
            return True
        return False

    def _add_baseball_plays_by_at_bat_id(self, parent_item, plays, away_label, home_label):
        """Group baseball plays by ESPN atBatId + summaryType codes.

        summaryType key:
          A = at-bat announcement ("Lopez pitches to Meadows")
          P = pitch (isPitch == True means it's an actual pitch)
          N = non-scoring result note
          S = scoring result
          C = player change / substitution
        """
        # Build ordered at-bat groups
        ab_order = []
        ab_plays = {}  # atBatId -> [plays]

        for play in plays:
            ab_id = play.get("atBatId") or play.get("id", "")
            st = play.get("summaryType", "")
            text = play.get("text", "")

            # Skip inning-transition markers (summaryType 'I' or empty) and blank plays
            if any(text.startswith(m) for m in (
                "Top of the", "Bottom of the", "End of the", "Middle of the"
            )):
                continue
            if st in ("I",) or (not st and not text.strip()):
                continue

            if ab_id not in ab_plays:
                ab_order.append(ab_id)
                ab_plays[ab_id] = []
            ab_plays[ab_id].append(play)

        for ab_id in ab_order:
            group = ab_plays[ab_id]

            # Separate player-change plays. ESPN sometimes omits summaryType="C"
            # on pinch-hit/pinch-run announcements, so also detect them by text.
            change_plays = [p for p in group if self._is_substitution_play(p)]
            non_change = [p for p in group if not self._is_substitution_play(p)]

            # Emit player-change banners before the at-bat
            for cp in change_plays:
                text = cp.get("text", "").strip()
                if text:
                    chg_item = QTreeWidgetItem([f">> {text}"])
                    chg_item.setBackground(0, QColor(255, 235, 200))  # light orange
                    parent_item.addChild(chg_item)

            # Find the at-bat announcement (summaryType == "A")
            a_play = next((p for p in non_change if p.get("summaryType") == "A"), None)

            # If the group is all player changes, nothing more to do
            if a_play is None and not non_change:
                continue

            header_text = a_play.get("text", "At-bat") if a_play else (
                non_change[0].get("text", "At-bat") if non_change else "At-bat"
            )

            # Result: prefer scoring 'S', then a non-substitution 'N' play.
            # ESPN uses summaryType='N' for BOTH outcomes and substitutions
            # (e.g. "Perkins hit for Jones" also has st='N'), so filter those out.
            result_play = (
                next((p for p in non_change if p.get("summaryType") == "S"), None)
                or next((p for p in non_change
                         if p.get("summaryType") == "N"
                         and not self._is_substitution_play(p)), None)
                or next((p for p in non_change
                         if p.get("summaryType") not in ("A", "P", "C", "I", "S", "N")
                         and p.get("text", "").strip()
                         and p is not a_play
                         and not self._is_substitution_play(p)), None)
            )
            result_text = result_play.get("text", "") if result_play else ""
            is_scoring = result_play is not None and result_play.get("summaryType") == "S"

            # Pitches: summaryType "P". ESPN's isPitch flag is unreliable
            # (often missing or empty string), so don't require it.
            pitches = [p for p in non_change if p.get("summaryType") == "P"]

            # Build at-bat header line
            score_suffix = ""
            if is_scoring:
                away = self._safe_int(result_play.get("awayScore"))
                home = self._safe_int(result_play.get("homeScore"))
                if away is not None and home is not None:
                    score_suffix = f"  ({away_label} {away} - {home_label} {home})"

            # Compose: "⚾ Header: Result  (score)  [Np xB yK zF]"
            prefix = "⚾ " if is_scoring else ""
            if result_text and result_text != header_text:
                main_text = f"{prefix}{header_text}: {result_text}{score_suffix}"
            else:
                main_text = f"{prefix}{header_text}{score_suffix}"

            if pitches:
                summary = self._build_pitch_count_summary(pitches)
                main_text += f"  [{len(pitches)}p{summary}]"

            at_bat_item = QTreeWidgetItem([main_text])
            at_bat_item.setExpanded(False)
            if is_scoring:
                at_bat_item.setBackground(0, QColor(255, 255, 150))
            parent_item.addChild(at_bat_item)

            for i, pitch in enumerate(pitches):
                at_bat_item.addChild(self._build_pitch_tree_item(pitch, i + 1, len(pitches)))

    def _add_baseball_plays_by_text_pattern(self, parent_item, plays):
        """Fallback at-bat grouper using text-pattern matching when atBatId is absent."""
        TRANSITION_PREFIXES = ("Top of the", "Bottom of the", "End of the", "Middle of the")
        OUTCOMES = [
            "struck out", "grounded out", "flied out", "popped out", "lined out",
            "fouled out", "reached on error", "singled", "doubled", "tripled",
            "homered", "walked", "hit by pitch", "reached on fielder's choice",
            "reached on", "grounded into", "flied into", "popped into",
            "single to", "double to",
        ]

        meaningful_plays = [
            p for p in plays
            if p.get("text", "").strip()
            and not any(p.get("text", "").startswith(t) for t in TRANSITION_PREFIXES)
        ]

        at_bats = []
        current_at_bat = None

        for play in meaningful_plays:
            play_text = play.get("text", "")

            if " pitches to " in play_text:
                if current_at_bat:
                    at_bats.append(current_at_bat)
                parts = play_text.split(" pitches to ")
                batter_name = parts[1].strip() if len(parts) >= 2 else ""
                current_at_bat = {
                    "batter": batter_name,
                    "header": play_text,
                    "plays": [],
                    "result": None,
                    "scoring": False,
                }
                continue

            if current_at_bat:
                current_at_bat["plays"].append(play)
                batter_name = current_at_bat["batter"]
                name_found = any(
                    w.lower() in play_text.lower()
                    for w in batter_name.split() if len(w) > 2
                )
                outcome_found = any(o in play_text.lower() for o in OUTCOMES)
                if name_found or outcome_found:
                    current_at_bat["result"] = play_text
                    if play.get("scoringPlay", False):
                        current_at_bat["scoring"] = True
                        away = self._safe_int(play.get("awayScore")) or 0
                        home = self._safe_int(play.get("homeScore")) or 0
                        current_at_bat["score"] = f"({away}-{home})"
                    at_bats.append(current_at_bat)
                    current_at_bat = None

        if current_at_bat:
            if current_at_bat["plays"] and not current_at_bat["result"]:
                current_at_bat["result"] = current_at_bat["plays"][-1].get("text", "At-bat in progress")
            at_bats.append(current_at_bat)

        for at_bat in at_bats:
            header = at_bat.get("header") or at_bat.get("batter", "Unknown")
            result_text = at_bat.get("result", "")

            if at_bat["scoring"]:
                main_text = f"⚾ {header}: {result_text} {at_bat.get('score', '')}"
            elif result_text and result_text != header:
                main_text = f"{header}: {result_text}"
            else:
                main_text = header

            at_bat_item = QTreeWidgetItem([main_text])
            at_bat_item.setExpanded(False)
            if at_bat["scoring"]:
                at_bat_item.setBackground(0, QColor(255, 255, 150))
            parent_item.addChild(at_bat_item)

            pitches = [
                p for p in at_bat["plays"]
                if p.get("text", "") != result_text
                and (
                    "Pitch" in p.get("text", "")
                    or any(k in p.get("text", "").lower()
                           for k in ["ball", "strike", "foul", "looking", "swinging"])
                )
            ]
            for i, play in enumerate(pitches):
                at_bat_item.addChild(self._build_pitch_tree_item(play, i + 1, len(pitches)))

    # ------------------------------------------------------------------ #
    #  Pitch helper methods                                                #
    # ------------------------------------------------------------------ #

    def _build_pitch_count_summary(self, pitches):
        """Return a short count string like ' 3B 2K 1F' from a list of pitch plays."""
        balls = strikes = fouls = 0
        for p in pitches:
            t = (p.get("type", {}) or {}).get("type", "").lower()
            if "ball" in t:
                balls += 1
            elif "called-strike" in t or "swinging-strike" in t:
                strikes += 1
            elif "foul" in t:
                fouls += 1
        parts = []
        if balls:   parts.append(f"{balls}B")
        if strikes: parts.append(f"{strikes}K")
        if fouls:   parts.append(f"{fouls}F")
        return " " + " ".join(parts) if parts else ""

    def _build_pitch_tree_item(self, play, pitch_num, total_pitches):
        """Build a QTreeWidgetItem for a single pitch with full details."""
        play_text = play.get("text", "")
        velocity = play.get("pitchVelocity")
        pitch_type_obj = play.get("pitchType", {}) or {}
        pitch_type_text = pitch_type_obj.get("text", "") if isinstance(pitch_type_obj, dict) else ""
        pitch_coordinate = play.get("pitchCoordinate", {}) or {}
        result_count = play.get("resultCount", {}) or {}

        # Ball-strike count BEFORE this pitch (from resultCount)
        count_text = ""
        if isinstance(result_count, dict) and ("balls" in result_count or "strikes" in result_count):
            b = result_count.get("balls", 0)
            s = result_count.get("strikes", 0)
            count_text = f"{b}-{s}"

        # Short pitch result label
        type_obj = play.get("type", {}) or {}
        type_type = type_obj.get("type", "").lower()
        pitch_label = self._get_pitch_result_label(type_type, play_text)

        # Coordinates and location
        espn_x = None
        espn_y = None
        batter_side = None
        location = ""
        if pitch_coordinate and isinstance(pitch_coordinate, dict):
            espn_x = pitch_coordinate.get("x")
            espn_y = pitch_coordinate.get("y")
            if espn_x is not None and espn_y is not None:
                if isinstance(play, dict) and "participants" in play:
                    for participant in play.get("participants", []):
                        if isinstance(participant, dict) and participant.get("type") == "batter":
                            batter_side = participant.get("batSide")
                            break
                location = get_pitch_location(espn_x, espn_y, batter_side)

        # Build display: "#N [label]  Type  Vel  count  location"
        parts = [f"#{pitch_num}"]
        if pitch_label:
            parts.append(f"[{pitch_label}]")
        if pitch_type_text:
            parts.append(pitch_type_text)
        if velocity:
            parts.append(f"{velocity} mph")
        if count_text:
            parts.append(f"count {count_text}")
        if location:
            parts.append(location)
        elif espn_x is not None and espn_y is not None:
            parts.append(f"({espn_x}, {espn_y})")

        display_text = "  " + "  ".join(parts)
        pitch_item = QTreeWidgetItem([display_text])

        bg = self._get_pitch_bg_color(type_type)
        if bg:
            pitch_item.setBackground(0, bg)

        pitch_data = {
            "x": espn_x,
            "y": espn_y,
            "velocity": velocity,
            "pitch_type": pitch_type_text,
            "batter_hand": batter_side,
            "is_pitch": True,
        }
        pitch_item.setData(0, Qt.ItemDataRole.UserRole, pitch_data)
        return pitch_item

    def _get_pitch_result_label(self, type_type, play_text=""):
        """Return a 1-letter pitch result label (B, C, S, F, X)."""
        if "ball" in type_type:             return "B"
        if "called-strike" in type_type:    return "C"
        if "swinging-strike" in type_type:  return "S"
        if "foul" in type_type:             return "F"
        if "in-play" in type_type:          return "X"
        # Text fallback
        tl = play_text.lower()
        if "ball" in tl:                             return "B"
        if "called strike" in tl or "looking" in tl: return "C"
        if "swinging" in tl:                         return "S"
        if "foul" in tl:                             return "F"
        return ""

    def _get_pitch_bg_color(self, type_type):
        """Return a QColor background for a pitch result, or None."""
        if "ball" in type_type:
            return QColor(200, 220, 255, 80)   # light blue
        if "called-strike" in type_type or "swinging-strike" in type_type:
            return QColor(255, 200, 200, 80)   # light red
        if "foul" in type_type:
            return QColor(255, 230, 180, 80)   # light orange
        if "in-play-score" in type_type:
            return QColor(180, 255, 180, 80)   # light green
        return None

    def _determine_drive_result(self, drive_plays):
        """Determine the result of an NFL drive"""
        if not drive_plays:
            return "No plays"

        last_play = drive_plays[-1]
        play_text = last_play.get("text", "").lower()

        if "touchdown" in play_text:
            return "Touchdown"
        elif "field goal" in play_text:
            return "Field Goal"
        elif "punt" in play_text:
            return "Punt"
        elif "turnover" in play_text or "interception" in play_text or "fumble" in play_text:
            return "Turnover"
        elif "safety" in play_text:
            return "Safety"
        elif any(end_indicator in play_text for end_indicator in ["end of quarter", "end of half", "end of game"]):
            return "End of Period"
        else:
            return f"{len(drive_plays)} plays"
    
    def _add_football_plays_to_drive(self, parent_item, plays):
        """Add NFL/NCAAF plays to a drive with down/distance, clock, and score."""
        for play in plays:
            play_text = play.get("text", "Unknown play")

            # Down & distance come from the play's start dict (not top-level fields)
            start = play.get("start", {}) or {}
            down = start.get("down", 0)
            distance = start.get("distance", 0)
            possession_text = start.get("possessionText", "")
            yards_to_endzone = start.get("yardsToEndzone", 0)
            stat_yardage = play.get("statYardage", 0) or 0

            # Build situation prefix
            situation = ""
            if yards_to_endzone and yards_to_endzone <= 5:
                situation = "GOAL LINE "
            elif yards_to_endzone and yards_to_endzone <= 20:
                situation = "RED ZONE "
            elif down == 4:
                situation = "4TH DOWN "

            if down:
                if possession_text:
                    down_text = f"[{situation}{down} & {distance} from {possession_text}] "
                else:
                    down_text = f"[{situation}{down} & {distance}] "
            else:
                down_text = ""

            # Yardage prefix
            if stat_yardage > 0:
                yardage_prefix = f"(+{stat_yardage} yds) "
            elif stat_yardage < 0:
                yardage_prefix = f"({stat_yardage} yds) "
            else:
                yardage_prefix = ""

            enhanced_text = f"{yardage_prefix}{play_text}"

            clock_time = self._extract_play_clock_display(play)
            score_info = self._extract_basketball_score_info(play)

            if clock_time not in ("--:--", ""):
                formatted_text = self._format_clock_play_entry(
                    f"{down_text}{enhanced_text}", clock_time, score_info
                )
            else:
                formatted_text = f"{down_text}{enhanced_text}"

            play_item = QTreeWidgetItem([formatted_text])
            if play.get("scoringPlay", False):
                play_item.setBackground(0, QColor(255, 255, 150))
            elif yards_to_endzone and yards_to_endzone <= 5:
                play_item.setBackground(0, QColor(255, 235, 235))
            elif yards_to_endzone and yards_to_endzone <= 20:
                play_item.setBackground(0, QColor(255, 248, 235))
            parent_item.addChild(play_item)

    # --- Basketball and hockey play audio -------------------------------------

    def _tag_play_for_audio(self, tree_item, play):
        """Attach a play's raw data to its tree item so Alt+P can sonify it.

        Only done for the leagues whose plays carry coordinates, so items in
        every other sport keep an empty UserRole as before. Baseball stores its
        own dict with `is_pitch`, which this never overwrites because the
        baseball tree has its own builder.
        """
        league = getattr(self, "_plays_sport_type", None)
        if not self.play_audio_mapper or not self.play_audio_mapper.supports(league):
            return
        tree_item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {"play_audio_league": league, "play": play},
        )

        # Say where the play happened as part of the item, so the location is
        # heard on arrival rather than announced over the tone. AccessibleText
        # leaves the visible column alone and falls back to the display text
        # when it is not set, which is how accessible_table.py uses it too.
        description = self.play_audio_mapper.describe_play(league, play)
        if description:
            tree_item.setData(
                0,
                Qt.ItemDataRole.AccessibleTextRole,
                f"{tree_item.text(0)}, {description}",
            )

    def _label_period_for_audio(self, period_item, plays):
        """Add "N with a location" to a period header for screen readers.

        Alt+S on the header plays every located play in the period and says
        nothing, so the count has to be available here or the listener has no
        idea how many tones to expect — plenty of plays carry no coordinates.
        """
        league = getattr(self, "_plays_sport_type", None)
        if not self.play_audio_mapper or not self.play_audio_mapper.supports(league):
            return
        located = sum(
            1 for play in plays if self.play_audio_mapper.describe_play(league, play)
        )
        if not located:
            return
        period_item.setData(
            0,
            Qt.ItemDataRole.AccessibleTextRole,
            f"{period_item.text(0)}, {located} with a location",
        )

    def _play_audio_league(self, tree_item):
        """The league to sonify this item under, or None if it is not sonifiable.

        A play item carries its own league. A period header carries nothing, so
        it falls back to the league of the tree as a whole — that is what makes
        Alt+S work on a period header.
        """
        if not tree_item or not self.play_audio_mapper:
            return None
        data = tree_item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("play_audio_league"):
            return data["play_audio_league"]
        league = getattr(self, "_plays_sport_type", None)
        return league if self.play_audio_mapper.supports(league) else None

    def _announce_play_audio(self, message):
        """Say something about the audio through the screen reader."""
        self._on_audio_feedback(message)
        helper = getattr(self, "notification_helper", None)
        if helper is None:
            helper = getattr(getattr(self, "parent_app", None), "notification_helper", None)
        if helper is not None:
            try:
                helper.announce(message)
            except Exception:
                pass

    def _play_play_audio(self, tree_item):
        """Play the tone for one basketball or hockey play."""
        league = self._play_audio_league(tree_item)
        if not league:
            return

        data = tree_item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or "play" not in data:
            # A period header on its own has no location to play.
            self._announce_play_audio("No play selected")
            return

        play = data["play"]
        # Nothing is spoken when a tone plays. The play's own tree label already
        # said where it happened, so an announcement here would repeat it and
        # talk over the audio.
        if not self.play_audio_mapper.generate_play_audio(league, play):
            # Substitutions, timeouts, free throws and most face-offs arrive
            # without coordinates, which is normal rather than a failure. This
            # is the one thing worth saying: no tone is coming.
            self._announce_play_audio("This play has no location")

    def _play_play_sequence(self, tree_item):
        """Walk a period, playing every play in it that has a location."""
        league = self._play_audio_league(tree_item)
        if not league:
            return

        period_item = tree_item if tree_item.parent() is None else tree_item.parent()
        plays = []
        for index in range(period_item.childCount()):
            data = period_item.child(index).data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "play" in data:
                plays.append(data["play"])

        if not plays:
            self._announce_play_audio("No plays to play")
            return

        # Silent when there is something to hear, for the same reason as above.
        if not self.play_audio_mapper.generate_play_sequence(league, plays):
            self._announce_play_audio("No plays in this period have a location")

    def _show_play_audio_context_menu(self, tree_item, global_position):
        """Shift+F10 options for a basketball or hockey play."""
        menu = QMenu(self)
        menu.setAccessibleName("Play Audio Options")

        data = tree_item.data(0, Qt.ItemDataRole.UserRole)
        has_play = isinstance(data, dict) and "play" in data

        if has_play:
            play_action = QAction("Play This Location", self)
            play_action.setShortcut("Alt+P")
            play_action.setStatusTip("Play spatial audio for where this play happened")
            play_action.triggered.connect(lambda: self._play_play_audio(tree_item))
            menu.addAction(play_action)

        sequence_action = QAction("Play Period Locations", self)
        sequence_action.setShortcut("Alt+S")
        sequence_action.setStatusTip(
            "Play audio for every play in this period that has a location"
        )
        sequence_action.triggered.connect(lambda: self._play_play_sequence(tree_item))
        menu.addAction(sequence_action)

        menu.exec(global_position)

    def _play_current_play_audio(self, plays_tree):
        """Play Audio button: sonify whatever the tree has selected."""
        current_item = plays_tree.currentItem()
        if not current_item:
            self._announce_play_audio("No play selected")
            return
        self._play_play_audio(current_item)

    def _handle_plays_audio_key(self, current_item, key, modifiers):
        """Alt+P and Alt+S on the plays tree. True if the key was handled."""
        if modifiers != Qt.KeyboardModifier.AltModifier:
            return False
        if key == Qt.Key.Key_P:
            # Basketball and hockey first. Their items are tagged explicitly
            # by _tag_play_for_audio, whereas _is_pitch_item only matches on
            # words in the text — and "Jump Ball" and "Personal Foul" both
            # trip its "ball" and "foul" indicators.
            if self._play_audio_league(current_item):
                self._play_play_audio(current_item)
                return True
            # Alt+P for pitch audio (only works on actual pitches)
            if self._is_pitch_item(current_item):
                self._play_pitch_audio(current_item)
                return True
        elif key == Qt.Key.Key_S:
            # Alt+S on a period header walks that period; on a play, the
            # period it belongs to. Checked before the pitch branch for the
            # same reason as Alt+P above.
            if self._play_audio_league(current_item):
                self._play_play_sequence(current_item)
                return True
            # Alt+S for pitch sequence (works on pitches and at-bat items)
            is_pitch = self._is_pitch_item(current_item)
            is_at_bat = current_item.parent() is None  # Top-level item
            if is_pitch or is_at_bat:
                self._play_pitch_sequence(current_item)
                return True
        return False

    def _is_pitch_item(self, tree_item):
        """Check if the tree item represents a pitch (for audio playback)"""
        if not tree_item:
            return False
            
        # Check if item text contains pitch-related keywords
        item_text = tree_item.text(0).lower()
        
        # Look for pitch indicators
        pitch_indicators = [
            "ball", "strike", "foul", "looking", "swinging",
            "fastball", "slider", "curveball", "changeup", "sinker", "cutter",
            "mph", "hit by pitch"
        ]
        
        # Also check for coordinate patterns (x, y)
        has_coordinates = "(" in item_text and ")" in item_text and "," in item_text
        
        return any(indicator in item_text for indicator in pitch_indicators) or has_coordinates
    
    def _play_pitch_audio(self, tree_item):
        """Extract pitch data from tree item and play spatial audio"""
        if not self.audio_mapper:
            return
            
        try:
            # Try to get stored pitch data first
            pitch_data = tree_item.data(0, Qt.ItemDataRole.UserRole)
            
            if pitch_data and isinstance(pitch_data, dict) and pitch_data.get('is_pitch'):
                # Use stored data
                x = pitch_data.get('x')
                y = pitch_data.get('y') 
                velocity = pitch_data.get('velocity')
                pitch_type = pitch_data.get('pitch_type')
                batter_hand = pitch_data.get('batter_hand')
            else:
                # Fall back to text parsing
                item_text = tree_item.text(0)
                parsed_data = self._extract_pitch_data_from_text(item_text)
                
                if not parsed_data:
                    self._on_audio_error("Could not parse pitch data from selected item")
                    return
                    
                x = parsed_data.get('x')
                y = parsed_data.get('y') 
                velocity = parsed_data.get('velocity')
                pitch_type = parsed_data.get('pitch_type')
                batter_hand = parsed_data.get('batter_hand')
            
            if x is not None and y is not None:
                # Generate and play spatial audio
                self.audio_mapper.generate_pitch_audio(
                    x, y, velocity, pitch_type, batter_hand
                )
                
                # Provide accessible feedback
                location_desc = self.audio_mapper._get_location_description(x, y, batter_hand)
                feedback = f"Playing audio for pitch at ({x}, {y}) - {location_desc}"
                self._on_audio_feedback(feedback)
            else:
                self._on_audio_error("Could not extract coordinates from pitch data")
                
        except Exception as e:
            self._on_audio_error(f"Failed to play pitch audio: {str(e)}")
    
    def _extract_pitch_data_from_text(self, item_text):
        """Extract pitch data from enhanced tree item text"""
        import re
        
        pitch_data = {}
        
        # Extract coordinates (x, y) 
        coord_pattern = r'\((\d+),\s*(\d+)\)'
        coord_match = re.search(coord_pattern, item_text)
        if coord_match:
            pitch_data['x'] = int(coord_match.group(1))
            pitch_data['y'] = int(coord_match.group(2))
        
        # Extract velocity
        velocity_pattern = r'(\d+)\s*mph'
        velocity_match = re.search(velocity_pattern, item_text, re.IGNORECASE)
        if velocity_match:
            pitch_data['velocity'] = int(velocity_match.group(1))
        
        # Extract pitch type
        pitch_types = [
            'four-seam fastball', 'fastball', 'slider', 'curveball', 'changeup', 
            'sinker', 'cutter', 'knuckleball', 'splitter', 'curve'
        ]
        
        for pitch_type in pitch_types:
            if pitch_type.lower() in item_text.lower():
                pitch_data['pitch_type'] = pitch_type
                break
        
        # Try to determine batter handedness from context
        # This is a simplified approach - in a full implementation, 
        # we'd track the current batter's handedness more systematically
        
        # For now, use heuristics based on location description
        if 'inside' in item_text.lower() and 'way' in item_text.lower():
            # Could indicate handedness based on coordinate ranges
            x = pitch_data.get('x', 127)
            if x < 100:  # Low X values
                pitch_data['batter_hand'] = 'R'  # Inside to right-handed batter
            else:
                pitch_data['batter_hand'] = 'L'  # Inside to left-handed batter
        else:
            # Default assumption
            pitch_data['batter_hand'] = 'R'
        
        return pitch_data
    
    def _show_pitch_context_menu(self, tree_item, global_position):
        """Show context menu for pitch-related audio options"""
        # Basketball and hockey get their own options. Checked first for the
        # same reason Alt+P is: _is_pitch_item matches on words in the text, and
        # "Jump Ball" and "Personal Foul" trip its "ball" and "foul" indicators.
        if self._play_audio_league(tree_item):
            self._show_play_audio_context_menu(tree_item, global_position)
            return

        if not self.audio_mapper:
            return

        menu = QMenu(self)
        menu.setAccessibleName("Pitch Audio Options")

        # Check if this is a pitch item or player/at-bat item
        is_pitch = self._is_pitch_item(tree_item)
        is_at_bat = tree_item.parent() is None  # Top-level item (at-bat)
        
        # Option 1: Play current pitch audio (only for actual pitches)
        if is_pitch:
            play_action = QAction("Play Pitch Audio", self)
            play_action.setShortcut("Alt+P")
            play_action.setStatusTip("Play spatial audio for the current pitch location")
            play_action.triggered.connect(lambda: self._play_pitch_audio(tree_item))
            menu.addAction(play_action)
        
        # Option 2: Play pitch sequence (works for both pitches and at-bat items)
        if is_pitch or is_at_bat:
            sequence_action = QAction("Play Pitch Sequence", self)
            sequence_action.setShortcut("Alt+S")
            sequence_action.setStatusTip("Play audio for all pitches in this at-bat from first to last")
            sequence_action.triggered.connect(lambda: self._play_pitch_sequence(tree_item))
            menu.addAction(sequence_action)
        
        # Option 3: Comprehensive Pitch Exploration (always available)
        if menu.actions():  # Only add separator if we have other actions
            menu.addSeparator()
            
        explore_action = QAction("Open Pitch Explorer", self)
        explore_action.setShortcut("Ctrl+E")
        explore_action.setStatusTip("Open comprehensive pitch exploration with strike zone grid and game data")
        explore_action.triggered.connect(lambda: self._open_pitch_explorer(tree_item))
        menu.addAction(explore_action)
        
        # Show menu
        menu.exec(global_position)
    
    def _play_pitch_sequence(self, tree_item):
        """Play audio sequence for all pitches in the current batter's at-bat"""
        if not self.audio_mapper:
            return
            
        try:
            # Find the parent at-bat item
            at_bat_item = tree_item.parent() if tree_item.parent() else tree_item
            
            # Collect all pitch items from this at-bat
            pitch_items = []
            for i in range(at_bat_item.childCount()):
                child_item = at_bat_item.child(i)
                if self._is_pitch_item(child_item):
                    pitch_items.append(child_item)
            
            if not pitch_items:
                self._on_audio_error("No pitches found in this at-bat")
                return
            
            # Get batter name for feedback
            batter_info = at_bat_item.text(0)
            batter_name = batter_info.split(':')[0] if ':' in batter_info else "Batter"
            
            self._on_audio_feedback(f"Playing pitch sequence for {batter_name} ({len(pitch_items)} pitches)")
            
            # Play sequence with timing
            self._play_pitch_sequence_with_timing(pitch_items, 0)
            
        except Exception as e:
            self._on_audio_error(f"Failed to play pitch sequence: {str(e)}")
    
    def _play_pitch_sequence_with_timing(self, pitch_items, index):
        """Play pitch sequence with appropriate timing between pitches"""
        if index >= len(pitch_items):
            self._on_audio_feedback("Pitch sequence complete")
            return
        
        # Play current pitch
        current_pitch = pitch_items[index]
        self._play_pitch_audio(current_pitch)
        
        # Schedule next pitch with reduced delay
        delay_ms = 800  # Reduced from 1200ms to 800ms (0.8 seconds between pitches)
        QTimer.singleShot(delay_ms, lambda: self._play_pitch_sequence_with_timing(pitch_items, index + 1))

    def _play_strike_zone_audio(self, zone_position):
        """Play audio for a specific strike zone position"""
        if not self.audio_mapper:
            return
            
        try:
            # Try to determine batter handedness from current context
            batter_hand = 'R'  # Default to right-handed
            
            # Try to get from currently selected item
            current_item = self.current_tree_widget.currentItem() if hasattr(self, 'current_tree_widget') else None
            if current_item:
                # Navigate to at-bat level to get batter info
                at_bat_item = current_item.parent() if current_item.parent() else current_item
                batter_info = at_bat_item.text(0)
                
                # Simple heuristic based on known players
                if 'Lindor' in batter_info:
                    batter_hand = 'L'
                # Add more known players as needed
            
            # Generate audio for the strike zone position
            self.audio_mapper.generate_strike_zone_audio(zone_position, batter_hand)
            
            # Provide feedback
            zone_name = zone_position.replace('_', ' ').title()
            self._on_audio_feedback(f"Strike zone: {zone_name}")
            
        except Exception as e:
            self._on_audio_error(f"Failed to play strike zone audio: {str(e)}")

    def _open_pitch_explorer(self, tree_item):
        """Open the comprehensive pitch exploration dialog"""
        if not AUDIO_AVAILABLE:
            QMessageBox.warning(self, "Audio Not Available", 
                              "Audio system is not available. Cannot open pitch explorer.")
            return
        
        try:
            # Extract pitch data from current game/at-bat
            game_pitches = self._extract_pitch_data_for_explorer(tree_item)
            
            # Open the pitch exploration dialog
            dialog = PitchExplorationDialog(self, game_pitches)
            
            # Connect dialog signals to main app feedback
            dialog.audio_feedback.connect(self._on_audio_feedback)
            dialog.audio_error.connect(self._on_audio_error)
            
            # Show dialog
            dialog.exec()
            
        except Exception as e:
            self._on_audio_error(f"Failed to open pitch explorer: {str(e)}")
    
    def _extract_pitch_data_for_explorer(self, tree_item):
        """Extract pitch data from the current game for the explorer"""
        pitch_data = []
        
        try:
            # If we have current plays data, extract pitches from it
            if hasattr(self, 'current_plays_data') and self.current_plays_data:
                for play in self.current_plays_data:
                    # Look for pitch coordinate data
                    pitch_coordinate = play.get("pitchCoordinate", {})
                    if pitch_coordinate and isinstance(pitch_coordinate, dict):
                        x = pitch_coordinate.get("x")
                        y = pitch_coordinate.get("y")
                        
                        if x is not None and y is not None:
                            # Extract additional pitch info from play text
                            play_text = play.get("text", "")
                            pitch_type = "Unknown"
                            velocity = None
                            result = "Unknown"
                            
                            # Try to parse pitch details from text
                            if "Fastball" in play_text:
                                pitch_type = "Fastball"
                            elif "Slider" in play_text:
                                pitch_type = "Slider"
                            elif "Changeup" in play_text:
                                pitch_type = "Changeup"
                            elif "Curveball" in play_text:
                                pitch_type = "Curveball"
                            
                            # Extract result
                            if "Strike" in play_text:
                                result = "Strike"
                            elif "Ball" in play_text:
                                result = "Ball"
                            elif "Foul" in play_text:
                                result = "Foul"
                            elif "Hit" in play_text or "In Play" in play_text:
                                result = "In Play"
                            
                            pitch_data.append({
                                'x': x,
                                'y': y,
                                'type': pitch_type,
                                'velocity': velocity,
                                'result': result,
                                'text': play_text
                            })
            
        except Exception as e:
            print(f"Error extracting pitch data: {e}")
        
        return pitch_data

    def _play_current_pitch_audio(self, plays_tree):
        """Play audio for the currently selected pitch"""
        current_item = plays_tree.currentItem()
        if current_item and self._is_pitch_item(current_item):
            self._play_pitch_audio(current_item)
        else:
            # Spoken rather than a parentless modal box, the same as play audio.
            self._announce_play_audio("Select a pitch to play its audio")

    def _export_game_log(self):
        """Export complete game log as HTML file"""
        try:
            # Check for either plays data or drives data
            has_plays = hasattr(self, 'current_plays_data') and self.current_plays_data
            has_drives = hasattr(self, 'current_drives_data') and self.current_drives_data
            
            if not has_plays and not has_drives:
                QMessageBox.warning(self, "Export Error", "No play or drive data available to export.")
                return
            
            # Generate filename with game information
            filename = self._generate_export_filename()
            
            # Generate HTML content
            html_content = self._generate_game_log_html()
            
            # Save to file in the application directory
            app_dir = os.getcwd()  # Current working directory where app was launched
            file_path = os.path.join(app_dir, filename)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Show success message with custom dialog
            self._show_export_success_dialog(filename, file_path, app_dir)
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export game log:\n{str(e)}")
    
    def _show_export_success_dialog(self, filename, file_path, app_dir):
        """Show custom export success dialog with View Log and Close buttons"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Complete")
        dialog.setModal(True)
        dialog.resize(450, 200)
        
        layout = QVBoxLayout(dialog)
        
        # Success message
        message = QLabel(f"Game log exported successfully!\n\nFile saved as:\n{filename}\n\nLocation: {app_dir}")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # View Log button (Alt+G)
        view_button = QPushButton("&View Log")
        view_button.setAccessibleName("View Log Button")
        view_button.setAccessibleDescription("Open the exported game log file")
        view_button.clicked.connect(lambda: self._open_exported_file(file_path, dialog))
        button_layout.addWidget(view_button)
        
        # Close button
        close_button = QPushButton("&Close")
        close_button.setAccessibleName("Close Button") 
        close_button.setAccessibleDescription("Close this dialog and return to game details")
        close_button.clicked.connect(dialog.accept)
        close_button.setDefault(True)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        # Set focus to View Log button initially
        view_button.setFocus()
        
        dialog.exec()
    
    def _open_exported_file(self, file_path, dialog):
        """Open the exported file in the default application"""
        import os
        import subprocess
        import platform
        
        try:
            # Close the dialog first
            dialog.accept()
            
            # Open file based on platform
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.call(["open", file_path])
            else:  # Linux and others
                subprocess.call(["xdg-open", file_path])
                
        except Exception as e:
            QMessageBox.warning(
                self, 
                "Open Error", 
                f"Could not open the exported file:\n{str(e)}\n\nFile location: {file_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export game log:\n{str(e)}")
    
    def _generate_export_filename(self):
        """Generate a unique filename for the exported game log"""
        from datetime import datetime
        
        # Get current date for the filename
        current_date = datetime.now().strftime("%Y%m%d")
        
        # Try to extract team information for a meaningful filename
        game_info = ""
        team_names = self._extract_team_nicknames()
        
        if team_names:
            away_team, home_team = team_names
            game_info = f"{away_team}_vs_{home_team}"
        elif hasattr(self, 'game_id') and self.game_id:
            game_info = f"game_{self.game_id}"
        
        # Fallback to league if no specific game info
        if not game_info:
            league = getattr(self, 'league', 'UNKNOWN').upper()
            game_info = f"{league}_game"
        
        # Create filename
        filename = f"game_log_{game_info}_{current_date}.html"
        
        # Sanitize filename (remove/replace invalid characters)
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        return filename
    
    def _extract_team_nicknames(self):
        """Extract team nicknames from game data"""
        try:
            # Try to get team info from the stored raw details
            if hasattr(self, 'current_raw_details') and self.current_raw_details:
                details = self.current_raw_details
                if 'header' in details:
                    competitors = details['header'].get('competitions', [{}])[0].get('competitors', [])
                    if len(competitors) >= 2:
                        # Find away team (order=0) and home team (order=1)
                        away_team = None
                        home_team = None
                        for competitor in competitors:
                            if competitor.get('homeAway') == 'away':
                                away_team = competitor['team']['name']  # e.g., "Athletics", "Brewers"
                            elif competitor.get('homeAway') == 'home':
                                home_team = competitor['team']['name']  # e.g., "Nationals", "Yankees"
                        
                        if away_team and home_team:
                            return away_team, home_team
                        
                        # Fallback to order-based extraction
                        if len(competitors) >= 2:
                            away_team = competitors[0]['team']['name']
                            home_team = competitors[1]['team']['name']
                            return away_team, home_team
            
            # Fallback: try to extract from plays data
            if hasattr(self, 'current_plays_data') and self.current_plays_data:
                # Look for team info in the first play
                first_play = self.current_plays_data[0]
                if 'homeTeam' in first_play and 'awayTeam' in first_play:
                    away_team = first_play['awayTeam'].get('name', first_play['awayTeam'].get('abbreviation', 'AWAY'))
                    home_team = first_play['homeTeam'].get('name', first_play['homeTeam'].get('abbreviation', 'HOME'))
                    return away_team, home_team
            
            # Fallback: try to extract from drives data
            if hasattr(self, 'current_drives_data') and self.current_drives_data:
                # Look for team info in drives
                all_teams = set()
                drives_data = self.current_drives_data
                
                # Check current drive
                current_drive = drives_data.get("current")
                if current_drive and isinstance(current_drive, dict):
                    team_info = current_drive.get("team", {})
                    if team_info.get("displayName"):
                        all_teams.add(team_info["displayName"])
                
                # Check previous drives
                previous_drives = drives_data.get("previous", [])
                for drive in previous_drives:
                    if isinstance(drive, dict):
                        team_info = drive.get("team", {})
                        if team_info.get("displayName"):
                            all_teams.add(team_info["displayName"])
                
                # If we found teams, return them (order may not be perfect but better than nothing)
                teams_list = list(all_teams)
                if len(teams_list) >= 2:
                    return teams_list[0], teams_list[1]
                elif len(teams_list) == 1:
                    return teams_list[0], "Opponent"
        except Exception:
            pass
        
        return None
    
    def _generate_and_display_game_wrap_up(self, raw_game_data):
        """Generate comprehensive game wrap-up HTML and open in browser"""
        try:
            # raw_game_data is the game's full summary, fetched for the right
            # league when the game opened. This used to fetch it again, on the
            # UI thread, from a hard-coded college football URL whatever the
            # sport, so every other league got nothing or the wrong game.
            html_content = self._generate_game_wrap_up_html(raw_game_data)
            
            # Create temporary HTML file
            import tempfile
            import os
            import webbrowser
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(html_content)
                temp_file_path = f.name
            
            # Open in default browser
            webbrowser.open(f'file://{temp_file_path}')
            
            # Show confirmation message
            QMessageBox.information(self, "Game Wrap Up", 
                "Game Wrap Up opened in your default web browser.")
                
        except Exception as e:
            QMessageBox.critical(self, "Wrap Up Error", 
                f"Failed to generate game wrap-up:\n{str(e)}")
    
    def _generate_game_wrap_up_html(self, raw_game_data):
        """Generate comprehensive HTML content for game wrap-up"""
        # Extract key information from raw game data
        header = raw_game_data.get('header', {})
        competitions = header.get('competitions', [])
        
        # Extract teams info and game details
        away_team = home_team = None
        away_score = home_score = "0"
        game_date = ""
        status = {}
        venue = {}
        
        if competitions:
            competition = competitions[0]
            competitors = competition.get('competitors', [])
            game_date = competition.get('date', '')
            status = competition.get('status', {})
            venue = competition.get('venue', {})
            
            for competitor in competitors:
                team_info = competitor.get('team', {})
                score = competitor.get('score', '0')
                
                if competitor.get('homeAway') == 'away':
                    away_team = team_info
                    away_score = score
                elif competitor.get('homeAway') == 'home':
                    home_team = team_info
                    home_score = score
        
        # Article content
        article = raw_game_data.get('article', {})
        
        # Process article text if text processor is available
        if article and text_processor:
            # Clean description (pass complete game data for player name extraction)
            if 'description' in article:
                article['description'] = text_processor.clean_description(article['description'], raw_game_data)
            # Clean story content (pass complete game data for player name extraction)
            if 'story' in article:
                article['story'] = text_processor.clean_description(article['story'], raw_game_data)
        
        # Leaders/statistics
        leaders = raw_game_data.get('leaders', [])
        
        # Boxscore data
        boxscore = raw_game_data.get('boxscore', {})
        
        # Scoring plays
        scoring_plays = raw_game_data.get('scoringPlays', [])
        
        # Drives (for football)
        drives = raw_game_data.get('drives', {})
        
        # HTML template
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Game Wrap Up - {away_team.get('displayName', 'Away')} vs {home_team.get('displayName', 'Home')}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #1a472a 0%, #2e7d32 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .score-line {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 40px;
            margin: 20px 0;
            font-size: 24px;
            font-weight: bold;
        }}
        .team {{
            text-align: center;
            min-width: 200px;
        }}
        .team-name {{
            font-size: 18px;
            margin-bottom: 10px;
        }}
        .team-score {{
            font-size: 36px;
            font-weight: bold;
            color: #ffd700;
        }}
        .vs {{
            font-size: 20px;
            opacity: 0.8;
        }}
        .game-info {{
            text-align: center;
            margin-top: 15px;
            opacity: 0.9;
        }}
        .content-section {{
            background: white;
            margin-bottom: 30px;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section-title {{
            color: #2e7d32;
            border-bottom: 3px solid #2e7d32;
            padding-bottom: 10px;
            margin-bottom: 20px;
            font-size: 24px;
            font-weight: bold;
        }}
        .article-content {{
            font-size: 16px;
            line-height: 1.8;
        }}
        .article-headline {{
            font-size: 28px;
            font-weight: bold;
            color: #1a472a;
            margin-bottom: 15px;
            line-height: 1.3;
        }}
        .article-description {{
            font-size: 18px;
            color: #555;
            font-style: italic;
            margin-bottom: 25px;
            border-left: 4px solid #2e7d32;
            padding-left: 20px;
        }}
        .leaders-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        .leader-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #2e7d32;
        }}
        .leader-category {{
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 10px;
        }}
        .leader-stat {{
            margin: 5px 0;
        }}
        .scoring-plays {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }}
        .play {{
            margin: 10px 0;
            padding: 10px;
            background: white;
            border-radius: 5px;
            border-left: 4px solid #ff6b35;
        }}
        .quarter {{
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 5px;
        }}
        .boxscore-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .boxscore-table th,
        .boxscore-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        .boxscore-table th {{
            background-color: #2e7d32;
            color: white;
            font-weight: bold;
        }}
        .boxscore-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .drive-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        .drive-table th,
        .drive-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #ddd;
            text-align: left;
        }}
        .drive-table th {{
            background-color: #f8f9fa;
            font-weight: bold;
            width: 30%;
        }}
        .drives-summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .drives-summary-table th,
        .drives-summary-table td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        .drives-summary-table thead th {{
            background-color: #2e7d32;
            color: white;
            font-weight: bold;
        }}
        .drives-summary-table tbody th {{
            background-color: #f8f9fa;
            font-weight: bold;
        }}
        .drives-summary-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .current-drive,
        .previous-drives {{
            margin: 20px 0;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 8px;
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            font-style: italic;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="score-line">
            <div class="team">
                <div class="team-name">{away_team.get('displayName', 'Away Team') if away_team else 'Away Team'}</div>
                <div class="team-score">{away_score}</div>
            </div>
            <div class="vs">@</div>
            <div class="team">
                <div class="team-name">{home_team.get('displayName', 'Home Team') if home_team else 'Home Team'}</div>
                <div class="team-score">{home_score}</div>
            </div>
        </div>
        <div class="game-info">
            {self._format_game_date(game_date)} • {venue.get('fullName', '')}
            <br>{status.get('type', {}).get('description', 'Final')}
        </div>
    </div>
"""
        
        # Add article content if available
        if article and article.get('headline'):
            # Clean description if text processor is available
            description = article.get('description', '')
            if text_processor:
                description = text_processor.clean_description(description, raw_game_data)
            
            html_content += f"""
    <div class="content-section">
        <h2 class="section-title">📰 Game Story</h2>
        <h1 class="article-headline">{article.get('headline', '')}</h1>
        <p class="article-description">{description}</p>
        <div class="article-content">
            {self._format_article_story(article.get('story', ''), raw_game_data)}
        </div>
    </div>
"""
        
        # Add key performers/leaders
        if leaders:
            html_content += f"""
    <div class="content-section">
        <h2 class="section-title">⭐ Key Performers</h2>
        <div class="leaders-grid">
            {self._format_leaders_html(leaders)}
        </div>
    </div>
"""
        
        # Add scoring plays if available
        if scoring_plays:
            html_content += f"""
    <div class="content-section">
        <h2 class="section-title">🎯 Scoring Summary</h2>
        <div class="scoring-plays">
            {self._format_scoring_plays_html(scoring_plays)}
        </div>
    </div>
"""
        
        # Add boxscore summary if available
        if boxscore and boxscore.get('teams'):
            html_content += f"""
    <div class="content-section">
        <h2 class="section-title">📊 Team Statistics</h2>
        {self._format_boxscore_html(boxscore)}
    </div>
"""
        
        # Add drives summary for football
        if drives and (drives.get('current') or drives.get('previous')):
            html_content += f"""
    <div class="content-section">
        <h2 class="section-title">🏈 Drive Summary</h2>
        {self._format_drives_html(drives)}
    </div>
"""
        
        # Close HTML
        html_content += f"""
    <div class="timestamp">
        Generated on {self._get_current_timestamp()}
    </div>
</body>
</html>
"""
        
        return html_content
    
    def _format_game_date(self, date_str):
        """Format game date for display"""
        try:
            from datetime import datetime
            if date_str:
                # Parse ISO date format
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                return dt.strftime('%B %d, %Y')
        except:
            pass
        return date_str or ''
    
    def _format_article_story(self, story, game_data=None):
        """Format article story content for HTML display"""
        if not story:
            return ""
        
        # Use text processor if available to clean ESPN placeholders
        if text_processor:
            story = text_processor.clean_description(story, game_data or {})
        
        # Clean up HTML tags and format for better display
        import re
        
        # Handle broken or incomplete story content more gracefully
        # Look for sentences that start with missing content
        story = re.sub(r'^\s*—\s*\[Player\]', '[Player]', story, flags=re.MULTILINE)
        story = re.sub(r'^\s*—\s*\\\d+', '[Player]', story, flags=re.MULTILINE)
        
        # Clean up any remaining orphaned dashes from broken content
        story = re.sub(r'—\s*(?=\s*[A-Z])', '', story)
        
        # Replace HTML links with text only for now (keep the linked text but remove the link)
        story = re.sub(r'<a[^>]*>(.*?)</a>', r'\\1', story)
        
        # Replace headline tags with proper HTML
        story = re.sub(r'<hl2>(.*?)</hl2>', r'<h3 style="color: #2e7d32; margin: 20px 0 10px 0;">\\1</h3>', story)
        
        # Clean up extra whitespace and newlines
        story = re.sub(r'\n\s*\n', '\n\n', story)  # Normalize paragraph breaks
        story = re.sub(r'\r\n', '\n', story)  # Normalize line endings
        
        # Replace double newlines with paragraph breaks
        story = story.replace('\n\n', '</p><p>')
        
        # Clean up any remaining whitespace issues
        story = re.sub(r'\s+', ' ', story)  # Multiple spaces to single space
        story = story.strip()
        
        # Wrap in paragraphs
        if story:
            story = f'<p>{story}</p>'
        
        return story
    
    def _format_leaders_html(self, leaders):
        """Format leaders data for HTML display"""
        html = ""
        
        for team_leaders in leaders:
            team_name = team_leaders.get('team', {}).get('displayName', 'Team')
            html += f'<div style="margin-bottom: 20px;"><h4 style="color: #2e7d32;">{team_name}</h4>'
            
            team_leader_data = team_leaders.get('leaders', [])
            for category in team_leader_data:
                category_name = category.get('displayName', 'Category')
                html += f'<div class="leader-card">'
                html += f'<div class="leader-category">{category_name}</div>'
                
                for leader in category.get('leaders', []):
                    athlete = leader.get('athlete', {})
                    display_value = leader.get('displayValue', leader.get('value', ''))
                    html += f'<div class="leader-stat">{athlete.get("displayName", "Player")}: {display_value}</div>'
                
                html += '</div>'
            
            html += '</div>'
        
        return html
    
    def _format_scoring_plays_html(self, scoring_plays):
        """Format scoring plays for HTML display"""
        html = ""
        current_period = None
        
        for play in scoring_plays:
            period = play.get('period', {})
            period_number = period.get('number', 1)
            period_name = period.get('displayName', f'Period {period_number}')
            
            if current_period != period_number:
                html += f'<div class="quarter">{period_name}</div>'
                current_period = period_number
            
            team = play.get('team', {})
            clock = play.get('clock', {}).get('displayValue', '')
            text = play.get('text', '')
            
            html += f'<div class="play">'
            html += f'<strong>{team.get("displayName", "Team")}</strong> - {clock}<br>'
            html += f'{text}'
            html += '</div>'
        
        return html
    
    def _format_boxscore_html(self, boxscore):
        """Format boxscore data for HTML display - screen reader friendly"""
        teams = boxscore.get('teams', [])
        if not teams or len(teams) < 2:
            return "<p>No team statistics available.</p>"
        
        # Extract team names
        team1 = teams[0].get('team', {}).get('displayName', 'Team 1')
        team2 = teams[1].get('team', {}).get('displayName', 'Team 2')
        
        # Get all statistics from both teams
        team1_stats = teams[0].get('statistics', [])
        team2_stats = teams[1].get('statistics', [])
        
        # Create a map of all available statistics
        all_stats = {}
        
        # Process team 1 stats
        for stat in team1_stats:
            label = stat.get('label', '')
            value = stat.get('displayValue', stat.get('value', ''))
            if label:
                all_stats[label] = {'team1': value, 'team2': '-'}
        
        # Process team 2 stats  
        for stat in team2_stats:
            label = stat.get('label', '')
            value = stat.get('displayValue', stat.get('value', ''))
            if label:
                if label in all_stats:
                    all_stats[label]['team2'] = value
                else:
                    all_stats[label] = {'team1': '-', 'team2': value}
        
        if not all_stats:
            return "<p>No statistics available.</p>"
        
        # Create a clean, accessible 3-column table
        html = '''
        <table class="boxscore-table" role="table" aria-label="Team Statistics Comparison">
            <thead>
                <tr>
                    <th scope="col">Statistic</th>
                    <th scope="col">{team1}</th>
                    <th scope="col">{team2}</th>
                </tr>
            </thead>
            <tbody>
        '''.format(team1=team1, team2=team2)
        
        # Add each statistic row
        for stat_name, values in all_stats.items():
            html += f'''
                <tr>
                    <th scope="row">{stat_name}</th>
                    <td>{values['team1']}</td>
                    <td>{values['team2']}</td>
                </tr>
            '''
        
        html += '''
            </tbody>
        </table>
        '''
        
        return html
    
    def _format_drives_html(self, drives):
        """Format drives data for HTML display - screen reader friendly"""
        html = ""
        
        # Current drive
        current = drives.get('current')
        if current:
            team = current.get('team', {})
            team_name = team.get('displayName', 'Team')
            plays = current.get('plays', 0)
            yards = current.get('yards', 0)
            
            html += f'''
            <div class="current-drive">
                <h4>Current Drive</h4>
                <table class="drive-table" role="table" aria-label="Current Drive Information">
                    <tr><th scope="row">Team:</th><td>{team_name}</td></tr>
                    <tr><th scope="row">Plays:</th><td>{plays}</td></tr>
                    <tr><th scope="row">Yards:</th><td>{yards}</td></tr>
                </table>
            </div>
            '''
        
        # Previous drives summary
        previous = drives.get('previous', [])
        if previous:
            html += f'''
            <div class="previous-drives">
                <h4>Recent Drives ({len(previous)} total)</h4>
                <table class="drives-summary-table" role="table" aria-label="Recent Drives Summary">
                    <thead>
                        <tr>
                            <th scope="col">Team</th>
                            <th scope="col">Plays</th>
                            <th scope="col">Yards</th>
                            <th scope="col">Result</th>
                        </tr>
                    </thead>
                    <tbody>
            '''
            
            # Show last 5 drives for readability
            for drive in previous[-5:]:
                team = drive.get('team', {})
                team_name = team.get('displayName', 'Team')
                result = drive.get('result', 'No result')
                plays = drive.get('plays', 0)
                yards = drive.get('yards', 0)
                
                html += f'''
                    <tr>
                        <th scope="row">{team_name}</th>
                        <td>{plays}</td>
                        <td>{yards}</td>
                        <td>{result}</td>
                    </tr>
                '''
            
            html += '''
                    </tbody>
                </table>
            </div>
            '''
        
        if not html:
            html = "<p>No drive information available.</p>"
            
        return html
    
    def _get_current_timestamp(self):
        """Get current timestamp for wrap-up generation"""
        from datetime import datetime
        return datetime.now().strftime('%B %d, %Y at %I:%M %p')

    def _generate_game_log_html(self):
        """Generate HTML content for the complete game log"""
        # Determine what data we have and sport type
        has_plays = hasattr(self, 'current_plays_data') and self.current_plays_data
        has_drives = hasattr(self, 'current_drives_data') and self.current_drives_data
        
        if has_plays:
            sport_type = self._detect_sport_type(self.current_plays_data)
            data_for_sport_detection = self.current_plays_data
            total_items = len(self.current_plays_data)
            data_type = "Plays"
        elif has_drives:
            sport_type = "Football"  # Drives are NFL/NCAAF
            data_for_sport_detection = self.current_drives_data
            # Count total drives from both current and previous
            total_drives = 0
            if self.current_drives_data.get("current"):
                total_drives += 1
            if self.current_drives_data.get("previous"):
                total_drives += len(self.current_drives_data.get("previous", []))
            total_items = total_drives
            data_type = "Drives"
        else:
            sport_type = "Unknown"
            total_items = 0
            data_type = "Items"
        
        # Generate better title with team names
        title = f"Exported Game Log - {sport_type}"
        team_names = self._extract_team_nicknames()
        if team_names:
            away_team, home_team = team_names
            title = f"Exported Game Log - {sport_type} - {away_team} vs {home_team}"
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }}
        .header {{
            background-color: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .period {{
            margin: 20px 0;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        .period-header {{
            background-color: #e9e9e9;
            padding: 10px;
            font-weight: bold;
            font-size: 18px;
        }}
        .half-section {{
            margin: 10px;
        }}
        .half-header {{
            background-color: #f9f9f9;
            padding: 8px;
            font-weight: bold;
            border-left: 4px solid #007cba;
            margin: 10px 0 5px 0;
        }}
        .at-bat {{
            margin: 10px 0;
            padding: 8px;
            border-left: 3px solid #ccc;
            background-color: #fafafa;
        }}
        .at-bat.scoring {{
            border-left-color: #ff6b35;
            background-color: #fff5f0;
        }}
        .at-bat-list {{
            list-style-type: none;
            padding-left: 0;
            margin: 10px 0;
        }}
        .at-bat-item {{
            margin: 10px 0;
            padding: 8px;
            border-left: 3px solid #ccc;
            background-color: #fafafa;
        }}
        .at-bat-item.scoring {{
            border-left-color: #ff6b35;
            background-color: #fff5f0;
        }}
        .at-bat-header {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .at-bat-title {{
            font-size: 18px;
            font-weight: bold;
            margin: 10px 0 8px 0;
            color: #333;
        }}
        .at-bat-title.scoring {{
            color: #ff6b35;
        }}
        .inning-half-title {{
            font-size: 20px;
            font-weight: bold;
            margin: 15px 0 10px 0;
            color: #444;
            border-bottom: 2px solid #007cba;
            padding-bottom: 5px;
        }}
        .at-bat-heading {{
            font-size: 16px;
            font-weight: bold;
            margin: 8px 0 5px 0;
            color: #333;
        }}
        .at-bat-heading.scoring {{
            color: #ff6b35;
        }}
        .pitch-list {{
            list-style-type: disc;
            margin: 8px 0;
            padding-left: 25px;
        }}
        .pitch-item {{
            color: #666;
            margin: 3px 0;
            font-size: 14px;
        }}
        .at-bat-result {{
            font-style: italic;
            color: #333;
            margin-top: 8px;
            font-weight: bold;
            border-top: 1px solid #ddd;
            padding-top: 5px;
        }}
        .pitch {{
            margin: 3px 0 3px 20px;
            color: #666;
            font-size: 14px;
        }}
        .drive {{
            margin: 10px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }}
        .drive-header {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
            font-size: 16px;
        }}
        .play-list {{
            list-style-type: disc;
            margin: 8px 0;
            padding-left: 25px;
        }}
        .play-item {{
            margin: 3px 0;
            color: #333;
            font-size: 14px;
        }}
        .play-item.scoring {{
            color: #ff6b35;
            font-weight: bold;
        }}
        .play {{
            margin: 3px 0 3px 15px;
            padding: 3px;
        }}
        .play.scoring {{
            background-color: #fff5f0;
            font-weight: bold;
        }}
        .export-info {{
            margin-top: 30px;
            padding: 10px;
            background-color: #f0f0f0;
            border-radius: 3px;
            font-size: 12px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p><strong>Total {data_type}:</strong> {total_items}</p>
        <p><strong>Export Date:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
"""
        
        if sport_type == "MLB":
            html += self._generate_baseball_html()
        elif sport_type in ("NFL", "Football", "NCAAF"):
            if has_drives:
                html += self._generate_football_drives_html()
            else:
                html += self._generate_football_html()
        elif sport_type in ("NBA", "WNBA", "NCAAM", "NCAAWB", "NCAAW"):
            html += self._generate_basketball_html()
        elif sport_type in ("NHL", "NCAAH", "NCAAWH"):
            html += self._generate_hockey_html()
        elif sport_type == "Soccer":
            html += self._generate_soccer_html()
        else:
            html += self._generate_generic_html()
        
        html += f"""
    <div class="export-info">
        <p>This game log was exported from the Sports Scores application.</p>
        <p>Generated on {datetime.now().strftime("%Y-%m-%d at %H:%M:%S")}</p>
    </div>
</body>
</html>"""
        
        return html
    
    def _generate_baseball_html(self):
        """Generate HTML for baseball game log"""
        # Check if we have plays data
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><div class="period-header">No baseball data available for export</div></div>'
        
        # Group plays by inning (similar to tree structure)
        inning_groups = {}
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", f"Period {period_info.get('number', 0)}")
            period_type = period_info.get("type", "Unknown").lower()
            
            if period_display not in inning_groups:
                inning_groups[period_display] = {"top": [], "bottom": []}
            
            if period_type == "top":
                inning_groups[period_display]["top"].append(play)
            elif period_type == "bottom":
                inning_groups[period_display]["bottom"].append(play)
            else:
                inning_groups[period_display]["top"].append(play)
        
        html = ""
        for period_display in sorted(inning_groups.keys(), key=lambda x: int(x.split()[0][:-2]) if x.split()[0][:-2].isdigit() else 0):
            period_data = inning_groups[period_display]
            
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{period_display}</h2>'
            
            # Top half
            if period_data["top"]:
                inning_num = period_display.split()[0]
                html += f'<div class="half-section">'
                html += f'<h3 class="inning-half-title">Top of the {inning_num}</h3>'
                html += self._generate_baseball_at_bats_html_with_lists(period_data["top"])
                html += '</div>'
            
            # Bottom half
            if period_data["bottom"]:
                inning_num = period_display.split()[0]
                html += f'<div class="half-section">'
                html += f'<h3 class="inning-half-title">Bottom of the {inning_num}</h3>'
                html += self._generate_baseball_at_bats_html_with_lists(period_data["bottom"])
                html += '</div>'
            
            html += '</div>'
        
        return html
    
    def _generate_baseball_at_bats_html_with_lists(self, plays):
        """Generate HTML for baseball at-bats using proper list structure"""
        # Group plays into at-bats with better logic
        at_bats = []
        current_at_bat = None
        
        for play in plays:
            play_type = play.get("type", {}).get("type", "")
            play_text = play.get("text", "")
            at_bat_id = play.get("atBatId")
            
            # Skip only true inning management plays
            if play_type in ["start-inning", "end-inning"] and "inning" in play_text.lower():
                continue
            
            # Start new at-bat or continue existing one
            if current_at_bat is None or (at_bat_id and current_at_bat["id"] != at_bat_id):
                if current_at_bat:
                    at_bats.append(current_at_bat)
                
                # Extract batter name from participants
                batter_name = "Unknown"
                participants = play.get("participants", [])
                for participant in participants:
                    if participant.get("type") == "batter":
                        athlete = participant.get("athlete", {})
                        batter_name = athlete.get("shortName") or athlete.get("displayName") or "Unknown"
                        break
                
                # If we still don't have a name, try the play text
                if batter_name == "Unknown" and play_text:
                    # Try to extract name from play text patterns
                    if " to " in play_text:
                        parts = play_text.split(" to ")
                        if len(parts) > 0:
                            potential_name = parts[0].strip()
                            if len(potential_name.split()) <= 3:
                                batter_name = potential_name
                    elif " struck out" in play_text:
                        name_part = play_text.split(" struck out")[0].strip()
                        if len(name_part.split()) <= 3:
                            batter_name = name_part
                
                current_at_bat = {
                    "id": at_bat_id,
                    "batter": batter_name,
                    "result": "",
                    "plays": [],
                    "scoring": False,
                    "score": ""
                }
            
            current_at_bat["plays"].append(play)
            
            # Check for scoring play
            if play.get("scoringPlay", False):
                current_at_bat["scoring"] = True
                away_score = play.get("awayScore", 0)
                home_score = play.get("homeScore", 0)
                current_at_bat["score"] = f"({away_score}-{home_score})"
            
            # Look for at-bat result plays (less restrictive)
            if not current_at_bat["result"] and play_text:
                # If it's not just a pitch description, it might be a result
                if not any(pitch_word in play_text.lower() for pitch_word in 
                          ["pitch", "ball ", "strike ", "foul tip"]):
                    current_at_bat["result"] = play_text
        
        if current_at_bat:
            at_bats.append(current_at_bat)
        
        if not at_bats:
            return '<p>No at-bats in this half inning.</p>'
        
        html = '<ul class="at-bat-list">'
        
        for at_bat in at_bats:
            # Be less restrictive about showing at-bats
            if not at_bat["batter"] or at_bat["batter"] == "Unknown":
                # If no batter name, use the play text as a fallback
                if at_bat["plays"] and at_bat["plays"][0].get("text"):
                    at_bat["batter"] = "Play"
                else:
                    continue
            
            # Use the result or fall back to the most meaningful play
            result_text = at_bat["result"]
            if not result_text and at_bat["plays"]:
                # Find the most meaningful play (not just pitch descriptions)
                for play in reversed(at_bat["plays"]):  # Start from the end
                    text = play.get("text", "")
                    if text and not any(pitch_word in text.lower() for pitch_word in 
                                      ["pitch ", "ball ", "strike ", "foul tip"]):
                        result_text = text
                        break
                
                # If still no result, use the last play
                if not result_text:
                    result_text = at_bat["plays"][-1].get("text", "")
            
            if not result_text:
                continue
                
            scoring_class = "scoring" if at_bat["scoring"] else ""
            score_text = f" {at_bat['score']}" if at_bat["scoring"] else ""
            
            html += f'<li class="at-bat-item {scoring_class}">'
            html += f'<h4 class="at-bat-heading {scoring_class}">{at_bat["batter"]}: {result_text}{score_text}</h4>'
            
            # Add pitch details as a nested list
            pitch_plays = []
            for play in at_bat["plays"]:
                play_text = play.get("text", "")
                
                # Skip the result play and include pitch-related plays
                if play_text != result_text and any(pitch_keyword in play_text.lower() for pitch_keyword in 
                       ["ball", "strike", "foul", "looking", "swinging", "pitch"]):
                    
                    # Extract additional pitch details if available (same logic as tree view)
                    enhanced_text = play_text
                    velocity = play.get("pitchVelocity")
                    pitch_type = play.get("pitchType", {})
                    pitch_type_text = pitch_type.get("text", "") if isinstance(pitch_type, dict) else ""
                    pitch_coordinate = play.get("pitchCoordinate", {})
                    
                    # Get pitch location with absolute coordinates (same logic as tree view)
                    location = ""
                    if pitch_coordinate and isinstance(pitch_coordinate, dict):
                        espn_x = pitch_coordinate.get("x")  # Horizontal (absolute)
                        espn_y = pitch_coordinate.get("y")  # Vertical (absolute)
                        if espn_x is not None and espn_y is not None:
                            # Try to determine batter handedness (simplified)
                            batter_side = None
                            
                            # Check if we can extract batter info from the play data (safely)
                            if isinstance(play, dict) and 'participants' in play:
                                for participant in play.get('participants', []):
                                    if isinstance(participant, dict) and participant.get('type') == 'batter':
                                        batter_side = participant.get('batSide')
                                        break
                            
                            # Use simple heuristics for known players
                            # TODO: Improve batter data extraction from ESPN API
                            
                            # Get location with batter context
                            location = get_pitch_location(espn_x, espn_y, batter_side)
                    
                    # Build enhanced text with velocity, type, and coordinates
                    # Note: location now contains coordinates, so no need for separate coordinates_text
                    details = []
                    if velocity:
                        details.append(f"{velocity} mph")
                    if pitch_type_text:
                        details.append(pitch_type_text)
                    
                    if details:
                        detail_text = " ".join(details)
                        if location:
                            enhanced_text = f"{play_text} ({detail_text}) - {location}"
                        else:
                            enhanced_text = f"{play_text} ({detail_text})"
                    elif location:
                        enhanced_text = f"{play_text} - {location}"
                    else:
                        enhanced_text = play_text
                    
                    pitch_plays.append(enhanced_text)
            
            if pitch_plays:
                html += '<ul class="pitch-list">'
                for pitch_text in pitch_plays:
                    html += f'<li class="pitch-item">{pitch_text}</li>'
                html += '</ul>'
            
            # Repeat the result at the end for better flow
            html += f'<div class="at-bat-result">Result: {result_text}{score_text}</div>'
            
            html += '</li>'
        
        html += '</ul>'
        return html
    
    def _generate_baseball_at_bats_html(self, plays):
        """Generate HTML for baseball at-bats"""
        # Group plays into at-bats with better logic
        at_bats = []
        current_at_bat = None
        
        for play in plays:
            play_type = play.get("type", {}).get("type", "")
            play_text = play.get("text", "")
            at_bat_id = play.get("atBatId")
            
            # Skip only true inning management plays
            if play_type in ["start-inning", "end-inning"] and "inning" in play_text.lower():
                continue
            
            # Start new at-bat or continue existing one
            if current_at_bat is None or (at_bat_id and current_at_bat["id"] != at_bat_id):
                if current_at_bat:
                    at_bats.append(current_at_bat)
                
                # Extract batter name from participants
                batter_name = "Unknown"
                participants = play.get("participants", [])
                for participant in participants:
                    if participant.get("type") == "batter":
                        athlete = participant.get("athlete", {})
                        batter_name = athlete.get("shortName") or athlete.get("displayName") or "Unknown"
                        break
                
                # If we still don't have a name, try the play text
                if batter_name == "Unknown" and play_text:
                    # Try to extract name from play text patterns
                    if " to " in play_text:
                        # Pattern: "John Smith to first base"
                        parts = play_text.split(" to ")
                        if len(parts) > 0:
                            potential_name = parts[0].strip()
                            if len(potential_name.split()) <= 3:  # Reasonable name length
                                batter_name = potential_name
                    elif " struck out" in play_text:
                        # Pattern: "Smith struck out swinging"
                        name_part = play_text.split(" struck out")[0].strip()
                        if len(name_part.split()) <= 3:
                            batter_name = name_part
                
                current_at_bat = {
                    "id": at_bat_id,
                    "batter": batter_name,
                    "result": "",
                    "plays": [],
                    "scoring": False,
                    "score": ""
                }
            
            current_at_bat["plays"].append(play)
            
            # Check for scoring play
            if play.get("scoringPlay", False):
                current_at_bat["scoring"] = True
                away_score = play.get("awayScore", 0)
                home_score = play.get("homeScore", 0)
                current_at_bat["score"] = f"({away_score}-{home_score})"
            
            # Look for at-bat result plays (less restrictive)
            if not current_at_bat["result"] and play_text:
                # If it's not just a pitch description, it might be a result
                if not any(pitch_word in play_text.lower() for pitch_word in 
                          ["pitch", "ball ", "strike ", "foul tip"]):
                    current_at_bat["result"] = play_text
        
        if current_at_bat:
            at_bats.append(current_at_bat)
        
        html = ""
        for at_bat in at_bats:
            # Be less restrictive about showing at-bats
            if not at_bat["batter"] or at_bat["batter"] == "Unknown":
                # If no batter name, use the play text as a fallback
                if at_bat["plays"] and at_bat["plays"][0].get("text"):
                    at_bat["batter"] = "Play"
                else:
                    continue
            
            # Use the result or fall back to the most meaningful play
            result_text = at_bat["result"]
            if not result_text and at_bat["plays"]:
                # Find the most meaningful play (not just pitch descriptions)
                for play in reversed(at_bat["plays"]):  # Start from the end
                    text = play.get("text", "")
                    if text and not any(pitch_word in text.lower() for pitch_word in 
                                      ["pitch ", "ball ", "strike ", "foul tip"]):
                        result_text = text
                        break
                
                # If still no result, use the last play
                if not result_text:
                    result_text = at_bat["plays"][-1].get("text", "")
            
            if not result_text:
                continue
                
            scoring_class = "scoring" if at_bat["scoring"] else ""
            score_text = f" {at_bat['score']}" if at_bat["scoring"] else ""
            
            html += f'<div class="at-bat {scoring_class}">'
            html += f'<strong>{at_bat["batter"]}: {result_text}{score_text}</strong>'
            
            # Add pitch details (but filter out the result play to avoid duplication)
            for play in at_bat["plays"]:
                play_text = play.get("text", "")
                
                # Skip the result play and include pitch-related plays
                if play_text != result_text and any(pitch_keyword in play_text.lower() for pitch_keyword in 
                       ["ball", "strike", "foul", "looking", "swinging", "pitch"]):
                    html += f'<div class="pitch">{play_text}</div>'
            
            html += '</div>'
        
        return html
    
    def _generate_football_html(self):
        """Generate HTML for football game log"""
        # Check if we have plays data
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><div class="period-header">No football play data available for export</div></div>'
        
        # Group by quarter and drive
        quarter_groups = {}
        
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", f"{period_info.get('number', 1)}Q")
            
            drive_number = play.get("driveNumber", "Unknown")
            drive_team = play.get("team", {}).get("id", "Unknown")
            
            if period_display not in quarter_groups:
                quarter_groups[period_display] = {}
            
            drive_key = f"Drive {drive_number} (Team {drive_team})"
            if drive_key not in quarter_groups[period_display]:
                quarter_groups[period_display][drive_key] = []
            
            quarter_groups[period_display][drive_key].append(play)
        
        html = ""
        for period_display in sorted(quarter_groups.keys()):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{period_display}</h2>'
            
            for drive_key, drive_plays in quarter_groups[period_display].items():
                html += f'<div class="drive">'
                html += f'<h3 class="drive-header">{drive_key}</h3>'
                html += '<ul class="plays-list">'
                
                for play in drive_plays:
                    scoring_class = "scoring" if play.get("scoringPlay", False) else ""
                    play_text = play.get("text", "")
                    
                    if play.get("scoringPlay", False):
                        away_score = play.get("awayScore", 0)
                        home_score = play.get("homeScore", 0)
                        play_text = f"🏈 {play_text} ({away_score}-{home_score})"
                    
                    css_class = f"play-item {scoring_class}".strip()
                    html += f'<li class="{css_class}">{play_text}</li>'
                
                html += '</ul>'
                html += '</div>'
            
            html += '</div>'
        
        return html
    
    def _generate_football_drives_html(self):
        """Generate HTML for football game log from drives data"""
        # Process drives data structure
        drives_data = self.current_drives_data
        all_drives = []
        
        # Add current drive if available
        current_drive = drives_data.get("current")
        if current_drive:
            all_drives.append(("Current Drive", current_drive))
        
        # Add previous drives if available
        previous_drives = drives_data.get("previous", [])
        for i, drive in enumerate(previous_drives):
            drive_num = len(previous_drives) - i  # Number drives in reverse order
            all_drives.append((f"Drive {drive_num}", drive))
        
        # Group drives by quarter for better organization
        quarter_groups = {}
        
        for drive_label, drive in all_drives:
            if not drive or not isinstance(drive, dict):
                continue
                
            # Get drive info
            description = drive.get("description", "Unknown drive")
            team_info = drive.get("team", {})
            team_name = team_info.get("displayName", "Unknown Team")
            
            # Determine quarter from plays
            plays = drive.get("plays", [])
            quarter = "Unknown Quarter"
            if plays and len(plays) > 0:
                first_play = plays[0]
                period_info = first_play.get("period", {})
                quarter = period_info.get("displayValue", f"{period_info.get('number', 1)}Q")
            
            # Separate kickoffs from regular drive plays
            drive_plays = []
            kickoff_plays = []
            
            for play in plays:
                play_type = play.get("type", {})
                play_type_text = play_type.get("text", "").lower()
                
                if "kickoff" in play_type_text:
                    kickoff_plays.append(play)
                else:
                    drive_plays.append(play)
            
            if quarter not in quarter_groups:
                quarter_groups[quarter] = []
            
            # Add kickoffs as separate entries
            for kickoff in kickoff_plays:
                quarter_groups[quarter].append({
                    "label": "Kickoff",
                    "team": "Special Teams",
                    "description": "Kickoff",
                    "plays": [kickoff],
                    "is_kickoff": True
                })
            
            # Add regular drive if it has non-kickoff plays
            if drive_plays:
                quarter_groups[quarter].append({
                    "label": drive_label,
                    "team": team_name,
                    "description": description,
                    "plays": drive_plays,
                    "is_kickoff": False
                })
        
        html = ""
        for quarter_name in sorted(quarter_groups.keys()):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{quarter_name}</h2>'
            
            for drive_info in quarter_groups[quarter_name]:
                html += f'<div class="drive">'
                
                # Handle kickoffs differently
                if drive_info.get("is_kickoff", False):
                    html += f'<h3 class="drive-header kickoff-header">⚡ Kickoff</h3>'
                else:
                    html += f'<h3 class="drive-header">{drive_info["team"]}: {drive_info["description"]}</h3>'
                
                html += f'<ul class="play-list">'
                
                for play in drive_info["plays"]:
                    play_text = play.get("text", "Unknown play")
                    play_type = play.get("type", {})
                    play_type_text = play_type.get("text", "").lower()
                    
                    # Handle kickoffs
                    if "kickoff" in play_type_text or drive_info.get("is_kickoff", False):
                        # Add clock context for kickoffs
                        clock = play.get("clock", {})
                        if clock:
                            clock_display = clock.get("displayValue", "")
                            if clock_display:
                                play_text = f"[{clock_display}] {play_text}"
                        
                        html += f'<li class="play-item kickoff">{play_text}</li>'
                        continue
                    
                    # Add down and distance information for regular plays
                    start = play.get("start", {})
                    down = start.get("down", 0)
                    distance = start.get("distance", 0)
                    possession_text = start.get("possessionText", "")
                    yards_to_endzone = start.get("yardsToEndzone", 0)
                    
                    # Get additional NFL-specific data
                    stat_yardage = play.get("statYardage", 0)
                    play_type_obj = play.get("type", {})
                    play_type_name = play_type_obj.get("text", "")
                    
                    # Build enhanced play description
                    enhanced_text = play_text
                    
                    # Add yardage information if available
                    if stat_yardage != 0:
                        yardage_display = f"(+{stat_yardage} yards)" if stat_yardage > 0 else f"({stat_yardage} yards)"
                        enhanced_text = f"{yardage_display} {enhanced_text}"
                    
                    # Add play type for clarity (accessible text)
                    if play_type_name and play_type_name.lower() not in enhanced_text.lower():
                        if "pass" in play_type_name.lower():
                            enhanced_text = f"PASS: {enhanced_text}"
                        elif "rush" in play_type_name.lower():
                            enhanced_text = f"RUSH: {enhanced_text}"
                        elif "sack" in play_type_name.lower():
                            enhanced_text = f"SACK: {enhanced_text}"
                        elif "penalty" in play_type_name.lower():
                            enhanced_text = f"PENALTY: {enhanced_text}"
                        elif "punt" in play_type_name.lower():
                            enhanced_text = f"PUNT: {enhanced_text}"
                        elif "field goal" in play_type_name.lower():
                            enhanced_text = f"FIELD GOAL: {enhanced_text}"
                    
                    # Add situational context
                    situation_prefix = ""
                    situation_class = ""
                    if yards_to_endzone <= 5:
                        situation_prefix = "GOAL LINE "
                        situation_class = "goal-line"
                    elif yards_to_endzone <= 20:
                        situation_prefix = "RED ZONE "
                        situation_class = "red-zone"
                    elif down == 4:
                        situation_prefix = "4TH DOWN "
                        situation_class = "fourth-down"
                    
                    # Use start data for down/distance display (not end!)
                    down_distance_prefix = ""
                    if down > 0:  # Regular downs
                        if possession_text:
                            if situation_prefix:
                                down_distance_prefix = f"[{situation_prefix}{down} & {distance} from {possession_text}] "
                            else:
                                down_distance_prefix = f"[{down} & {distance} from {possession_text}] "
                        else:
                            down_distance_prefix = f"[{situation_prefix}{down} & {distance}] "
                    
                    # Check for scoring play
                    scoring_class = ""
                    if play.get("scoringPlay"):
                        scoring_class = "scoring"
                        away_score = play.get("awayScore", 0)
                        home_score = play.get("homeScore", 0)
                        play_text = f"TOUCHDOWN: {down_distance_prefix}{enhanced_text} ({away_score}-{home_score})"
                    else:
                        play_text = f"{down_distance_prefix}{enhanced_text}"
                    
                    # Add clock context
                    clock = play.get("clock", {})
                    if clock:
                        clock_display = clock.get("displayValue", "")
                        if clock_display:
                            play_text = f"[{clock_display}] {play_text}"
                    
                    # Combine CSS classes
                    css_classes = f"play-item {scoring_class} {situation_class}".strip()
                    html += f'<li class="{css_classes}">{play_text}</li>'
                
                html += '</ul>'
                html += '</div>'
            
            html += '</div>'
        
        return html
    
    def _generate_generic_html(self):
        """Generate HTML for generic sport game log"""
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><p>No play data available for export.</p></div>'

        # Group by period, mirroring _build_generic_tree
        period_groups = {}
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", "Unknown Period")
            if period_display not in period_groups:
                period_groups[period_display] = []
            period_groups[period_display].append(play)

        html = ""
        for period_display in sorted(period_groups.keys()):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{period_display}</h2>'
            html += '<ul class="plays-list">'

            for play in period_groups[period_display]:
                play_text = play.get("text", "Unknown play")
                clock_time = self._extract_play_clock_display(play)
                score_info = self._extract_basketball_score_info(play)
                if clock_time != "--:--":
                    formatted_text = self._format_clock_play_entry(play_text, clock_time, score_info)
                else:
                    formatted_text = play_text
                html += f'<li class="play-item">{formatted_text}</li>'

            html += '</ul>'
            html += '</div>'

        return html

    def _generate_basketball_html(self):
        """Generate HTML for basketball game log"""
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><p>No basketball data available for export.</p></div>'

        # Group by quarter, mirroring _build_basketball_tree
        quarter_groups = {}
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", f"{period_info.get('number', 1)}Q")
            if period_display not in quarter_groups:
                quarter_groups[period_display] = []
            quarter_groups[period_display].append(play)

        html = ""
        for period_display in sorted(quarter_groups.keys(), key=lambda x: int(x.replace('Q', '')) if x.replace('Q', '').isdigit() else 999):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">Period {period_display}</h2>'
            html += '<ul class="plays-list">'

            # Sort plays by clock descending (most recent first), matching the UI tree
            period_plays = sorted(
                quarter_groups[period_display],
                key=lambda p: self._parse_basketball_clock(p.get("clock", "00:00")),
                reverse=True,
            )

            for play in period_plays:
                action_text = play.get("text", "Play")
                score_info = self._extract_basketball_score_info(play)
                clock_time = play.get("clock", "00:00")
                formatted_play = self._format_basketball_play_entry(action_text, score_info, clock_time)
                scoring_class = "scoring" if play.get("scoringPlay", False) else ""
                css_class = f"play-item {scoring_class}".strip()
                html += f'<li class="{css_class}">{formatted_play}</li>'

            html += '</ul>'
            html += '</div>'

        return html

    def _generate_hockey_html(self):
        """Generate HTML for hockey game log"""
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><p>No hockey data available for export.</p></div>'

        # Group by period
        period_groups = {}
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", f"Period {period_info.get('number', 1)}")
            if period_display not in period_groups:
                period_groups[period_display] = []
            period_groups[period_display].append(play)

        html = ""
        for period_display in sorted(period_groups.keys()):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{period_display}</h2>'
            html += '<ul class="plays-list">'

            for play in period_groups[period_display]:
                play_text = play.get("text", "Play")
                clock_time = self._extract_play_clock_display(play)
                score_info = self._extract_basketball_score_info(play)
                if clock_time != "--:--":
                    formatted_text = self._format_clock_play_entry(play_text, clock_time, score_info)
                else:
                    formatted_text = play_text
                scoring_class = "scoring" if play.get("scoringPlay", False) else ""
                css_class = f"play-item {scoring_class}".strip()
                html += f'<li class="{css_class}">{formatted_text}</li>'

            html += '</ul>'
            html += '</div>'

        return html

    def _generate_soccer_html(self):
        """Generate HTML for soccer game log"""
        if not hasattr(self, 'current_plays_data') or not self.current_plays_data:
            return '<div class="period"><p>No soccer data available for export.</p></div>'

        # Group by half
        half_groups = {}
        for play in self.current_plays_data:
            period_info = play.get("period", {})
            period_display = period_info.get("displayValue", f"Half {period_info.get('number', 1)}")
            if period_display not in half_groups:
                half_groups[period_display] = []
            half_groups[period_display].append(play)

        html = ""
        for period_display in sorted(half_groups.keys()):
            html += f'<div class="period">'
            html += f'<h2 class="period-header">{period_display}</h2>'
            html += '<ul class="plays-list">'

            for play in half_groups[period_display]:
                play_text = play.get("text", "Play")
                clock_time = self._extract_play_clock_display(play)
                score_info = self._extract_basketball_score_info(play)
                if clock_time != "--:--":
                    formatted_text = self._format_clock_play_entry(play_text, clock_time, score_info)
                else:
                    formatted_text = play_text
                event_type = play.get("type", {}).get("text", "")
                scoring_class = "scoring" if "goal" in event_type.lower() else ""
                css_class = f"play-item {scoring_class}".strip()
                html += f'<li class="{css_class}">{formatted_text}</li>'

            html += '</ul>'
            html += '</div>'

        return html

    def _add_injuries_list_to_layout(self, layout, data):
        """Add injuries list to layout using accessible table"""
        if not data:
            layout.addWidget(QLabel("No injury data available."))
            return
        
        # Create accessible injury table
        injury_table = InjuryTable(parent=self, title="Injury Report")
        injury_table.setColumnCount(len(INJURY_HEADERS))
        injury_table.setHorizontalHeaderLabels(INJURY_HEADERS)
        
        # Populate with injury data using the specialized method
        injury_table.populate_injury_data(data, set_focus=True)
        
        # Configure table appearance
        header = injury_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Player name stretches
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Team name stretches
        
        layout.addWidget(injury_table)
    
    def _add_officials_list_to_layout(self, layout, data):
        """Add officials list to layout"""
        if not data:
            layout.addWidget(QLabel("No officials data available."))
            return
        
        # Create a clean list widget for officials
        officials_list = QListWidget()
        officials_list.setAccessibleName("Officials List")
        officials_list.setAccessibleDescription("List of game officials and their positions")
        
        for official in data:
            name = official.get('displayName', 'Unknown Official')
            position_info = official.get('position', {})
            position = position_info.get('displayName', 'Unknown Position')
            order = official.get('order', 0)
            
            # Create formatted display text
            list_item = f"{order}. {name} - {position}"
            officials_list.addItem(list_item)
        
        layout.addWidget(officials_list)
    
    def _add_news_list_to_layout(self, layout, data):
        """Add news list to layout"""
        if not data:
            layout.addWidget(QLabel("No news data available."))
            return
        
        # Handle different news data formats and enhance game-specific news
        news_articles = []
        
        # Check if this is game details data that might have both 'article' and 'news'
        if isinstance(data, dict):
            if "articles" in data:
                # Standard news format with articles array
                news_articles = data["articles"]
            elif "article" in data or "news" in data:
                # This might be full game details - check for game-specific article first
                game_article = data.get("article")
                general_news = data.get("news", {}).get("articles", [])
                
                # Prioritize game-specific article, then add general news
                if game_article and isinstance(game_article, dict):
                    news_articles.append(game_article)
                if general_news and isinstance(general_news, list):
                    news_articles.extend(general_news)
            else:
                # Single article format
                news_articles = [data]
        elif isinstance(data, list):
            # Direct list of articles
            news_articles = data
        
        if not news_articles:
            layout.addWidget(QLabel("No news articles available."))
            return
        
        # Create list widget for news headlines (consistent with other views)
        news_list = QListWidget()
        news_list.setAccessibleName("News Headlines List")
        news_list.setAccessibleDescription("List of news headlines - Enter or double-click opens in browser")
        
        # Add articles as list items, with special labeling for game-specific content
        for i, news_item in enumerate(news_articles):
            news_data = NewsData(news_item)
            # Get just the headline for consistent list display
            headline = news_data.headline if hasattr(news_data, 'headline') else news_data.get_display_text()
            
            # Add indicator for game-specific article (first item if it came from 'article' field)
            if i == 0 and isinstance(data, dict) and "article" in data and "news" in data:
                headline = f"🎯 {headline}"  # Game-specific indicator
            
            item = QListWidgetItem(headline)
            item.setData(Qt.ItemDataRole.UserRole, news_data)
            news_list.addItem(item)
        
        # Connect activation (Enter key or double-click) to open in browser
        def open_news_item(item):
            news_data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(news_data, NewsData) and news_data.has_web_url():
                if news_data.web_url.startswith(("http://", "https://")):
                    try:
                        webbrowser.open(news_data.web_url)
                    except Exception as e:
                        QMessageBox.warning(None, "Browser Error", f"Could not open browser: {str(e)}")
                else:
                    QMessageBox.warning(None, "Invalid URL", "The URL for this story is invalid.")
            else:
                QMessageBox.information(None, "No Link", "No web link available for this story.")
        
        news_list.itemActivated.connect(open_news_item)
        news_list.itemDoubleClicked.connect(open_news_item)
        
        layout.addWidget(QLabel("News Headlines (🎯 = Game-specific, Enter or double-click to open in browser):"))
        layout.addWidget(news_list)

    def keyPressEvent(self, event):
        """Handle key press events, but let dialog handle Escape when in modal context"""
        if event.key() == Qt.Key.Key_Escape:
            # Check if we're in a dialog context
            parent_widget = self.parent()
            while parent_widget:
                if isinstance(parent_widget, QDialog):
                    # Let the dialog handle the escape key
                    parent_widget.keyPressEvent(event)
                    return
                parent_widget = parent_widget.parent()
            
            # If not in dialog, use BaseView's escape handling
            super().keyPressEvent(event)
        else:
            # For all other keys, use BaseView's handling
            super().keyPressEvent(event)

class MLBWildCardLoader(QThread):
    """Background fetch of the MLB wild card standings.

    Threaded for the same reason every other loader in this file is: the fetch
    runs from a `currentChanged` slot, and a synchronous call there freezes the
    event loop — which with a screen reader attached means silence, no UIA
    events, and no way to arrow back off the tab.
    """
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_mlb_wildcard_standings() or {})
        except Exception as e:
            self.error_occurred.emit(str(e))


class WildCardTabsMixin:
    """Adds the MLB wild card tabs to a standings dialog that shows division tabs.

    The two tabs sit after the six division ones and are filled the first time a
    user opens one, so the divisions people usually want are never held up by a
    second network call. Requires `self.tab_widget` and `self.league`.
    """

    WILDCARD_TABS = (("AL", "AL Wild Card"), ("NL", "NL Wild Card"))

    def _build_wildcard_tabs(self):
        self._wildcard_tabs = {}
        self._wildcard_loader = None
        if self.league != "MLB" or not self.tab_widget:
            return
        for league_key, label in self.WILDCARD_TABS:
            placeholder = QWidget()
            placeholder_layout = QVBoxLayout()
            # A focusable list rather than a bare QLabel: an unfocusable label is
            # not in the tab order and fires no live-region event, so a screen
            # reader user would hear the tab name and then nothing at all.
            status = QListWidget()
            status.addItem("Loading wild card standings...")
            status.setAccessibleName(f"{label} status")
            placeholder_layout.addWidget(status)
            placeholder.setLayout(placeholder_layout)
            index = self.tab_widget.addTab(placeholder, label)
            self._wildcard_tabs[index] = [league_key, label, False]
        self.tab_widget.currentChanged.connect(self._on_standings_tab_changed)

    def _on_standings_tab_changed(self, index: int):
        """Kick off the wild card fetch the first time a user opens the tab.

        Wrapped end to end: an exception escaping a Qt slot invoked from C++
        calls qFatal(), which aborts the process rather than logging anything.
        """
        try:
            entry = getattr(self, "_wildcard_tabs", {}).get(index)
            if not entry or entry[2]:
                return
            league_key, label, _ = entry
            entry[2] = True

            cache = DataCache()
            cached = cache.get_mlb_wildcard()
            if cached is not None:
                self._populate_wildcard_tab(index, cached)
                return

            self._announce_wildcard(f"Loading {label} standings")
            loader = MLBWildCardLoader()
            loader.data_loaded.connect(
                lambda data, i=index: self._on_wildcard_loaded(i, data))
            loader.error_occurred.connect(
                lambda _msg, i=index: self._on_wildcard_loaded(i, {}))
            # Switching tabs mid-load replaces _wildcard_loader, so the running
            # thread is held until it finishes instead.
            self._wildcard_loader = loader
            _start_detached_thread(loader)
        except Exception as e:
            print(f"[WARNING] Wild card tab failed: {e}")

    def _on_wildcard_loaded(self, index: int, wildcard: dict):
        try:
            if wildcard:
                DataCache().set_mlb_wildcard(wildcard)
            self._populate_wildcard_tab(index, wildcard)
        except Exception as e:
            print(f"[WARNING] Wild card tab failed to populate: {e}")

    def _populate_wildcard_tab(self, index: int, wildcard: dict):
        entry = getattr(self, "_wildcard_tabs", {}).get(index)
        if not entry:
            return
        league_key, label, _ = entry

        container = self.tab_widget.widget(index)
        container_layout = container.layout()
        while container_layout.count():
            item = container_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        teams = (wildcard or {}).get(league_key) or []
        if not teams:
            # Allow a retry on the next visit rather than leaving the tab dead
            # for the life of the dialog.
            entry[2] = False
            status = QListWidget()
            status.addItem("Wild card standings are unavailable right now. "
                           "Leave this tab and return to try again.")
            status.setAccessibleName(f"{label} unavailable")
            container_layout.addWidget(status)
            container.table = None  # type: ignore[attr-defined]
            self._announce_wildcard(f"{label} standings unavailable")
            return

        # set_focus=False, and no setFocus() here: currentChanged fires for any
        # tab change including a plain arrow along the tab bar, so grabbing focus
        # would trap a keyboard user in the table and stop them arrowing on.
        table = WildCardTable(parent=self, division_name=label)
        table.populate_standings(teams, set_focus=False)
        container_layout.addWidget(table)
        container.table = table  # type: ignore[attr-defined]
        self._announce_wildcard(f"{label} standings ready, {len(teams)} teams")

    def _announce_wildcard(self, message: str):
        helper = getattr(self, "notification_helper", None)
        if helper is None:
            helper = getattr(getattr(self, "parent_app", None), "notification_helper", None)
        if helper is not None:
            try:
                helper.announce(message)
            except Exception:
                pass


class StandingsDetailDialog(WildCardTabsMixin, QDialog):
    """Dialog for displaying team standings from game details with keyboard navigation"""
    
    def __init__(self, standings_data: List, league: str, parent=None):
        super().__init__(parent)
        self.standings_data = StandingsData(standings_data)
        self.league = league
        self.setWindowTitle(f"{league} Standings Details")
        self.resize(STANDINGS_DIALOG_WIDTH, STANDINGS_DIALOG_HEIGHT)
        
        self.tab_widget: QTabWidget | None = None
        self.single_table: StandingsTable | None = None
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        if not self.standings_data.teams:
            layout.addWidget(QLabel(f"No standings data available for {self.league}."))
        else:
            has_divisions = len(self.standings_data.divisions) > 1 or any(
                div != "League" for div in self.standings_data.divisions.keys()
            )
            if has_divisions and self.league in ["MLB", "NFL"]:
                self._build_division_tabs(layout)
            else:
                self.single_table = self._create_single_standings_table(self.standings_data.teams)
                layout.addWidget(QLabel(f"Current {self.league} Standings:"))
                layout.addWidget(self.single_table)
                self.single_table.setFocus()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)
    
    def _build_division_tabs(self, layout: QVBoxLayout):
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName(
            "Standings" if self.league == "MLB" else "Division Standings")
        self.tab_widget.setAccessibleDescription(
            "Team standings by division, plus AL and NL wild card, use arrow keys to move between tabs"
            if self.league == "MLB"
            else "Team standings by division, use arrow keys to navigate between divisions")
        
        if self.league == "MLB":
            division_order = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West", "League"]
        elif self.league == "NFL":
            division_order = ["AFC East", "AFC North", "AFC South", "AFC West", 
                            "NFC East", "NFC North", "NFC South", "NFC West", "League"]
        else:
            division_order = ["League"]
            
        ordered: List[tuple[str, List[Dict]]] = []
        for name in division_order:
            if name in self.standings_data.divisions:
                ordered.append((name, self.standings_data.divisions[name]))
        for name, teams in self.standings_data.divisions.items():
            if name not in division_order:
                ordered.append((name, teams))
        for name, teams in ordered:
            if teams:
                tab = self._create_division_table(name, teams)
                self.tab_widget.addTab(tab, name)

        self._build_wildcard_tabs()

        layout.addWidget(self.tab_widget)
        if self.tab_widget.count():
            first = self.tab_widget.widget(0)
            if hasattr(first, "table"):
                first.table.setFocus()  # type: ignore[attr-defined]
    
    def _create_division_table(self, division_name: str, teams: List[Dict]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        table = StandingsTable(parent=self, division_name=division_name)
        table.populate_standings(teams, set_focus=True)
        layout.addWidget(table)
        widget.setLayout(layout)
        widget.table = table  # type: ignore[attr-defined]
        return widget
    
    def _create_single_standings_table(self, teams: List[Dict]) -> StandingsTable:
        table = StandingsTable(parent=self)
        table.populate_standings(teams, set_focus=True)
        return table
    
    def _configure_table(self, table: QTableWidget):
        """Configure table appearance and behavior"""
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)  # Allow cell selection
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Enable keyboard navigation
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setTabKeyNavigation(True)
        
        # Enable accessibility features
        table.setAccessibleName("Standings Table")
        table.setAccessibleDescription("Team standings with arrow key navigation. Use arrow keys to navigate cells, Tab to enter/exit table.")
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if table.columnCount() > 1:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Team name stretches

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if self.tab_widget:
            if event.key() == Qt.Key.Key_F6:
                self.tab_widget.setFocus(); event.accept(); return
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_Tab:
                    i = (self.tab_widget.currentIndex() + 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()  # type: ignore[attr-defined]
                    event.accept(); return
                if event.key() == Qt.Key.Key_Backtab:
                    i = (self.tab_widget.currentIndex() - 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()  # type: ignore[attr-defined]
                    event.accept(); return
        super().keyPressEvent(event)

class KitchenSinkDialog(QDialog):
    """Dialog for displaying additional MLB data features not shown in main views"""
    
    def __init__(self, raw_game_data: Dict, parent=None):
        super().__init__(parent)
        self.raw_data = raw_game_data
        self.setWindowTitle("Kitchen Sink - Additional MLB Data")
        self.resize(1000, 700)
        
        self.tab_widget: QTabWidget | None = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Create tabs for different data types
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Kitchen Sink Data")
        self.tab_widget.setAccessibleDescription("Additional baseball data features, use arrow keys to navigate between sections")
        
        # Add tabs for each available feature (only if data exists)
        self._add_rosters_tab()
        self._add_season_series_tab()
        self._add_articles_tab()
        self._add_betting_tab()
        self._add_picks_tab()
        self._add_win_probability_tab()
        self._add_videos_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        
        # Set focus to first tab
        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)
            QTimer.singleShot(50, lambda: self.tab_widget.setFocus())
    
    def _add_rosters_tab(self):
        """Add rosters/lineups tab"""
        rosters_data = self.raw_data.get("rosters")
        if not rosters_data:
            return
            
        scroll_area = QScrollArea()
        content_widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🧑‍🤝‍🧑 STARTING LINEUPS & ROSTERS"))
        
        if isinstance(rosters_data, list):
            for team_data in rosters_data:
                if isinstance(team_data, dict):
                    team_info = team_data.get("team", {})
                    team_name = team_info.get("displayName", "Unknown Team")
                    layout.addWidget(QLabel(f"\n{team_name}:"))
                    
                    roster = team_data.get("roster", [])
                    if roster:
                        table = AccessibleTable()
                        table.setColumnCount(4)
                        table.setHorizontalHeaderLabels(["Position", "Player", "Number", "Status"])
                        
                        table.setRowCount(len(roster))
                        for row, player in enumerate(roster):
                            position = player.get("position", {})
                            pos_name = position.get("displayName", "") if isinstance(position, dict) else str(position)
                            
                            athlete = player.get("athlete", {})
                            player_name = athlete.get("displayName", "") if isinstance(athlete, dict) else str(athlete)
                            jersey = athlete.get("jersey", "") if isinstance(athlete, dict) else ""
                            
                            status = player.get("status", "")
                            
                            table.setItem(row, 0, QTableWidgetItem(pos_name))
                            table.setItem(row, 1, QTableWidgetItem(player_name))
                            table.setItem(row, 2, QTableWidgetItem(str(jersey)))
                            table.setItem(row, 3, QTableWidgetItem(str(status)))
                        
                        table.resizeColumnsToContents()
                        layout.addWidget(table)
                    else:
                        layout.addWidget(QLabel("  No roster data available"))
        else:
            layout.addWidget(QLabel("No roster data available"))
        
        content_widget.setLayout(layout)
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)
        self.tab_widget.addTab(scroll_area, "Rosters")
    
    def _add_season_series_tab(self):
        """Add season series head-to-head tab"""
        series_data = self.raw_data.get("seasonseries")
        if not series_data:
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🗓️ SEASON SERIES (Head-to-Head Record)"))
        
        if isinstance(series_data, list):
            for series_item in series_data:
                if isinstance(series_item, dict):
                    summary = series_item.get("summary", "No series data available")
                    layout.addWidget(QLabel(f"\nSeries Summary: {summary}"))
                    
                    # Show individual games if available
                    events = series_item.get("events", [])
                    if events:
                        layout.addWidget(QLabel(f"\nGames in Series ({len(events)} total):"))
                        
                        table = AccessibleTable()
                        table.setColumnCount(4)
                        table.setHorizontalHeaderLabels(["Date", "Matchup", "Score", "Result"])
                        
                        table.setRowCount(len(events))
                        for row, event in enumerate(events):
                            date = event.get("date", "")
                            name = event.get("name", "")
                            score = event.get("shortName", "")
                            status = event.get("status", {})
                            completed = status.get("type", {}).get("completed", False) if isinstance(status, dict) else False
                            result = "Completed" if completed else "Scheduled"
                            
                            table.setItem(row, 0, QTableWidgetItem(date))
                            table.setItem(row, 1, QTableWidgetItem(name))
                            table.setItem(row, 2, QTableWidgetItem(score))
                            table.setItem(row, 3, QTableWidgetItem(result))
                        
                        table.resizeColumnsToContents()
                        layout.addWidget(table)
        else:
            layout.addWidget(QLabel("No season series data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Season Series")
    
    def _add_win_probability_tab(self):
        """Add win probability tracking tab"""
        win_prob_data = self.raw_data.get("winprobability")
        if not win_prob_data or (isinstance(win_prob_data, list) and len(win_prob_data) == 0):
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("📊 WIN PROBABILITY TRACKING"))
        
        if isinstance(win_prob_data, list) and win_prob_data:
            layout.addWidget(QLabel(f"\nTotal probability data points: {len(win_prob_data)}"))
            
            # Show current/final probability
            latest = win_prob_data[-1] if win_prob_data else {}
            home_prob = latest.get("homeWinPercentage", 0)
            away_prob = 100 - home_prob
            
            layout.addWidget(QLabel(f"Final/Current Probabilities:"))
            layout.addWidget(QLabel(f"  Home Team: {home_prob:.1f}%"))
            layout.addWidget(QLabel(f"  Away Team: {away_prob:.1f}%"))
            
            # Show probability changes over time (sample)
            if len(win_prob_data) > 5:
                layout.addWidget(QLabel(f"\nSample probability changes:"))
                
                table = AccessibleTable()
                table.setColumnCount(3)
                table.setHorizontalHeaderLabels(["Play", "Home Win %", "Away Win %"])
                
                # Show first 10 entries as sample
                sample_data = win_prob_data[:10]
                table.setRowCount(len(sample_data))
                
                for row, prob_point in enumerate(sample_data):
                    play_id = str(prob_point.get("playId", f"Play {row+1}"))
                    home_pct = f"{prob_point.get('homeWinPercentage', 0):.1f}%"
                    away_pct = f"{100 - prob_point.get('homeWinPercentage', 0):.1f}%"
                    
                    table.setItem(row, 0, QTableWidgetItem(play_id))
                    table.setItem(row, 1, QTableWidgetItem(home_pct))
                    table.setItem(row, 2, QTableWidgetItem(away_pct))
                
                table.resizeColumnsToContents()
                layout.addWidget(table)
        else:
            layout.addWidget(QLabel("No win probability data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Win Probability")
    
    def _add_articles_tab(self):
        """Add game articles/recaps tab"""
        article_data = self.raw_data.get("article")
        if not article_data:
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("📰 GAME ARTICLES & RECAPS"))
        
        # Handle both single article and multiple articles
        articles_list = []
        if isinstance(article_data, dict):
            # Single article
            articles_list = [article_data]
        elif isinstance(article_data, list):
            # Multiple articles
            articles_list = article_data
        
        if articles_list:
            # Create list widget for articles (consistent with news display)
            articles_list_widget = QListWidget()
            articles_list_widget.setAccessibleName("Game Articles List")
            articles_list_widget.setAccessibleDescription("List of game articles and recaps")
            
            # Add each article as a list item (just the headline)
            for article in articles_list:
                if isinstance(article, dict):
                    headline = article.get("headline", "No headline")
                    article_type = article.get("type", "")
                    
                    # Create clean headline display
                    display_text = headline
                    if article_type and article_type != "Unknown":
                        display_text = f"[{article_type}] {headline}"
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.ItemDataRole.UserRole, article)
                    articles_list_widget.addItem(item)
            
            # Connect activation to show full article details
            def show_article_details(item):
                article = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(article, dict):
                    # Create a detailed view dialog
                    dialog = QDialog(self)
                    dialog.setWindowTitle("Article Details")
                    dialog.resize(600, 400)
                    
                    dialog_layout = QVBoxLayout()
                    
                    headline = article.get("headline", "No headline")
                    article_type = article.get("type", "Unknown")
                    description = article.get("description", "")
                    story = article.get("story", "")
                    
                    dialog_layout.addWidget(QLabel(f"Headline: {headline}"))
                    dialog_layout.addWidget(QLabel(f"Type: {article_type}"))
                    
                    if description:
                        dialog_layout.addWidget(QLabel("\nDescription:"))
                        desc_text = QTextEdit()
                        desc_text.setPlainText(description)
                        desc_text.setReadOnly(True)
                        desc_text.setMaximumHeight(100)
                        dialog_layout.addWidget(desc_text)
                    
                    if story:
                        dialog_layout.addWidget(QLabel("\nFull Article:"))
                        story_text = QTextEdit()
                        story_text.setPlainText(story)
                        story_text.setReadOnly(True)
                        dialog_layout.addWidget(story_text)
                    
                    close_btn = QPushButton("Close")
                    close_btn.clicked.connect(dialog.accept)
                    dialog_layout.addWidget(close_btn)
                    
                    dialog.setLayout(dialog_layout)
                    dialog.exec()
            
            articles_list_widget.itemActivated.connect(show_article_details)
            articles_list_widget.itemDoubleClicked.connect(show_article_details)
            
            layout.addWidget(QLabel("\nArticles (Enter or double-click to view details):"))
            layout.addWidget(articles_list_widget)
        else:
            layout.addWidget(QLabel("No article data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Articles")
    
    def _add_videos_tab(self):
        """Add game videos/highlights tab"""
        videos_data = self.raw_data.get("videos")
        if not videos_data or (isinstance(videos_data, list) and len(videos_data) == 0):
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🎥 GAME HIGHLIGHTS & VIDEOS"))
        
        if isinstance(videos_data, list) and videos_data:
            layout.addWidget(QLabel(f"\nAvailable videos: {len(videos_data)}"))
            
            table = AccessibleTable()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Title", "Description", "Duration", "Keywords"])
            
            table.setRowCount(len(videos_data))
            for row, video in enumerate(videos_data):
                title = video.get("headline", video.get("title", ""))
                description = video.get("description", "")
                duration = f"{video.get('duration', 0)} seconds"
                keywords = ", ".join(video.get("keywords", []))
                
                table.setItem(row, 0, QTableWidgetItem(title))
                table.setItem(row, 1, QTableWidgetItem(description))
                table.setItem(row, 2, QTableWidgetItem(duration))
                table.setItem(row, 3, QTableWidgetItem(keywords))
            
            table.resizeColumnsToContents()
            layout.addWidget(table)
        else:
            layout.addWidget(QLabel("No video data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Videos")
    
    def _add_betting_tab(self):
        """Add against the spread betting performance tab"""
        ats_data = self.raw_data.get("againstTheSpread")
        if not ats_data:
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🎰 AGAINST THE SPREAD PERFORMANCE"))
        
        if isinstance(ats_data, list):
            for team_data in ats_data:
                if isinstance(team_data, dict):
                    team_name = team_data.get("displayName", "Unknown Team")
                    record = team_data.get("record", "No record")
                    
                    layout.addWidget(QLabel(f"\n{team_name}:"))
                    layout.addWidget(QLabel(f"  ATS Record: {record}"))
        else:
            layout.addWidget(QLabel("No betting performance data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Betting ATS")
    
    def _add_picks_tab(self):
        """Add expert picks and predictions tab"""
        picks_data = self.raw_data.get("pickcenter")
        if not picks_data:
            return
            
        widget = QWidget()
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("🎯 EXPERT PICKS & PREDICTIONS"))
        
        if isinstance(picks_data, list) and picks_data:
            for pick_item in picks_data:
                if isinstance(pick_item, dict):
                    provider = pick_item.get("provider", {}).get("name", "Unknown")
                    details = pick_item.get("details", "")
                    spread = pick_item.get("spread", "")
                    over_under = pick_item.get("overUnder", "")
                    
                    layout.addWidget(QLabel(f"\nProvider: {provider}"))
                    if details:
                        layout.addWidget(QLabel(f"Pick Details: {details}"))
                    if spread:
                        layout.addWidget(QLabel(f"Spread: {spread}"))
                    if over_under:
                        layout.addWidget(QLabel(f"Over/Under: {over_under}"))
        else:
            layout.addWidget(QLabel("No expert picks data available"))
        
        widget.setLayout(layout)
        self.tab_widget.addTab(widget, "Expert Picks")
    
    def keyPressEvent(self, event):
        """Handle F6 for tab navigation and Escape to close"""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        elif event.key() == Qt.Key.Key_F6 and self.tab_widget:
            current_tab = self.tab_widget.currentIndex()
            next_tab = (current_tab + 1) % self.tab_widget.count()
            self.tab_widget.setCurrentIndex(next_tab)
            self.tab_widget.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

class NewsDialog(QDialog):
    """Dialog for displaying news headlines"""
    
    def __init__(self, news_headlines: List, league: str, parent=None):
        super().__init__(parent)
        self.news_headlines = news_headlines
        self.league = league
        self.setWindowTitle(f"News Headlines - {league}")
        self.resize(NEWS_DIALOG_WIDTH, NEWS_DIALOG_HEIGHT)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        if not self.news_headlines:
            layout.addWidget(QLabel("No news headlines available for this league."))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)
            self.setLayout(layout)
            return
        
        self.news_list = QListWidget()
        self.news_list.setAccessibleName("News Headlines List")
        self.news_list.setAccessibleDescription("List of news headlines - Enter or double-click opens in browser")
        
        # Display headlines as consistent list items
        for item in self.news_headlines:
            news = NewsData(item)
            # Get just the headline for consistent display
            headline = news.headline if hasattr(news, 'headline') else news.get_display_text()
            list_item = QListWidgetItem(headline)
            list_item.setData(Qt.ItemDataRole.UserRole, news)
            self.news_list.addItem(list_item)
        
        self.news_list.itemActivated.connect(self._open_news_story)
        self.news_list.itemDoubleClicked.connect(self._open_news_story)
        
        layout.addWidget(QLabel("Press Enter or double-click a headline to open in your browser:"))
        layout.addWidget(self.news_list)
        
        btn_row = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(lambda: self._open_selected_news_story())
        btn_row.addWidget(open_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        
        self.setLayout(layout)
        self.news_list.setFocus()
    
    def keyPressEvent(self, event):
        """Handle Escape key to close dialog"""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
    
    def _open_news_story(self, item):
        if isinstance(item, QListWidgetItem):
            news_data = item.data(Qt.ItemDataRole.UserRole)
        else:
            news_data = item.data(Qt.ItemDataRole.UserRole) if item else None  # fallback
        if isinstance(news_data, NewsData) and news_data.has_web_url():
            if news_data.web_url.startswith(("http://", "https://")):
                webbrowser.open(news_data.web_url)
            else:
                QMessageBox.warning(self, "Invalid URL", "The URL for this story is invalid.")
        else:
            QMessageBox.information(self, "No Link", "No web link available for this story.")
    
    def _open_selected_news_story(self):
        item = self.news_list.currentItem()
        if item:
            self._open_news_story(item)
        else:
            QMessageBox.information(self, "No Selection", "Select a story first.")


# Background loading classes for performance optimization

# Threads started by views that may be deleted before the thread finishes.
# A QThread garbage-collected while running aborts the whole process, so each
# one is held here until its finished signal.
_running_threads = set()


def _start_detached_thread(thread: QThread):
    _running_threads.add(thread)
    thread.finished.connect(lambda: _running_threads.discard(thread))
    thread.start()


class LiveScoresLoader(QThread):
    """Fetches everything Live Scores - All Sports shows, off the UI thread."""
    data_loaded = pyqtSignal(list, list, list)  # live games, today's games, golf
    error_occurred = pyqtSignal(str)

    def __init__(self, fetch):
        super().__init__()
        self.fetch = fetch

    def run(self):
        try:
            self.data_loaded.emit(*self.fetch())
        except Exception as e:
            self.error_occurred.emit(str(e))


class LeagueScoresLoader(QThread):
    """Fetches a league view's scoreboard and news, and the football calendar
    the first time a football league opens."""
    # generation, (season, season_type, week) or None, scores, news
    data_loaded = pyqtSignal(int, object, list, list)
    error_occurred = pyqtSignal(int, str)

    def __init__(self, generation, league, request, resolve_calendar=False,
                 requested_week=None, requested_season_type=None):
        super().__init__()
        self.generation = generation
        self.league = league
        self.request = dict(request)
        self.resolve_calendar = resolve_calendar
        self.requested_week = requested_week
        self.requested_season_type = requested_season_type

    def _resolve_calendar(self):
        """(season, season_type, week) to show, per ESPN's calendar.

        A week number alone does not identify a week (they restart at 1 in each
        season type), so the type travels with it. That pairing is what lets
        preseason show at all: ESPN's week.number is 1 during preseason, which
        read as the September opener.
        """
        from services.football_calendar import (
            get_current_season_week_and_type, SEASON_TYPE_REGULAR)
        week, season_type = self.requested_week, self.requested_season_type
        try:
            season, current_type, current_week = get_current_season_week_and_type(self.league)
        except Exception:
            return (datetime.now().year, season_type or SEASON_TYPE_REGULAR,
                    week if week is not None else 1)
        if season_type is None:
            season_type = current_type if week is None else SEASON_TYPE_REGULAR
        return season, season_type, (week if week is not None else current_week)

    def run(self):
        try:
            calendar = None
            if self.resolve_calendar:
                calendar = self._resolve_calendar()
                season, season_type, week = calendar
                self.request.update(week=week, season=season, seasontype=season_type)
            scores = ApiService.get_scores(self.league, **self.request) or []
            if self.request.get("week") is not None:
                scores = ApiService.freshen_live_games(self.league, scores)
            try:
                news = ApiService.get_news(self.league) or []
            except Exception:
                news = []
            self.data_loaded.emit(self.generation, calendar, scores, news)
        except Exception as e:
            self.error_occurred.emit(self.generation, str(e))


class GameDetailsLoader(QThread):
    """Fetches a game's summary and the details shown from it."""
    data_loaded = pyqtSignal(int, dict, dict)  # generation, raw summary, details
    error_occurred = pyqtSignal(int, str)

    def __init__(self, generation, league, game_id):
        super().__init__()
        self.generation = generation
        self.league = league
        self.game_id = game_id

    def run(self):
        try:
            raw = ApiService.get_game_details(self.league, self.game_id) or {}
            details = ApiService.extract_meaningful_game_info(raw) or {}
            self.data_loaded.emit(self.generation, raw, details)
        except Exception as e:
            self.error_occurred.emit(self.generation, str(e))


class CallLoader(QThread):
    """Runs one function off the UI thread and emits its result."""
    data_loaded = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.data_loaded.emit(self.fn())
        except Exception as e:
            self.error_occurred.emit(str(e))


class StatisticsLoader(QThread):
    """Loads a league's team or player statistics for StatisticsViewDialog."""
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, league: str, stat_type: str):
        super().__init__()
        self.league = league
        self.stat_type = stat_type

    def run(self):
        try:
            if self.stat_type == "player":
                data = ApiService.get_player_statistics(self.league)
            else:
                data = ApiService.get_team_statistics(self.league)
            self.data_loaded.emit(data or {})
        except Exception as e:
            self.error_occurred.emit(str(e))


class StandingsLoader(QThread):
    """Background thread for loading standings data"""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, league: str):
        super().__init__()
        self.league = league
    
    def run(self):
        try:
            standings_data = ApiService.get_standings(self.league)
            if standings_data:
                self.data_loaded.emit(standings_data)
            else:
                self.error_occurred.emit(f"No standings data available for {self.league}")
        except Exception as e:
            self.error_occurred.emit(f"Failed to load standings: {str(e)}")


class UpdateCheckLoader(QThread):
    """Background check of the GitHub release feed for a newer version."""
    # object rather than dict: None means "already up to date", which a dict
    # signal cannot carry.
    data_loaded = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            self.data_loaded.emit(updater.check_for_update())
        except Exception as e:
            self.error_occurred.emit(str(e))


class UpdateDownloadLoader(QThread):
    """Background download of the installer for a newer version."""
    data_loaded = pyqtSignal(object)          # installer path, or None if cancelled
    progress_changed = pyqtSignal(int, int)   # bytes downloaded, total bytes
    error_occurred = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            path = updater.download_installer(
                self.url,
                progress=lambda done, total: self.progress_changed.emit(done, total),
                should_cancel=lambda: self._cancelled,
            )
            self.data_loaded.emit(path)
        except Exception as e:
            self.error_occurred.emit(str(e))


class GameDetailsDialog(QDialog):
    """Dialog wrapper for GameDetailsView to show game details"""
    
    def __init__(self, game_id: str, league: str, parent=None, original_game_data=None):
        super().__init__(parent)
        self.game_id = game_id
        self.league = league
        self.original_game_data = original_game_data
        
        # Add config attribute that GameDetailsView expects
        self.config = {league: ["standings", "leaders", "boxscore", "injuries", "news"]}
        
        self.setWindowTitle(f"Game Details - {league}")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        # Create layout
        layout = QVBoxLayout()
        
        # Create game details view
        self.game_details_view = GameDetailsView(self, league, game_id, original_game_data)
        layout.addWidget(self.game_details_view)
        
        # Add close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def update_window_title(self, context_parts=None):
        """Update dialog window title with context information"""
        if context_parts:
            # Build title from context parts
            title = " - ".join(str(part) for part in context_parts)
            self.setWindowTitle(title)
        else:
            # Default title
            self.setWindowTitle(f"Game Details - {self.league}")
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class TeamHubDialog(QDialog):
    """Five-tab team hub: Info, Roster, Schedule, News, Transactions."""

    def __init__(self, team_data: Dict, league: str, parent=None):
        super().__init__(parent)
        self.team_data = team_data
        self.league = league
        self.team_name = team_data.get('team_name', 'Unknown Team')
        self.team_id = team_data.get('team_id', '')
        self._tabs_loaded: set = set()
        self._loaders = []  # keep loader references alive

        self.setWindowTitle(f"{self.team_name} - {league} - Sports Scores")
        self.setMinimumSize(900, 650)
        self.resize(1000, 750)

        self._setup_ui()
        self._on_tab_changed(0)  # load Info tab immediately

    # ------------------------------------------------------------------ setup

    def _setup_ui(self):
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()
        name_lbl = QLabel(self.team_name)
        font = QFont(); font.setPointSize(14); font.setBold(True)
        name_lbl.setFont(font)
        name_lbl.setAccessibleName(f"Team: {self.team_name}")
        header_layout.addWidget(name_lbl)

        wins = self.team_data.get('wins', '')
        losses = self.team_data.get('losses', '')
        ties = self.team_data.get('ties', 0)
        if wins and losses:
            if self.league == "NFL" and ties and int(ties) > 0:
                rec_text = f"({wins}-{losses}-{ties})"
            else:
                rec_text = f"({wins}-{losses})"
            rec_lbl = QLabel(rec_text)
            rec_lbl.setFont(font)
            header_layout.addWidget(rec_lbl)
        header_layout.addStretch()

        self.fav_btn = QPushButton()
        self._refresh_fav_button()
        self.fav_btn.clicked.connect(self._toggle_favorite)
        header_layout.addWidget(self.fav_btn)

        layout.addLayout(header_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Tab 0 — Info
        info_w = QWidget()
        info_layout = QVBoxLayout(info_w)
        self.info_list = QListWidget()
        self.info_list.setAccessibleName(f"{self.team_name} Team Info")
        self.info_list.setAccessibleDescription("Team details including record, venue, coach, and next game")
        info_layout.addWidget(self.info_list)
        self.tab_widget.addTab(info_w, "&Info")

        # Tab 1 — Roster
        roster_w = QWidget()
        roster_layout = QVBoxLayout(roster_w)
        self.roster_table = AccessibleTable(accessible_name=f"{self.team_name} Roster",
                                            accessible_description="Team roster. Alt+V to cycle view modes.")
        self.roster_table.setup_columns(["#", "Name", "Position", "Age", "Height", "Weight"])
        roster_layout.addWidget(self.roster_table)
        self.tab_widget.addTab(roster_w, "R&oster")

        # Tab 2 — Schedule
        sched_w = QWidget()
        sched_layout = QVBoxLayout(sched_w)
        season_row = QHBoxLayout()
        season_row.addWidget(QLabel("Season:"))
        self.season_combo = QComboBox()
        self.season_combo.setAccessibleName("Season Selection")
        self.season_combo.setAccessibleDescription("Select a season to view the team schedule")
        try:
            for val, display in ApiService.get_available_seasons(self.league):
                self.season_combo.addItem(display, val)
        except Exception:
            year = datetime.now().year
            for y in range(year, year - 3, -1):
                self.season_combo.addItem(f"{y} Season", y)
        self.season_combo.currentIndexChanged.connect(self._on_season_changed)
        season_row.addWidget(self.season_combo)
        season_row.addStretch()
        sched_layout.addLayout(season_row)
        self.schedule_list = QListWidget()
        self.schedule_list.setAccessibleName(f"{self.team_name} Schedule")
        self.schedule_list.itemActivated.connect(self._on_game_selected)
        sched_layout.addWidget(self.schedule_list)
        self.tab_widget.addTab(sched_w, "&Schedule")

        # Tab 3 — News
        news_w = QWidget()
        news_layout = QVBoxLayout(news_w)
        self.news_list = QListWidget()
        self.news_list.setAccessibleName(f"{self.team_name} News")
        self.news_list.setAccessibleDescription("Team news articles. Press Enter to open in browser.")
        self.news_list.itemActivated.connect(self._on_news_activated)
        news_layout.addWidget(self.news_list)
        open_btn = QPushButton("&Open Story in Browser")
        open_btn.clicked.connect(self._open_selected_news)
        news_layout.addWidget(open_btn)
        self.tab_widget.addTab(news_w, "&News")

        # Tab 4 — Transactions
        trans_w = QWidget()
        trans_layout = QVBoxLayout(trans_w)
        self.trans_list = QListWidget()
        self.trans_list.setAccessibleName(f"{self.team_name} Transactions")
        self.trans_list.setAccessibleDescription("Recent player transactions for this team")
        trans_layout.addWidget(self.trans_list)
        self.tab_widget.addTab(trans_w, "&Transactions")

        layout.addWidget(self.tab_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    # --------------------------------------------------------- lazy tab loading

    def _on_tab_changed(self, index):
        if index in self._tabs_loaded:
            return
        self._tabs_loaded.add(index)
        {0: self._load_info, 1: self._load_roster,
         2: self._load_schedule, 3: self._load_news,
         4: self._load_transactions}.get(index, lambda: None)()

    def _on_season_changed(self):
        self._tabs_loaded.discard(2)
        self._on_tab_changed(2)

    # --------------------------------------------------------------- info tab

    def _load_info(self):
        self.info_list.clear()
        self.info_list.addItem("Loading team info...")
        loader = TeamInfoLoader(self.team_id, self.league)
        loader.data_loaded.connect(self._on_info_loaded)
        loader.error_occurred.connect(lambda e: self._show_list_error(self.info_list, e))
        self._loaders.append(loader)
        loader.start()

    def _on_info_loaded(self, info):
        self.info_list.clear()
        if not info:
            self.info_list.addItem("No team info available.")
            return
        def add(label, value):
            if value:
                self.info_list.addItem(f"{label}: {value}")
        add("Team", info.get('name'))
        add("Division", info.get('division'))
        add("Conference", info.get('conference'))
        add("Record (Overall)", info.get('record_overall'))
        add("Record (Home)", info.get('record_home'))
        add("Record (Road)", info.get('record_road'))
        add("Head Coach", info.get('head_coach'))
        add("Venue", info.get('venue_name'))
        add("Location", info.get('venue_location'))
        opp = info.get('next_game_opponent')
        ha = info.get('next_game_home_away')
        date = info.get('next_game_date')
        if opp and date:
            add("Next Game", f"{ha} {opp}  —  {date}")

    # -------------------------------------------------------------- roster tab

    def _load_roster(self):
        self.roster_table.populate_data([["Loading roster...", "", "", "", "", ""]])
        loader = TeamRosterLoader(self.team_id, self.league)
        loader.data_loaded.connect(self._on_roster_loaded)
        loader.error_occurred.connect(
            lambda e: self.roster_table.populate_data([[f"Error: {e}", "", "", "", "", ""]]))
        self._loaders.append(loader)
        loader.start()

    def _on_roster_loaded(self, players):
        if not players:
            self.roster_table.populate_data([["No roster data available.", "", "", "", "", ""]])
            return
        rows = [[p['jersey'], p['name'], p['position'], p['age'], p['height'], p['weight']]
                for p in players]
        self.roster_table.populate_data(rows, set_focus=True)

    # ------------------------------------------------------------ schedule tab

    def _load_schedule(self):
        self.schedule_list.clear()
        loading_item = QListWidgetItem("Loading schedule...")
        self.schedule_list.addItem(loading_item)
        season = self.season_combo.currentData() if self.season_combo.count() else None
        # Changing season while a schedule loads starts another load. Only the
        # newest may touch the list: an older one finishing last would show the
        # season just left, and its progress text would land on a deleted row.
        self._schedule_generation = getattr(self, '_schedule_generation', 0) + 1
        gen = self._schedule_generation
        current = lambda: gen == self._schedule_generation
        loader = TeamScheduleLoader(self.team_id, self.team_name, self.league, season)
        loader.data_loaded.connect(
            lambda data, name, league: current() and self._on_schedule_loaded(data, name, league))
        loader.error_occurred.connect(
            lambda e: current() and self._show_list_error(self.schedule_list, e))
        loader.loading_progress.connect(lambda msg: current() and loading_item.setText(msg))
        self._loaders.append(loader)
        _start_detached_thread(loader)

    def _on_schedule_loaded(self, schedule_data: List[Dict], team_name: str, league: str):
        self.schedule_list.clear()
        if not schedule_data:
            self.schedule_list.addItem("No games found in schedule.")
            return
        today_idx = -1
        for i, game in enumerate(schedule_data):
            date_str   = game.get('date_display', '')
            opponent   = game.get('opponent', 'Unknown')
            home_away  = game.get('home_away', '')
            time_str   = game.get('time', '')
            status     = game.get('status', '')
            venue      = game.get('venue', '')
            if status in ('Final', 'Cancelled', 'Postponed'):
                hs = game.get('home_score', '')
                as_ = game.get('away_score', '')
                if hs and as_:
                    hi, ai = int(hs), int(as_)
                    if hi == ai:
                        txt = f"{date_str}: {home_away} {opponent} - T {hs}-{as_}"
                    elif home_away == 'vs':
                        txt = f"{date_str}: {home_away} {opponent} - {'W' if hi>ai else 'L'} {hs}-{as_}"
                    else:
                        txt = f"{date_str}: {home_away} {opponent} - {'W' if ai>hi else 'L'} {as_}-{hs}"
                else:
                    txt = f"{date_str}: {home_away} {opponent} - {status}"
            else:
                txt = f"{date_str}: {home_away} {opponent} - {time_str}"
                if venue and venue != "TBD":
                    txt += f" ({venue})"
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, game)
            if game.get('is_today', False):
                f = QFont(); f.setBold(True)
                item.setFont(f)
                item.setBackground(QColor(255, 255, 200))
                today_idx = i
            self.schedule_list.addItem(item)
        if today_idx >= 0:
            self.schedule_list.setCurrentRow(today_idx)
        else:
            future = next((i for i, g in enumerate(schedule_data)
                           if g.get('status', '') not in ('Final', 'Cancelled', 'Postponed')), 0)
            self.schedule_list.setCurrentRow(future)
        self.schedule_list.setFocus()

    def _on_game_selected(self, item):
        game_data = item.data(Qt.ItemDataRole.UserRole)
        if not game_data:
            return
        game_id = game_data.get('game_id')
        if game_id:
            try:
                GameDetailsDialog(game_id, self.league, self, game_data).exec()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open game details: {e}")

    # --------------------------------------------------------------- news tab

    def _load_news(self):
        self.news_list.clear()
        self.news_list.addItem("Loading news...")
        loader = TeamNewsLoader(self.team_id, self.league)
        loader.data_loaded.connect(self._on_news_loaded)
        loader.error_occurred.connect(lambda e: self._show_list_error(self.news_list, e))
        self._loaders.append(loader)
        loader.start()

    def _on_news_loaded(self, articles):
        self.news_list.clear()
        if not articles:
            self.news_list.addItem("No news available for this team.")
            return
        for a in articles:
            headline = a.get('headline', '')
            desc = a.get('description', '')
            text = f"{headline}\n{desc}" if desc else headline
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, a)
            self.news_list.addItem(item)

    def _on_news_activated(self, item):
        article = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(article, dict):
            url = article.get('web_url', '')
            if url and url.startswith(('http://', 'https://')):
                webbrowser.open(url)

    def _open_selected_news(self):
        item = self.news_list.currentItem()
        if item:
            self._on_news_activated(item)
        else:
            QMessageBox.information(self, "No Selection", "Select a news story first.")

    # --------------------------------------------------------- transactions tab

    def _load_transactions(self):
        self.trans_list.clear()
        self.trans_list.addItem("Loading transactions...")
        loader = TeamTransactionsLoader(self.team_id, self.league)
        loader.data_loaded.connect(self._on_transactions_loaded)
        loader.error_occurred.connect(lambda e: self._show_list_error(self.trans_list, e))
        self._loaders.append(loader)
        loader.start()

    def _on_transactions_loaded(self, transactions):
        self.trans_list.clear()
        if not transactions:
            self.trans_list.addItem("No transactions available for this team.")
            return
        for t in transactions:
            parts = [p for p in [t.get('date'), t.get('type'),
                                  t.get('player') or t.get('description'),
                                  f"({t['position']})" if t.get('position') else ''] if p]
            self.trans_list.addItem(" — ".join(parts))

    # ---------------------------------------------------------------- helpers

    def _show_list_error(self, list_widget, error_msg):
        list_widget.clear()
        list_widget.addItem(f"Error loading data: {error_msg}")

    def _refresh_fav_button(self):
        if settings.is_favorite(self.team_id, self.league):
            self.fav_btn.setText("★ Favorited")
            self.fav_btn.setAccessibleName("Remove from Favorites")
            self.fav_btn.setAccessibleDescription(
                f"Remove {self.team_name} from your favorite teams")
        else:
            self.fav_btn.setText("☆ Add to Favorites")
            self.fav_btn.setAccessibleName("Add to Favorites")
            self.fav_btn.setAccessibleDescription(
                f"Add {self.team_name} to your favorite teams")

    def _toggle_favorite(self):
        added = settings.toggle_favorite(
            self.team_id, self.team_name, self.league,
            self.team_data.get('abbreviation', ''))
        self._refresh_fav_button()
        msg = f"{self.team_name} added to favorites." if added \
              else f"{self.team_name} removed from favorites."
        QMessageBox.information(self, "Favorites", msg)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


# Backward-compatibility alias — existing call sites use TeamScheduleDialog
TeamScheduleDialog = TeamHubDialog


class TeamScheduleLoader(QThread):
    """Background thread for loading team schedule data"""
    data_loaded = pyqtSignal(list, str, str)  # schedule_data, team_name, league
    error_occurred = pyqtSignal(str)
    loading_progress = pyqtSignal(str)  # progress message

    def __init__(self, team_id: str, team_name: str, league: str, season=None):
        super().__init__()
        self.team_id = team_id
        self.team_name = team_name
        self.league = league
        self.season = season

    def run(self):
        try:
            self.loading_progress.emit("Loading schedule...")
            schedule_data = ApiService.get_team_schedule(self.league, self.team_id, season=self.season)
            self.loading_progress.emit(f"Loaded {len(schedule_data)} games")
            self.data_loaded.emit(schedule_data, self.team_name, self.league)
        except Exception as e:
            self.error_occurred.emit(f"Failed to load schedule: {str(e)}")


class FavoriteCardLoader(QThread):
    """Fetches today's game, next game, and news for one favorite team."""
    card_ready = pyqtSignal(str, str, str, list)  # team_id, league, summary, news_headlines

    def __init__(self, team_id: str, team_name: str, league: str, abbreviation: str = ''):
        super().__init__()
        self.team_id = team_id
        self.team_name = team_name
        self.league = league
        self.abbreviation = abbreviation

    def run(self):
        import espn_api
        summary = ''
        try:
            today = datetime.now().date()
            scores = espn_api.get_scores(self.league, today)
            for game in scores:
                teams = game.get('teams', [])
                abbrevs = {t.get('abbreviation', '') for t in teams}
                names = {t.get('name', '') for t in teams}
                if (self.abbreviation and self.abbreviation in abbrevs) or self.team_name in names:
                    status = game.get('status', '')
                    t0, t1 = (teams + [{}, {}])[:2]
                    s0, s1 = t0.get('score', ''), t1.get('score', '')
                    n0, n1 = t0.get('name', ''), t1.get('name', '')
                    if s0 and s1:
                        summary = f"{n0} {s0} — {n1} {s1}  ({status})"
                    else:
                        summary = f"vs {n1 if n0 == self.team_name else n0}  ({status})"
                    break
        except Exception:
            pass

        if not summary:
            try:
                info = espn_api.get_team_info(self.league, self.team_id)
                rec = info.get('record_overall', '')
                opp = info.get('next_game_opponent', '')
                ha = info.get('next_game_home_away', '')
                date = info.get('next_game_date', '')
                parts = []
                if rec:
                    parts.append(f"({rec})")
                if opp and date:
                    parts.append(f"Next: {ha} {opp} — {date}")
                summary = '  '.join(parts)
            except Exception:
                pass

        news_lines = []
        try:
            articles = espn_api.get_team_news(self.league, self.team_id, limit=2)
            news_lines = [a.get('headline', '') for a in articles[:2] if a.get('headline')]
        except Exception:
            pass

        self.card_ready.emit(self.team_id, self.league, summary, news_lines)


class LeagueTransactionsLoader(QThread):
    data_loaded = pyqtSignal(list, bool)  # transactions, has_more
    error_occurred = pyqtSignal(str)

    def __init__(self, league: str, team_id=None, page: int = 1):
        super().__init__()
        self.league = league
        self.team_id = team_id
        self.page = page

    def run(self):
        try:
            transactions, has_more = ApiService.get_transactions(
                self.league, self.team_id, page=self.page)
            self.data_loaded.emit(transactions, has_more)
        except Exception as e:
            self.error_occurred.emit(str(e))


class NFLDraftMetaLoader(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, year: int):
        super().__init__()
        self.year = year

    def run(self):
        try:
            meta = ApiService.get_draft(self.year)
            self.data_loaded.emit(meta or {})
        except Exception as e:
            self.error_occurred.emit(str(e))


class NFLDraftRoundLoader(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, year: int, round_num: int):
        super().__init__()
        self.year = year
        self.round_num = round_num

    def run(self):
        try:
            picks = ApiService.get_draft_round(self.year, self.round_num)
            self.data_loaded.emit(picks)
        except Exception as e:
            self.error_occurred.emit(str(e))


class FantasyCheatsheetLoader(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, season=None):
        super().__init__()
        self.season = season

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_fantasy_cheatsheet(self.season) or {})
        except Exception as e:
            self.error_occurred.emit(str(e))


class GolfLeaderboardLoader(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, tour: str):
        super().__init__()
        self.tour = tour

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_golf_leaderboard(self.tour) or {})
        except Exception as e:
            self.error_occurred.emit(str(e))


class GolfScheduleLoader(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, tour: str):
        super().__init__()
        self.tour = tour

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_golf_schedule(self.tour))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TeamInfoLoader(QThread):
    data_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, team_id: str, league: str):
        super().__init__()
        self.team_id = team_id
        self.league = league

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_team_info(self.league, self.team_id))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TeamRosterLoader(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, team_id: str, league: str):
        super().__init__()
        self.team_id = team_id
        self.league = league

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_team_roster(self.league, self.team_id))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TeamNewsLoader(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, team_id: str, league: str):
        super().__init__()
        self.team_id = team_id
        self.league = league

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_team_news(self.league, self.team_id))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TeamTransactionsLoader(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, team_id: str, league: str):
        super().__init__()
        self.team_id = team_id
        self.league = league

    def run(self):
        try:
            self.data_loaded.emit(ApiService.get_team_transactions(self.league, self.team_id))
        except Exception as e:
            self.error_occurred.emit(str(e))


# Caching system for improved performance
class DataCache:
    """Simple cache for standings and team data"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.standings_cache = {}
            cls._instance.schedule_cache = {}
            cls._instance.cache_timeout = 300  # 5 minutes
        return cls._instance
    
    def get_standings(self, league: str):
        """Get cached standings data"""
        key = f"standings_{league}"
        if key in self.standings_cache:
            data, timestamp = self.standings_cache[key]
            if time.time() - timestamp < self.cache_timeout:
                return data
        return None
    
    def set_standings(self, league: str, data):
        """Cache standings data"""
        key = f"standings_{league}"
        self.standings_cache[key] = (data, time.time())

    def get_mlb_wildcard(self):
        """Get cached MLB wild card standings, or None when stale/absent."""
        entry = self.standings_cache.get("mlb_wildcard")
        if entry:
            data, timestamp = entry
            if time.time() - timestamp < self.cache_timeout:
                return data
        return None

    def set_mlb_wildcard(self, data):
        """Cache MLB wild card standings."""
        self.standings_cache["mlb_wildcard"] = (data, time.time())
    
    def get_schedule(self, team_id: str):
        """Get cached schedule data"""
        key = f"schedule_{team_id}"
        if key in self.schedule_cache:
            data, timestamp = self.schedule_cache[key]
            if time.time() - timestamp < self.cache_timeout:
                return data
        return None
    
    def set_schedule(self, team_id: str, data):
        """Cache schedule data"""
        key = f"schedule_{team_id}"
        self.schedule_cache[key] = (data, time.time())


class StandingsDialog(WildCardTabsMixin, QDialog):
    """Dialog for displaying team standings (invoked from league view)"""
    
    def __init__(self, standings_data: List, league: str, parent=None):
        super().__init__(parent)
        self.standings_data = StandingsData(standings_data)
        self.league = league
        self.setWindowTitle(f"{league} Standings")
        self.resize(STANDINGS_DIALOG_WIDTH, STANDINGS_DIALOG_HEIGHT)
        self.tab_widget: QTabWidget | None = None
        self.single_table: StandingsTable | None = None
        self.expanded_view = False
        self.division_tables: List[StandingsTable] = []
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Always use expanded view (no user toggle to prevent issues)
        self.expanded_view = True
        
        if not self.standings_data.teams:
            layout.addWidget(QLabel(f"No standings data available for {self.league}."))
        else:
            has_divisions = len(self.standings_data.divisions) > 1 or any(
                d != "League" for d in self.standings_data.divisions
            )
            if has_divisions and self.league in ["MLB", "NFL", "NBA", "NHL", "NCAAF", "NCAAM", "NCAAWB", "WNBA"]:
                self._build_division_tabs(layout)
            else:
                self.single_table = self._create_single_standings_table(self.standings_data.teams)
                layout.addWidget(QLabel(f"Current {self.league} Standings:"))
                layout.addWidget(self.single_table)
                self.single_table.setFocus()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)
    
    def _on_view_changed(self, index):
        """Handle combo box selection change"""
        expanded = index == 1  # 1 = expanded view
        self._toggle_view(expanded)
    
    def _toggle_view(self, expanded: bool):
        """Toggle between basic and expanded standings view"""
        if self.expanded_view == expanded:
            return
            
        self.expanded_view = expanded
        
        # Update tables
        if self.single_table:
            self.single_table.set_expanded_view(expanded)
            self.single_table.populate_standings(self.standings_data.teams, set_focus=True)
        
        # Update division tables through tab widget
        if self.tab_widget:
            current_tab_index = self.tab_widget.currentIndex()
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if hasattr(widget, 'table'):
                    table = widget.table
                    table.set_expanded_view(expanded)
                    # Repopulate with the table's division data
                    division_name = table.division_name
                    if division_name in self.standings_data.divisions:
                        # Set focus on the currently visible tab's table
                        should_focus = (i == current_tab_index)
                        table.populate_standings(self.standings_data.divisions[division_name], set_focus=should_focus)
            
            # Ensure focus is properly restored after toggle with a slight delay
            from PyQt6.QtCore import QTimer
            def restore_focus():
                if current_tab_index < self.tab_widget.count():
                    current_widget = self.tab_widget.widget(current_tab_index)
                    if hasattr(current_widget, 'table'):
                        current_widget.table.setFocus()
                        current_widget.table.setCurrentCell(0, 0)
            
            QTimer.singleShot(50, restore_focus)
    
    def _build_division_tabs(self, layout: QVBoxLayout):
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName(
            "Standings" if self.league == "MLB" else "Division Standings")
        self.tab_widget.setAccessibleDescription(
            "Team standings by division, plus AL and NL wild card, use arrow keys to move between tabs"
            if self.league == "MLB"
            else "Team standings by division, use arrow keys to navigate between divisions")
        
        if self.league == "MLB":
            division_order = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West", "League"]
        elif self.league == "NFL":
            division_order = ["AFC East", "AFC North", "AFC South", "AFC West", 
                            "NFC East", "NFC North", "NFC South", "NFC West", "League"]
        else:
            division_order = ["League"]
            
        ordered: List[tuple[str, List[Dict]]] = []
        for name in division_order:
            if name in self.standings_data.divisions:
                ordered.append((name, self.standings_data.divisions[name]))
        for name, teams in self.standings_data.divisions.items():
            if name not in division_order:
                ordered.append((name, teams))
        for name, teams in ordered:
            if teams:
                tab = self._create_division_table(name, teams)
                self.tab_widget.addTab(tab, name)

        self._build_wildcard_tabs()

        layout.addWidget(self.tab_widget)
        if self.tab_widget.count():
            first = self.tab_widget.widget(0)
            if hasattr(first, "table"):
                first.table.setFocus()  # type: ignore[attr-defined]
    
    def _create_division_table(self, division_name: str, teams: List[Dict]) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        table = StandingsTable(parent=self, division_name=division_name, league=self.league, expanded=self.expanded_view)
        table.populate_standings(teams, set_focus=True)
        layout.addWidget(table)
        widget.setLayout(layout)
        widget.table = table  # type: ignore[attr-defined]
        return widget
    
    def _create_single_standings_table(self, teams: List[Dict]) -> StandingsTable:
        table = StandingsTable(parent=self, league=self.league, expanded=self.expanded_view)
        table.populate_standings(teams, set_focus=True)
        return table
    
    def _configure_table(self, table: QTableWidget):
        """Configure table appearance and behavior"""
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)  # Allow cell selection
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Enable keyboard navigation
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setTabKeyNavigation(True)
        
        # Enable accessibility features
        table.setAccessibleName("Standings Table")
        table.setAccessibleDescription("Team standings with arrow key navigation. Use arrow keys to navigate cells, Tab to enter/exit table.")
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if table.columnCount() > 1:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Team name stretches

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if self.tab_widget:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_Tab:
                    i = (self.tab_widget.currentIndex() + 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()  # type: ignore[attr-defined]
                    event.accept(); return
                if event.key() == Qt.Key.Key_Backtab:
                    i = (self.tab_widget.currentIndex() - 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()  # type: ignore[attr-defined]
                    event.accept(); return
        super().keyPressEvent(event)


class PollsTable(AccessibleTable):
    """Specialized table for displaying poll rankings"""
    
    def __init__(self, parent=None, poll_name: str = "Poll", is_hockey: bool = False):
        super().__init__(
            parent=parent,
            accessible_name=f"{poll_name} Rankings",
            accessible_description=f"{poll_name} rankings table showing team positions and records"
        )
        self.poll_name = poll_name
        self.is_hockey = is_hockey
        
        # Setup columns
        if is_hockey:
            headers = ["Rank", "Team", "Record (W-L-T)", "Points", "Previous"]
        else:
            headers = ["Rank", "Team", "Record", "Points", "Previous"]
        
        self.setup_columns(headers, stretch_column=1)  # Team name stretches
    
    def populate_poll(self, ranks: List[Dict], set_focus: bool = True):
        """
        Populate table with poll ranking data.
        
        Args:
            ranks: List of rank dictionaries from poll data
            set_focus: Whether to set focus to first cell after populating
        """
        if not ranks:
            self.table_widget.setRowCount(0)
            return
        
        rows = []
        for rank_data in ranks:
            current_rank = rank_data.get('current', 0)
            previous_rank = rank_data.get('previous', 0)
            points = rank_data.get('points', 0)
            record = rank_data.get('recordSummary', 'N/A')
            
            team_info = rank_data.get('team', {})
            # Construct team name from location and name/nickname
            location = team_info.get('location', '')
            name = team_info.get('name', team_info.get('nickname', ''))
            if location and name:
                team_name = f"{location} {name}"
            else:
                team_name = location or name or team_info.get('displayName', 'Unknown')
            
            # Points display
            points_str = f"{points:.0f}" if points > 0 else ""
            
            # Previous rank with movement indicator
            if previous_rank == 0:
                prev_str = "NR"  # Not Ranked
            elif previous_rank > current_rank:
                prev_str = f"{previous_rank} ↑"
            elif previous_rank < current_rank:
                prev_str = f"{previous_rank} ↓"
            else:
                prev_str = f"{previous_rank} —"
            
            row = [str(current_rank), team_name, record, points_str, prev_str]
            rows.append(row)
        
        self.populate_data(rows, set_focus)


class PollsDialog(QDialog):
    """Dialog for displaying poll/ranking data with multi-tab view"""
    
    def __init__(self, polls_data: Dict, league: str, parent=None):
        super().__init__(parent)
        self.polls_data = polls_data
        self.league = league
        self.setWindowTitle(f"{league} Polls & Rankings")
        self.resize(STANDINGS_DIALOG_WIDTH, STANDINGS_DIALOG_HEIGHT)
        self.tab_widget: QTabWidget | None = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        polls = self.polls_data.get('polls', [])
        
        if not polls:
            layout.addWidget(QLabel(f"No poll data available for {self.league}."))
        elif len(polls) == 1:
            # Single poll - just show the table
            table = self._create_poll_table(polls[0])
            layout.addWidget(QLabel(f"{polls[0].get('name', 'Rankings')}:"))
            layout.addWidget(table)
            table.setFocus()
        else:
            # Multiple polls - use tabs
            self._build_poll_tabs(layout, polls)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)
    
    def _build_poll_tabs(self, layout: QVBoxLayout, polls: List[Dict]):
        """Build tabbed interface for multiple polls"""
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Poll Rankings")
        self.tab_widget.setAccessibleDescription("Rankings from different polls. Use arrow keys to navigate between polls.")
        
        for poll in polls:
            poll_name = poll.get('shortName', poll.get('name', 'Poll'))
            table = self._create_poll_table(poll)
            
            # Wrap table in a widget
            tab_widget = QWidget()
            tab_layout = QVBoxLayout()
            tab_layout.addWidget(table)
            tab_widget.setLayout(tab_layout)
            tab_widget.table = table  # Store reference for focus management
            
            self.tab_widget.addTab(tab_widget, poll_name)
        
        layout.addWidget(self.tab_widget)
        
        # Set focus on first table
        if self.tab_widget.count() > 0:
            first_widget = self.tab_widget.widget(0)
            if hasattr(first_widget, 'table'):
                first_widget.table.setFocus()
    
    def _create_poll_table(self, poll: Dict) -> PollsTable:
        """Create an accessible table for a single poll"""
        # Determine if this is hockey (has ties in record)
        is_hockey = self.league in ["NCAAH", "NCAAWH"]
        
        poll_name = poll.get('shortName', poll.get('name', 'Poll'))
        table = PollsTable(parent=self, poll_name=poll_name, is_hockey=is_hockey)
        
        # Get rankings and populate
        ranks = poll.get('ranks', [])
        table.populate_poll(ranks, set_focus=True)
        
        return table
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        
        # Tab navigation between polls
        if self.tab_widget:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_Tab:
                    # Next tab
                    i = (self.tab_widget.currentIndex() + 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()
                    event.accept()
                    return
                elif event.key() == Qt.Key.Key_Backtab:
                    # Previous tab
                    i = (self.tab_widget.currentIndex() - 1) % self.tab_widget.count()
                    self.tab_widget.setCurrentIndex(i)
                    w = self.tab_widget.widget(i)
                    if hasattr(w, "table"):
                        w.table.setFocus()
                    event.accept()
                    return
        
        super().keyPressEvent(event)


class TransactionsDialog(QDialog):
    """League-wide transactions browser with team filter and pagination."""

    def __init__(self, league: str, parent=None):
        super().__init__(parent)
        self.league = league
        self.current_page = 1
        self.current_team_id = None
        self._loaders = []

        self.setWindowTitle(f"Transactions — {league} — Sports Scores")
        self.setMinimumSize(700, 500)
        self.resize(850, 620)

        self._setup_ui()
        self._load_teams()
        self._load_transactions(reset=True)

    def _setup_ui(self):
        layout = QVBoxLayout()

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter by team:"))
        self.team_combo = QComboBox()
        self.team_combo.setAccessibleName("Team Filter")
        self.team_combo.setAccessibleDescription(
            "Select a team to filter transactions, or All Teams for league-wide results")
        self.team_combo.addItem("All Teams", None)
        self.team_combo.currentIndexChanged.connect(self._on_team_changed)
        filter_row.addWidget(self.team_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.trans_list = QListWidget()
        self.trans_list.setAccessibleName(f"{self.league} Transactions")
        self.trans_list.setAccessibleDescription(
            "Transaction list. Each item shows date, type, player name, and position.")
        layout.addWidget(self.trans_list)

        btn_row = QHBoxLayout()
        self.load_more_btn = QPushButton("Load &More")
        self.load_more_btn.setEnabled(False)
        self.load_more_btn.clicked.connect(self._load_more)
        btn_row.addWidget(self.load_more_btn)
        btn_row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _load_teams(self):
        loader = StandingsLoader(self.league)
        loader.data_loaded.connect(self._on_teams_loaded)
        loader.error_occurred.connect(lambda _: None)
        self._loaders.append(loader)
        loader.start()

    def _on_teams_loaded(self, standings_data):
        teams = sorted(
            {(t.get('team_name', ''), t.get('team_id', ''))
             for t in standings_data if t.get('team_name') and t.get('team_id')},
            key=lambda x: x[0],
        )
        self.team_combo.blockSignals(True)
        for name, tid in teams:
            self.team_combo.addItem(name, tid)
        self.team_combo.blockSignals(False)

    def _on_team_changed(self, _index):
        self.current_team_id = self.team_combo.currentData()
        self._load_transactions(reset=True)

    def _load_transactions(self, reset=False):
        if reset:
            self.current_page = 1
            self.trans_list.clear()
            self.load_more_btn.setEnabled(False)
        loading_item = QListWidgetItem("Loading transactions...")
        self.trans_list.addItem(loading_item)
        loader = LeagueTransactionsLoader(self.league, self.current_team_id, self.current_page)
        loader.data_loaded.connect(lambda data, more: self._on_loaded(data, more, loading_item))
        loader.error_occurred.connect(lambda e: self._on_error(e, loading_item))
        self._loaders.append(loader)
        loader.start()

    def _load_more(self):
        self.current_page += 1
        self._load_transactions(reset=False)

    def _on_loaded(self, transactions, has_more, loading_item):
        row = self.trans_list.row(loading_item)
        if row >= 0:
            self.trans_list.takeItem(row)
        if not transactions and self.trans_list.count() == 0:
            team_label = self.team_combo.currentText()
            self.trans_list.addItem(f"No transactions available for {team_label}.")
            return
        for t in transactions:
            parts = [p for p in [
                t.get('date'),
                t.get('team'),
                t.get('description') or t.get('player'),
            ] if p]
            self.trans_list.addItem(" — ".join(parts))
        self.load_more_btn.setEnabled(has_more)
        if self.current_page == 1 and self.trans_list.count() > 0:
            self.trans_list.setCurrentRow(0)
            self.trans_list.setFocus()

    def _on_error(self, _error, loading_item):
        row = self.trans_list.row(loading_item)
        if row >= 0:
            self.trans_list.takeItem(row)
        if self.trans_list.count() == 0:
            self.trans_list.addItem(f"No transactions available for {self.league}.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class NFLDraftDialog(QDialog):
    """NFL Draft viewer: year selector, per-round pick list with player/position/college/trade info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NFL Draft — Sports Scores")
        self.setMinimumSize(750, 550)
        self.resize(950, 680)
        self._loaders = []
        self._tabs_loaded: set = set()
        self._current_year: int = datetime.now().year
        self._setup_ui()
        self._load_year(self._current_year)

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QHBoxLayout()
        header.addWidget(QLabel("Year:"))
        self.year_combo = QComboBox()
        self.year_combo.setAccessibleName("Draft Year")
        current_year = datetime.now().year
        for y in range(current_year, 2000, -1):
            self.year_combo.addItem(str(y), y)
        self.year_combo.currentIndexChanged.connect(self._on_year_changed)
        header.addWidget(self.year_combo)
        self.status_label = QLabel("")
        self.status_label.setAccessibleName("Draft status")
        header.addWidget(self.status_label)
        header.addStretch()
        layout.addLayout(header)

        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Draft rounds")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _on_year_changed(self, _idx):
        year = self.year_combo.currentData()
        if year and year != self._current_year:
            self._load_year(year)

    def _load_year(self, year: int):
        self._current_year = year
        self._tabs_loaded.clear()
        self.tab_widget.blockSignals(True)
        self.tab_widget.clear()
        self.tab_widget.blockSignals(False)
        self.status_label.setText("Loading…")

        loader = NFLDraftMetaLoader(year)
        loader.data_loaded.connect(self._on_meta_loaded)
        loader.error_occurred.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._loaders.append(loader)
        loader.start()

    def _on_meta_loaded(self, meta: dict):
        if not meta:
            self.status_label.setText("Draft data not available for this year.")
            return

        status_map = {'pre': 'Draft not yet started', 'in': 'Draft in progress', 'post': 'Draft complete'}
        self.status_label.setText(status_map.get(meta.get('status', 'post'), ''))

        self.tab_widget.blockSignals(True)
        for rd in meta.get('rounds', []):
            lw = QListWidget()
            lw.setAccessibleName(f"Round {rd['number']} picks")
            lw.setAccessibleDescription(
                f"Draft picks for round {rd['number']}. Each item shows pick number, team, player, position, and college.")
            lw.addItem(f"Loading Round {rd['number']}…")
            lw.setProperty('round_num', rd['number'])
            self.tab_widget.addTab(lw, rd.get('short_name', str(rd['number'])))
        self.tab_widget.blockSignals(False)

        if self.tab_widget.count() > 0:
            self.tab_widget.setCurrentIndex(0)
            self._load_round(0)

    def _on_tab_changed(self, index: int):
        if index not in self._tabs_loaded:
            self._load_round(index)

    def _load_round(self, tab_index: int):
        if tab_index in self._tabs_loaded:
            return
        widget = self.tab_widget.widget(tab_index)
        if not widget:
            return
        round_num = widget.property('round_num')
        if not round_num:
            return

        loader = NFLDraftRoundLoader(self._current_year, round_num)
        loader.data_loaded.connect(lambda picks, idx=tab_index: self._on_round_loaded(picks, idx))
        loader.error_occurred.connect(lambda e, idx=tab_index: self._on_round_error(e, idx))
        self._loaders.append(loader)
        loader.start()

    def _on_round_loaded(self, picks: list, tab_index: int):
        self._tabs_loaded.add(tab_index)
        widget = self.tab_widget.widget(tab_index)
        if not widget:
            return
        widget.clear()
        if not picks:
            widget.addItem("No pick data available for this round.")
            return

        for pick in picks:
            overall = pick.get('overall') or pick.get('pick', '?')
            team = pick.get('team_abbrev', '')
            player = pick.get('player_name', '')
            position = pick.get('position', '')
            college = pick.get('college', '')
            trade_note = pick.get('trade_note', '')
            status_name = pick.get('status_name', '')

            if status_name and status_name != 'SELECTION_MADE':
                parts = [f"#{overall}", team or "TBD", "Selection pending"]
            else:
                parts = [p for p in [f"#{overall}", team, player, position, college] if p]

            line = " — ".join(parts)
            if trade_note:
                line += f" (via trade {trade_note})"

            widget.addItem(line)

        if tab_index == self.tab_widget.currentIndex() and widget.count() > 0:
            widget.setCurrentRow(0)
            widget.setFocus()

    def _on_round_error(self, error: str, tab_index: int):
        self._tabs_loaded.add(tab_index)
        widget = self.tab_widget.widget(tab_index)
        if widget:
            widget.clear()
            widget.addItem(f"Failed to load picks: {error}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


FANTASY_SCORING_FORMATS = {"Standard": 0.0, "Half-PPR": 0.5, "PPR": 1.0}

# (label, positions or None for all, rookies only). Rookies share this control
# rather than getting their own: it is the one filter users reach for while
# scanning a board, and a second combo would be another stop for keyboard users
# on every pass.
FANTASY_POSITION_FILTERS = [
    ("All Positions", None, False),
    ("QB", ("QB",), False),
    ("RB", ("RB",), False),
    ("WR", ("WR",), False),
    ("TE", ("TE",), False),
    ("FLEX (RB, WR, TE)", ("RB", "WR", "TE"), False),
    ("K", ("K",), False),
    ("D/ST", ("D/ST",), False),
    ("Rookies", None, True),
    ("Rookie QB", ("QB",), True),
    ("Rookie RB", ("RB",), True),
    ("Rookie WR", ("WR",), True),
    ("Rookie TE", ("TE",), True),
]

FANTASY_SORTS = ["ESPN Rank", "ADP", "Auction Value", "Projected Points", "Player Name"]

# Shown in any column with no value. Spelled out rather than a dash so screen
# readers say something meaningful in all three view modes.
FANTASY_NO_VALUE = "N/A"

# Undrafted players arrive with adp already cleared to None — ESPN's placeholder
# value is stripped in espn_api, where the whole pool is visible and the
# placeholder can be identified rather than guessed at.


class CheatsheetTable(AccessibleTable):
    """Draft board table: Space drafts or un-drafts, Enter opens player details.

    Both keys are handled here rather than on the individual views so they behave
    identically in Table, Quick List and Full List mode.
    """

    toggle_requested = pyqtSignal()
    details_requested = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            accessible_name="Fantasy Draft Board",
            accessible_description=(
                "Fantasy football draft board. Press Space to mark the selected player "
                "drafted or available, Enter for full player details"
            ),
        )
        self.setup_columns(
            ["Rank", "Player", "Pos", "Team", "ADP", "Auction", "Proj", "Status"],
            stretch_column=1,
        )
        # AccessibleTable only exposes the table view's selection signal, but the
        # board has to track the selection in whichever view mode is showing.
        self.table_widget.currentCellChanged.connect(lambda *_: self.selection_changed.emit())
        self.quick_list.currentRowChanged.connect(lambda *_: self.selection_changed.emit())
        self.full_list.currentRowChanged.connect(lambda *_: self.selection_changed.emit())

    def current_row_index(self) -> int:
        """Index of the selected row in whichever view mode is showing."""
        return self._get_current_row()

    def select_row(self, row: int, focus: bool = False, reannounce: bool = False):
        """Move the selection to a row, keeping the current column in table view.

        `reannounce` forces the selection through an empty state first. Re-setting
        the cell a row already sits on is a no-op in Qt — no selection event, so
        nothing for a screen reader to speak — which matters when the row's own
        contents just changed underneath it. The list views clear on repopulate,
        so they already emit the change and need no help.
        """
        if row < 0:
            return
        if self._current_view == self.VIEW_TABLE:
            if row < self.table_widget.rowCount():
                if reannounce:
                    self.table_widget.setCurrentCell(-1, -1)
                self.table_widget.setCurrentCell(row, max(0, self.table_widget.currentColumn()))
        else:
            self._restore_position(row)
        if focus:
            self._set_focus_to_current_view()

    def eventFilter(self, obj, event):
        # Keypad Enter always carries KeypadModifier, so it is masked out rather
        # than excluded — otherwise it would fall through to the dialog's default
        # button and do something other than what the main Enter key does.
        if event.type() == QEvent.Type.KeyPress:
            modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            if modifiers == Qt.KeyboardModifier.NoModifier:
                if event.key() == Qt.Key.Key_Space:
                    self.toggle_requested.emit()
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.details_requested.emit()
                    return True
        return super().eventFilter(obj, event)


class FantasyCheatsheetDialog(QDialog):
    """NFL fantasy football draft cheatsheet.

    A "good starting point" draft board built on ESPN's fantasy feed: every
    draftable player plus all 32 team defenses, with ESPN's consensus rank,
    average draft position, auction value and season projection. Filter by
    position, team or name, sort by any of those, and mark players drafted as a
    live draft goes by. The drafted set and the scoring format persist between
    sessions.

    Changing the scoring format never refetches: each row carries projected
    points excluding receptions plus a projected reception count, so
    Standard / Half-PPR / PPR is a local recalculation.
    """

    # Process-wide cache — the board comes from a ~38 MB download, so reopening
    # the dialog mid-draft should not pay for it again.
    _cached_board = None
    _active_loader = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fantasy Cheatsheet — NFL — Sports Scores")
        self.setMinimumSize(820, 560)
        self.resize(1020, 700)

        self._players = []      # the whole board, as loaded
        self._filtered = []     # the rows the table is currently showing
        self._season = datetime.now().year

        self.scoring = settings.get('fantasy_scoring', 'PPR')
        if self.scoring not in FANTASY_SCORING_FORMATS:
            self.scoring = 'PPR'
        self._taken = set(settings.get('fantasy_taken') or [])

        self._setup_ui()
        self._load_board()

    # ------------------------------------------------------------------ UI

    def _setup_ui(self):
        layout = QVBoxLayout()

        layout.addLayout(self._build_filter_row())
        layout.addLayout(self._build_sort_row())

        self.status_label = QLabel("Loading draft board…")
        self.status_label.setAccessibleName("Draft board status")
        layout.addWidget(self.status_label)

        self.table = CheatsheetTable()
        self.table.toggle_requested.connect(self._toggle_selected)
        self.table.details_requested.connect(self._show_selected_details)
        self.table.selection_changed.connect(self._update_toggle_button)
        layout.addWidget(self.table)

        layout.addLayout(self._build_button_row())
        self.setLayout(layout)
        self._set_controls_enabled(False)

    def _build_filter_row(self):
        row = QHBoxLayout()

        search_label = QLabel("&Search:")
        self.search_box = QLineEdit()
        self.search_box.setAccessibleName("Search players")
        self.search_box.setAccessibleDescription(
            "Type part of a player name or team abbreviation to narrow the board")
        self.search_box.setPlaceholderText("Player or team")
        # Every filter control is debounced through one timer. A rebuild is ~100 ms
        # on the full board, and each of these fires per keystroke: typing in the
        # search box, and arrowing through a *closed* combo box, which a keyboard
        # user does constantly. Undebounced, each press stalls the UI thread
        # before the screen reader gets to speak the new value.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._apply_filters)
        self.search_box.textChanged.connect(lambda _: self._schedule_filters())
        search_label.setBuddy(self.search_box)
        row.addWidget(search_label)
        row.addWidget(self.search_box)

        position_label = QLabel("&Position:")
        self.position_combo = QComboBox()
        self.position_combo.setAccessibleName("Position filter")
        self.position_combo.setAccessibleDescription(
            "Show only players at the selected fantasy position, or only rookies")
        for label, positions, rookies_only in FANTASY_POSITION_FILTERS:
            self.position_combo.addItem(label, (positions, rookies_only))
        self.position_combo.currentIndexChanged.connect(lambda _: self._schedule_filters())
        position_label.setBuddy(self.position_combo)
        row.addWidget(position_label)
        row.addWidget(self.position_combo)

        # Alt+T, Alt+V, Alt+Q and Alt+F belong to AccessibleTable's view switching
        # app-wide. Qt gives a label mnemonic priority over the focused widget's
        # key handling, so no control in this dialog may claim one of them.
        team_label = QLabel("Te&am:")
        self.team_combo = QComboBox()
        self.team_combo.setAccessibleName("Team filter")
        self.team_combo.setAccessibleDescription(
            "Show only players from the selected NFL team")
        self.team_combo.addItem("All Teams", None)
        self.team_combo.currentIndexChanged.connect(lambda _: self._schedule_filters())
        team_label.setBuddy(self.team_combo)
        row.addWidget(team_label)
        row.addWidget(self.team_combo)

        row.addStretch()
        return row

    def _build_sort_row(self):
        row = QHBoxLayout()

        sort_label = QLabel("Sort &by:")
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName("Sort order")
        self.sort_combo.setAccessibleDescription("Column the draft board is sorted by")
        self.sort_combo.addItems(FANTASY_SORTS)
        self.sort_combo.currentIndexChanged.connect(lambda _: self._schedule_filters())
        sort_label.setBuddy(self.sort_combo)
        row.addWidget(sort_label)
        row.addWidget(self.sort_combo)

        scoring_label = QLabel("Sc&oring:")
        self.scoring_combo = QComboBox()
        self.scoring_combo.setAccessibleName("Scoring format")
        self.scoring_combo.setAccessibleDescription(
            "League scoring format. Sets which ESPN rankings and projected points are shown")
        self.scoring_combo.addItems(list(FANTASY_SCORING_FORMATS))
        self.scoring_combo.setCurrentText(self.scoring)
        self.scoring_combo.currentTextChanged.connect(self._on_scoring_changed)
        scoring_label.setBuddy(self.scoring_combo)
        row.addWidget(scoring_label)
        row.addWidget(self.scoring_combo)

        self.hide_drafted_check = QCheckBox("&Hide drafted players")
        self.hide_drafted_check.setAccessibleName("Hide drafted players")
        self.hide_drafted_check.setAccessibleDescription(
            "When checked, players marked drafted are removed from the board")
        self.hide_drafted_check.toggled.connect(lambda _: self._apply_filters())
        row.addWidget(self.hide_drafted_check)

        row.addStretch()
        return row

    def _build_button_row(self):
        row = QHBoxLayout()

        self.toggle_btn = QPushButton("&Mark Drafted")
        self.toggle_btn.setAccessibleDescription(
            "Mark the selected player drafted or available. "
            "Space does the same thing on the board")
        self.toggle_btn.clicked.connect(self._toggle_selected)
        row.addWidget(self.toggle_btn)

        self.details_btn = QPushButton("Player &Details")
        self.details_btn.setAccessibleDescription(
            "Show every draft value and projection for the selected player")
        self.details_btn.clicked.connect(self._show_selected_details)
        row.addWidget(self.details_btn)

        self.clear_btn = QPushButton("C&lear Draft Board")
        self.clear_btn.setAccessibleDescription("Mark every drafted player available again")
        self.clear_btn.clicked.connect(self._clear_draft)
        row.addWidget(self.clear_btn)

        self.export_btn = QPushButton("&Export to CSV")
        self.export_btn.setAccessibleDescription(
            "Save every player on the board to a spreadsheet file")
        self.export_btn.clicked.connect(self._export_csv)
        row.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("&Reload from ESPN")
        self.refresh_btn.setAccessibleDescription(
            "Download the draft board again. Your drafted marks are kept")
        self.refresh_btn.clicked.connect(self._reload_board)
        row.addWidget(self.refresh_btn)

        row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)

        # None of these may become the default button: Enter belongs to the board
        # (open player details) and to the search box, and an auto-default button
        # would silently steal it and draft whoever happens to be selected.
        for button in (self.toggle_btn, self.details_btn, self.clear_btn,
                       self.export_btn, self.refresh_btn, close_btn):
            button.setAutoDefault(False)
            button.setDefault(False)
        return row

    def _set_controls_enabled(self, enabled: bool):
        for widget in (self.search_box, self.position_combo, self.team_combo,
                       self.sort_combo, self.scoring_combo, self.hide_drafted_check,
                       self.toggle_btn, self.details_btn, self.clear_btn,
                       self.export_btn):
            widget.setEnabled(enabled)

    # ---------------------------------------------------------------- Load

    def _load_board(self):
        if FantasyCheatsheetDialog._cached_board:
            self._on_board_loaded(FantasyCheatsheetDialog._cached_board)
            return
        self.refresh_btn.setEnabled(False)
        loader = FantasyCheatsheetLoader()
        loader.data_loaded.connect(self._on_board_loaded)
        loader.error_occurred.connect(self._on_board_error)
        # Held on the class, not the instance: the download outlives a dialog the
        # user closes straight away, and a QThread deleted mid-run warns and can
        # take the process with it.
        # Reopening the board mid-download replaces _active_loader too.
        FantasyCheatsheetDialog._active_loader = loader
        _start_detached_thread(loader)

    def _reload_board(self):
        FantasyCheatsheetDialog._cached_board = None
        self.status_label.setText("Reloading draft board from ESPN…")
        self._load_board()

    def _on_board_loaded(self, board: dict):
        self.refresh_btn.setEnabled(True)
        players = (board or {}).get('players') or []
        if not players:
            self._set_controls_enabled(False)
            self.status_label.setText(
                "ESPN has not published fantasy draft data yet. Try again closer to the season.")
            return

        FantasyCheatsheetDialog._cached_board = board
        self._players = players
        self._season = board.get('season', self._season)
        self._drop_marks_from_a_past_season()

        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        self.team_combo.addItem("All Teams", None)
        teams = {p['team'] for p in players if p.get('team')}
        for team in sorted(teams - {'FA'}):
            self.team_combo.addItem(team, team)
        if 'FA' in teams:
            # Unsigned players are a real slice of the board — Tyreek Hill and
            # Keenan Allen are both FA here — and were previously reachable only
            # by accidentally searching "fa".
            self.team_combo.addItem("Free Agents", 'FA')
        self.team_combo.blockSignals(False)

        self._set_controls_enabled(True)
        self._apply_filters(focus_table=True)

    def _drop_marks_from_a_past_season(self):
        """Forget drafted marks left over from an earlier season's draft.

        ESPN player ids are stable year to year, so last August's board would
        otherwise open with a third of this year's players already crossed off.
        """
        marked_season = settings.get('fantasy_taken_season')
        if marked_season == self._season:
            return
        if self._taken:
            self._taken.clear()
            settings.set('fantasy_taken', [])
        settings.set('fantasy_taken_season', self._season)

    def _on_board_error(self, error: str):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(
            f"Could not load the draft board: {error}. "
            "Choose Reload from ESPN to try again.")

    # ------------------------------------------------------- Value helpers

    def _rank(self, player):
        """Position on this board for the current format: 1, 2, 3 with no gaps.

        ESPN publishes PPR and Standard boards only, so Half-PPR reuses the PPR
        one. The number shown is a dense position rather than ESPN's published
        rank, which orders a pool full of players this board excludes and so
        arrives full of holes — see `_assign_board_ranks`.
        """
        key = 'standard_board_rank' if self.scoring == 'Standard' else 'ppr_board_rank'
        return player.get(key)

    def _espn_rank(self, player):
        """ESPN's published overall rank, for cross-referencing their site."""
        key = 'standard_rank' if self.scoring == 'Standard' else 'ppr_rank'
        return player.get(key)

    def _projected_points(self, player, scoring=None):
        """Projected season points in the given format, or None when unscored."""
        base = player.get('proj_base')
        if base is None:
            return None
        per_reception = FANTASY_SCORING_FORMATS[scoring or self.scoring]
        return base + player.get('proj_receptions', 0) * per_reception

    def _adp_text(self, player):
        adp = player.get('adp')
        return f"{adp:.1f}" if adp and adp > 0 else FANTASY_NO_VALUE

    def _auction_text(self, player):
        value = player.get('auction')
        return f"${value:.0f}" if value and value > 0 else FANTASY_NO_VALUE

    def _projection_text(self, player, scoring=None):
        points = self._projected_points(player, scoring)
        return f"{points:.1f}" if points is not None else FANTASY_NO_VALUE

    def _status_text(self, player):
        parts = []
        if self.is_taken(player):
            parts.append("Drafted")
        if player.get('injury'):
            parts.append(player['injury'])
        return ", ".join(parts) if parts else "Available"

    def _row_for(self, player):
        rank = self._rank(player)
        return [
            str(rank) if rank else FANTASY_NO_VALUE,
            player['name'],
            player['position'],
            player['team'],
            self._adp_text(player),
            self._auction_text(player),
            self._projection_text(player),
            self._status_text(player),
        ]

    # ---------------------------------------------------- Filter and sort

    def _matches(self, player, query, positions, team, rookies_only=False):
        if positions and player['position'] not in positions:
            return False
        if rookies_only and not player.get('rookie'):
            return False
        if team and player['team'] != team:
            return False
        if self.hide_drafted_check.isChecked() and self.is_taken(player):
            return False
        if query and query not in player['name'].lower() and query not in player['team'].lower():
            return False
        return True

    def _sort_key(self, sort_name):
        """Comparison key for a sort choice. Rank breaks every tie but the name sort.

        Numeric keys are rounded to the precision the column actually displays.
        Comparing at full precision means rows showing the same number order by
        digits the user cannot see, and the rank tiebreak never gets a chance to
        run — which is how a rank-2534 camp body ends up above a rank-430 starter
        with both rows reading "169.9".
        """
        def rank(player):
            return self._rank(player) or 9999

        if sort_name == "ADP":
            # Players ESPN treats as undrafted sort to the bottom, not the top.
            def adp(player):
                value = player.get('adp')
                return round(value, 1) if value and value > 0 else float('inf')
            return lambda p: (adp(p), rank(p))
        if sort_name == "Auction Value":
            return lambda p: (-round(p.get('auction') or 0), rank(p))
        if sort_name == "Projected Points":
            # Kickers and defenses carry no projection, so they sort last.
            def points(player):
                value = self._projected_points(player)
                return -round(value, 1) if value is not None else float('inf')
            return lambda p: (points(p), rank(p))
        if sort_name == "Player Name":
            return lambda p: (p['name'].lower(), rank(p))
        return lambda p: (rank(p), p['name'].lower())

    def _schedule_filters(self):
        """Coalesce rapid filter changes into one rebuild."""
        self._filter_timer.start()

    def _apply_filters(self, focus_table: bool = False, preserve_row: int = None,
                       reannounce: bool = False):
        self._filter_timer.stop()   # an immediate rebuild satisfies a pending one
        if not self._players:
            return

        query = self.search_box.text().strip().lower()
        positions, rookies_only = self.position_combo.currentData() or (None, False)
        team = self.team_combo.currentData()

        self._filtered = sorted(
            (p for p in self._players
             if self._matches(p, query, positions, team, rookies_only)),
            key=self._sort_key(self.sort_combo.currentText()),
        )

        keep_focus = focus_table or self.table.hasFocus()
        self.table.populate_data([self._row_for(p) for p in self._filtered], set_focus=False)
        self._update_status()

        if self._filtered:
            row = min(preserve_row, len(self._filtered) - 1) if preserve_row is not None else 0
            self.table.select_row(row, focus=keep_focus, reannounce=reannounce)
        self._update_toggle_button()

    def _update_status(self):
        if not self._filtered:
            self.status_label.setText(
                f"No players match the current filters. "
                f"{len(self._players)} players are on the {self._season} board.")
            return
        drafted = sum(1 for p in self._players if self.is_taken(p))
        self.status_label.setText(
            f"{len(self._filtered)} of {len(self._players)} players — "
            f"{self._season} {self.scoring} rankings, ADP and projections from ESPN — "
            f"{drafted} marked drafted"
        )

    def _on_scoring_changed(self, scoring: str):
        # State updates now, redraw is debounced: arrowing a closed combo emits
        # this per keypress.
        self.scoring = scoring
        settings.set('fantasy_scoring', scoring)
        self._schedule_filters()

    # -------------------------------------------------------- Draft board

    def _selected_player(self):
        row = self.table.current_row_index()
        if 0 <= row < len(self._filtered):
            return row, self._filtered[row]
        return -1, None

    def is_taken(self, player) -> bool:
        """Whether this player is marked drafted."""
        return player['id'] in self._taken

    def toggle_taken(self, player) -> bool:
        """Flip a player between drafted and available. Returns the new state."""
        if player['id'] in self._taken:
            self._taken.discard(player['id'])
            drafted = False
        else:
            self._taken.add(player['id'])
            drafted = True
        settings.set('fantasy_taken', sorted(self._taken))
        return drafted

    def _toggle_selected(self):
        row, player = self._selected_player()
        if not player:
            return
        drafted = self.toggle_taken(player)
        # reannounce: the row's contents change under a selection that does not
        # move, which by itself produces no accessibility event. Forcing the
        # selection through an empty state makes the screen reader read the row
        # back, so the new Drafted/Available status is spoken right away.
        self._apply_filters(preserve_row=row, reannounce=True)
        state = "drafted" if drafted else "available"
        self.status_label.setText(f"{player['name']} marked {state}. {self.status_label.text()}")

    def _update_toggle_button(self):
        _, player = self._selected_player()
        drafted = bool(player) and self.is_taken(player)
        self.toggle_btn.setText("&Mark Available" if drafted else "&Mark Drafted")

    def _clear_draft(self):
        if not self._taken:
            self.status_label.setText("No players are marked drafted.")
            return
        confirm = QMessageBox.question(
            self, "Clear Draft Board",
            f"Mark all {len(self._taken)} drafted players available again?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._taken.clear()
        settings.set('fantasy_taken', [])
        self._apply_filters(preserve_row=self.table.current_row_index())
        self.status_label.setText(f"Draft board cleared. {self.status_label.text()}")

    # ------------------------------------------------------------- Export

    CSV_HEADERS = [
        "PPR Rank", "Standard Rank", "Player", "Position", "Team", "Rookie",
        "Injury Status", "ADP", "Auction Value",
        "Projected Points Standard", "Projected Points Half-PPR",
        "Projected Points PPR", "Drafted",
        "ESPN Overall PPR Rank", "ESPN Overall Standard Rank",
    ]

    def csv_rows(self):
        """Every player on the board, ordered by ESPN's rank for the chosen format.

        Deliberately the whole board rather than the current filter: the export
        is for taking the data elsewhere, and a spreadsheet can filter itself.
        Numbers are written unformatted so they arrive as numbers, not text —
        blanks rather than "N/A", which would make a whole column text in Excel.
        """
        def number(value, digits=1):
            return "" if value is None else f"{value:.{digits}f}"

        players = sorted(self._players, key=self._sort_key("ESPN Rank"))
        rows = []
        for p in players:
            adp = p.get('adp') or None
            rows.append([
                p.get('ppr_board_rank') or "",
                p.get('standard_board_rank') or "",
                p['name'],
                p['position'],
                p['team'],
                "Yes" if p.get('rookie') else "No",
                p.get('injury') or "",
                number(adp),
                number(p.get('auction') or None, 2),
                number(self._projected_points(p, "Standard")),
                number(self._projected_points(p, "Half-PPR")),
                number(self._projected_points(p, "PPR")),
                "Yes" if self.is_taken(p) else "No",
                p.get('ppr_rank') or "",
                p.get('standard_rank') or "",
            ])
        return rows

    def _export_csv(self):
        if not self._players:
            return
        default_name = f"fantasy-cheatsheet-{self._season}.csv"
        default_dir = os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.isdir(default_dir):
            default_dir = os.path.expanduser("~")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Draft Board", os.path.join(default_dir, default_name),
            "CSV files (*.csv);;All files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".csv"

        try:
            # utf-8-sig: Excel assumes the system codepage without a BOM and
            # mangles every non-ASCII name in the league.
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(self.CSV_HEADERS)
                writer.writerows(self.csv_rows())
        except OSError as e:
            QMessageBox.critical(self, "Export Failed",
                                 f"Could not write the file:\n{e}")
            return

        self.status_label.setText(
            f"Exported {len(self._players)} players to {path}. {self.status_label.text()}")
        QMessageBox.information(
            self, "Export Complete",
            f"Saved {len(self._players)} players to:\n{path}")

    # ------------------------------------------------------------ Details

    def detail_rows(self, player):
        """Field/value pairs describing one player, for the details dialog."""
        def rank_text(rank):
            return f"#{rank}" if rank else FANTASY_NO_VALUE

        rows = [
            ["Position", player['position']],
            ["Team", player['team'] if player['team'] != 'FA' else "Free agent"],
            ["Rookie", "Yes" if player.get('rookie') else "No"],
            ["PPR Rank", rank_text(player.get('ppr_board_rank'))],
            ["Standard Rank", rank_text(player.get('standard_board_rank'))],
            # ESPN's own numbering, for anyone comparing against their site. It
            # counts defensive players and Team QB slots this board leaves out,
            # so it runs well ahead of the board position.
            ["ESPN overall rank, PPR", rank_text(player.get('ppr_rank'))],
            ["ESPN overall rank, Standard", rank_text(player.get('standard_rank'))],
            ["Average Draft Position", self._adp_text(player)],
            ["Auction Value", self._auction_text(player)],
        ]
        for scoring in FANTASY_SCORING_FORMATS:
            rows.append([f"Projected Points, {scoring}", self._projection_text(player, scoring)])
        rows.append(["Injury Status", player.get('injury') or "None reported"])
        rows.append(["Draft Status", "Drafted" if self.is_taken(player) else "Available"])
        return rows

    def _show_selected_details(self):
        row, player = self._selected_player()
        if not player:
            return
        dialog = FantasyPlayerDialog(player, self, self)
        dialog.exec()
        # The details dialog can draft the player, so rebuild on the way out.
        self._apply_filters(preserve_row=row, focus_table=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class FantasyPlayerDialog(QDialog):
    """Every draft value ESPN publishes for one cheatsheet player or defense."""

    def __init__(self, player, board, parent=None):
        super().__init__(parent)
        self.player = player
        self.board = board

        self.setWindowTitle(f"{player['name']} — Fantasy Cheatsheet — Sports Scores")
        self.setMinimumSize(520, 460)

        layout = QVBoxLayout()

        heading = QLabel(f"{player['name']} — {player['position']}, {player['team']}")
        heading.setAccessibleName("Player")
        layout.addWidget(heading)

        self.table = AccessibleTable(
            accessible_name=f"{player['name']} draft values",
            accessible_description="Draft values and projections for this player",
        )
        self.table.setup_columns(["Field", "Value"], stretch_column=1)
        self.table.populate_data(board.detail_rows(player), set_focus=True)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.toggle_btn = QPushButton()
        self.toggle_btn.clicked.connect(self._toggle)
        self._sync_toggle_button()
        row.addWidget(self.toggle_btn)
        row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

        # Focus opens on the table, so Enter has to mean "I'm done reading" —
        # the first button added would otherwise become the default and draft
        # the player instead.
        self.toggle_btn.setAutoDefault(False)
        self.toggle_btn.setDefault(False)
        close_btn.setAutoDefault(True)
        close_btn.setDefault(True)

        self.setLayout(layout)

    def _sync_toggle_button(self):
        drafted = self.board.is_taken(self.player)
        self.toggle_btn.setText("&Mark Available" if drafted else "&Mark Drafted")
        self.toggle_btn.setAccessibleDescription(
            f"{self.player['name']} is currently {'drafted' if drafted else 'available'}")

    def _toggle(self):
        self.board.toggle_taken(self.player)
        self.table.populate_data(self.board.detail_rows(self.player), set_focus=False)
        self._sync_toggle_button()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class GolfTournamentDialog(QDialog):
    """Golf tournament viewer: current leaderboard + full season schedule."""

    _TOUR_NAMES = {"PGA": "PGA Tour", "LPGA": "LPGA Tour"}

    def __init__(self, tour: str, parent=None):
        super().__init__(parent)
        self.tour = tour
        tour_name = self._TOUR_NAMES.get(tour, tour)
        self.setWindowTitle(f"{tour_name} — Sports Scores")
        self.setMinimumSize(700, 500)
        self.resize(950, 680)
        self._loaders = []
        self._setup_ui()
        self._load_leaderboard()
        self._load_schedule()

    def _setup_ui(self):
        layout = QVBoxLayout()

        tour_name = self._TOUR_NAMES.get(self.tour, self.tour)
        header = QLabel(tour_name)
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        self.tournament_label = QLabel("Loading current tournament…")
        self.tournament_label.setAccessibleName("Current tournament")
        layout.addWidget(self.tournament_label)

        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName(f"{tour_name} sections")

        self.leaderboard_list = QListWidget()
        self.leaderboard_list.setAccessibleName(f"{tour_name} Leaderboard")
        self.leaderboard_list.setAccessibleDescription(
            "Current tournament leaderboard. Each entry shows position, player name, total score, and round scores.")
        self.leaderboard_list.addItem("Loading leaderboard…")
        self.tab_widget.addTab(self.leaderboard_list, "Leaderboard")

        self.schedule_list = QListWidget()
        self.schedule_list.setAccessibleName(f"{tour_name} Schedule")
        self.schedule_list.setAccessibleDescription(
            "Season schedule. Completed events show winner and score. Upcoming events show dates.")
        self.schedule_list.addItem("Loading schedule…")
        self.tab_widget.addTab(self.schedule_list, "Schedule")

        layout.addWidget(self.tab_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _load_leaderboard(self):
        loader = GolfLeaderboardLoader(self.tour)
        loader.data_loaded.connect(self._on_leaderboard_loaded)
        loader.error_occurred.connect(lambda e: self._list_error(self.leaderboard_list, e))
        self._loaders.append(loader)
        loader.start()

    def _load_schedule(self):
        loader = GolfScheduleLoader(self.tour)
        loader.data_loaded.connect(self._on_schedule_loaded)
        loader.error_occurred.connect(lambda e: self._list_error(self.schedule_list, e))
        self._loaders.append(loader)
        loader.start()

    @staticmethod
    def _fmt_date_range(start, end):
        try:
            from datetime import datetime as dt
            s = dt.strptime(start, "%Y-%m-%d")
            e = dt.strptime(end, "%Y-%m-%d")
            if s.month == e.month:
                return f"{s.strftime('%b')} {s.day}–{e.day}"
            return f"{s.strftime('%b %d')} – {e.strftime('%b %d')}"
        except Exception:
            return f"{start}–{end}" if end else start

    def _on_leaderboard_loaded(self, data: dict):
        self.leaderboard_list.clear()
        if not data:
            self.leaderboard_list.addItem("No current tournament data available.")
            return

        name = data.get('name', '')
        start = data.get('date', '')
        end = data.get('end_date', '')
        status_detail = data.get('status_detail', '')
        date_range = self._fmt_date_range(start, end) if start else ''
        header_parts = [p for p in [name, status_detail, date_range] if p]
        self.tournament_label.setText("  |  ".join(header_parts))

        players = data.get('players', [])
        if not players:
            self.leaderboard_list.addItem("No leaderboard data available.")
            return

        # Detect ties: group players by total_score, record first position for each score
        from collections import Counter
        score_count = Counter(p['total_score'] for p in players)
        score_first_pos: dict = {}
        for p in players:
            s = p['total_score']
            if s not in score_first_pos:
                score_first_pos[s] = p['position']

        for player in players:
            pos = player['position']
            score = player['total_score']
            first_pos = score_first_pos[score]
            tied = score_count[score] > 1
            pos_str = f"T{first_pos}" if tied else str(pos)

            name = player['name']
            country = player.get('country', '')
            rounds = player.get('rounds', [])

            parts = [f"{pos_str:>4}", name]
            if country:
                parts.append(f"({country})")
            parts.append(f"{score:>5}")
            if rounds:
                parts.append("  " + "  ".join(rounds))

            self.leaderboard_list.addItem("  ".join(parts))

        if self.leaderboard_list.count() > 0 and self.tab_widget.currentIndex() == 0:
            self.leaderboard_list.setCurrentRow(0)
            self.leaderboard_list.setFocus()

    def _on_schedule_loaded(self, events: list):
        self.schedule_list.clear()
        if not events:
            self.schedule_list.addItem("No schedule available.")
            return

        for event in events:
            name = event.get('name', '')
            start = event.get('start_date', '')
            end = event.get('end_date', '')
            state = event.get('state', 'pre')
            winner = event.get('winner', '')
            date_str = self._fmt_date_range(start, end) if start else ''

            if state == 'post' and winner:
                line = f"[Final]  {name}  —  {date_str}  —  {winner}"
            elif state == 'in':
                line = f"[Live]   {name}  —  {date_str}"
            else:
                line = f"         {name}  —  {date_str}"

            self.schedule_list.addItem(line)

    def _list_error(self, lw: QListWidget, error: str):
        lw.clear()
        lw.addItem(f"Error loading data: {error}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


# ─────────────────────────── World Cup ───────────────────────────────────────

# Tournament phase definitions: (id, label, start_date, end_date)
_WC2026_PHASES = [
    ("1", "Group Stage",     datetime(2026, 6, 11).date(), datetime(2026, 6, 27).date()),
    ("2", "Round of 32",     datetime(2026, 6, 28).date(), datetime(2026, 7,  3).date()),
    ("3", "Round of 16",     datetime(2026, 7,  4).date(), datetime(2026, 7,  7).date()),
    ("4", "Quarterfinals",   datetime(2026, 7,  9).date(), datetime(2026, 7, 11).date()),
    ("5", "Semifinals",      datetime(2026, 7, 14).date(), datetime(2026, 7, 15).date()),
    ("6", "3rd-Place Match", datetime(2026, 7, 18).date(), datetime(2026, 7, 18).date()),
    ("7", "Final",           datetime(2026, 7, 19).date(), datetime(2026, 7, 19).date()),
]

_WWC2027_PHASES = [
    ("1", "Group Stage",     datetime(2027, 7,  1).date(), datetime(2027, 7, 20).date()),
    ("2", "Round of 16",     datetime(2027, 7, 21).date(), datetime(2027, 7, 24).date()),
    ("3", "Quarterfinals",   datetime(2027, 7, 26).date(), datetime(2027, 7, 29).date()),
    ("4", "Semifinals",      datetime(2027, 8,  1).date(), datetime(2027, 8,  2).date()),
    ("5", "3rd-Place Match", datetime(2027, 8,  5).date(), datetime(2027, 8,  5).date()),
    ("6", "Final",           datetime(2027, 8,  6).date(), datetime(2027, 8,  6).date()),
]

_WC_DISPLAY_NAMES = {
    "WC2026":  "2026 FIFA World Cup",
    "WWC2027": "2027 FIFA Women's World Cup",
}


class WorldCupStandingsLoader(QThread):
    """Background loader for World Cup group standings."""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, league_key: str):
        super().__init__()
        self.league_key = league_key

    def run(self):
        try:
            groups = ApiService.get_world_cup_standings(self.league_key)
            self.data_loaded.emit(groups or [])
        except Exception as e:
            self.error_occurred.emit(str(e))


class WorldCupScoresLoader(QThread):
    """Background loader for World Cup scores on a single date."""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, league_key: str, date):
        super().__init__()
        self.league_key = league_key
        self.date = date

    def run(self):
        try:
            games = ApiService.get_scores(self.league_key, self.date)
            self.data_loaded.emit(games or [])
        except Exception as e:
            self.error_occurred.emit(str(e))


class WorldCupBracketLoader(QThread):
    """Background loader for World Cup games in a date range (knockout phases)."""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, league_key: str, start_date, end_date):
        super().__init__()
        self.league_key = league_key
        self.start_date = start_date
        self.end_date = end_date

    def run(self):
        try:
            games = ApiService.get_world_cup_scores_range(
                self.league_key, self.start_date, self.end_date)
            self.data_loaded.emit(games or [])
        except Exception as e:
            self.error_occurred.emit(str(e))


class WorldCupNewsLoader(QThread):
    """Background loader for World Cup news."""
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, league_key: str):
        super().__init__()
        self.league_key = league_key

    def run(self):
        try:
            news = ApiService.get_news(self.league_key, limit=25)
            self.data_loaded.emit(news or [])
        except Exception as e:
            self.error_occurred.emit(str(e))


class WorldCupDialog(QDialog):
    """World Cup hub dialog: Scores · Groups · Bracket · News.

    Covers both men's (WC2026, soccer/fifa.world) and
    women's (WWC2027, soccer/fifa.wwc) tournaments.
    """

    _GROUP_HEADERS = ["Team", "GP", "W", "D", "L", "GD", "Pts"]

    def __init__(self, league_key: str, parent=None):
        super().__init__(parent)
        self.league_key = league_key
        self.display_name = _WC_DISPLAY_NAMES.get(league_key, league_key)
        self.phases = _WC2026_PHASES if league_key == "WC2026" else _WWC2027_PHASES
        self.current_date = datetime.now().date()
        self.current_groups: list = []
        self._loaders: list = []
        self._group_tables: list = []  # AccessibleTable widgets (one per group)

        self.setWindowTitle(f"{self.display_name} — Sports Scores")
        self.setMinimumSize(750, 550)
        self.resize(1000, 700)

        self._setup_ui()
        self._load_all()
        QTimer.singleShot(0, self.scores_list.setFocus)

    # ─────────────── UI setup ───────────────

    def _setup_ui(self):
        layout = QVBoxLayout()

        header = QLabel(self.display_name)
        font = header.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        header.setFont(font)
        layout.addWidget(header)

        self.phase_label = QLabel(self._current_phase_label())
        self.phase_label.setAccessibleName("Current tournament phase")
        layout.addWidget(self.phase_label)

        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName(f"{self.display_name} sections")

        self.tab_widget.addTab(self._build_scores_tab(),  "Scores")
        self.tab_widget.addTab(self._build_groups_tab(),  "Groups")
        self.tab_widget.addTab(self._build_bracket_tab(), "Bracket")
        self.tab_widget.addTab(self._build_news_tab(),    "News")

        layout.addWidget(self.tab_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("&Refresh")
        refresh_btn.clicked.connect(self._load_all)
        btn_row.addWidget(refresh_btn)
        close_btn = QPushButton("&Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    # ── Scores tab ──

    def _build_scores_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Date navigation bar
        nav = QHBoxLayout()
        self.scores_prev_btn = QPushButton("◀ Previous Day (Alt+P)")
        self.scores_prev_btn.setAccessibleName("Previous Day")
        self.scores_prev_btn.setShortcut("Alt+P")
        self.scores_prev_btn.clicked.connect(self._scores_prev_day)
        nav.addWidget(self.scores_prev_btn)

        self.scores_date_label = QLabel()
        self.scores_date_label.setAccessibleName("Selected date")
        self.scores_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self.scores_date_label, 1)

        self.scores_next_btn = QPushButton("Next Day ▶ (Alt+N)")
        self.scores_next_btn.setAccessibleName("Next Day")
        self.scores_next_btn.setShortcut("Alt+N")
        self.scores_next_btn.clicked.connect(self._scores_next_day)
        nav.addWidget(self.scores_next_btn)

        self.scores_today_btn = QPushButton("Today")
        self.scores_today_btn.setAccessibleName("Go to Today")
        self.scores_today_btn.clicked.connect(self._scores_go_today)
        nav.addWidget(self.scores_today_btn)
        layout.addLayout(nav)

        self.scores_list = QListWidget()
        self.scores_list.setAccessibleName("World Cup Scores")
        self.scores_list.setAccessibleDescription(
            "World Cup matches for the selected date. Press Enter to view match details.")
        self.scores_list.addItem("Loading matches…")
        self.scores_list.itemActivated.connect(self._on_game_activated)
        layout.addWidget(self.scores_list)

        self._update_scores_date_label()
        return widget

    # ── Groups tab ──

    def _build_groups_tab(self) -> QWidget:
        self.groups_scroll = QScrollArea()
        self.groups_scroll.setWidgetResizable(True)
        self.groups_scroll.setAccessibleName("World Cup Group Standings")

        self.groups_content = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_content)
        self.groups_layout.setSpacing(12)

        loading_label = QLabel("Loading group standings…")
        self.groups_layout.addWidget(loading_label)
        self.groups_layout.addStretch()

        self.groups_scroll.setWidget(self.groups_content)
        return self.groups_scroll

    # ── Bracket tab ──

    def _build_bracket_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        phase_bar = QHBoxLayout()
        phase_bar.addWidget(QLabel("Phase:"))
        self.phase_combo = QComboBox()
        self.phase_combo.setAccessibleName("Tournament phase selector")
        self.phase_combo.setAccessibleDescription(
            "Select a tournament phase to view its matches")
        for pid, label, start, end in self.phases:
            self.phase_combo.addItem(label, userData=(pid, start, end))
        self.phase_combo.currentIndexChanged.connect(self._on_phase_selected)
        phase_bar.addWidget(self.phase_combo, 1)
        layout.addLayout(phase_bar)

        # Pre-select the currently active (or most recent) phase
        self._presort_phase_combo()

        self.bracket_stack = QStackedWidget()

        # Page 0: groups view (shown when Group Stage is selected)
        self.bracket_groups_scroll = QScrollArea()
        self.bracket_groups_scroll.setWidgetResizable(True)
        self.bracket_groups_content = QWidget()
        self.bracket_groups_layout = QVBoxLayout(self.bracket_groups_content)
        self.bracket_groups_layout.addWidget(QLabel("Loading…"))
        self.bracket_groups_scroll.setWidget(self.bracket_groups_content)
        self.bracket_stack.addWidget(self.bracket_groups_scroll)

        # Page 1: knockout match list
        self.bracket_list = QListWidget()
        self.bracket_list.setAccessibleName("Bracket matches")
        self.bracket_list.setAccessibleDescription(
            "Matches for the selected tournament phase. Press Enter to view match details.")
        self.bracket_list.addItem("Select a phase above to load matches.")
        self.bracket_list.itemActivated.connect(self._on_game_activated)
        self.bracket_stack.addWidget(self.bracket_list)

        layout.addWidget(self.bracket_stack)
        return widget

    # ── News tab ──

    def _build_news_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.news_list = QListWidget()
        self.news_list.setAccessibleName("World Cup News")
        self.news_list.setAccessibleDescription(
            "News headlines. Press Enter or double-click to open in browser.")
        self.news_list.addItem("Loading news…")
        self.news_list.itemActivated.connect(self._on_news_activated)
        layout.addWidget(self.news_list)

        open_btn = QPushButton("Open Selected Story")
        open_btn.clicked.connect(lambda: self._on_news_activated(self.news_list.currentItem()))
        layout.addWidget(open_btn)
        return widget

    # ─────────────── Data loading ───────────────

    def _load_all(self):
        self._load_scores()
        self._load_standings()
        self._load_news()
        # Trigger bracket load for the initially selected phase
        self._on_phase_selected(self.phase_combo.currentIndex())

    def _load_standings(self):
        loader = WorldCupStandingsLoader(self.league_key)
        loader.data_loaded.connect(self._on_standings_loaded)
        loader.error_occurred.connect(lambda e: self._set_group_error(e))
        self._loaders.append(loader)
        loader.start()

    def _load_scores(self):
        self.scores_list.clear()
        self.scores_list.addItem("Loading matches…")
        loader = WorldCupScoresLoader(self.league_key, self.current_date)
        loader.data_loaded.connect(self._on_scores_loaded)
        loader.error_occurred.connect(lambda e: self._list_error(self.scores_list, e))
        self._loaders.append(loader)
        loader.start()

    def _load_news(self):
        loader = WorldCupNewsLoader(self.league_key)
        loader.data_loaded.connect(self._on_news_loaded)
        loader.error_occurred.connect(lambda e: self._list_error(self.news_list, e))
        self._loaders.append(loader)
        loader.start()

    # ─────────────── Data handlers ───────────────

    def _on_standings_loaded(self, groups: list):
        self.current_groups = groups
        self._rebuild_groups_widget(self.groups_layout, self.groups_content)
        # Also refresh bracket groups page if Group Stage is selected
        if self.phase_combo.currentData() and self.phase_combo.currentData()[0] == "1":
            self._rebuild_groups_widget(self.bracket_groups_layout, self.bracket_groups_content)

    def _on_scores_loaded(self, games: list):
        self._populate_game_list(self.scores_list, games)

    def _on_news_loaded(self, news: list):
        self.news_list.clear()
        if not news:
            self.news_list.addItem("No news available.")
            return
        for item in news:
            headline = item.get("headline", "No headline")
            li = QListWidgetItem(headline)
            li.setData(Qt.ItemDataRole.UserRole, item)
            self.news_list.addItem(li)
        if self.news_list.count() > 0:
            self.news_list.setCurrentRow(0)

    # ─────────────── Groups widget builder ───────────────

    def _rebuild_groups_widget(self, layout: QVBoxLayout, container: QWidget):
        """Clear and repopulate a groups scroll-area layout with current_groups data."""
        # Remove all existing children
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_groups:
            layout.addWidget(QLabel("Group standings not available yet."))
            layout.addStretch()
            return

        for group in self.current_groups:
            group_label = QLabel(group["name"])
            lf = group_label.font()
            lf.setBold(True)
            group_label.setFont(lf)
            group_label.setAccessibleName(group["name"])
            layout.addWidget(group_label)

            table = AccessibleTable(
                parent=container,
                accessible_name=f"{group['name']} Standings",
                accessible_description=(
                    f"Standings for {group['name']}. "
                    "Columns: Team, Games Played, Wins, Draws, Losses, Goal Difference, Points."
                ),
            )
            table.setup_columns(self._GROUP_HEADERS, stretch_column=0)

            rows = []
            for t in group["teams"]:
                abbr = t["abbreviation"]
                if t.get("advancement_note"):
                    abbr += " ✓"
                gd = t["goal_difference"]
                gd_str = f"+{gd}" if gd > 0 else str(gd)
                rows.append([
                    abbr,
                    str(t["games_played"]),
                    str(t["wins"]),
                    str(t["draws"]),
                    str(t["losses"]),
                    gd_str,
                    str(t["points"]),
                ])
            table.populate_data(rows, set_focus=False)
            table.setMaximumHeight(140)
            layout.addWidget(table)

        layout.addStretch()

    def _set_group_error(self, msg: str):
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.groups_layout.addWidget(QLabel(f"Could not load standings: {msg}"))
        self.groups_layout.addStretch()

    # ─────────────── Game list helpers ───────────────

    def _populate_game_list(self, lw: QListWidget, games: list):
        lw.clear()
        if not games:
            lw.addItem("No matches scheduled for this date.")
            return
        for raw in games:
            game = GameData(raw, self.league_key)
            li = QListWidgetItem(game.get_display_text())
            li.setData(Qt.ItemDataRole.UserRole, raw.get("id", ""))
            lw.addItem(li)
        if lw.count() > 0:
            lw.setCurrentRow(0)

    @staticmethod
    def _list_error(lw: QListWidget, msg: str):
        lw.clear()
        lw.addItem(f"Error loading data: {msg}")

    # ─────────────── Date navigation ───────────────

    def _update_scores_date_label(self):
        today = datetime.now().date()
        if self.current_date == today:
            label = f"Today — {self.current_date.strftime('%A, %B %d, %Y')}"
        else:
            label = self.current_date.strftime("%A, %B %d, %Y")
        self.scores_date_label.setText(label)
        self.scores_today_btn.setVisible(self.current_date != today)

    def _scores_prev_day(self):
        self.current_date -= timedelta(days=1)
        self._update_scores_date_label()
        self._load_scores()

    def _scores_next_day(self):
        self.current_date += timedelta(days=1)
        self._update_scores_date_label()
        self._load_scores()

    def _scores_go_today(self):
        self.current_date = datetime.now().date()
        self._update_scores_date_label()
        self._load_scores()

    # ─────────────── Phase / bracket ───────────────

    def _presort_phase_combo(self):
        """Pre-select the currently active phase, or the last past phase."""
        today = datetime.now().date()
        best = 0
        for i, (pid, label, start, end) in enumerate(self.phases):
            if start <= today <= end:
                best = i
                break
            if end < today:
                best = i
        self.phase_combo.setCurrentIndex(best)

    def _current_phase_label(self) -> str:
        today = datetime.now().date()
        for pid, label, start, end in self.phases:
            if start <= today <= end:
                return f"Current phase: {label}"
        for pid, label, start, end in reversed(self.phases):
            if end < today:
                return f"Concluded: {label}"
        start_date = self.phases[0][2]
        days_until = (start_date - today).days
        return f"Tournament begins in {days_until} days" if days_until > 0 else "Tournament concluded"

    def _on_phase_selected(self, index: int):
        if index < 0:
            return
        data = self.phase_combo.itemData(index)
        if not data:
            return
        pid, start, end = data
        if pid == "1":
            # Group Stage — show group standings widget
            self._bracket_generation = getattr(self, '_bracket_generation', 0) + 1
            self.bracket_stack.setCurrentIndex(0)
            if self.current_groups:
                self._rebuild_groups_widget(
                    self.bracket_groups_layout, self.bracket_groups_content)
        else:
            self.bracket_stack.setCurrentIndex(1)
            self.bracket_list.clear()
            self.bracket_list.addItem(f"Loading {self.phase_combo.itemText(index)} matches…")
            # Only the newest phase's load may fill the list; an older one
            # finishing last would show the phase just left.
            self._bracket_generation = getattr(self, '_bracket_generation', 0) + 1
            gen = self._bracket_generation
            current = lambda: gen == self._bracket_generation
            loader = WorldCupBracketLoader(self.league_key, start, end)
            loader.data_loaded.connect(
                lambda games: current() and self._populate_game_list(self.bracket_list, games))
            loader.error_occurred.connect(
                lambda e: current() and self._list_error(self.bracket_list, e))
            self._loaders.append(loader)
            _start_detached_thread(loader)

    # ─────────────── Item activation ───────────────

    def _on_game_activated(self, item: QListWidgetItem):
        if not item:
            return
        game_id = item.data(Qt.ItemDataRole.UserRole)
        if game_id and isinstance(game_id, str):
            dialog = GameDetailsDialog(game_id, self.league_key, self)
            dialog.exec()

    def _on_news_activated(self, item):
        if not item:
            return
        news_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(news_data, dict):
            url = news_data.get("web_url", "")
            if url and url.startswith(("http://", "https://")):
                webbrowser.open(url)
            else:
                QMessageBox.information(self, "No Link", "No web link available for this story.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class StatisticsChoiceDialog(QDialog):
    """First dialog for statistics: Choose between Team or Player statistics"""
    
    def __init__(self, league: str, parent=None):
        super().__init__(parent)
        self.league = league
        self.choice = None
        self.setWindowTitle(f"{league} Statistics")
        self.resize(400, 300)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"Choose Statistics Type for {self.league}")
        title.setAccessibleName(f"{self.league} Statistics Selection")
        layout.addWidget(title)
        
        # Choice list (consistent with rest of app)
        self.choice_list = QListWidget()
        self.choice_list.setAccessibleName("Statistics Type List")
        self.choice_list.setAccessibleDescription("Choose between team or player statistics. Press Enter to select.")
        
        # Add options
        team_item = QListWidgetItem("Team Statistics")
        team_item.setData(Qt.ItemDataRole.UserRole, "team")
        team_item.setToolTip("View statistics for all teams in the league")
        self.choice_list.addItem(team_item)
        
        player_item = QListWidgetItem("Player Statistics")
        player_item.setData(Qt.ItemDataRole.UserRole, "player") 
        player_item.setToolTip("View statistics for individual players")
        self.choice_list.addItem(player_item)
        
        # Connect selection events
        self.choice_list.itemActivated.connect(self._on_choice_activated)
        self.choice_list.itemDoubleClicked.connect(self._on_choice_activated)
        
        layout.addWidget(self.choice_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        select_btn = QPushButton("Select")
        select_btn.setDefault(True)
        select_btn.clicked.connect(self._on_select_clicked)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(select_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to list
        self.choice_list.setFocus()
        self.choice_list.setCurrentRow(0)
    
    def _on_choice_activated(self, item):
        """Handle item activation (Enter or double-click)"""
        choice_type = item.data(Qt.ItemDataRole.UserRole)
        if choice_type:
            self.choice = choice_type
            self.accept()
    
    def _on_select_clicked(self):
        """Handle Select button click"""
        current_item = self.choice_list.currentItem()
        if current_item:
            self._on_choice_activated(current_item)
    
    def get_choice(self):
        return self.choice


class StatisticsViewDialog(QDialog):
    """Second dialog for statistics: Select stat and view results table"""
    
    def __init__(self, league: str, stat_type: str, parent=None):
        super().__init__(parent)
        print(f"DEBUG: StatisticsViewDialog.__init__ called with league={league}, stat_type={stat_type}")
        self.league = league
        self.stat_type = stat_type  # "team" or "player"
        self.setWindowTitle(f"{league} {stat_type.title()} Statistics")
        self.resize(1000, 700)
        self.statistics_data = None
        print(f"DEBUG: About to call setup_ui")
        self.setup_ui()
        print(f"DEBUG: setup_ui completed")
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"{self.league} {self.stat_type.title()} Statistics")
        layout.addWidget(title)
        
        # Statistics load on a thread: team stats are one request per team
        # (30-60+), MLB player stats are 39. Fetched here in the constructor
        # they froze the window before the dialog even appeared. The dialog
        # opens at once on a focusable "Loading" row, and the stats replace it.
        self._content_layout = QVBoxLayout()
        self._loading_list = QListWidget()
        self._loading_list.setAccessibleName(f"{self.stat_type.title()} statistics")
        self._loading_list.addItem(f"Loading {self.league} {self.stat_type} statistics...")
        self._loading_list.setCurrentRow(0)
        self._content_layout.addWidget(self._loading_list)
        layout.addLayout(self._content_layout)

        loader = StatisticsLoader(self.league, self.stat_type)
        loader.data_loaded.connect(self._on_statistics_loaded)
        loader.error_occurred.connect(self._on_statistics_error)
        self._statistics_loader = loader
        _start_detached_thread(loader)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setAutoDefault(False)  # Prevent auto-activation
        close_btn.setDefault(False)      # Not the default button
        close_btn.clicked.connect(lambda: self._debug_accept("Main close button"))
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _clear_loading_row(self):
        self._content_layout.removeWidget(self._loading_list)
        self._loading_list.deleteLater()

    def _on_statistics_error(self, message: str):
        self._clear_loading_row()
        error_label = QLabel(f"Error loading statistics: {message}")
        self._content_layout.addWidget(error_label)

    def _on_statistics_loaded(self, statistics_data: dict):
        self._clear_loading_row()
        self._show_statistics(self._content_layout, statistics_data)  # catches its own errors
        if hasattr(self, 'stats_list'):
            self.stats_list.setFocus()

    def _show_statistics(self, layout, statistics_data):
        """Build the statistics interface from loaded data. No network access."""
        try:
            self.statistics_data = statistics_data
            if self.statistics_data:
                available_stats = self._get_available_statistics()
                print(f"DEBUG: Got {len(available_stats)} available stats")
                
                if available_stats:
                    self._create_working_statistics_interface(layout, available_stats)
                else:
                    no_data_label = QLabel(f"No {self.stat_type} statistics available for {self.league}")
                    layout.addWidget(no_data_label)
            else:
                no_data_label = QLabel(f"Unable to load statistics data for {self.league}")
                layout.addWidget(no_data_label)
                
        except Exception as e:
            print(f"DEBUG: Exception in setup_ui: {str(e)}")
            import traceback
            traceback.print_exc()
            error_label = QLabel(f"Error loading statistics: {str(e)}")
            layout.addWidget(error_label)

    def _debug_accept(self, reason):
        """Debug wrapper for accept() to track why dialog is closing"""
        print(f"DEBUG: StatisticsViewDialog.accept() called - reason: {reason}")
        self.accept()
    
    def keyPressEvent(self, event):
        """Handle key press events for navigation"""
        if event.key() == Qt.Key.Key_F6:
            # Cycle between stats list and results list
            current_focus = self.focusWidget()
            if hasattr(self, 'stats_list') and hasattr(self, 'results_list'):
                if current_focus == self.stats_list:
                    # Move to results list if visible
                    if self.results_list.isVisible():
                        self.results_list.setFocus()
                    else:
                        # If no results visible, stay on stats list
                        self.stats_list.setFocus()
                else:
                    # Move back to stats list
                    self.stats_list.setFocus()
            event.accept()
        elif event.key() == Qt.Key.Key_D and event.modifiers() == Qt.KeyboardModifier.AltModifier:
            # Alt+D: Show stat definitions
            self._show_stat_definitions()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def _switch_to_player_stats(self):
        """Switch to player statistics"""
        self.stat_type = "player"
        self.setWindowTitle(f"{self.league} {self.stat_type.title()} Statistics")
        
        # Clear layout and rebuild
        layout = self.layout()
        self._clear_layout(layout)
        self.setup_ui()
    
    def _switch_to_team_stats(self):
        """Switch to team statistics"""
        self.stat_type = "team"
        self.setWindowTitle(f"{self.league} {self.stat_type.title()} Statistics")
        
        # Clear layout and rebuild
        layout = self.layout()
        self._clear_layout(layout)
        self.setup_ui()
    
    def _clear_layout(self, layout):
        """Clear all widgets from layout"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _create_working_statistics_interface(self, layout, available_stats):
        """Create working statistics interface with immediate data display"""
        
        # Split layout: Left side for stat selection, right side for results
        h_layout = QHBoxLayout()
        
        # Left side: Statistics list
        left_widget = QWidget()
        left_widget.setMaximumWidth(300)
        left_layout = QVBoxLayout()
        
        stats_label = QLabel("Select a Statistic:")
        left_layout.addWidget(stats_label)
        
        # Add note about data timeframe  
        if self.league.upper() == "MLB":
            note_label = QLabel("📊 Full Season Statistics")
            note_label.setStyleSheet("color: #0066cc; font-weight: bold; font-size: 9pt;")
        else:
            note_label = QLabel("📊 Note: Shows recent performance leaders")
            note_label.setStyleSheet("color: #666; font-style: italic; font-size: 9pt;")
        note_label.setWordWrap(True)
        left_layout.addWidget(note_label)
        
        self.stats_list = QListWidget()
        self.stats_list.setAccessibleName(f"{self.stat_type.title()} Statistics List")
        self.stats_list.setAccessibleDescription(f"List of available {self.stat_type} statistics. Select one to view rankings.")
        
        # Populate statistics list with ACTUAL available stats (not categories)
        for stat_info in available_stats:
            stat_name = stat_info.get('name', 'Unknown')
            item = QListWidgetItem(stat_name)
            item.setData(Qt.ItemDataRole.UserRole, stat_info)  # Store the actual stat data
            self.stats_list.addItem(item)
        
        # Connect selection events
        self.stats_list.itemActivated.connect(self._on_working_stat_selected)
        self.stats_list.itemClicked.connect(self._on_working_stat_selected)
        
        left_layout.addWidget(self.stats_list)
        left_widget.setLayout(left_layout)
        
        # Right side: Results display
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        
        self.results_label = QLabel("Select a statistic to view rankings")
        right_layout.addWidget(self.results_label)
        
        # Results list (concatenated format: rank team value)
        self.results_list = QListWidget()
        self.results_list.setAccessibleName("Statistics Results List")
        self.results_list.setAccessibleDescription("List showing rankings for the selected statistic")
        self.results_list.hide()  # Hide until stat is selected
        right_layout.addWidget(self.results_list)
        
        right_widget.setLayout(right_layout)
        
        # Add to horizontal layout
        h_layout.addWidget(left_widget)
        h_layout.addWidget(right_widget)
        
        layout.addLayout(h_layout)
        
        # Set the main layout
        self.setLayout(layout)
    
    def _on_working_stat_selected(self, item):
        """Handle stat selection with working approach - data is already loaded"""
        print(f"DEBUG: _on_working_stat_selected called")
        if item:
            stat_info = item.data(Qt.ItemDataRole.UserRole)
            if stat_info:
                print(f"DEBUG: Displaying results for: {stat_info.get('name')}")
                self._display_stat_results(stat_info)
            else:
                print(f"DEBUG: No stat_info in item data")
        else:
            print(f"DEBUG: _on_working_stat_selected called with None item")
    
    def _display_stat_results(self, stat_info):
        """Display results in concatenated list format for the selected statistic"""
        try:
            stat_name = stat_info.get('stat_name', 'Unknown')
            stat_type = stat_info.get('type', 'unknown')
            data = stat_info.get('data', [])
            
            # Update results label with data context
            if stat_type == "player":
                if self.league.upper() == "MLB":
                    header_text = f"Season Leaders: {stat_info.get('name', stat_name)}"
                else:
                    header_text = f"Recent Performance Leaders: {stat_info.get('name', stat_name)}"
            else:
                header_text = f"Top Rankings: {stat_info.get('name', stat_name)}"
            
            self.results_label.setText(header_text)
            
            # Clear and show results list
            self.results_list.clear()
            self.results_list.show()
            
            # Display in concatenated list format
            if stat_type == "player":
                self._setup_player_results_list(data, stat_name)
            elif stat_type == "team":
                self._setup_team_results_list(data, stat_name)
            
        except Exception as e:
            print(f"ERROR in _display_stat_results: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _setup_player_results_list(self, data, stat_name):
        """Setup concatenated list view for player statistics results"""
        
        def safe_float_convert(value):
            """Safely convert value to float for sorting"""
            try:
                if isinstance(value, (int, float)):
                    return float(value)
                
                value_str = str(value).strip()
                if not value_str or value_str.lower() in ['none', 'n/a', '']:
                    return 0.0
                
                # Handle fraction format like "1-1"
                if '-' in value_str and value_str.count('-') == 1:
                    parts = value_str.split('-')
                    if len(parts) == 2:
                        try:
                            return float(parts[0]) / max(1, float(parts[1]))
                        except (ValueError, ZeroDivisionError):
                            return 0.0
                
                return float(value_str)
            except (ValueError, TypeError):
                return 0.0
        
        # Convert data to proper format with numeric sorting
        converted_data = []
        for item in data:
            player_name = item.get('player_name', 'Unknown')
            team = item.get('team', '')
            value = item.get('value', '')
            
            numeric_value = safe_float_convert(value)
            converted_data.append({
                'name': f"{player_name} ({team})" if team else player_name,
                'value': numeric_value,
                'display_value': str(value)
            })
        
        # Sort by numeric value (descending for most stats)
        converted_data.sort(key=lambda x: x['value'], reverse=True)
        
        # Populate the list with rank
        for rank, item in enumerate(converted_data, 1):
            list_text = f"{rank} {item['name']} {item['display_value']}"
            list_item = QListWidgetItem(list_text)
            self.results_list.addItem(list_item)
        
        # Set focus to first item in results list
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self.results_list.setFocus()  # Move focus to results list
    
    def _setup_team_results_list(self, data, stat_name):
        """Setup concatenated list view for team statistics results"""
        
        # Sort data by numeric value (descending for most stats)
        sorted_data = sorted(data, key=lambda x: x.get('value', 0), reverse=True)
        
        # Populate the list with rank
        for rank, item in enumerate(sorted_data, 1):
            team_name = item.get('name', 'Unknown')
            display_value = item.get('displayValue', str(item.get('value', '')))
            list_text = f"{rank} {team_name} {display_value}"
            list_item = QListWidgetItem(list_text)
            self.results_list.addItem(list_item)
        
        # Set focus to first item in results list
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self.results_list.setFocus()  # Move focus to results list
    
    def _get_stat_categories(self):
        """Get available stat categories without loading full data"""
        # Return actual individual statistics that users want to see
        if self.league.upper() == "MLB":
            if self.stat_type == "team":
                # Show actual team stats available across all categories
                return [
                    "Batting Average", "Home Runs", "RBIs", "Runs", "Hits", "Doubles", "Triples",
                    "ERA", "Wins", "Strikeouts", "WHIP", "Saves", "Innings Pitched",
                    "Fielding Percentage", "Errors", "Double Plays"
                ]
            else:  # player
                # Based on actual ESPN player stats structure
                return [
                    "Batting Average", "Home Runs", "RBIs", "Runs", "OPS", "On Base Percentage", "Slugging Percentage",
                    "ERA", "Wins", "Strikeouts", "WHIP", "Saves", "Quality Starts", "Opponent Batting Average",
                    "Stolen Bases", "Hits", "Holds", "MLB Rating", "Average Game Score", "Wins Above Replacement"
                ]
        elif self.league.upper() == "NFL":
            if self.stat_type == "team":
                return [
                    "Total Yards", "Passing Yards", "Rushing Yards", "Points For", "Points Against",
                    "Turnovers", "Third Down Efficiency", "Red Zone Efficiency"
                ]
            else:  # player
                return [
                    "Passing Yards", "Passing TDs", "Rushing Yards", "Rushing TDs",
                    "Receiving Yards", "Receiving TDs", "Tackles", "Sacks", "Interceptions"
                ]
        elif self.league.upper() == "NBA":
            if self.stat_type == "team":
                return [
                    "Points Per Game", "Field Goal %", "Three Point %", "Free Throw %",
                    "Rebounds", "Assists", "Steals", "Blocks", "Turnovers"
                ]
            else:  # player
                return [
                    "Points Per Game", "Field Goal %", "Three Point %", "Free Throw %",
                    "Rebounds", "Assists", "Steals", "Blocks", "Minutes"
                ]
        else:
            # Generic categories for other leagues
            return ["Points", "Wins", "Goals", "Assists"] if self.stat_type == "team" else ["Points", "Goals", "Assists", "Games"]
    
    def _get_available_statistics(self):
        """Extract available statistics from the data"""
        print(f"DEBUG: _get_available_statistics called for {self.stat_type}")
        
        if not self.statistics_data:
            print(f"DEBUG: No statistics_data available")
            return []
        
        available_stats = []
        
        if self.stat_type == "player":
            player_stats = self.statistics_data.get("player_stats", [])
            print(f"DEBUG: Found {len(player_stats)} player stat categories")
            
            # Handle new MLB API format vs old ESPN format
            for i, category in enumerate(player_stats):
                # Check if this is the new MLB API format
                if 'leaders' in category and 'name' in category:
                    # New MLB API format
                    stat_name = category.get('name', 'Unknown')
                    leaders = category.get('leaders', [])
                    
                    print(f"DEBUG: MLB Category {i}: {stat_name} with {len(leaders)} leaders")
                    
                    # Convert MLB format to expected format
                    converted_leaders = []
                    for leader in leaders:
                        converted_leaders.append({
                            'player_name': leader.get('name', 'Unknown'),
                            'stat_value': leader.get('value', 0),
                            'value': leader.get('value', 0),  # Also add 'value' key for compatibility
                            'team': leader.get('team', 'N/A'),
                            'position': leader.get('position', None)
                        })
                    
                    available_stats.append({
                        'name': stat_name,
                        'category': 'MLB Stats',
                        'stat_name': stat_name,
                        'data': converted_leaders,
                        'type': 'player'
                    })
                    print(f"DEBUG: Added MLB stat: {stat_name} with {len(converted_leaders)} players")
                    
                else:
                    # Old ESPN API format
                    category_name = category.get("category", "Unknown")
                    stats_list = category.get("stats", [])
                    print(f"DEBUG: ESPN Category {i}: {category_name} with {len(stats_list)} stats")
                    
                    # Group by stat types
                    stat_types = {}
                    for stat in stats_list:
                        stat_name = stat.get("stat_name", "Unknown")
                        if stat_name not in stat_types:
                            stat_types[stat_name] = []
                        stat_types[stat_name].append(stat)
                    
                    # Add each unique stat type
                    for stat_name, stats in stat_types.items():
                        # Avoid duplicate names when category and stat name are the same
                        if stat_name.lower() == category_name.lower():
                            display_name = stat_name  # Just use the stat name
                        else:
                            display_name = f"{stat_name} ({category_name})"  # Include category for clarity
                        
                        available_stats.append({
                            'name': display_name,
                            'category': category_name,
                            'stat_name': stat_name,
                            'data': stats,
                            'type': 'player'
                        })
                        print(f"DEBUG: Added ESPN stat: {display_name} with {len(stats)} players")
        
        elif self.stat_type == "team":
            team_stats = self.statistics_data.get("team_stats", [])
            print(f"DEBUG: Found {len(team_stats)} team stat categories")
            for category in team_stats:
                category_name = category.get("category", "Unknown")
                teams_list = category.get("stats", [])
                
                if teams_list:
                    # Get all stat names from first team
                    first_team = teams_list[0]
                    team_stats_dict = first_team.get("stats", {})
                    
                    for stat_name in team_stats_dict.keys():
                        # Process the teams data for this specific stat
                        teams_data = []
                        for team_info in teams_list:
                            team_name = team_info.get("team_name", "Unknown")
                            team_stats_dict = team_info.get("stats", {})
                            
                            if stat_name in team_stats_dict:
                                stat_value = team_stats_dict[stat_name]
                                
                                # Try to convert to numeric for sorting
                                numeric_value = 0
                                try:
                                    numeric_value = float(stat_value)
                                except (ValueError, TypeError):
                                    pass
                                
                                teams_data.append({
                                    "name": team_name,
                                    "value": numeric_value,
                                    "displayValue": str(stat_value)
                                })
                        
                        # Sort teams by value (descending for most stats)
                        teams_data.sort(key=lambda x: x["value"], reverse=True)
                        
                        available_stats.append({
                            'name': f"{stat_name} ({category_name})",
                            'category': category_name,
                            'stat_name': stat_name,
                            'data': teams_data,  # Pre-processed data ready for display
                            'type': 'team'
                        })
                        print(f"DEBUG: Added team stat: {stat_name} ({category_name}) with {len(teams_data)} teams")
        
        print(f"DEBUG: Total available stats: {len(available_stats)}")
        return available_stats
    
    def _on_stat_selected(self, item):
        """Handle when a statistic is clicked (mouse click)"""
        print(f"DEBUG: _on_stat_selected called with item: {item}")
        if item:
            category_info = item.data(Qt.ItemDataRole.UserRole)
            print(f"DEBUG: category_info: {category_info}")
            if category_info:
                print(f"DEBUG: About to load data for category: {category_info.get('category')}")
                try:
                    # Load data on demand
                    stat_info = self._load_stat_data_for_category(category_info.get('category'))
                    if stat_info:
                        self._display_stat_results(stat_info)
                        print(f"DEBUG: _display_stat_results completed successfully")
                    else:
                        print(f"DEBUG: No stat_info returned for category")
                except Exception as e:
                    print(f"DEBUG: Exception in _on_stat_selected: {str(e)}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"DEBUG: No category_info found in item data")
        else:
            print(f"DEBUG: _on_stat_selected called with None item")
    
    def _on_stat_activated(self, item):
        """Handle when a statistic is activated (Enter key or double-click)"""
        print(f"DEBUG: _on_stat_activated called")
        self._on_stat_selected(item)  # Use same logic
    
    def _load_stat_data_for_category(self, category):
        """Load statistics data for a specific category on demand"""
        # Show loading message
        if hasattr(self, 'results_label'):
            self.results_label.setText(f"Loading {category}...")
        
        # Load full data if not already loaded
        if not self.statistics_data:
            try:
                print(f"DEBUG: Loading statistics data for {self.league}")
                self.statistics_data = ApiService.get_statistics(self.league)
            except Exception as e:
                print(f"DEBUG: Exception loading statistics data: {str(e)}")
                if hasattr(self, 'results_label'):
                    self.results_label.setText(f"Error loading data: {str(e)}")
                return None
        
        if not self.statistics_data:
            print(f"DEBUG: No statistics data available")
            if hasattr(self, 'results_label'):
                self.results_label.setText("No statistics data available")
            return None
        
        # Find matching statistics for the category
        return self._find_stat_for_category(category)
    
    def _find_stat_for_category(self, category):
        """Find the best matching statistic for a given category"""
        if self.stat_type == "team":
            team_stats = self.statistics_data.get("team_stats", [])
            
            # Search across all team stat categories for the specific stat
            for stat_category in team_stats:
                category_name = stat_category.get("category", "")
                teams_in_category = stat_category.get("stats", [])
                
                if teams_in_category:
                    # Get the first team's stats to see what's available
                    first_team = teams_in_category[0]
                    team_stats_dict = first_team.get("stats", {})
                    
                    # Look for the exact stat name the user wants
                    best_stat_name = None
                    
                    # Direct match
                    if category in team_stats_dict:
                        best_stat_name = category
                    else:
                        # Fuzzy matching
                        for stat_name in team_stats_dict.keys():
                            if (category.lower() in stat_name.lower() or
                                self._is_category_match(category, stat_name, stat_name)):
                                best_stat_name = stat_name
                                break
                    
                    if best_stat_name:
                        # Collect all teams' data for this stat
                        teams_data = []
                        for team_info in teams_in_category:
                            team_name = team_info.get("team_name", "Unknown")
                            team_stats_dict = team_info.get("stats", {})
                            
                            if best_stat_name in team_stats_dict:
                                stat_value = team_stats_dict[best_stat_name]
                                
                                # Try to convert to numeric for sorting
                                numeric_value = 0
                                try:
                                    numeric_value = float(stat_value)
                                except (ValueError, TypeError):
                                    # Keep as string, use 0 for sorting
                                    pass
                                
                                teams_data.append({
                                    "name": team_name,
                                    "value": numeric_value,
                                    "displayValue": str(stat_value)
                                })
                        
                        if teams_data:
                            # Sort teams by value (descending for most stats)
                            teams_data.sort(key=lambda x: x["value"], reverse=True)
                            
                            return {
                                'name': f"{best_stat_name}",
                                'category': category,
                                'stat_name': best_stat_name,
                                'data': teams_data,
                                'type': 'team'
                            }
        
        else:  # player stats
            player_stats = self.statistics_data.get("player_stats", [])
            
            # Player stats structure: [{'category': name, 'stats': [{'player_name': name, 'team': team, 'value': value, 'stat_name': stat}]}]
            for stat_category in player_stats:
                category_name = stat_category.get("category", "")
                stats_list = stat_category.get("stats", [])
                
                if not stats_list:
                    continue
                
                # Check if this category matches what we're looking for
                if (category.lower() in category_name.lower() or
                    self._is_category_match(category, category_name, category_name)):
                    
                    # All stats in this category should be the same stat type
                    # Just use the data as-is since it's already in the right format
                    players_data = []
                    for stat in stats_list:
                        player_name = stat.get("player_name", "Unknown")
                        stat_value = stat.get("value", "")
                        
                        # Try to convert to numeric for sorting
                        numeric_value = 0
                        try:
                            # Handle fraction format like "1-1" 
                            if '-' in str(stat_value) and str(stat_value).count('-') == 1:
                                parts = str(stat_value).split('-')
                                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                    numeric_value = int(parts[0]) / max(1, int(parts[1]))  # Avoid division by zero
                                else:
                                    numeric_value = float(stat_value)
                            else:
                                numeric_value = float(stat_value)
                        except (ValueError, TypeError):
                            # Keep as 0 for sorting if can't convert
                            pass
                        
                        players_data.append({
                            "name": f"{player_name} ({stat.get('team', 'N/A')})",
                            "value": numeric_value,
                            "displayValue": str(stat_value)
                        })
                    
                    if players_data:
                        # Sort players by value (descending for most stats)
                        players_data.sort(key=lambda x: x["value"], reverse=True)
                        
                        return {
                            'name': f"{category_name}",
                            'category': category,
                            'stat_name': category_name,
                            'data': players_data,
                            'type': 'player'
                        }
        
        # If no exact match found, return None
        print(f"DEBUG: No matching stat found for category: {category}")
        return None
    
    def _is_category_match(self, category, stat_name, stat_display_name):
        """Check if a category matches a statistic using fuzzy matching"""
        category_lower = category.lower()
        stat_name_lower = stat_name.lower()
        stat_display_lower = stat_display_name.lower()
        
        # Define mapping for common statistics
        category_mappings = {
            "batting average": ["avg", "average", "batting"],
            "home runs": ["hr", "homerun", "home run"],
            "rbis": ["rbi", "runs batted in"],
            "runs": ["run", "r"],
            "hits": ["hit", "h"],
            "stolen bases": ["sb", "steal", "stolen"],
            "era": ["era", "earned run average"],
            "wins": ["win", "w"],
            "strikeouts": ["so", "k", "strikeout"],
            "whip": ["whip", "walks hits innings"],
            "saves": ["save", "sv"],
            "innings pitched": ["ip", "inning"],
            "passing yards": ["passing", "pass yards"],
            "rushing yards": ["rushing", "rush yards"],
            "receiving yards": ["receiving", "rec yards"],
            "touchdowns": ["td", "touchdown"],
            "points per game": ["ppg", "points"],
            "field goal": ["fg", "field goal"],
            "assists": ["ast", "assist"],
            "rebounds": ["reb", "rebound"],
            "steals": ["stl", "steal"],
            "blocks": ["blk", "block"]
        }
        
        # Check if category has specific mappings
        if category_lower in category_mappings:
            for mapping in category_mappings[category_lower]:
                if mapping in stat_name_lower or mapping in stat_display_lower:
                    return True
        
        return False
    
    def _show_stat_definitions(self):
        """Show statistics definitions dialog"""
        definitions_dialog = StatDefinitionsDialog(self.league, self)
        definitions_dialog.exec()

class StatDefinitionsDialog(QDialog):
    """Dialog showing definitions of statistics for different leagues"""
    
    def __init__(self, league, parent=None):
        super().__init__(parent)
        self.league = league
        self.setWindowTitle(f"{league} Statistics Definitions")
        self.resize(600, 500)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"{self.league} Statistics Definitions")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel("Browse definitions for statistical categories:")
        layout.addWidget(instructions)
        
        # Definitions list
        self.definitions_list = QListWidget()
        self.definitions_list.setAccessibleName("Statistics Definitions")
        
        # Populate definitions
        definitions = self._get_stat_definitions()
        for stat_name, definition in definitions.items():
            item_text = f"{stat_name}: {definition}"
            item = QListWidgetItem(item_text)
            self.definitions_list.addItem(item)
        
        layout.addWidget(self.definitions_list)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def _get_stat_definitions(self):
        """Get statistics definitions for the current league"""
        if self.league.upper() == "MLB":
            return {
                "AVG (Batting Average)": "Hits divided by at bats. Measures how often a batter gets a hit.",
                "HR (Home Runs)": "Number of hits that allow the batter to circle all bases and score.",
                "RBI (Runs Batted In)": "Number of runs that scored as a result of the batter's action.",
                "R (Runs)": "Number of times a player crosses home plate to score.",
                "H (Hits)": "Number of times a batter safely reaches base via a hit.",
                "SB (Stolen Bases)": "Number of bases stolen by advancing while the ball is in play.",
                "ERA (Earned Run Average)": "Average number of earned runs allowed per 9 innings pitched.",
                "W (Wins)": "Number of games won by a pitcher (must be pitcher of record).",
                "K/SO (Strikeouts)": "Number of batters struck out by a pitcher.",
                "WHIP": "Walks plus hits divided by innings pitched. Lower is better.",
                "SV (Saves)": "Number of times a relief pitcher preserved a lead for the win.",
                "IP (Innings Pitched)": "Number of complete innings pitched (outs divided by 3).",
                "OBP (On-Base %)": "Percentage of plate appearances reaching base safely.",
                "SLG (Slugging %)": "Total bases divided by at bats. Measures power hitting.",
                "OPS": "On-base percentage plus slugging percentage. Overall offensive measure."
            }
        elif self.league.upper() == "NFL":
            return {
                "Passing Yards": "Total yards gained through forward passes.",
                "Passing TDs": "Number of touchdown passes thrown by a quarterback.",
                "Rushing Yards": "Total yards gained by running with the football.",
                "Rushing TDs": "Number of touchdowns scored by running the ball.",
                "Receiving Yards": "Total yards gained from catching passes.",
                "Receiving TDs": "Number of touchdowns scored by catching passes.",
                "Tackles": "Number of times a defensive player brings down the ball carrier.",
                "Sacks": "Number of times the quarterback is tackled behind the line.",
                "Interceptions": "Number of passes caught by the opposing defense.",
                "Completion %": "Percentage of pass attempts that were completed.",
                "QBR (Quarterback Rating)": "Composite statistic measuring quarterback performance.",
                "Total Yards": "Combined offensive yards (passing + rushing).",
                "Points For": "Total points scored by a team.",
                "Points Against": "Total points allowed by a team's defense.",
                "Turnovers": "Number of times possession was lost (fumbles + interceptions).",
                "3rd Down %": "Percentage of third down attempts converted for first downs."
            }
        elif self.league.upper() == "NBA":
            return {
                "PPG (Points Per Game)": "Average number of points scored per game.",
                "FG% (Field Goal %)": "Percentage of field goal attempts made.",
                "3P% (Three Point %)": "Percentage of three-point attempts made.",
                "FT% (Free Throw %)": "Percentage of free throw attempts made.",
                "RPG (Rebounds Per Game)": "Average number of rebounds per game.",
                "APG (Assists Per Game)": "Average number of assists per game.",
                "SPG (Steals Per Game)": "Average number of steals per game.",
                "BPG (Blocks Per Game)": "Average number of blocks per game.",
                "TOV (Turnovers)": "Number of times possession was lost.",
                "MPG (Minutes Per Game)": "Average playing time per game.",
                "PER (Player Efficiency Rating)": "Overall player productivity rating.",
                "TS% (True Shooting %)": "Shooting efficiency including free throws and 3-pointers.",
                "USG% (Usage Rate)": "Percentage of team plays used by a player.",
                "ORtg (Offensive Rating)": "Points produced per 100 possessions.",
                "DRtg (Defensive Rating)": "Points allowed per 100 possessions."
            }
        else:
            return {
                "Points": "Total points scored by team or individual player.",
                "Wins": "Number of games or matches won.",
                "Goals": "Number of goals scored (varies by sport).",
                "Assists": "Number of assists made to help teammates score.",
                "Games": "Number of games or matches played.",
                "Average": "Mean value across all games or attempts."
            }
    
    def keyPressEvent(self, event):
        """Handle Escape key to close dialog"""
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class StatisticsDialog(QDialog):
    """Dialog for displaying league statistics with player and team stats"""
    
    def __init__(self, statistics_data: Dict, league: str, parent=None):
        super().__init__(parent)
        self.statistics_data = statistics_data
        self.league = league
        self.setWindowTitle(f"{league} Statistics")
        self.resize(900, 600)
        self.tab_widget: QTabWidget | None = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        player_stats = self.statistics_data.get("player_stats", [])
        team_stats = self.statistics_data.get("team_stats", [])
        
        if not player_stats and not team_stats:
            layout.addWidget(QLabel(f"No statistics data available for {self.league}."))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)
            self.setLayout(layout)
            return
        
        # Create tab widget for Player/Team separation
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Statistics")
        self.tab_widget.setAccessibleDescription("Statistics data with player and team tabs. Use Left/Right arrow keys to navigate tabs.")
        self.tab_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Add Player Statistics tab
        if player_stats:
            player_widget = self._create_player_stats_widget(player_stats)
            self.tab_widget.addTab(player_widget, "Player Statistics")
        
        # Add Team Statistics tab  
        if team_stats:
            team_widget = self._create_team_stats_widget(team_stats)
            self.tab_widget.addTab(team_widget, "Team Statistics")
        
        layout.addWidget(self.tab_widget)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        
        # Set focus
        QTimer.singleShot(100, lambda: self.tab_widget.setFocus())
    
    def _create_player_stats_widget(self, player_stats: List) -> QWidget:
        """Create widget for player statistics using accessible tables"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        if not player_stats:
            layout.addWidget(QLabel("No player statistics available."))
            widget.setLayout(layout)
            return widget
        
        # Create a tab widget for different player stat categories
        category_tabs = QTabWidget()
        category_tabs.setAccessibleName("Player Statistics Categories")
        category_tabs.setAccessibleDescription("Statistics organized by category. Use Ctrl+Tab to switch between categories.")
        
        for category in player_stats:
            category_name = category.get("category", "Unknown")
            stats_list = category.get("stats", [])
            
            if not stats_list:
                continue
            
            # Create table for this category
            table = QTableWidget()
            table.setAccessibleName(f"{category_name} Statistics Table")
            table.setAccessibleDescription(f"Table showing {category_name} statistics. Use arrow keys to navigate cells.")
            
            # Set up table structure
            table.setRowCount(len(stats_list))
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Player", "Team", "Statistic", "Value"])
            
            # Enable sorting and selection
            table.setSortingEnabled(True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            
            # Populate table data
            for row, stat in enumerate(stats_list):
                player_name = stat.get("player_name", "Unknown")
                team = stat.get("team", "")
                stat_name = stat.get("stat_name", "")
                value = str(stat.get("value", ""))
                
                # Create table items with accessibility info
                player_item = QTableWidgetItem(player_name)
                player_item.setToolTip(f"Player: {player_name}")
                
                team_item = QTableWidgetItem(team)
                team_item.setToolTip(f"Team: {team}")
                
                stat_item = QTableWidgetItem(stat_name)
                stat_item.setToolTip(f"Statistic: {stat_name}")
                
                value_item = QTableWidgetItem(value)
                value_item.setToolTip(f"Value: {value}")
                
                table.setItem(row, 0, player_item)
                table.setItem(row, 1, team_item)
                table.setItem(row, 2, stat_item)
                table.setItem(row, 3, value_item)
            
            # Auto-resize columns to content
            table.resizeColumnsToContents()
            
            # Add table to category tabs
            category_tabs.addTab(table, category_name)
        
        layout.addWidget(category_tabs)
        widget.setLayout(layout)
        return widget
    
    def _create_team_stats_widget(self, team_stats: List) -> QWidget:
        """Create widget for team statistics using accessible tables"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        if not team_stats:
            layout.addWidget(QLabel("Team statistics not available yet."))
            layout.addWidget(QLabel("(Feature will be enhanced in future updates)"))
            widget.setLayout(layout)
            return widget
        
        # Create a tab widget for different team stat categories
        category_tabs = QTabWidget()
        category_tabs.setAccessibleName("Team Statistics Categories")
        category_tabs.setAccessibleDescription("Team statistics organized by category. Use Ctrl+Tab to switch between categories.")
        
        for category in team_stats:
            category_name = category.get("category", "Unknown")
            teams_list = category.get("stats", [])
            
            if not teams_list:
                continue
            
            # Get all unique stat names across all teams in this category
            all_stat_names = set()
            for team_data in teams_list:
                team_stats_dict = team_data.get("stats", {})
                all_stat_names.update(team_stats_dict.keys())
            
            stat_names = sorted(list(all_stat_names))
            
            # Create table for this category
            table = QTableWidget()
            table.setAccessibleName(f"{category_name} Team Statistics Table")
            table.setAccessibleDescription(f"Table showing team {category_name} statistics. Use arrow keys to navigate cells.")
            
            # Set up table structure: Team name + all stat columns
            table.setRowCount(len(teams_list))
            table.setColumnCount(1 + len(stat_names))
            
            headers = ["Team"] + stat_names
            table.setHorizontalHeaderLabels(headers)
            
            # Enable sorting and selection
            table.setSortingEnabled(True)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            
            # Populate table data
            for row, team_data in enumerate(teams_list):
                team_name = team_data.get("team_name", "Unknown Team")
                team_stats_dict = team_data.get("stats", {})
                
                # Set team name in first column
                team_item = QTableWidgetItem(team_name)
                team_item.setToolTip(f"Team: {team_name}")
                table.setItem(row, 0, team_item)
                
                # Set stat values in subsequent columns
                for col, stat_name in enumerate(stat_names, 1):
                    stat_value = team_stats_dict.get(stat_name, "N/A")
                    
                    stat_item = QTableWidgetItem(str(stat_value))
                    stat_item.setToolTip(f"{team_name} {stat_name}: {stat_value}")
                    table.setItem(row, col, stat_item)
            
            # Auto-resize columns to content
            table.resizeColumnsToContents()
            
            # Add table to category tabs
            category_tabs.addTab(table, category_name)
        
        layout.addWidget(category_tabs)
        widget.setLayout(layout)
        return widget
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class SimpleTeamsDialog(QDialog):
    """Simple teams dialog with tabs for divisions"""
    
    def __init__(self, teams_data: List, league: str, parent=None):
        super().__init__(parent)
        self.teams_data = teams_data
        self.league = league
        self.setWindowTitle(f"{league} Teams")
        self.resize(600, 400)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setAccessibleName("Team Information")
        self.tab_widget.setAccessibleDescription("Team information by division, use arrow keys to navigate between divisions")
        self.tab_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tab_widget.setUsesScrollButtons(False)  # Disable scroll buttons as requested
        
        # Group teams by division
        divisions = {}
        for team in self.teams_data:
            div = team.get('division', 'Other')
            if div == 'League':  # Skip generic league designation
                continue
            if div not in divisions:
                divisions[div] = []
            divisions[div].append(team)
        
        # Create tabs for each division
        if self.league == "MLB":
            division_order = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]
        elif self.league == "NFL":
            division_order = ["AFC East", "AFC North", "AFC South", "AFC West", 
                            "NFC East", "NFC North", "NFC South", "NFC West"]
        elif self.league == "NBA":
            division_order = ["Atlantic", "Central", "Southeast", "Northwest", "Pacific", "Southwest"]
        elif self.league == "NCAAF":
            # Use actual ESPN conference names
            division_order = ["Southeastern Conference", "Big Ten Conference", "Big 12 Conference", 
                            "Atlantic Coast Conference", "Pac-12 Conference", "American Conference", 
                            "Conference USA", "Mid-American Conference", "Mountain West Conference", 
                            "FBS Independents"]
        elif self.league in ["NCAAB", "NCAAM", "NCAAW"]:
            # College basketball conferences (major conferences first)
            division_order = ["Southeastern Conference", "Big Ten Conference", "Big 12 Conference",
                            "Atlantic Coast Conference", "Pac-12 Conference", "Big East Conference",
                            "American Conference", "Conference USA", "Mid-American Conference",
                            "Mountain West Conference", "Atlantic 10 Conference", "Missouri Valley Conference",
                            "West Coast Conference", "Ivy League", "Colonial Conference", 
                            "Southern Conference", "Ohio Valley Conference", "Big Sky Conference"]
        elif self.league == "WNBA":
            # WNBA has Eastern and Western conferences
            division_order = ["Eastern Conference", "Western Conference"]
        else:
            division_order = []
        
        # Add tabs in order
        for div_name in division_order:
            if div_name in divisions:
                self.create_division_tab(div_name, divisions[div_name])
        
        # Add any remaining divisions not in the standard order
        for div_name, teams in divisions.items():
            if div_name not in division_order:
                self.create_division_tab(div_name, teams)
        
        layout.addWidget(self.tab_widget)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        
        # Set focus on first tab
        if self.tab_widget.count() > 0:
            first_widget = self.tab_widget.widget(0)
            if hasattr(first_widget, 'teams_table'):
                first_widget.teams_table.setFocus()
    
    def keyPressEvent(self, event):
        """Handle key press events to keep focus in tab widget for left/right arrows"""
        key = event.key()
        
        # Handle left/right arrows to stay in tab widget
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            # Ensure focus stays on tab widget navigation
            self.tab_widget.setFocus()
            current_index = self.tab_widget.currentIndex()
            
            if key == Qt.Key.Key_Left:
                new_index = current_index - 1 if current_index > 0 else self.tab_widget.count() - 1
            else:  # Right arrow
                new_index = current_index + 1 if current_index < self.tab_widget.count() - 1 else 0
            
            self.tab_widget.setCurrentIndex(new_index)
            return
        
        # For all other keys, use default behavior
        super().keyPressEvent(event)
    
    def create_division_tab(self, division_name: str, teams: List):
        """Create a tab for a division with team table"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Create accessible table instead of list widget
        teams_table = AccessibleTable(
            parent=self,
            accessible_name=f"{division_name} Teams Table",
            accessible_description=f"Teams in {division_name} division with wins, losses, and other statistics"
        )
        
        # Set up table headers - include Ties for NFL
        if self.league == "NFL":
            headers = ["Team", "Wins", "Losses", "Ties", "Win %"]
        else:
            headers = ["Team", "Wins", "Losses", "Win %"]
        teams_table.setColumnCount(len(headers))
        teams_table.setHorizontalHeaderLabels(headers)
        
        # Sort teams by wins (descending), then by name (ascending) - ensure stable sort
        def sort_key(team):
            wins = team.get('wins', 0)
            name = team.get('team_name', 'Unknown Team')
            team_id = team.get('team_id', '')  # Add team_id for stable sorting
            # Return negative wins for descending order, then name for ascending, then ID for stability
            return (-wins, name, team_id)
        
        sorted_teams = sorted(teams, key=sort_key)
        
        # Set table row count
        teams_table.setRowCount(len(sorted_teams))
        
        # Populate table with team data
        for row, team in enumerate(sorted_teams):
            name = team.get('team_name', 'Unknown Team')
            wins = team.get('wins', 0)
            losses = team.get('losses', 0)
            ties = team.get('ties', 0)
            
            # Calculate win percentage - NFL counts ties as half a win
            if self.league == "NFL" and ties > 0:
                total_games = wins + losses + ties
                # NFL formula: (wins + 0.5 * ties) / total_games
                win_pct = (wins + 0.5 * ties) / total_games if total_games > 0 else 0.0
            else:
                total_games = wins + losses
                win_pct = wins / total_games if total_games > 0 else 0.0
            
            # Create table items
            name_item = QTableWidgetItem(name)
            wins_item = QTableWidgetItem(str(wins))
            losses_item = QTableWidgetItem(str(losses))
            win_pct_item = QTableWidgetItem(f"{win_pct:.3f}")
            
            # Store team data in the name item for potential future use
            name_item.setData(Qt.ItemDataRole.UserRole, team)
            
            # Set items in table - include ties for NFL
            if self.league == "NFL":
                ties_item = QTableWidgetItem(str(ties))
                teams_table.setItem(row, 0, name_item)
                teams_table.setItem(row, 1, wins_item)
                teams_table.setItem(row, 2, losses_item)
                teams_table.setItem(row, 3, ties_item)
                teams_table.setItem(row, 4, win_pct_item)
            else:
                teams_table.setItem(row, 0, name_item)
                teams_table.setItem(row, 1, wins_item)
                teams_table.setItem(row, 2, losses_item)
                teams_table.setItem(row, 3, win_pct_item)
        
        # Configure table appearance
        header = teams_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Team name stretches
        
        # Set focus to first cell when table is created
        if teams_table.rowCount() > 0:
            teams_table.setCurrentCell(0, 0)
        
        # Connect table activation signal for team selection
        teams_table.itemActivated.connect(self.on_team_selected)
        
        layout.addWidget(teams_table)
        widget.setLayout(layout)
        
        # Store reference to table for focus management
        widget.teams_table = teams_table
        
        self.tab_widget.addTab(widget, division_name)
    
    def on_team_selected(self, item):
        """Handle team selection - open schedule view"""
        team_data = item.data(Qt.ItemDataRole.UserRole)
        if not team_data:
            return
            
        team_name = team_data.get('team_name', 'Unknown Team')
        
        # Open schedule dialog
        schedule_dialog = TeamScheduleDialog(team_data, self.league, self)
        schedule_dialog.exec()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class VenuesDialog(QDialog):
    """Dialog for browsing stadiums and venues by league"""
    
    def __init__(self, venues_data: Dict, league: str, parent=None):
        super().__init__(parent)
        self.venues_data = venues_data
        self.league = league
        self.setWindowTitle(f"{league} Venues")
        self.resize(800, 600)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Header with venue count
        venue_count = len(self.venues_data)
        header_label = QLabel(f"{self.league} Stadiums and Venues ({venue_count} total)")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
        layout.addWidget(header_label)
        
        # Create list widget for venues
        self.venues_list = QListWidget()
        self.venues_list.setAccessibleName(f"{self.league} Venues List")
        self.venues_list.setAccessibleDescription(f"List of {self.league} stadiums and venues. Press Enter for detailed information.")
        self.venues_list.itemActivated.connect(self.on_venue_selected)
        
        # Sort venues by name for easier browsing
        sorted_venues = sorted(self.venues_data.values(), key=lambda x: x.get('name', ''))
        
        # Add venues to list with summary info
        for venue in sorted_venues:
            venue_name = venue.get('name', 'Unknown Venue')
            city = venue.get('city', 'Unknown')
            state = venue.get('state', 'Unknown')
            
            # Add visual indicators for venue characteristics
            indicators = []
            if venue.get('indoor'):
                indicators.append("Indoor")
            else:
                indicators.append("Outdoor")
            
            if venue.get('grass') is True:
                indicators.append("Grass")
            elif venue.get('grass') is False:
                indicators.append("Turf")
            else:
                indicators.append("Unknown Surface")
            
            # Show home teams if available
            home_teams = venue.get('home_teams', [])
            team_info = ""
            if home_teams:
                if len(home_teams) == 1:
                    team_info = f" - {home_teams[0].get('name', 'Unknown Team')}"
                else:
                    team_info = f" - {len(home_teams)} teams"
            
            # Format: "Stadium Name (City, State) [Indoor, Grass] - Team Name" 
            surface_info = " | ".join(indicators)
            display_text = f"{venue_name} ({city}, {state}) [{surface_info}]{team_info}"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, venue)
            self.venues_list.addItem(item)
        
        layout.addWidget(self.venues_list)
        
        # Add close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        
        layout.addLayout(close_layout)
        self.setLayout(layout)
        
        # Set focus to venues list
        self.venues_list.setFocus()
        if self.venues_list.count() > 0:
            self.venues_list.setCurrentRow(0)
    
    def on_venue_selected(self, item):
        """Show detailed venue information dialog"""
        venue_data = item.data(Qt.ItemDataRole.UserRole)
        if not venue_data:
            return
        
        # Get detailed venue information
        venue_id = venue_data.get('id')
        league_key = self.league.lower()
        venue_details = venue_service.get_venue_details(venue_id, league_key)
        
        if not venue_details:
            QMessageBox.information(self, "Venue Details", "No detailed information available for this venue.")
            return
        
        # Show venue details dialog
        details_dialog = VenueDetailsDialog(venue_details, self)
        details_dialog.exec()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class VenueDetailsDialog(QDialog):
    """Dialog showing detailed information about a specific venue"""
    
    def __init__(self, venue_details: Dict, parent=None):
        super().__init__(parent)
        self.venue_details = venue_details
        basic_info = venue_details.get('basic_info', {})
        venue_name = basic_info.get('name', 'Unknown Venue')
        self.setWindowTitle(f"{venue_name} - Details")
        self.resize(600, 500)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Create list widget for venue details
        self.details_list = QListWidget()
        
        # Get venue information sections
        basic_info = self.venue_details.get('basic_info', {})
        characteristics = self.venue_details.get('characteristics', {})
        home_teams = self.venue_details.get('home_teams', [])
        interesting_facts = self.venue_details.get('interesting_facts', [])
        media = self.venue_details.get('media', {})
        images = media.get('images', [])
        
        # Venue name header
        venue_name = basic_info.get('name', 'Unknown Venue')
        self.details_list.addItem(QListWidgetItem(f"=== {venue_name} ==="))
        self.details_list.addItem(QListWidgetItem(""))
        
        # Basic Information Section
        self.details_list.addItem(QListWidgetItem("--- Basic Information ---"))
        if basic_info.get('city') and basic_info.get('state'):
            self.details_list.addItem(QListWidgetItem(f"Location: {basic_info['city']}, {basic_info['state']}"))
        if basic_info.get('league'):
            self.details_list.addItem(QListWidgetItem(f"League: {basic_info['league']}"))
        if basic_info.get('zip_code'):
            self.details_list.addItem(QListWidgetItem(f"ZIP Code: {basic_info['zip_code']}"))
        self.details_list.addItem(QListWidgetItem(""))
        
        # Characteristics Section
        if characteristics:
            self.details_list.addItem(QListWidgetItem("--- Stadium Characteristics ---"))
            if characteristics.get('indoor') is not None:
                venue_type = "Indoor stadium" if characteristics['indoor'] else "Outdoor stadium"
                self.details_list.addItem(QListWidgetItem(f"Type: {venue_type}"))
            
            if characteristics.get('grass') is not None:
                if characteristics['grass']:
                    self.details_list.addItem(QListWidgetItem("Playing Surface: Natural grass"))
                else:
                    self.details_list.addItem(QListWidgetItem("Playing Surface: Artificial turf"))
            
            if characteristics.get('capacity'):
                try:
                    capacity = int(characteristics['capacity'])
                    self.details_list.addItem(QListWidgetItem(f"Capacity: {capacity:,} fans"))
                except (ValueError, TypeError):
                    self.details_list.addItem(QListWidgetItem(f"Capacity: {characteristics['capacity']}"))
            self.details_list.addItem(QListWidgetItem(""))
        
        # Home Teams Section
        if home_teams:
            self.details_list.addItem(QListWidgetItem("--- Home Teams ---"))
            for team in home_teams:
                team_name = team.get('name', 'Unknown Team')
                team_abbrev = team.get('abbreviation', '')
                if team_abbrev:
                    self.details_list.addItem(QListWidgetItem(f"{team_name} ({team_abbrev})"))
                else:
                    self.details_list.addItem(QListWidgetItem(team_name))
            self.details_list.addItem(QListWidgetItem(""))
        
        # Interesting Facts Section
        if interesting_facts:
            self.details_list.addItem(QListWidgetItem("--- Interesting Facts ---"))
            for fact in interesting_facts:
                self.details_list.addItem(QListWidgetItem(f"• {fact}"))
            self.details_list.addItem(QListWidgetItem(""))
        
        # Images Section
        if images:
            self.details_list.addItem(QListWidgetItem("--- Available Media ---"))
            self.details_list.addItem(QListWidgetItem(f"{len(images)} high-quality images available"))
            # Show first few image types for information
            for i, img in enumerate(images[:3]):
                rel_info = ", ".join(img.get('rel', []))
                if rel_info:
                    self.details_list.addItem(QListWidgetItem(f"  • {rel_info.title()} view"))
            
            if len(images) > 3:
                self.details_list.addItem(QListWidgetItem(f"  • ... and {len(images) - 3} more"))
        
        layout.addWidget(self.details_list)
        
        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        
        layout.addLayout(close_layout)
        self.setLayout(layout)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(event)


class BowlsAndPlayoffsDialog(QDialog):
    """Dialog for viewing NCAA Football Bowl Games and College Football Playoff"""
    
    def __init__(self, league: str, parent=None):
        super().__init__(parent)
        self.league = league
        self.parent_app = parent
        self.setWindowTitle(f"{league} Bowls & Playoffs")
        self.resize(900, 700)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header_label = QLabel("College Football Playoff & Bowl Games")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px 0;")
        layout.addWidget(header_label)
        
        # List of bowl games
        self.bowl_list = QListWidget()
        self.bowl_list.itemActivated.connect(self.on_bowl_game_selected)
        layout.addWidget(self.bowl_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.load_bowl_games()
    
    def load_bowl_games(self):
        """Start loading bowl games and the CFP (postseason, seasontype=3).

        Fetched on a thread: in the dialog's constructor it froze the window
        before the dialog appeared.
        """
        from services.api_service import ApiService
        self.bowl_list.clear()
        self.bowl_list.addItem("Loading bowl games...")
        self.bowl_list.setCurrentRow(0)
        loader = CallLoader(lambda: ApiService.get_scores(self.league, seasontype=3))
        loader.data_loaded.connect(self._on_bowl_games_loaded)
        loader.error_occurred.connect(self._on_bowl_games_error)
        _start_detached_thread(loader)

    def _on_bowl_games_error(self, message):
        self.bowl_list.clear()
        self.bowl_list.addItem(f"Error loading bowl games: {message}")
        self.bowl_list.setCurrentRow(0)

    def _on_bowl_games_loaded(self, games_data):
        had_focus = self.bowl_list.hasFocus()
        self.bowl_list.clear()
        self._show_bowl_games(games_data or [])
        if self.bowl_list.count():
            self.bowl_list.setCurrentRow(0)
        if had_focus:
            self.bowl_list.setFocus()

    def _show_bowl_games(self, games_data):
        """Fill the list from loaded postseason games. No network access."""
        try:
            if not games_data:
                self.bowl_list.addItem("No bowl games or playoff games found.")
                return
            
            # Categorize games by competition type
            categories = {
                'Championship': [],  # type 33
                'Semifinals': [],     # type 35
                'Quarterfinals': [],  # type 40 (Major Bowl)
                'First Round': [],    # type 42 (Bowl Game) - early playoff games
                'Other Bowls': []     # Other bowl games
            }
            
            for game in games_data:
                comp_type = game.get('competitions', [{}])[0].get('type', {}).get('id')
                comp_name = game.get('competitions', [{}])[0].get('type', {}).get('text', '')
                
                if comp_type == 33:  # Championship
                    categories['Championship'].append(game)
                elif comp_type == 35:  # Semifinal
                    categories['Semifinals'].append(game)
                elif comp_type == 40:  # Major Bowl (Quarterfinals)
                    categories['Quarterfinals'].append(game)
                elif comp_type == 42:  # Bowl Game
                    # Check if it's part of CFP or regular bowl
                    notes = game.get('competitions', [{}])[0].get('notes', [])
                    if notes and 'first round' in notes[0].get('headline', '').lower():
                        categories['First Round'].append(game)
                    else:
                        categories['Other Bowls'].append(game)
                else:
                    categories['Other Bowls'].append(game)
            
            # Display categories in order
            for category_name in ['Championship', 'Semifinals', 'Quarterfinals', 'First Round', 'Other Bowls']:
                games = categories[category_name]
                if games:
                    # Add category header
                    header_item = QListWidgetItem(f"=== {category_name} ===")
                    header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
                    font = header_item.font()
                    font.setBold(True)
                    header_item.setFont(font)
                    self.bowl_list.addItem(header_item)
                    
                    # Add games in this category
                    for game in games:
                        self._add_game_item(game)
                    
                    # Add spacing
                    self.bowl_list.addItem("")
        
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to load bowl games: {str(e)}")
    
    def _add_game_item(self, game):
        """Add a game item to the list"""
        from models.game import GameData

        # Get bowl/playoff information
        comp = game.get('competitions', [{}])[0]
        notes = comp.get('notes', [])
        comp_type = comp.get('type', {})
        comp_type_text = comp_type.get('text', '')
        
        # Get bowl name from notes or use competition type
        bowl_name = ''
        if notes and notes[0].get('headline'):
            bowl_name = notes[0].get('headline', '')
        elif comp_type_text and comp_type_text != 'Standard':
            bowl_name = comp_type_text
        
        # Create game data object for display
        game_obj = GameData(game, self.league)
        item_text = game_obj.get_display_text()
        
        # Format with bowl/playoff name prominently at the start
        if bowl_name:
            # Check if it's a playoff game
            comp_type_id = comp_type.get('id')
            if comp_type_id in [33, 35, 40]:  # Championship, Semifinal, Major Bowl (Quarterfinals)
                item_text = f"[{bowl_name}] {item_text}"
            else:
                item_text = f"{bowl_name} - {item_text}"
        
        list_item = QListWidgetItem(item_text)
        list_item.setData(Qt.ItemDataRole.UserRole, game.get("id"))
        self.bowl_list.addItem(list_item)

    def on_bowl_game_selected(self, item):
        """Handle selection of a bowl game"""
        game_id = item.data(Qt.ItemDataRole.UserRole)
        if game_id and self.parent_app and hasattr(self.parent_app, 'parent_app'):
            # Close this dialog and open game details
            self.accept()
            self.parent_app.parent_app.open_game_details(game_id)


class SportsScoresApp(QWidget):
    """Main application class using QStackedWidget for better view management"""
    
    def __init__(self, startup_params=None):
        super().__init__()
        self.setWindowTitle("Sports Scores")
        
        # Initialize window title tracking
        self.base_title = "Sports Scores"
        self.current_context = []  # Stack for building breadcrumb-style titles
        
        # Set proper window sizing behavior
        self.setMinimumSize(500, 300)  # Minimum usable size
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)  # Initial size
        
        # Enable proper window controls and resizing
        self.setWindowFlags(Qt.WindowType.Window | 
                           Qt.WindowType.WindowMinimizeButtonHint | 
                           Qt.WindowType.WindowMaximizeButtonHint | 
                           Qt.WindowType.WindowCloseButtonHint)
        
        # Allow the window to be resizable
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Application state
        self.config = {}
        self.view_stack = []  # Stack for navigation history
        self.startup_params = startup_params
        
        # Initialize configuration
        self._init_config()
        
        # Setup UI with stacked widget
        self.setup_ui()
        
        # Handle startup navigation
        self._handle_startup_navigation()
        self.show()

        # Automatic update check, once the window is up so it never delays launch.
        QTimer.singleShot(2000, self._maybe_auto_check_updates)

    def _init_config(self):
        try:
            leagues = ApiService.get_leagues()
            for league in leagues:
                # Start with a minimal default config (can be expanded later)
                self.config[league] = ["standings", "leaders", "boxscore", "injuries", "news"]
        except Exception as e:
            print(f"[WARNING] Failed to initialize config: {e}")

    def setup_ui(self):
        """Setup the main UI with QStackedWidget"""
        layout = QVBoxLayout()
        
        # Create stacked widget for view management
        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)
        
        self.setLayout(layout)
    
    def show_home(self):
        """Show the home view"""
        try:
            home_view = HomeView(self)
            home_view.setup_ui()
            self._switch_to_view(home_view, "home", None)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show home view: {str(e)}")
    
    def show_live_scores(self):
        """Show the live scores view"""
        try:
            live_scores_view = LiveScoresView(self)
            self._switch_to_view(live_scores_view, "live_scores", None)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show live scores view: {str(e)}")
    
    def open_league(self, league: str, week: int = None, season_type: int = None):
        """Open a league view, optionally for a specific week (football).

        `season_type` accompanies `week` because football week numbers restart in
        each season type; without it a week is ambiguous. Leave both unset to let
        the view resolve today's week from the season calendar.
        """
        try:
            self._push_to_stack("home", None)
            league_view = LeagueView(self, league, week=week, season_type=season_type)
            self._switch_to_view(league_view, "league", league)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open league: {e}")

    def open_live_scores(self):
        """Open live scores view"""
        try:
            self._push_to_stack("home", None)
            live_scores_view = LiveScoresView(self)
            self._switch_to_view(live_scores_view, "live_scores", None)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open live scores: {e}")

    def open_game_details(self, game_id: str, from_live_scores=False):
        """Open game details view"""
        try:
            # Track where we came from for proper navigation
            if from_live_scores:
                self._push_to_stack("live_scores", None)
            else:
                self._push_to_stack("league", self.current_league if hasattr(self, 'current_league') else None)
            gdv = GameDetailsView(self, getattr(self, 'current_league', None), game_id, None)
            self._switch_to_view(gdv, "game", game_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open game details: {e}")
    
    def open_team_schedule(self, team_id: str, team_name: str, league: str):
        """Open team schedule view"""
        try:
            QMessageBox.information(self, "Team Schedule", 
                                  f"Schedule for {team_name} in {league} would be displayed here.\n"
                                  f"Team ID: {team_id}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open team schedule: {e}")

    def open_teams_directly(self, league: str):
        """Open teams view directly for a specific league"""
        try:
            # Set current league and navigate to teams
            self.current_league = league
            self._show_teams_dialog_directly(league)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open teams for {league}: {e}")

    def open_standings_directly(self, league: str):
        """Open standings view directly for a specific league"""
        try:
            # Set current league and navigate to standings  
            self.current_league = league
            self._show_standings_dialog_directly(league)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open standings for {league}: {e}")

    def _fetch_standings_then(self, league: str, title: str, show):
        """Fetch standings on a thread, then show(data) here.

        Used by the --<sport>-teams / --<sport>-standings startup actions, which
        fetched on the UI thread before their dialog appeared.
        """
        def loaded(data):
            try:
                show(data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to show {title}: {e}")
        loader = CallLoader(lambda: ApiService.get_standings(league))
        loader.data_loaded.connect(loaded)
        loader.error_occurred.connect(
            lambda e: QMessageBox.critical(self, "Error", f"Failed to show {title}: {e}"))
        _start_detached_thread(loader)

    def _show_teams_dialog_directly(self, league: str):
        """Show teams dialog directly without being in a league view"""
        self._fetch_standings_then(
            league, "teams", lambda data: self._open_teams_dialog_directly(league, data))

    def _open_teams_dialog_directly(self, league: str, standings_data):
        try:
            if not standings_data:
                QMessageBox.information(self, "Teams", 
                                      f"No teams data available for {league}.")
                return
            
            # Filter data by league to avoid mixing
            filtered_data = [team for team in standings_data 
                           if self._is_team_for_league(team, league)]
            
            dialog = SimpleTeamsDialog(filtered_data, league, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show teams: {str(e)}")

    def _show_standings_dialog_directly(self, league: str):
        """Show standings dialog directly without being in a league view"""
        self._fetch_standings_then(
            league, "standings", lambda data: self._open_standings_dialog_directly(league, data))

    def _open_standings_dialog_directly(self, league: str, standings_data):
        try:
            if not standings_data:
                QMessageBox.information(self, "Standings", 
                                      f"No standings data available for {league}.")
                return
            
            dialog = StandingsDialog(standings_data, league, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to show standings: {str(e)}")

    def _is_team_for_league(self, team_data: Dict, league: str) -> bool:
        """Check if team belongs to the specified league"""
        # This is a helper method that should already exist in LeagueView
        # We'll implement a simple version here
        try:
            # Look for league indicators in team data
            team_league = team_data.get('league', {}).get('abbreviation', '').upper()
            if team_league == league:
                return True
            
            # Fallback: check parent group info
            parent = team_data.get('parent', {})
            if parent:
                parent_name = parent.get('name', '').upper()
                return league in parent_name
            
            return True  # Default to include if we can't determine
        except:
            return True  # Default to include on error

    def update_window_title(self, context_items=None):
        """Update window title with breadcrumb-style context for accessibility
        
        Args:
            context_items: List of context items from most specific to most general
                          e.g., ["Standings", "MLB"] -> "MLB, Standings - Sports Scores"
                          e.g., ["Yankees vs Red Sox", "MLB"] -> "Yankees vs Red Sox - MLB - Sports Scores"
        """
        if not context_items:
            # Just show base title
            self.setWindowTitle(self.base_title)
            return
            
        # Build title following the pattern: most specific, then general context, then base
        if len(context_items) == 1:
            # Single context item: "{Context} - Sports Scores"
            title = f"{context_items[0]} - {self.base_title}"
        else:
            # Multiple context items: reverse order for breadcrumb
            # Most specific first, then increasingly general
            breadcrumb_parts = list(reversed(context_items))
            title = f"{', '.join(breadcrumb_parts)} - {self.base_title}"
            
        self.setWindowTitle(title)

    def _handle_startup_navigation(self):
        """Handle navigation based on startup parameters"""
        if not self.startup_params:
            # Default: show home view
            self.show_home()
            return
        
        action = self.startup_params.get('action')
        league = self.startup_params.get('league')
        
        if not action:
            self.show_home()
            return
        
        # For actions that don't require a league (like live_scores)
        if action not in ['live_scores'] and not league:
            self.show_home()
            return
        
        try:
            if action == 'live_scores':
                # Navigate directly to Live Scores view
                self.show_live_scores()
            elif action == 'league':
                # Navigate directly to league games view
                self.open_league(league)
            elif action == 'teams':
                # Show home first, then open teams dialog
                self.show_home()
                QTimer.singleShot(100, lambda: self.open_teams_directly(league))
            elif action == 'standings':
                # Show home first, then open standings dialog
                self.show_home()
                QTimer.singleShot(100, lambda: self.open_standings_directly(league))
            else:
                self.show_home()
        except Exception as e:
            QMessageBox.critical(self, "Startup Error", 
                               f"Failed to navigate to {action} for {league}: {str(e)}")
            self.show_home()

    def go_back(self):
        if not self.view_stack:
            return
        try:
            prev = self.view_stack.pop()
            vtype, data = prev.get('type'), prev.get('data')
            if vtype == "home":
                self.show_home(); return
            if vtype == "live_scores":
                self.show_live_scores(); return
            if vtype == "league" and data:
                self._show_league_view(data); return
            if vtype == "teams" and data:
                # Going back from team details -> league (simplified)
                self._show_league_view(data); return
            if vtype == "game" and data:
                # Going back from game details -> league
                if hasattr(self, 'current_league') and self.current_league:
                    self._show_league_view(self.current_league)
                else:
                    self.show_home()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to go back: {e}")

    def _show_league_view(self, data):
        """Helper method to show league view"""
        league_view = LeagueView(self, data)
        self._switch_to_view(league_view, "league", data)

    def _switch_to_view(self, view: BaseView, view_type: str, data: Any):
        # Clear existing widgets
        while self.stacked_widget.count():
            w = self.stacked_widget.widget(0)
            self.stacked_widget.removeWidget(w)
            w.deleteLater()
        self.stacked_widget.addWidget(view)
        self.stacked_widget.setCurrentWidget(view)
        # Track current league
        if view_type == "league" and data:
            self.current_league = data
        if hasattr(view, 'on_show'):
            view.on_show()

    def _push_to_stack(self, view_type: str, data: Any):
        self.view_stack.append({"type": view_type, "data": data})

    # ------------------------------------------------------------- updates

    def _maybe_auto_check_updates(self):
        """Startup check, skipped when running from source or turned off."""
        if updater.is_frozen() and settings.get('auto_check_updates', True):
            self.check_for_updates(manual=False)

    def check_for_updates(self, manual=False):
        """Ask GitHub whether a newer release exists.

        A manual check reports every outcome; the automatic one stays silent
        unless there is an update, so a failed network call never interrupts
        launch.
        """
        if getattr(self, '_update_check_loader', None) and self._update_check_loader.isRunning():
            return
        self._update_check_manual = manual
        self._update_check_loader = UpdateCheckLoader()
        self._update_check_loader.data_loaded.connect(self._on_update_check_done)
        self._update_check_loader.error_occurred.connect(self._on_update_check_error)
        self._update_check_loader.start()
        # A manual check needs visible (and screen-reader announced) feedback that
        # something is happening; the automatic one must stay out of the way.
        self._update_check_progress = None
        if manual:
            progress = QProgressDialog("Checking for updates...", None, 0, 0, self)
            progress.setWindowTitle("Checking for Updates - Sports Scores")
            progress.setAccessibleName("Checking for updates")
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.show()
            self._update_check_progress = progress

    def _close_update_check_progress(self):
        if getattr(self, '_update_check_progress', None):
            self._update_check_progress.close()
            self._update_check_progress = None

    def _on_update_check_done(self, info):
        self._close_update_check_progress()
        if not info:
            if self._update_check_manual:
                QMessageBox.information(
                    self, "No Updates",
                    f"You're up to date (version {__version__}).")
            return
        self._prompt_update(info)

    def _on_update_check_error(self, message):
        self._close_update_check_progress()
        if self._update_check_manual:
            QMessageBox.warning(
                self, "Update Check",
                f"Couldn't check for updates: {message}")

    def _prompt_update(self, info):
        notes = info.get('notes', '')
        if len(notes) > 600:
            notes = notes[:600] + "\n..."

        # No installer asset (or running from source): point at the releases page
        # rather than offering an install this build can't perform.
        if not info.get('url') or not updater.is_frozen():
            answer = QMessageBox.question(
                self, "Update Available",
                f"Scores {info['version']} is available (you have {__version__}).\n\n"
                f"{notes}\n\nOpen the downloads page?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                webbrowser.open(updater.RELEASES_PAGE)
            return

        if updater.installer_running(info['url']):
            # An earlier attempt already launched it; downloading again would
            # fail on the locked file.
            QMessageBox.information(
                self, "Update Available",
                f"The Scores {info['version']} installer is already open. "
                "Switch to it with Alt+Tab to finish the update.")
            return

        relocate = "" if updater.is_installed() else (
            "\n\nThis will install Scores to your user Programs folder; you can "
            "delete the portable copy afterwards.")
        answer = QMessageBox.question(
            self, "Update Available",
            f"Scores {info['version']} is available (you have {__version__}).\n\n"
            f"{notes}\n\nDownload and install now? Scores will close to finish "
            f"installing.{relocate}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._download_update(info)

    def _download_update(self, info):
        self._update_progress = QProgressDialog(
            f"Downloading Scores {info['version']}...", "Cancel", 0, 100, self)
        self._update_progress.setWindowTitle("Downloading Update - Sports Scores")
        self._update_progress.setAccessibleName("Update download progress")
        self._update_progress.setAutoClose(False)
        self._update_progress.setAutoReset(False)
        self._update_progress.setMinimumDuration(0)
        self._update_progress.show()  # shown up front, not on the first chunk

        self._update_download_loader = UpdateDownloadLoader(info['url'])
        self._update_progress.canceled.connect(self._update_download_loader.cancel)
        self._update_download_loader.progress_changed.connect(self._on_update_progress)
        self._update_download_loader.data_loaded.connect(self._on_update_downloaded)
        self._update_download_loader.error_occurred.connect(self._on_update_download_error)
        self._update_download_loader.start()

    def _on_update_progress(self, done, total):
        if total > 0:
            self._update_progress.setValue(int(done * 100 / total))
        else:
            # Unknown length: an indeterminate bar beats a percentage that lies.
            self._update_progress.setRange(0, 0)

    def _on_update_downloaded(self, path):
        self._update_progress.close()
        if not path:
            return  # cancelled
        updater.launch_installer(path)
        QApplication.quit()

    def _on_update_download_error(self, message):
        self._update_progress.close()
        QMessageBox.critical(
            self, "Update", f"The update download failed: {message}")

    def keyPressEvent(self, event):
        # Global back shortcut
        if event.modifiers() == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_B:
            self.go_back(); event.accept(); return
        # Escape key also goes back
        elif event.key() == Qt.Key.Key_Escape:
            self.go_back(); event.accept(); return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Handle window resize events to ensure proper content scaling"""
        super().resizeEvent(event)
        # Ensure the stacked widget takes full advantage of available space
        if hasattr(self, 'stacked_widget'):
            self.stacked_widget.resize(event.size())
            # Notify current view of resize if it has a resize handler
            current_widget = self.stacked_widget.currentWidget()
            if current_widget and hasattr(current_widget, 'handle_resize'):
                current_widget.handle_resize(event.size())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Held for the life of the process so the installer can detect a running copy.
    app._scores_mutex = updater.hold_app_mutex()
    window = SportsScoresApp()
    sys.exit(app.exec())
