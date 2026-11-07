#!/usr/bin/env python3
"""
Pitch Exploration Dialog
========================
A comprehensive pitch exploration interface that opens from the main application's
context menu, replacing the simple 9-position strike zone menu with a full
interactive experience.
"""

import sys
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, 
                            QPushButton, QLabel, QGridLayout, QTreeWidget, 
                            QTreeWidgetItem, QSplitter, QFrame, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QAction
from stereo_audio_mapper import StereoAudioPitchMapper
from simple_audio_mapper import SimpleAudioPitchMapper

class PitchExplorationDialog(QDialog):
    """
    Enhanced pitch exploration dialog that combines strike zone exploration
    with real pitch data from the current game
    """
    
    audio_feedback = pyqtSignal(str)
    audio_error = pyqtSignal(str)
    
    def __init__(self, parent=None, game_pitches=None):
        super().__init__(parent)
        self.setWindowTitle("Pitch Exploration - Strike Zone & Game Data")
        self.setGeometry(200, 200, 1000, 700)
        self.setModal(True)
        
        # Audio system - use stereo with optimized 3.75 multiplier
        self.audio_mapper = StereoAudioPitchMapper(lr_multiplier=3.75)
        
        # Fallback to simple audio if stereo fails
        self.simple_audio = SimpleAudioPitchMapper()
        self.use_stereo = True
        
        # Game pitch data passed from main application
        self.game_pitches = game_pitches or {}
        
        # Strike zone positions (matching our validated system)
        self.strike_zone_positions = {
            'high_left': (100, 50, "High Left"),
            'high_center': (127, 50, "High Center"), 
            'high_right': (155, 50, "High Right"),
            'center_left': (100, 127, "Center Left"),
            'center_center': (127, 127, "Center Center"),
            'center_right': (155, 127, "Center Right"),
            'low_left': (100, 200, "Low Left"),
            'low_center': (127, 200, "Low Center"),
            'low_right': (155, 200, "Low Right")
        }
        
        self.setup_ui()
        self.populate_pitch_data()
        
        # Set initial focus to tree if we have data, otherwise to first sample button
        if self.game_pitches:
            self.pitch_tree.setFocus()
        
        # Connect audio signals
        self.audio_mapper.audio_generated.connect(self.audio_feedback)
        self.audio_mapper.audio_error.connect(self.audio_error)
        self.simple_audio.audio_generated.connect(self.audio_feedback)
        self.simple_audio.audio_error.connect(self.audio_error)
        
        # Setup keyboard shortcuts
        self.setup_shortcuts()
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts for the dialog"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Alt+P for Play Pitch Audio
        self.play_pitch_shortcut = QShortcut(QKeySequence("Alt+P"), self)
        self.play_pitch_shortcut.activated.connect(self.handle_play_pitch_shortcut)
        
        # Alt+S for Play Pitch Sequence
        self.play_sequence_shortcut = QShortcut(QKeySequence("Alt+S"), self)
        self.play_sequence_shortcut.activated.connect(self.handle_play_sequence_shortcut)
    
    def handle_play_pitch_shortcut(self):
        """Handle Alt+P shortcut"""
        current_item = self.pitch_tree.currentItem()
        if not current_item:
            return
            
        item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if item_data and item_data.get('type') == 'pitch':
            self.play_pitch_audio(item_data['data'])
    
    def handle_play_sequence_shortcut(self):
        """Handle Alt+S shortcut"""
        current_item = self.pitch_tree.currentItem()
        if not current_item:
            return
            
        item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        
        # If on a pitch, find the parent at-bat
        if item_data and item_data.get('type') == 'pitch':
            parent_item = current_item.parent()
            if parent_item:
                parent_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
                if parent_data and parent_data.get('type') == 'at_bat':
                    self.play_pitch_sequence(parent_data['pitches'])
        
        # If on an at-bat, play its sequence
        elif item_data and item_data.get('type') == 'at_bat':
            self.play_pitch_sequence(item_data['pitches'])
    
    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("Pitch Exploration Center")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Strike Zone Grid
        self.setup_strike_zone_panel(splitter)
        
        # Right side: Pitch Data Trees
        self.setup_pitch_data_panel(splitter)
        
        # Set splitter proportions
        splitter.setSizes([400, 600])
        
        # Bottom: Audio controls and status
        self.setup_audio_controls(layout)
        
        # Close button
        close_btn = QPushButton("Close Exploration")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
    
    def setup_strike_zone_panel(self, parent):
        """Set up the strike zone exploration panel"""
        zone_widget = QWidget()
        zone_layout = QVBoxLayout(zone_widget)
        
        # Strike zone title
        zone_title = QLabel("Strike Zone Exploration")
        zone_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        zone_layout.addWidget(zone_title)
        
        # 3x3 grid of strike zone positions
        grid_frame = QFrame()
        grid_frame.setFrameStyle(QFrame.Shape.Box)
        grid_layout = QGridLayout(grid_frame)
        
        # Create buttons for each zone position
        self.zone_buttons = {}
        positions = [
            ('high_left', 0, 0), ('high_center', 0, 1), ('high_right', 0, 2),
            ('center_left', 1, 0), ('center_center', 1, 1), ('center_right', 1, 2),
            ('low_left', 2, 0), ('low_center', 2, 1), ('low_right', 2, 2)
        ]
        
        for zone_id, row, col in positions:
            x, y, display_name = self.strike_zone_positions[zone_id]
            btn = QPushButton(display_name)
            btn.setMinimumHeight(60)
            btn.setAccessibleName(f"Strike zone {display_name.lower()}")
            btn.setStatusTip(f"Explore pitches in {display_name.lower()} strike zone")
            
            # Connect to show pitch list for this zone
            btn.clicked.connect(lambda checked, z=zone_id: self.show_zone_pitches(z))
            
            grid_layout.addWidget(btn, row, col)
            self.zone_buttons[zone_id] = btn
        
        zone_layout.addWidget(grid_frame)
        
        # Audio test button
        test_btn = QPushButton("Test Audio at Center")
        test_btn.clicked.connect(lambda: self.play_zone_audio('center_center'))
        zone_layout.addWidget(test_btn)
        
        parent.addWidget(zone_widget)
    
    def setup_pitch_data_panel(self, parent):
        """Set up the pitch data exploration panel"""
        pitch_widget = QWidget()
        pitch_layout = QVBoxLayout(pitch_widget)
        
        # Pitch data title
        pitch_title = QLabel("Game Pitch Data")
        pitch_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        pitch_layout.addWidget(pitch_title)
        
        # Pitch tree widget
        self.pitch_tree = QTreeWidget()
        self.pitch_tree.setHeaderLabels(["Pitch Information", "Location", "Details"])
        self.pitch_tree.setRootIsDecorated(True)
        self.pitch_tree.setAlternatingRowColors(True)
        
        # Add sample game selection buttons above the tree
        sample_layout = QHBoxLayout()
        
        sample_btn1 = QPushButton("Strikeout Looking")
        sample_btn1.setToolTip("Jose Altuve strikes out looking on 4 pitches")
        sample_btn1.clicked.connect(lambda: self.load_sample_at_bat(1))
        sample_layout.addWidget(sample_btn1)
        
        sample_btn2 = QPushButton("Four-Pitch Walk") 
        sample_btn2.setToolTip("Aaron Judge draws a walk after falling behind 0-1")
        sample_btn2.clicked.connect(lambda: self.load_sample_at_bat(2))
        sample_layout.addWidget(sample_btn2)
        
        sample_btn3 = QPushButton("First-Pitch Single")
        sample_btn3.setToolTip("Vladimir Guerrero Jr. singles to left on the second pitch")
        sample_btn3.clicked.connect(lambda: self.load_sample_at_bat(3))
        sample_layout.addWidget(sample_btn3)
        
        pitch_layout.addLayout(sample_layout)
        
        # Context menu for pitch actions
        self.pitch_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pitch_tree.customContextMenuRequested.connect(self.show_pitch_context_menu)
        
        # Enable keyboard shortcuts for the tree
        self.pitch_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        pitch_layout.addWidget(self.pitch_tree)
        
        parent.addWidget(pitch_widget)
    
    def setup_audio_controls(self, layout):
        """Set up audio controls and status"""
        controls_frame = QFrame()
        controls_frame.setFrameStyle(QFrame.Shape.Box)
        controls_layout = QHBoxLayout(controls_frame)
        
        # Audio status
        self.status_label = QLabel("Ready for pitch exploration - Load an at-bat to begin")
        controls_layout.addWidget(self.status_label)
        
        layout.addWidget(controls_frame)
    
    def load_sample_at_bat(self, sample_num):
        """Load sample at-bat data that matches the main application format"""
        if sample_num == 1:
            # Strikeout looking - Classic 4-pitch strikeout
            self.game_pitches = [
                {
                    'x': 145, 'y': 165, 
                    'text': 'Pitch 1 : Ball 1',
                    'at_bat': 'Jose Altuve batting',
                    'pitch_num': 1,
                    'count': '1-0'
                },
                {
                    'x': 120, 'y': 150, 
                    'text': 'Pitch 2 : Strike 1 Looking',
                    'at_bat': 'Jose Altuve batting', 
                    'pitch_num': 2,
                    'count': '1-1'
                },
                {
                    'x': 110, 'y': 175, 
                    'text': 'Pitch 3 : Strike 2 Foul',
                    'at_bat': 'Jose Altuve batting',
                    'pitch_num': 3, 
                    'count': '1-2'
                },
                {
                    'x': 125, 'y': 155, 
                    'text': 'Pitch 4 : Strike 3 Looking',
                    'at_bat': 'Jose Altuve batting',
                    'pitch_num': 4,
                    'count': '1-2',
                    'result': 'Altuve struck out looking.'
                }
            ]
            sequence_name = "Strikeout Looking"
        elif sample_num == 2:
            # Four-pitch walk - Patient at-bat 
            self.game_pitches = [
                {
                    'x': 130, 'y': 145, 
                    'text': 'Pitch 1 : Strike 1 Looking',
                    'at_bat': 'Aaron Judge batting',
                    'pitch_num': 1,
                    'count': '0-1'
                },
                {
                    'x': 95, 'y': 160, 
                    'text': 'Pitch 2 : Ball 1', 
                    'at_bat': 'Aaron Judge batting',
                    'pitch_num': 2,
                    'count': '1-1'
                },
                {
                    'x': 85, 'y': 140, 
                    'text': 'Pitch 3 : Ball 2',
                    'at_bat': 'Aaron Judge batting',
                    'pitch_num': 3,
                    'count': '2-1'
                },
                {
                    'x': 170, 'y': 180, 
                    'text': 'Pitch 4 : Ball 3',
                    'at_bat': 'Aaron Judge batting', 
                    'pitch_num': 4,
                    'count': '3-1'
                },
                {
                    'x': 75, 'y': 165, 
                    'text': 'Pitch 5 : Ball 4',
                    'at_bat': 'Aaron Judge batting',
                    'pitch_num': 5,
                    'count': '3-1', 
                    'result': 'Judge walked.'
                }
            ]
            sequence_name = "Four-Pitch Walk"
        else:  # sample_num == 3
            # First-pitch single - Quick at-bat
            self.game_pitches = [
                {
                    'x': 140, 'y': 170, 
                    'text': 'Pitch 1 : Ball 1',
                    'at_bat': 'Vladimir Guerrero Jr. batting',
                    'pitch_num': 1,
                    'count': '1-0'
                },
                {
                    'x': 115, 'y': 155, 
                    'text': 'Pitch 2 : Ball In Play',
                    'at_bat': 'Vladimir Guerrero Jr. batting',
                    'pitch_num': 2,
                    'count': '1-0',
                    'result': 'Guerrero Jr. singled to left.'
                }
            ]
            sequence_name = "First-Pitch Single"
        
        # Repopulate the display
        self.populate_pitch_data()
        
        # Set focus to the tree (like main app) and select first item
        self.pitch_tree.setFocus()
        if self.pitch_tree.topLevelItemCount() > 0:
            first_item = self.pitch_tree.topLevelItem(0)
            self.pitch_tree.setCurrentItem(first_item)
            self.pitch_tree.expandAll()
        
        self.status_label.setText(f"Loaded {sequence_name} - Use Alt+P for pitch audio, Alt+S for sequence")
    
    def populate_pitch_data(self):
        """Populate the pitch tree with game data in the same format as main app"""
        self.pitch_tree.clear()
        
        if not self.game_pitches:
            no_data_item = QTreeWidgetItem(["No pitch data available", "", ""])
            self.pitch_tree.addTopLevelItem(no_data_item)
            return
        
        # Group pitches by at-bat (like main application)
        at_bats = {}
        for pitch in self.game_pitches:
            at_bat_name = pitch.get('at_bat', 'Unknown Batter')
            if at_bat_name not in at_bats:
                at_bats[at_bat_name] = []
            at_bats[at_bat_name].append(pitch)
        
        # Create tree structure matching main application
        for at_bat_name, pitches in at_bats.items():
            # At-bat parent item (like main app)
            result_text = ""
            final_pitch = pitches[-1] if pitches else None
            if final_pitch and 'result' in final_pitch:
                result_text = f" - {final_pitch['result']}"
            
            at_bat_item = QTreeWidgetItem([
                f"{at_bat_name}{result_text}",
                "",
                f"{len(pitches)} pitches"
            ])
            at_bat_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'at_bat', 'pitches': pitches})
            
            # Add individual pitch items (exactly like main app format)
            for pitch in pitches:
                pitch_text = pitch.get('text', 'Unknown pitch')
                x = pitch.get('x')
                y = pitch.get('y')
                
                # Add coordinates if available (like main app)
                coordinates_text = ""
                if x is not None and y is not None:
                    # Determine location (using main app logic)
                    location = self.get_pitch_location(x, y)
                    coordinates_text = f" - {location} ({x}, {y})"
                
                full_text = f"{pitch_text}{coordinates_text}"
                
                pitch_item = QTreeWidgetItem([full_text, "", ""])
                pitch_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'pitch', 'data': pitch})
                at_bat_item.addChild(pitch_item)
            
            self.pitch_tree.addTopLevelItem(at_bat_item)
        
        # Expand all like main application
        self.pitch_tree.expandAll()
    
    def get_pitch_location(self, x, y):
        """Get pitch location description using main app logic"""
        # Simplified version of main app logic
        if 60 <= x <= 155:  # Strike zone width
            if y <= 120:
                return "High Strike Zone"
            elif y <= 180:
                return "Strike Zone Center" 
            else:
                return "Low Strike Zone"
        elif x < 60:
            return "Inside"
        else:
            return "Outside"
    
    def show_zone_pitches(self, zone_id):
        """Play audio for the selected strike zone position"""
        self.play_zone_audio(zone_id)
    
    def show_pitch_context_menu(self, position):
        """Show context menu for pitch items"""
        item = self.pitch_tree.itemAt(position)
        if not item:
            return
        
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data:
            return
        
        menu = self.create_pitch_context_menu(item, item_data)
        if menu:
            global_pos = self.pitch_tree.mapToGlobal(position)
            from popup_menu import exec_menu
            exec_menu(menu, global_pos)
    
    def create_pitch_context_menu(self, item, item_data):
        """Create context menu based on item type"""
        from PyQt6.QtWidgets import QMenu
        
        menu = QMenu(self)
        menu.setAccessibleName("Pitch Options")

        if item_data.get('type') == 'pitch':
            # Individual pitch actions (matching main app)
            play_action = QAction("Play Pitch Audio", self)
            play_action.setShortcut("Alt+P")
            play_action.triggered.connect(lambda: self.play_pitch_audio(item_data['data']))
            menu.addAction(play_action)
            
        elif item_data.get('type') == 'at_bat':
            # At-bat actions (matching main app)
            play_sequence_action = QAction("Play Pitch Sequence", self)
            play_sequence_action.setShortcut("Alt+S")
            play_sequence_action.triggered.connect(lambda: self.play_pitch_sequence(item_data['pitches']))
            menu.addAction(play_sequence_action)
        
        return menu
    
    def play_zone_audio(self, zone_id):
        """Play audio for a strike zone position"""
        if zone_id not in self.strike_zone_positions:
            return
        
        x, y, display_name = self.strike_zone_positions[zone_id]
        
        try:
            if self.use_stereo:
                self.audio_mapper.generate_strike_zone_audio(zone_id, 'R')  # Default right-handed
            else:
                self.simple_audio.generate_strike_zone_audio(zone_id, 'R')
            
            self.status_label.setText(f"Playing audio for {display_name}")
            
        except Exception as e:
            self.status_label.setText(f"Audio error: {str(e)}")
    
    def play_pitch_audio(self, pitch_data):
        """Play audio for a specific pitch"""
        x = pitch_data.get('x')
        y = pitch_data.get('y')
        
        if x is None or y is None:
            self.status_label.setText("No coordinates available for this pitch")
            return
        
        try:
            # Extract pitch details from text (like main app)
            pitch_text = pitch_data.get('text', '')
            velocity = 90  # Default velocity
            pitch_type = "Unknown"
            
            # Simple parsing (could be enhanced)
            if "Ball" in pitch_text:
                pitch_type = "Ball"
            elif "Strike" in pitch_text:
                pitch_type = "Strike"
            elif "Foul" in pitch_text:
                pitch_type = "Foul"
            
            if self.use_stereo:
                self.audio_mapper.generate_pitch_audio(x, y, velocity, pitch_type, 'R')
            else:
                self.simple_audio.generate_pitch_audio(x, y, velocity, pitch_type, 'R')
            
            location = self.get_pitch_location(x, y)
            self.status_label.setText(f"Playing {pitch_type} at {location} ({x}, {y})")
            
        except Exception as e:
            self.status_label.setText(f"Audio error: {str(e)}")
    
    def play_pitch_sequence(self, pitches):
        """Play audio sequence for all pitches in an at-bat (like main app)"""
        if not pitches:
            self.status_label.setText("No pitches to play in this sequence")
            return
        
        self.status_label.setText(f"Playing sequence of {len(pitches)} pitches...")
        
        # Play each pitch with a small delay (simplified version)
        for i, pitch in enumerate(pitches):
            # In a full implementation, you'd use QTimer for proper timing
            self.play_pitch_audio(pitch)

if __name__ == "__main__":
    # Test the dialog
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    
    # Sample pitch data for testing
    sample_pitches = [
        {'x': 100, 'y': 150, 'type': 'Fastball', 'velocity': 95, 'result': 'Strike'},
        {'x': 127, 'y': 127, 'type': 'Slider', 'velocity': 85, 'result': 'Ball'},
        {'x': 155, 'y': 180, 'type': 'Changeup', 'velocity': 82, 'result': 'Foul'},
    ]
    
    dialog = PitchExplorationDialog(game_pitches=sample_pitches)
    dialog.show()
    
    sys.exit(app.exec())
