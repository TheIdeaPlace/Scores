# Sports Scores Application

A comprehensive sports scores application with enhanced accessibility features, detailed game analysis, and **revolutionary multiple view modes** for optimal data consumption.

## 🏟️ What is Scores?

Scores is a desktop application that provides real-time access to:
- **Live Game Scores** - Current and completed games for MLB, NFL and more
- **Detailed Game Analysis** - Box scores, play-by-play, team statistics
- **Team Standings** - Complete league standings and division rankings  
- **Player Statistics** - Individual player performance data
- **News & Updates** - Latest sports news and headlines
- **🚀 Multiple View Modes** - **INNOVATIVE**: Choose how you see data (Table/Quick List/Full List)

### 🎯 Who Should Use Scores?

- **Sports Fans**: Stay updated with your favorite MLB and NFL teams with real-time scores and detailed analysis
- **Baseball Enthusiasts**: Experience unique audio pitch mapping and spatial strike zone exploration
- **Accessibility-Focused Users**: Revolutionary multiple view modes, screen reader support, keyboard navigation
- **Developers**: Contribute to an open-source sports analysis platform with modern Python architecture

## 🚀 BREAKTHROUGH FEATURE: Multiple View Modes

**Industry-First Accessible Data Presentation**: Every table in the application now offers three distinct view modes, revolutionizing how users consume sports data.

### Three Ways to View Any Data:
- **📊 Table View**: Traditional grid format with full arrow key navigation
- **📋 Quick List**: Comma-separated values ideal for rapid scanning ("Team, Wins, Losses...")  
- **📖 Full List**: Header-value pairs for complete context ("Team: Brewers; Wins: 84...")

### Universal Keyboard Shortcuts:
- **Alt+V**: Cycle through all view modes
- **Alt+T**: Direct to Table View
- **Alt+Q**: Direct to Quick List  
- **Alt+F**: Direct to Full List

**Available Everywhere**: Standings, statistics, leaders, box scores, injury reports—every table automatically supports all three modes with seamless focus management.

## Key Features

### Multi-Sport Coverage
- **Live scores and updates** for NFL, MLB, NBA, NHL, and more
- **Detailed play-by-play analysis** with contextual information
- **Real-time game status** and statistical tracking
- **News integration** with latest headlines and stories

### Baseball Pitch Audio System
Experience baseball like never before with spatial audio mapping that converts pitch locations into sound:

- **Spatial Audio Mapping**: Each pitch location is mapped to unique audio frequencies
- **Strike Zone Exploration**: Audio feedback helps understand pitch placement relative to the strike zone
- **Stereo Positioning**: Left/right audio channels represent inside/outside pitch locations
- **Interactive Controls**: 
    - **Shift+F10** for keyboard context menu access, also supports right click
  - Pitch exploration dialog with detailed coordinate information
- **Educational Tool**: Learn to "hear" the strike zone and understand pitch patterns

### Enhanced NFL Drive Analysis
- **Detailed play information** with actual yards gained/lost
- **Situational context** including red zone and goal line situations  
- **Play type identification** for passes, rushes, and special teams
- **Drive momentum tracking** to follow game flow

## Quick Start

### For End Users (Recommended)

1. **Download**: Get `Scores-<version>-Setup.exe` from the [latest release](https://github.com/TheIdeaPlace/Scores/releases)
2. **Install**: Run it — it installs just for you, needs no administrator rights,
   and adds a Start Menu shortcut. The download is code-signed, so there is no
   SmartScreen warning to click through.
3. **Explore**: Choose your sport and start browsing games
4. **Navigate**: Use mouse or keyboard to explore scores, standings, and statistics
5. **Stay current**: Scores checks for new versions at startup and can install them
   for you. Turn that off in Settings if you would rather check by hand with
   *Check for Updates* on the home page.

Prefer no installer? `Scores.exe` on the same release page is a standalone
portable build that needs no installation. It updates itself the same way — the
update installs to your user Programs folder, after which the portable copy can be
deleted.

**System Requirements:**
- Windows 10/11 (64-bit)
- Internet connection (required for live sports data)
- 100MB RAM minimum, 50MB storage space

### For Developers
If you want to run from source or contribute to development:

```bash
# Clone the repository
git clone https://github.com/TheIdeaPlace/Scores.git
cd Scores

# Use the automated build setup (recommended)
build-enhanced.bat

# OR manual setup:
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python scores.py
```

## Application Structure

### Core Application Files
- `scores.py` - Main application entry point and UI
- `espn_api.py` - All network calls
- `accessible_table.py` - Accessible table widgets for screen readers
- `exceptions.py` - Custom error handling
- `main.py` - Alternative entry point

### Audio System Files
- `simple_audio_mapper.py` - Core pitch-to-audio mapping system
- `stereo_audio_mapper.py` - Stereo audio positioning for pitch locations
- `pitch_exploration_dialog.py` - Interactive pitch exploration interface

### Data Models & Services
- `models/game.py` - Game data model and structure
- `models/news.py` - News data model
- `models/standings.py` - Standings data model
- `services/api_service.py` - API service abstraction layer

### Development Archive
- `TheBench/` - Contains all development files, tests, documentation, and analysis tools

## Navigation & Usage

### Basic Navigation
- **League Selection**: Choose between MLB and NFL on the home screen
- **Date Navigation**: Use Previous/Next Day buttons or press **Ctrl+G** to jump to any date
- **Game Details**: Click on any game to see detailed statistics and play-by-play
- **Refresh Data**: Press **F5** to update scores and statistics

### Screen Flow
1. **Home Screen**: Select from available leagues (NFL, NBA, MLB, etc.)
2. **League Screen**: View games with scores, times, and news
3. **Game Details**: Comprehensive play-by-play with enhanced features
4. **News Dialog**: League headlines and stories

### Keyboard Controls
- **Enter**: Select items (games, news, menu options)
- **Escape** or **Alt+B**: Navigate back to previous screen
- **Shift+F10**: Open context menu for audio features (baseball)
- **Ctrl+G**: Jump to specific date
- **F5**: Refresh current data
- **Double-click**: Open news stories in browser

### Baseball Audio Features
When viewing MLB games with play-by-play data:
- **Right-click** on any pitch in the plays list to hear its location
- **Shift+F10** opens audio context menu for keyboard users
- **Alt+P**: Audio feedback for individual pitch locations
- **Alt+S**: Audio feedback for pitch sequences
- Select "Explore Pitch Locations" for detailed audio mapping
- Use stereo headphones for best spatial audio experience

### NFL Drive Analysis
Enhanced play-by-play display shows:
```
[1st & 10 from GB 25] PASS: (+8 yards) Love complete to Watson
[RED ZONE 3rd & 2 from GB 18] RUSH: (+1 yard) Jones up the middle  
[GOAL LINE 4th & 1 from GB 3] TOUCHDOWN: Pass complete for touchdown
```

## Technical Requirements

### For End Users
- **Operating System**: Windows 10/11 (64-bit)
- **Memory**: 100MB RAM minimum
- **Storage**: 50MB available space
- **Network**: Internet connection required for live sports data
- **Audio**: Windows sound system (optional, for audio features)

### For Developers
- **Python 3.9+**
- **PyQt6** - GUI framework
- **requests** - HTTP client for API calls
- **ESPN API** - Live sports data source
- **Audio system** (Windows: winsound, cross-platform: PyAudio optional)

## Development & Testing
All development files, test scripts, documentation, and analysis tools have been organized in the `TheBench/` directory to keep the main project clean and focused. This includes:

- Test scripts and unit tests
- API analysis and debugging tools  
- Development documentation and guides
- Data analysis tools and sample data
- Web application prototype
- Audio system development files

See `TheBench/README_TheBench.md` for a complete index of archived development materials.

## Frequently Asked Questions

**Q: Is this free?**  
A: Yes! Scores is completely free to use and open source.

**Q: Do I need to install Python?**  
A: No! The standalone executable includes everything needed to run. Developers can also run from source.

**Q: Can I use this without internet?**  
A: No, live sports data requires an internet connection.

**Q: Why is the executable file so large (40MB)?**  
A: The executable includes the entire GUI framework and Python runtime for portability.

**Q: Does this work on Mac or Linux?**  
A: Currently Windows only, but cross-platform versions are planned for future releases.

**Q: How do I report bugs or request features?**  
A: Visit the [GitHub Issues page](https://github.com/TheIdeaPlace/Scores/issues) to report bugs or request features.

## Support & Contributing

- **Issues**: Report bugs through the [GitHub repository](https://github.com/TheIdeaPlace/Scores/issues)
- **Feature Requests**: Let us know what sports data you'd like to see
- **Accessibility**: Help us improve accessibility features
- **Contributing**: This project focuses on accessibility and comprehensive sports data presentation

Contributions that enhance accessibility features or expand sports coverage are welcome.

## License
See `LICENSE` file for license information.
