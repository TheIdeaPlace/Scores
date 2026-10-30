# Changelog

All notable changes to the Scores application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Hear where a basketball or hockey play happened.** Alt+P on a play in the
  play-by-play plays a tone for where it was: the note says how far from the
  basket or the goal, and the stereo position says where across the court or the
  ice. Alt+S walks a whole period, Shift+F10 offers the same as a menu, and a
  Play Audio button does it with the mouse. Basketball (NBA, WNBA, NCAAM,
  NCAAWB) and hockey (NHL, NCAAH, NCAAWH); football and soccer plays carry no
  coordinates, so they have no audio.
  - Every play reads its location as part of its entry — "from three, left
    side", "near end, in the slot" — and each period heading says how many of
    its plays can be heard. Nothing is spoken over the tone itself.
  - Hockey sides are as seen facing the goal at that end, so mirror-image shots
    at the two ends do not sound alike.
  - Not every play has a location. Substitutions, timeouts, free throws and most
    face-offs arrive without one, so about a third of basketball plays and one
    in twenty hockey plays stay silent and say so.
- **iPhone: the same play audio**, as the "Play location" and "Play locations"
  VoiceOver actions on a play and on a period heading, or by tapping a play.

### Fixed
- **The MLB Pitch Audio button never appeared.** It was shown only when the
  sport was `baseball`, but the check it was given returns league keys like
  `MLB`, so the button was hidden on every game. Alt+P on a pitch had always
  worked; the button now shows with it.

### Changed
- **Moved to the TheIdeaPlace/Scores repository**, including the in-app updater,
  the installer and the docs.
- Dependency updates: pytz, the PyQt group and the Python group.

### In Progress
- **Game Wrap Up Feature**: ESPN text processing and game story extraction (under construction)
  - Core infrastructure implemented, text processing being refined
  - Game story text placeholders currently under investigation

## [0.9.9.1] - 2026-10-10

A Windows-only update; the iPhone app stays at 0.9.9.

### Added
- **Windows: live games in a single sport's scores now show the current play,**
  as Live Scores does. Football shows the last play, clock, possession and down
  and distance; baseball shows runners, count, outs, batter and last play;
  other sports show the latest play. Before, the In Progress section showed only
  the score and clock.

### Fixed
- **Windows: NFL and college football live scores ran minutes behind** in a
  sport's own scores list, because ESPN's week-by-week scoreboard lags its
  daily one. Live games in a football week now come from today's scoreboard.
- **Windows: a live football game's clock was read twice** in Live Scores.
- **Windows: Live Scores read some scores backwards.** "Colts at Commanders -
  13-30" gave the home score first after an away-first name; scores now follow
  the team order. Games without a play no longer read their status twice.
- **Windows: F5 in a sport's scores list jumped back to the top.** It now stays
  on the game you were on.
- Updated Python dependencies, including urllib3 2.8.0.

## [0.9.9] - 2026-10-03

The first release of the Windows and iOS apps together: one version, one tag.

### Fixed
- **Windows: game details, Polls, Teams, Venues and Bowls & Playoffs froze the
  window while they downloaded.** All now load in the background. Opening a
  team's schedule from a game, and the `--<sport>-teams` / `--<sport>-standings`
  startup actions, do too.
- **Windows: pitch sounds blocked the keyboard while they played.** They now
  play on their own thread, in order.
- **Windows: a second update attempt failed with "Permission denied"** when the
  first attempt's installer was still open. Scores now says the installer is
  already open.
- **Windows: changing the TeamHub season or World Cup phase quickly** could show
  results for the one just left.
- **Windows: Game Wrap Up fetched a college football game** whatever the sport.
- **iOS: golf totals left out the round in progress**, and tied golfers showed
  as 1 and 2 instead of T1.

### Changed
- **A `v*` tag now releases both apps.** The iOS app takes its version from
  `VERSION` and uploads to TestFlight from the same tag as the Windows release,
  with the commit count as its build number.

## [0.9.8] - 2026-10-03

### Changed
- **Scores are grouped by game status.** A league's scores list showed games in
  ESPN's kickoff order, which on a college football Saturday mixed finals, live
  games and evening kickoffs. Games are now grouped as on iOS: In Progress
  (suspended games included), Upcoming, Completed, then Postponed / Cancelled.
  Each group opens with a header row giving its count ("Upcoming, 42 games").
  The arrow keys stop on the headers, and activating one does nothing.
- **Live Scores loads the way the iOS app does.** It made about 85 requests on a
  busy Saturday: every scoreboard twice, plus a full summary per live game for
  its latest play. It now makes one request per league for today, all at once,
  and reads the latest play from the scoreboard. About 5 seconds instead of more
  than a minute.
- **Golf in Live Scores** has its own section at the top, as on iOS: each
  tournament in progress with its round and top three, ties shown as T1. Enter
  opens the tour's leaderboard.

### Fixed
- **Live Scores - All Sports froze and never recovered on a busy day.** It loaded
  on the UI thread, and the refresh started the next load as soon as one
  finished. It now loads in the background, skips a refresh while one is
  running, and keeps your place in the list.
- **Golf tournaments in Live Scores read "Unknown at Unknown".**
- **Golf scores were wrong for golfers partway through a round.** ESPN's total
  leaves out the round in progress, so +1, -4 and -8 through 12 holes showed -3
  instead of -11. Totals are now added up from the round scores, in Live Scores
  and on the leaderboard. CUT, WD and DQ are unchanged.
- **League views and Statistics froze the window while loading.** Both now load
  in the background behind a "Loading..." row.
- **Crashes when leaving or reopening a screen mid-load** (Standings, Wild Card
  tabs, fantasy cheatsheet, favorite team cards).
- **ESPN requests had no timeout**, so one stalled response could hang the app.
  Every request now gives up after 15 seconds.

## [0.9.7] - 2026-09-27

### Fixed
- **NFL and college football showed "No games found" for every week.** ESPN's
  scoreboard stopped accepting a date range (`dates=YYYYMMDD-YYYYMMDD`) and now
  answers one with an error, for every sport. Football weeks were fetched by the
  week's date range, so every week, current or not, came back empty. Weeks are
  now requested by week number, season type and season year, which ESPN still
  honours, and preseason, postseason and bowl weeks all load again.
- **Team schedules for WNBA, college basketball and soccer, and the venue
  list,** used the same kind of date range and came back empty too. They now
  ask for one month at a time.

## [0.9.6] - 2026-09-20

### Fixed
- **NHL and the other winter sports were stuck on last season.** Team schedules
  asked ESPN for season 2026 — the 2025-26 season — because the season year was
  hardcoded rather than worked out from the date, so in September 2026 the NHL
  schedule showed the season that had already finished. The season year is now
  derived per sport: the winter sports (NHL, NBA, NCAA basketball and hockey)
  use the year their season ends in and roll over in July, once the previous
  season is done and the new schedule has been published; football stays on the
  previous year through January and February. The season picker follows, so it
  now leads with "2026-27 Season" instead of topping out at 2025-26, and NBA
  standings track the current season instead of the one frozen into the URL.

## [0.9.5] - 2026-09-01

### Added
- **MLB wild card standings.** The standings view could only show divisions, so
  the playoff race — the thing most people are actually tracking in September —
  was not visible anywhere. Two tabs, "AL Wild Card" and "NL Wild Card", now sit
  beside the six division tabs. Each shows its league's three division leaders
  followed by the 12-team wild card race, with the teams holding the three
  berths marked "Wild card 1/2/3" in a Status column rather than separated by a
  drawn line, so a screen reader speaks the playoff cut instead of relying on a
  visual boundary nobody can hear. The tabs load the first time they are opened,
  so the divisions view is never held up by the extra request.

  The data comes from ESPN's standings endpoint the app already calls, with
  `type=1`, which returns the wild card table directly. Division leaders are the
  three teams it omits. ESPN's published seed is used rather than a
  win-percentage sort, so teams tied on record land in a deterministic, official
  order — four pairs are tied as of this writing.

### Fixed
- **College football was missing most of the games played.** ESPN serves the two
  Division I halves separately through its `groups=` scoreboard parameter, and
  the app asked only for FBS (`groups=80`). That is a small fraction of an
  opening weekend, which is largely FCS: on Saturday 29 August the scoreboard
  showed 8 games out of the 48 Division I games actually played. Coverage is now
  a setting on the home page settings dialog — **All Division I (FBS and FCS)**,
  the new default at around 200 games a week, or **FBS only** at around 100.
  A team's own schedule always uses the widest coverage, since it is filtered
  down to that team anyway and FBS-only returned nothing at all for an FCS team.

  Requests also send `limit=400`. ESPN doubles that internally on undated
  queries and collapses the page to 25 games past an effective 1000, so a larger
  limit is worse than none; 400 clears a full Division I week either way.
  A week-indexed postseason query returns nothing at all under `groups=90`, so
  an empty college football response is retried as FBS — without that, the Bowls
  and Playoffs view came back empty.

- **College basketball was missing most of the games played**, the same ESPN
  `groups=` omission and proportionally worse. A Saturday in January returned 21
  of 145 men's Division I games and 4 of 122 women's. Both now ask for Division I
  explicitly. Basketball needs no coverage setting the way football does — ESPN
  has no FBS/FCS-style split below Division I for it — and college hockey needs
  no change at all, since `groups=` returns nothing there and the plain call is
  already complete.

- **College basketball team schedules were nearly empty.** They fell through to
  a 60-day scoreboard range that returned nothing without a division filter and,
  once one was added, stopped at the page limit — 400 games covering 12 days of
  the 61 requested. They now use the dedicated per-team endpoint, like every
  other league.

## [0.9.4] - 2026-08-13

### Fixed
- **Fantasy cheatsheet: the Rank column skipped numbers.** It showed ESPN's
  published rank, which orders a far larger pool than a fantasy board — roughly
  1,750 defensive players, 51 punters and the 32 "Team QB" slots. Sorted by
  rank, the board ran 1 to 2565 with 1,539 gaps in it, jumping 36 to 69 near the
  top and 519 to 978 further down. The column now counts the board itself: 1, 2,
  3 with nothing missing, in exactly the order ESPN puts them. ESPN's own number
  is still shown on the player details screen and in the CSV export, for anyone
  cross-referencing their site.

## [0.9.3] - 2026-08-10

### Fixed
- **Fantasy cheatsheet: the board was missing two-thirds of the players ESPN
  ranks.** The pool was capped at ESPN's overall draft rank, on the assumption
  that rank tracked draft relevance. It does not — Ricky Pearsall ranks 1507 and
  is rostered in a third of ESPN leagues, Tyreek Hill ranks 1899 — so the cap
  was hiding players people actually draft. The board now carries every active
  fantasy-position player ESPN publishes a rank for: 1,026 rather than 368.
  Players ESPN ranks nowhere, and players it flags as inactive, are still left
  out; every one of those is owned in 0.0% of leagues.
- **Fantasy cheatsheet: ADP no longer invents a draft position.** ESPN gives
  undrafted players a placeholder ADP just past the end of a real draft rather
  than omitting it — around 170 this season, shared by 826 of the 1,026 players.
  It read as a genuine draft slot, and because the placeholder is jittered in
  the third decimal it also broke the ADP sort: rows all displaying "170.0"
  ordered by invisible digits, putting deep camp bodies above real starters.
  Those players now show ADP as N/A and sort to the bottom by rank.
- **Fantasy cheatsheet: free agents are reachable.** The team filter gained a
  *Free Agents* entry — 212 players, including Tyreek Hill and Keenan Allen,
  previously findable only by accident.
- **Fantasy cheatsheet: filter controls are debounced** and the dialog is
  released when closed, so repeatedly opening the board no longer grows memory.

## [0.9.2] - 2026-08-09

### Added
- **Fantasy cheatsheet: rookie filters.** The position filter gains *Rookies*
  plus *Rookie QB / RB / WR / TE*. Rookies are identified from the fantasy feed
  itself — a player with no stat line from any earlier season — which also
  catches undrafted rookies that a draft-list lookup would miss.
- **Fantasy cheatsheet: export to CSV.** *Export to CSV* saves the whole board,
  not just what the filters currently show: both rank boards, player, position,
  team, rookie flag, injury, ADP, auction value, projected points in all three
  scoring formats, and whether you have marked the player drafted.

## [0.9.1] - 2026-08-09

### Added
- **Fantasy football cheatsheet**: a draft board on the NFL screen with every
  draftable player plus all 32 team defenses — ESPN consensus rank, average draft
  position, auction value and projected season points. Search by player or team,
  filter by position (including FLEX) or team, sort by any column, and switch
  between Standard, Half-PPR and PPR scoring without a refetch. Space marks a
  player drafted, *Hide drafted players* clears them off the board, and both the
  drafted set and the scoring format persist between sessions. Kickers and team
  defenses show no projection: ESPN's published numbers for those two positions
  are unusable, so the board shows N/A rather than a wrong number.

### Fixed
- **NFL preseason games and weeks now appear.** The NFL screen only ever showed
  regular-season weeks, so during August it opened on the September opener
  labelled "Week: 1" and there was no way to reach the preseason at all. Weeks
  are now resolved from ESPN's season calendar and carry their season type, the
  Previous/Next Week buttons roll over between preseason, regular season and
  postseason, and weeks are named as ESPN names them — "Hall of Fame Weekend",
  "Preseason Week 1", "Wild Card" — instead of a bare, ambiguous week number.
- **Football weeks no longer include the next week's games.** ESPN marks the end
  of a week at 23:59 Pacific, which reads as the following day in UTC; the extra
  day pulled the next week's Thursday games into the current week. Affected the
  regular season too, and was most visible in the preseason.

## [0.9.0] - 2026-08-05

### Added
- **Windows installer**: `Scores-<version>-Setup.exe`, a per-user install into
  `%LocalAppData%\Programs\Scores` that needs no administrator rights and adds a
  Start Menu shortcut (desktop shortcut optional). Built with Inno Setup from
  `installer/scores.iss`.
- **Automatic updates**: Scores checks GitHub for a newer release at startup and
  can download and install it for you; *Check for Updates* on the home page runs
  the same check on demand. The startup check can be turned off in Settings.
  Portable copies update too — the installer relocates them.
- **Code signing**: releases are Authenticode-signed with Azure Artifact Signing
  via GitHub OIDC, so downloads no longer trip SmartScreen.
- `build.py` builds both distributables (one-dir installer input plus the portable
  one-file exe) and is what CI runs.
- `docs/INSTALLER.md` documents the installer, the updater and the signing setup.

### Changed
- The application version now lives in `version.py`, and the release workflow
  refuses to build a `v*` tag that disagrees with it or with the VERSION file.

## [0.65.0] - 2025-12-14

### Added
- **NCAA Hockey Support**: Complete Men's and Women's Hockey coverage
  - NCAA Men's Hockey (NCAAH): 50 teams across 10+ conferences
  - NCAA Women's Hockey (NCAAWH): 44 teams with conference standings
  - Live games, scores, and play-by-play details
  - Full team listings with schedule navigation
  - Conference-based standings (Hockey East, Big Ten, ECAC, NCHC, CCHA, CHA, Atlantic Hockey America, etc.)
  - Hockey-specific record format handling (W-L-T)

- **Polls & Rankings Feature**: Official poll tracking for all NCAA sports
  - NCAA Football: CFP Rankings, CFP Seedings, AP Poll, Coaches Poll (4 polls)
  - NCAA Men's Basketball: AP Poll, Coaches Poll (2 polls)
  - NCAA Women's Basketball: AP Poll, Coaches Poll (2 polls)
  - NCAA Men's Hockey: USA Hockey Poll, USCHO Poll (2 polls)
  - NCAA Women's Hockey: USA Hockey Poll, USCHO Poll (2 polls)
  - Multi-tab interface for sports with multiple polls
  - Rank change indicators (↑/↓) showing movement from previous week
  - Displays rank, team, record, points, and previous rank
  - Accessible table format with keyboard navigation (Ctrl+Tab between polls)

### Changed
- **Enhanced League Name Display**: All league abbreviations now display with full, descriptive names
  - Main league selection screen shows complete sport names with gender designation
  - Live scores section headers use formatted league names
  - Window titles display full sport names in breadcrumb navigation
  - Applied to: NCAA Women's Hockey, NCAA Men's Hockey, NCAA Women's Basketball, NCAA Men's Basketball, NCAA Football

### Technical
- Added `get_rankings()` API endpoint integration for poll data
- Created `PollsDialog` component with multi-tab support
- Implemented hockey conference structure parsing
- Added `format_league_name()` utility function for consistent name formatting
- Internal API calls maintain efficient abbreviation codes for performance

## [0.55.0] - 2025-08-31

### 🚀 BREAKTHROUGH ACCESSIBILITY FEATURES
- **Dynamic Window Titles for Screen Readers**: **FIRST-IN-CLASS** window title management system
  - **Contextual Titles**: Window titles dynamically reflect user location in the application
  - **Screen Reader Optimized**: "MLB - Sports Scores", "MLB, Standings - Sports Scores", "Yankees vs Red Sox - MLB - Sports Scores"
  - **Hierarchical Navigation**: Most specific information first, following accessibility best practices
  - **Universal Coverage**: All views, dialogs, and navigation contexts included
  - **Cross-Platform**: Both desktop (PyQt6) and web (JavaScript) implementations
  - **Zero Breaking Changes**: Enhances existing functionality without disruption

- **Multiple View Modes for All Tables**: **INDUSTRY-FIRST** accessible data presentation system
  - **Three View Modes**: Table, Quick List, Full List for every tabular data display
  - **Universal Keyboard Shortcuts**: Alt+V (cycle), Alt+T (table), Alt+Q (quick), Alt+F (full)
  - **Seamless Focus Management**: Maintains position when switching between view modes
  - **Real-time Data Sync**: All views reflect live data updates immediately
  - **Universal Integration**: Automatically available for standings, statistics, leaders, box scores, injuries
  - **Screen Reader Optimized**: Proper ARIA attributes and view change announcements
  - **Zero Breaking Changes**: All existing functionality preserved and enhanced

### Added
- **Comprehensive Conference/Division Support**: Restored and expanded sports organization
  - College Football (NCAAF): Full conference tabs (SEC, Big Ten, Big 12, ACC, Pac-12, etc.)
  - College Basketball (NCAAB/NCAAM/NCAAW): Major conference support with priority ordering
  - WNBA: Eastern/Western conference organization
  - All sports now properly display natural divisions/conferences as tabs

- **Enhanced Accessibility Infrastructure**: Foundation improvements for screen reader support
  - Removed problematic view selector combo box that caused focus conflicts
  - Default expanded view for comprehensive data presentation
  - Improved Ctrl+Tab navigation between division tabs
  - Consistent keyboard navigation patterns across all table types

### Enhanced
- **Expanded Standings Feature**: Toggle between basic and expanded standings views
  - Basic View: Traditional 7-column standings (Position, Team, W, L, PCT, GB, Streak)
  - Expanded View: Sport-specific additional columns with advanced statistics
  - MLB Expanded: Runs For/Against, Run Differential, Home/Road Records, Playoff %, Magic Numbers
  - NFL Expanded: Points For/Against, Point Differential, Division Record, Playoff Seed
  - NBA Expanded: PPG, Opponent PPG, Point Differential, Division Win %, Playoff Seed
  - NHL Expanded: Points, OT Losses, Goals For/Against, Goal Differential, Playoff Seed
  - Toggle buttons in standings dialog for supported sports (MLB, NFL, NBA, NHL)

- **News Articles**: Increased news article retrieval from 6 to 20 articles per league
  - Added configurable limit parameter (max 50 articles available from ESPN)
  - Better news coverage with more comprehensive headlines
  - Maintains same user interface with enhanced content

### Fixed  
- **MLB Standings**: Fixed incorrect "American League" tab appearing alongside proper divisions
  - Corrected Chicago White Sox abbreviation mapping (CHW vs CWS)
- **Text Processing**: Enhanced ESPN news text name replacement and pattern detection
  - Now displays exactly 6 division tabs as expected

## [0.54.0-preview] - 2025-08-27

### Added
- **Venue Browsing Feature**: Complete stadium/venue exploration system
  - Browse stadiums and venues by league (NFL, MLB, NBA, NHL, NCAA Football)
  - Comprehensive venue details including capacity, surface type, location, and facts
  - Home team information for each venue
  - NCAAF venue support through proper college-football API mapping
- **Enhanced Team Navigation Infrastructure**: Robust system for navigating between games and team schedules
  - Smart team ID resolution with multiple fallback mechanisms
  - College football team mapping for major programs ensuring reliable navigation
  - Improved back navigation with context preservation
- **Automatic Timezone Conversion**: All game times converted to user's local timezone
  - ESPN timezone data processing and local time conversion
  - Cross-platform timezone handling with verification tools
- **UI Consistency Improvements**: Unified interface design across all dialogs
  - Venue details use consistent QListWidget format matching rest of application
  - Text-based indicators ([Indoor, Grass]) replacing emoji decorations
  - Clean "--- Section ---" headers for organized information display

### Changed
- **Venue Service Architecture**: New venue service with efficient API usage and smart caching
- **Code Organization**: Test and demo files properly organized in TheBench directory
- **Interface Design**: Standardized on list-based UI elements for consistency and accessibility

### Fixed
- **NCAAF Venue Access**: Added proper "ncaaf" to "college-football" league mapping
- **Case Sensitivity**: Fixed venue dialog league case sensitivity for reliable data access
- **Team Navigation**: Enhanced team ID resolution prevents navigation failures in college football

## [0.53.0-preview] - 2025-08-18

### Added
- **Statistics Feature**: Complete new statistics system for comprehensive sports analysis
  - Two-dialog interface: Choose Team/Player → Select statistic → View rankings
  - Multi-sport framework supporting MLB, NFL, NBA, NHL, NCAA Football
  - Professional-grade statistical categories with official data sources
  - Accessible design with full keyboard navigation and screen reader support
- **MLB Full Season Statistics**: Official MLB Stats API integration for baseball
  - 39 comprehensive statistical categories (vs 18 from ESPN)
  - Hitting statistics: 16 categories including advanced metrics (AVG, OPS, SB, etc.)
  - Pitching statistics: 15 categories with complete season data (ERA, Saves, etc.)
  - Fielding statistics: 8 categories for defensive analysis
  - Official MLB source with full season totals
  - Parallel loading for optimal performance (6x faster: 157ms vs 953ms)
- **Enhanced Baseball Information**: Improved game details and pitch location system
  - Pitch location validation with 85.4% strike zone accuracy
  - Enhanced game details display (venue, weather, broadcast info)
  - Better configuration options for game information fields
  - Cross-game validation with real umpire call analysis

### Fixed
- **Statistics Display**: Resolved "No player stats available for mlb" error
  - Fixed data format conversion between MLB API and UI expectations
  - Proper player name, stat value, and team information display
  - Seamless integration with existing statistics interface
- **MLB Data Quality**: Eliminated misleading limited-game statistics
  - Real season totals replacing recent performance samples
  - Complete statistical picture for informed analysis

### Changed
- **Statistics Architecture**: New comprehensive statistics system implementation
- **MLB Data Source**: ESPN API → Official MLB Stats API for baseball statistics
- **Data Coverage**: Recent games → Full season comprehensive statistics
- **Performance Optimization**: Enhanced concurrent request handling for statistics
- **User Interface**: Added Statistics menu option to all major sports

### Technical Details
- **Statistics Framework**: Scalable system ready for all major sports
- **MLB API Integration**: statsapi.mlb.com/api/v1/stats/leaders endpoints
- **No Authentication Required**: Public MLB API endpoints
- **Backward Compatibility**: All existing functionality preserved
- **Enhanced Error Handling**: Robust statistics processing and display

## [0.52.0-preview] - 2025-08-16

### Added
- **Live Scores Feature**: Real-time sports monitoring with auto-refresh capabilities
  - Multiple refresh intervals: 10s, 15s, 30s, 60s, 2min, 5min
  - Continuous background updates for live game tracking
  - Resource-efficient monitoring with pause/resume functionality
- **Scoring Drive Enhancement**: Visual identification system for football scoring plays
  - Touchdown indicators with "TD 7pts" badges
  - Field goal markers with "FG 3pts" badges  
  - Missed field goal, turnover, punt, and safety indicators
  - WCAG AA compliant color coding for accessibility
  - Enhanced drive summaries with scoring context
- **Enhanced Football Display**: Comprehensive game situation awareness
  - Hybrid format showing down/distance + drive statistics
  - Redzone indicators for teams in scoring position
  - Last play information for momentum context
  - Consistent team naming and score formatting
- **Command Line Options**: Quick access for power users
  - `--live`: Shorthand to launch Live Scores directly
  - `--live-scores`: Full command option for Live Scores mode
- **Multi-Platform Research**: Comprehensive analysis document for Mac and iOS expansion
- **Windows UIA Integration**: Enhanced accessibility with notification helpers

### Fixed
- **Score Display**: Resolved missing scores in football game listings
- **Team Naming**: Fixed inconsistent team name formatting across views
- **Navigation**: Improved startup parameter handling and validation
- **Memory Management**: Enhanced cleanup for long-running Live Scores sessions

### Changed
- **ESPN API Integration**: Enhanced data extraction for scoring drive detection
- **Performance**: Optimized real-time update processing and resource usage
- **Code Organization**: Improved project structure with comprehensive testing
- **Documentation**: Expanded guides for new features and implementation details

### Technical Details
- **NFL & NCAAF Support**: Scoring drive enhancement works with both professional and college football
- **Accessibility Compliance**: Full WCAG AA compliance for visual indicators
- **Background Processing**: Efficient real-time updates without blocking UI
- **Cross-Platform Planning**: Research completed for future Mac and iOS versions

### Build Artifacts
- `dist/Scores.exe` - Enhanced Windows executable (~43MB due to new features)
- Improved startup performance and resource management

## [0.51.0-preview] - 2025-08-15

### Added
- **Season Selection**: Enhanced team schedule dialogs with season dropdown for viewing historical data
- **Command Line Interface**: Comprehensive CLI options for direct navigation to specific sport sections
  - Game views: `--mlb`, `--nfl`, `--nba`, `--nhl`, `--ncaaf`
  - Teams views: `--mlb-teams`, `--nfl-teams`, etc.
  - Standings views: `--mlb-standings`, `--nfl-standings`, etc.
- **Accessibility Improvements**: 
  - Replaced QListWidget with AccessibleTable in teams dialogs for better screen reader support
  - Enhanced focus management in team schedule dialogs
  - Added proper accessible names and descriptions to UI components
- **Smart Navigation**: Enhanced team schedule dialogs now focus on today's games or next upcoming games
- **Visual Enhancements**: Today's games are highlighted with bold text and light yellow background

### Fixed
- **Team Name Display**: Fixed team names to show proper team nicknames instead of abbreviations
- **Date Display**: Enhanced date formatting for historical seasons to include year
- **Cache Management**: Cleaned up Python cache files from repository
- **Tab Accessibility**: Added setAccessibleName and setAccessibleDescription to all QTabWidget instances

### Changed
- **Schedule Loading**: Improved team schedule loading with background threading for better performance
- **Season Handling**: Enhanced season availability ranges for different sports leagues
- **UI Focus**: Improved focus management in schedule dialogs to highlight relevant games

### Technical Details
- **Enhanced CLI Support**: Full argument parsing with help documentation
- **Improved Data Display**: Better handling of historical vs current season data
- **Accessibility Standards**: Compliance improvements for screen reader compatibility

### Build Artifacts
- Same as 0.5.0: `dist/Scores.exe` - Standalone Windows executable
- Enhanced command line capabilities for power users

## [0.5.0-preview] - 2025-08-13

### Added
- Complete virtual environment setup with Python 3.13.6
- Comprehensive build system with PyInstaller
- Windows executable generation (standalone ~40MB)
- Enhanced build script (`build-enhanced.bat`) with error handling
- Minimal and complete requirements files
- Comprehensive build documentation (`BUILD_GUIDE.md`)
- Setup completion guide (`SETUP_COMPLETE.md`)

### Fixed
- Fixed `main.py` import issues - now works as alternative entry point
- Resolved PyQt6 6.9.1 compatibility
- Fixed dependency management with proper virtual environment isolation

### Changed
- Updated build process to use virtual environment
- Improved error handling in build scripts
- Enhanced documentation structure

### Technical Details
- **Python Version**: 3.13.6
- **GUI Framework**: PyQt6 6.9.1
- **HTTP Library**: requests 2.32.4
- **Build Tool**: PyInstaller 6.15.0
- **Target Platform**: Windows 10/11 (x64)

### Build Artifacts
- `dist/Scores.exe` - Standalone Windows executable
- `.venv/` - Isolated Python virtual environment
- `requirements.txt` - Complete dependency list
- `requirements-minimal.txt` - Essential dependencies only

### Installation
1. Download `Scores.exe` from releases
2. Run directly (no installation required)
3. For development: use virtual environment setup

### Known Issues
- Audio features require Windows sound system
- Application requires internet connection for ESPN API data
- First launch may take longer due to PyQt6 initialization

### Notes
This is a preview release focusing on build system improvements and deployment preparation. The core sports scoring functionality remains stable from previous versions.
