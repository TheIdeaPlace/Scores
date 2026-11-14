# iOS App Feature Parity Plan
**Date:** February 25, 2026  
**Status:** Active — implementation ~85% complete  
**Scope:** Full audit of Python app features → gap analysis → implementation roadmap for iOS

---

## Executive Summary

As of February 26, 2026, Phases 1–7 are complete and Phase 8.2 is done. The iOS app now has: date/week navigation, season type handling (no more broken Super Bowl), date picker, NFL drives view, MLB hierarchical play-by-play with pitch audio, divisions in standings, expanded stats columns, news, team schedules, league statistics, college polls, venue/odds/officials/injuries in game detail, team schedule deep-links from game detail, score change monitoring with notifications, game share, live MLB base runner situation on score rows, and all 10 sports including WNBA/NCAAH/NCAAWH.

**Remaining gap:** Phase 8.1 only — MLB KitchenSink "More" tab (Win Probability Audio Graph, Season Series, game-specific key articles). The Phase 8 features are nice-to-haves; the core app is now feature-equivalent to the Python app on all critical paths.

---

## Part 0: Implementation Progress Tracker

| Phase | Title | Status |
|-------|-------|--------|
| 1.1 | Date navigation | ✅ Done |
| 1.2 | Season type awareness | ✅ Done |
| 1.3 | Date picker modal | ✅ Done |
| 1.4 | Game detail — all states | ✅ Done |
| 2.1 | News | ✅ Done |
| 2.2 | NFL Drives view | ✅ Done |
| 2.3 | Venue in game detail | ✅ Done |
| 2.4 | Betting / Broadcast in game detail | ✅ Done |
| 3.1 | Standings — division grouping | ✅ Done |
| 3.2 | Standings — expanded stat columns | ✅ Done |
| 4.1 | Team model / schedule API | ✅ Done |
| 4.2 | TeamScheduleView | ✅ Done |
| 5.1 | ESPN stats (NFL/NBA/NHL) | ✅ Done |
| 5.2 | MLB Stats API | ❌ Deferred |
| 6.1 | College rankings / Polls | ✅ Done |
| 7.1 | WNBA, NCAAH, NCAAWH in Sport enum | ✅ Done |
| 7.2 | Score change monitoring | ✅ Done |
| 7.3 | Injuries in game detail | ✅ Done |
| 7.4 | Officials in game detail | ✅ Done |
| 7.x | Live MLB situation (bases/count/outs) | ✅ Done |
| 8.1 | MLB KitchenSink (Win Prob, Series, Videos) | ✅ Done — Win Prob chart + Season Series + game news |
| 8.2 | Game wrap-up / Share | ✅ Done |
| 8.x | Auto-refresh (30s/1m/2m/Manual) | ✅ Done — Scores + Live Scores |
| 8.x | NFL Red zone indicator | ✅ Done |
| 8.x | Live MLB base runner situation | ✅ Done |
| 8.x | Game-specific news in Info tab | ✅ Done (all sports) |
| — | MLB Stats API (statsapi.mlb.com) | ❌ Deferred — separate API, separate effort |

---

## Part 1: Complete Python App Feature Inventory

### Sports / Leagues Supported

| League | Python | iOS | Notes |
|--------|--------|-----|-------|
| MLB | ✅ Full | ✅ Partial | Game detail broken for past games; stats API missing |
| NFL | ✅ Full | ✅ Partial | Drives view missing; week nav missing; past games broken |
| NBA | ✅ Full | ⚠️ Partial | Season year format (year+1) may be wrong |
| NHL | ✅ Full | ⚠️ Partial | OTL in standings missing |
| NCAAF | ✅ Full | ⚠️ Partial | Week nav missing; bowls/playoffs missing; polls missing |
| NCAAM | ✅ Full | ⚠️ Partial | Polls missing |
| NCAAWB | ✅ Full | ⚠️ Partial | Polls missing |
| WNBA | ✅ Full | ✅ Done | Added P7.1 |
| NCAAH | ✅ Full | ✅ Done (data often incomplete) | Added P7.1 |
| NCAAWH | ✅ Full | ✅ Done (data often incomplete) | Added P7.1 |
| Soccer (EPL) | ✅ Basic | ❌ Missing | Python treats it generically; reasonable to defer |

---

### Navigation and Date/Season Control

| Feature | Python | iOS |
|---------|--------|-----|
| Previous Day / Next Day | ✅ | ✅ Done |
| Go to Date (date picker) | ✅ Month/Day/Year picker, Ctrl+G | ✅ Done — DatePickerView sheet |
| Previous Week / Next Week (football) | ✅ | ✅ Done |
| Current week auto-detect (football) | ✅ Via calendar API | ✅ Done — resolved from scoreboard response |
| Season year selector on scores view | ✅ (team schedules) | ✅ Done — year picker in TeamScheduleView |
| Back navigation history | ✅ view_stack list | ✅ NavigationStack |
| Postseason / seasontype switching | ✅ | ✅ Done — seasonType stored on Game, auto-detected from API |

**Critical bug:** The Super Bowl and any past playoff/postseason game fails because the iOS app always requests `seasontype=2` (regular season). The ESPN summary API works fine; the scoreboard request needs `seasontype=3` for postseason. The iOS app has no concept of season type at all.

---

### Scores / Live View

| Feature | Python | iOS |
|---------|--------|-----|
| Live scores — all sports combined view | ✅ `LiveScoresView` | ✅ `LiveScoresView` (exists, unclear quality) |
| Per-sport scores for a given date | ✅ | ✅ `ScoresView` |
| Section headers: LIVE / UPCOMING / COMPLETED | ✅ Color-coded | ⚠️ Partial |
| Per-league sub-headers in live view | ✅ | Unknown |
| Score change monitoring (Alt+M) | ✅ Per-game toggle | ✅ Done — swipe or long-press on game row; UNNotification + VoiceOver |
| Auto-refresh with interval selector | ✅ 30s/1m/2m/Manual | ✅ Done — 30s/1m/2m/Manual menu on Scores + Live Scores |
| Live game situation: base runners, count, outs | ✅ MLB only | ✅ Done — shows on score row |
| Live game situation: down/distance/red zone | ✅ NFL only | ✅ Done — displayed on score row |
| Local notifications on score change | ✅ Windows UIA; `winsound` | ✅ Done — UNUserNotificationCenter |

---

### Game Detail View

| Feature | Python | iOS |
|---------|--------|-----|
| Teams, score, game time, status | ✅ | ✅ |
| Venue (city, state, name) | ✅ | ✅ Done |
| Officials list | ✅ Press Enter → dialog | ✅ Done — in Info tab |
| Betting line, over/under | ✅ | ✅ Done |
| TV broadcast | ✅ | ✅ Done |
| Injuries (count → drill-down table) | ✅ | ✅ Done — in Info tab |
| Box score — batting stats per player | ✅ Player-level | ⚠️ Team-level only |
| Box score — pitching stats per player | ✅ Player-level | ⚠️ Team-level only |
| Leaders (per team, by category) | ✅ | ✅ Done |
| News (game-specific, 🎯 prefix) | ✅ | ✅ Done — shown in Info tab via `news` field in summary API |
| Play-by-play — MLB hierarchy | ✅ | ✅ Done (just fixed) |
| Play-by-play — NFL drives | ✅ `QTreeWidget` by quarter/drive | ✅ Done — NFLDrivesView |
| Play-by-play — NBA/NHL | ✅ Generic flat | ✅ `GenericPlaysView` |
| Drives view (NFL) | ✅ Full drive tree w/ result emoji | ✅ Done — collapsible quarter/drive/play hierarchy |
| Win probability (MLB KitchenSink) | ✅ | ✅ Done — Swift Charts line chart in "More" tab |
| Season series (MLB KitchenSink) | ✅ | ✅ Done — current/season/preseason series cards |
| Videos (MLB KitchenSink) | ✅ | ❌ Deferred — often empty; links open in Safari |
| Betting ATS / expert picks | ✅ | ❌ Missing — `againstTheSpread` not yet decoded |
| Game wrap-up export (HTML) | ✅ Browser | ✅ Done — native ShareLink |
| Configurable fields per league | ✅ `ConfigDialog` | ❌ Missing — deferred |
| F5 refresh | ✅ | ✅ Done — auto-refresh + pull-to-refresh |

---

### News

| Feature | Python | iOS |
|---------|--------|-----|
| League-level headlines list | ✅ `NewsDialog` | ✅ Done — NewsView with SFSafariViewController |
| Open article in browser (web URL) | ✅ `webbrowser.open()` | ✅ Done |
| Game-specific news with 🎯 prefix | ✅ | ❌ Missing |
| NBA/NFL/MLB/NHL news endpoint | ✅ All supported | ✅ Done |

---

### Standings

| Feature | Python | iOS |
|---------|--------|-----|
| Basic W/L/PCT/GB/Streak | ✅ | ✅ Done |
| Division tabs (MLB: 6, NFL: 8) | ✅ | ✅ Done — DivisionStandings (ESPN level=3 divisions) + grouped sections |
| MLB expanded: R/RA/Diff/Home/Road/Playoff%/Magic# | ✅ | ✅ Done — expand button in table mode |
| NFL expanded: PF/PA/Diff/Div Rec/Seed/Ties | ✅ | ✅ Done |
| NBA expanded: PPG/OppPPG/DivW%/Seed | ✅ | ✅ Done |
| NHL expanded: OTL/Pts/GF/GA/Diff/Seed | ✅ | ✅ Done |
| Win% with ties (NFL: W+0.5T)/(W+L+T) | ✅ | ⚠️ Probably wrong |
| NCAAF standings + conferences | ✅ | ⚠️ Unknown |

---

### Team Schedules

| Feature | Python | iOS |
|---------|--------|-----|
| Team schedule view (full season) | ✅ `TeamScheduleDialog` | ✅ Done — TeamScheduleView |
| Season selector (2001–current) | ✅ `QComboBox` | ✅ Done — year picker menu |
| Today's game highlighted | ✅ Bold + yellow bg | ✅ Done — accent color highlight |
| Activate game → go to game detail | ✅ | ✅ Done — NavigationLink |
| MLB: 3 season types (pre/regular/post) | ✅ All fetched and merged | ⚠️ Regular season only for now |
| Background loading with progress | ✅ `QThread` | ✅ Done — async/await |
| Press team name in game detail → schedule | ✅ | ✅ Done — NavigationLink on team abbreviation |

---

### Venues

| Feature | Python | iOS |
|---------|--------|-----|
| Venues list for a league | ✅ `VenuesDialog` | ❌ Missing |
| Venue detail: type, surface, capacity | ✅ `VenueDetailsDialog` | ❌ Missing |
| Home teams per venue | ✅ | ❌ Missing |
| Interesting facts | ✅ | ❌ Missing |
| Venue shown in game detail | ✅ city/state | ❌ Missing |

---

### Statistics

| Feature | Python | iOS |
|---------|--------|-----|
| Team statistics per league | ✅ `StatisticsChoiceDialog` → categories | ✅ Done — StatisticsView / league leaders |
| Player statistics per league | ✅ | ✅ Done — athletes shown per leader category |
| Ranked results (1st, 2nd…) | ✅ | ✅ Done |
| Stat definitions help (Alt+D) | ✅ | ❌ Missing |
| MLB stats: MLB Stats API, 39 categories | ✅ `statsapi.mlb.com` | ❌ Deferred (P5.2) |
| NFL/NBA/NHL stats: ESPN API | ✅ | ✅ Done |
| ThreadPoolExecutor parallel fetch | ✅ 10–15 workers | ✅ async/await equivalent |

---

### Rankings / Polls

| Feature | Python | iOS |
|---------|--------|-----|
| NCAAF AP Poll, Coaches Poll | ✅ `PollsDialog` | ✅ Done — PollsView |
| NCAAM polls | ✅ | ✅ Done |
| NCAAWB polls | ✅ | ✅ Done |
| Rank movement indicators (↑/↓/—/NR) | ✅ | ✅ Done |

---

### Football-Specific

| Feature | Python | iOS |
|---------|--------|-----|
| Drives view: quarter → drive → plays | ✅ `QTreeWidget` | ✅ Done — NFLDrivesView |
| Drive result emoji (🏈/🥅/🔄/⚡) | ✅ | ✅ Done |
| Red zone indicator | ✅ | ✅ Done — red badge on live score row |
| Down/distance in score row | ✅ | ✅ Done |
| NCAAF Bowls & Playoffs tree | ✅ By competition type | ❌ Missing — games show but no bowl/playoff grouping |

---

### Accessibility Features

| Feature | Python | iOS |
|---------|--------|-----|
| Screen reader labels on all UI | ✅ | ✅ Good |
| AccessibleTable (3 view modes: Table/Quick/Full) | ✅ Platform-specific | ⚠️ `DataTableView` component (unclear quality) — iOS needs this for large stat tables |
| Voiceover on standings (with categories) | ⚠️ Partial | ⚠️ Partial |
| MLB pitch VoiceOver (adjust action) | ❌ Windows only | ✅ Done — better than Python |
| Score monitoring announcements | ✅ Windows UIA | ❌ Missing (iOS: post local notification) |
| Breadcrumb window/tab titles | ✅ | ❌ Navigation titles inconsistent |
| HTML export accessibility (ARIA tables) | ✅ | ❌ Missing |

---

## Part 2: Open Questions and Concerns

### 1. Past Game / Postseason Failures (HIGH PRIORITY — fix first)
The Super Bowl fails because the iOS app fetches the scoreboard with only `seasontype=2`. When a game was played in the postseason, it doesn't appear. The ESPN scoreboard API key: `seasontype=1` (preseason), `2` (regular), `3` (postseason). The fix requires:
- Detecting what season type a game belongs to
- Storing `seasontype` alongside `game_id` in the `Game` model
- Passing it through to the summary API fetch (the summary URL itself doesn't need it, but the game must be discoverable)

**Deeper issue:** The iOS app has no way to browse past dates, so past games are inaccessible even if postseason was fixed.

### 2. NFL Drives vs Plays
The Python app has both a drives tree AND a plays tree for NFL. For iOS, the current `GenericPlaysView` shows flat play-by-play. NFL drives deserve a dedicated `NFLDrivesView` that mirrors the MLB hierarchy — Quarter → Drive (result + yards) → individual plays. This is arguably more important for football than the flat plays list.

### 3. Statistics API Split
MLB statistics use `statsapi.mlb.com` (completely separate from ESPN), not ESPN's own API. ESPN's stats endpoint for other sports returns `leaders` data, not full ranked leaderboards. The Python app has separate code paths for each. On iOS, using `URLSession` to `statsapi.mlb.com` is no different technically, but the response model is completely different — it needs its own `Codable` types.

### 4. NBA Season Year Format
NBA and WNBA use year+1 format (2025-26 season = `season=2026`). The current iOS API service may be passing the wrong year. The Python app has a workaround: if early-season standings fail, fall back to teams endpoint. This needs to be replicated.

### 5. Venue Data Latency
The Python app disables enhanced venue details by default because fetching them requires per-game summary calls. On iOS, this should be lazy-loaded: venues list loads fast, tapping a venue kicks off the detail fetch. Not a concern, just needs async thinking.

### 6. Score Change Notifications
Python uses `winsound` + Windows-specific UIA. On iOS this becomes `UNUserNotificationCenter` for when the app is backgrounded, and `accessibilityAnnouncement` via `UIAccessibility.post(notification:)` when foregrounded. The monitoring pattern (Alt+M equivalent) should be a long-press or context menu on a game row.

### 7. Team Schedule Deep Linking
Python allows pressing the team name in game detail to jump to that team's schedule. This is premium UX — makes the app feel like a proper information system. Requires `NavigationLink` passing a `Team` object that triggers schedule fetch.

### 8. WNBA, NCAAH, NCAAWH
These are trivially addable to the `Sport` enum and API paths. NCAAH/NCAAWH have incomplete ESPN data (standings may show 0-0) — same as Python's known limitation. Should be added but not promised to have complete data.

### 9. Config / Per-League Feature Flags
The Python app has a `ConfigDialog` that lets users control which sections appear in game detail. On iOS this maps to Settings (app-level `UserDefaults`). Not critical for initial phases but worth designing the data architecture for from the start.

### 10. Pitch Explorer / Strike Zone Grid
The Python `PitchExplorationDialog` with 3×3 zone buttons is interesting but iOS already has `PitchMapView` which is arguably better. The iOS version should focus on the `PitchMapView` + AudioGraph + VoiceOver adjustable actions already built, rather than porting the 9-button grid literally.

---

## Part 3: Implementation Plan

### Guiding Principles
1. **Fix what's broken before adding new features.** A working app that does less is better than a broken app that does more.
2. **No dead-end UI.** Every screen needs working back navigation and error states.
3. **Data model first, views second.** Get the API models right before building views around them.
4. **Accessibility is not an afterthought.** Every view built without VoiceOver labels is incomplete.
5. **Ship phases, not features.** Each phase must result in a build that is better than the prior one across the board.

---

### Phase 1: Fix the Foundation (What's Broken Now)

These are blocking issues — the app is embarrassingly broken for anything off today's date.

**P1.1 — Date navigation on scores view**
- Add Previous/Next Day buttons to `ScoresView` for non-football sports
- Add Previous/Next Week buttons for NFL and NCAAF
- `ScoresViewModel` must hold a `currentDate: Date` and `currentWeek: Int` state
- For football: call the calendar API to resolve from today's scoreboard `week.number`
- For other sports: `dates=YYYYMMDD` query param

**P1.2 — Season type awareness**
- Add `seasonType: Int` (1/2/3) to the `Game` model
- Scoreboard API: try postseason first when a game isn't found in regular season
- Store `seasonType` in game so it can be passed to any related API calls
- This is the fix for the Super Bowl and all other playoff games

**P1.3 — Date picker modal**
- `DatePickerView` as a sheet: month wheel, day wheel, year wheel (SwiftUI `DatePicker` handles this natively)
- Accessible: `DatePicker` is natively VoiceOver-compatible with the `.graphical` or `.wheels` style

**P1.4 — Fix game detail view for all game states**
- Verify game detail loads for completed regular season, completed postseason, and in-progress games
- All three tabs (Box Score, Plays, Leaders) must not crash on empty data
- NFL plays tab currently shows nothing meaningful — wire it to the drives data at minimum for now

---

### Phase 2: Core Missing Features

**P2.1 — News**
- Add `NewsService.fetchNews(sport:) async throws -> [NewsItem]` to `ESPNAPIService`
- `NewsModel`: `headline`, `description`, `url`, `published`, `byline`
- `NewsView`: List of headlines, tap → `SFSafariViewController` (or opens Safari)
- Add "News" to the sport tab (add a 4th tab in the per-sport view alongside Scores, Standings)
- Game-specific news: add a "News" section within `GameDetailView`

**P2.2 — NFL Drives View**
- `NFLDrivesView` in `PlaysView.swift` or its own file
- Data model: `DriveGroup` (quarter, driveResult, description, yards, plays)
- Hierarchy: Quarter → Drive (collapsible, shows result emoji + yardage) → individual plays
- Drive results: 🏈 Touchdown, 🥅 Field Goal, 🔄 Turnover, ⚡ Punt, ❌ Incomplete
- Use the existing `drives` array from the summary API (it's already fetched, just not rendered)
- VoiceOver: `accessibilityLabel` on drive row = "Drive 3, Touchdown, 65 yards, 8 plays"

**P2.3 — Venue in Game Detail**
- Extract `venue.fullName`, `venue.address.city`, `venue.address.state` from `gameInfo` in summary API response
- Already in the response — just not displayed
- Add to the game header section of `GameDetailView`

**P2.4 — Betting / Broadcast in Game Detail**
- Extract `odds[0].details` (spread), `odds[0].overUnder`, `broadcasts[].names[]` from summary
- Add a collapsible "Game Info" row in `GameDetailView` (below the score header, collapsed by default)

---

### Phase 3: Standings Done Right

The current standings view is a flat list. It needs to match the Python app.

**P3.1 — Division grouping**
- Group standings results into divisions using the `children` array from the v2 standings API
- `StandingsView` becomes a `Picker`-based division selector or expandable division sections
- Divisions per league:
  - MLB: AL East/Central/West, NL East/Central/West (6 tabs)
  - NFL: AFC East/North/South/West, NFC East/North/South/West (8 tabs)
  - NBA: Atlantic/Central/Southeast, Northwest/Pacific/Southwest (6 tabs)
  - NHL: Atlantic/Metropolitan, Central/Pacific (4 tabs)

**P3.2 — Expanded stats columns**
- Toggle between basic (W/L/PCT/GB/Streak) and expanded per-sport columns
- Use the existing `Grid` from `BoxScoreView` for the table — horizontal swipe for overflow columns
- MLB: add R/RA/Diff/Home/Road/Playoff%/Magic#
- NFL: add PF/PA/Diff/Div Rec/Seed/Ties (with correct win% calculation)
- NBA: add PPG/OppPPG/Seed
- NHL: add OTL/Pts/GF/GA/Diff/Seed

---

### Phase 4: Team Schedules

**P4.1 — Team model**
- Add `Team` struct to the app (already partially in `Game.swift` as `TeamScore`)
- Add `TeamService.fetchSchedule(teamId:sport:season:) async throws -> [ScheduleGame]`
- Fetch all 3 season types (pre/regular/post) for MLB; regular only for NFL

**P4.2 — TeamScheduleView**
- Launched by tapping a team name in `GameDetailView`
- Season year picker at top
- List of games: date, opponent, home/away, score/status
- Today's game highlighted
- Tap game → `GameDetailView`

---

### Phase 5: Statistics

**P5.1 — ESPN stats (NFL/NBA/NHL)**
- Use existing leaders data from summary API — it's already being fetched
- `StatisticsView`: category list (left column or picker) → ranked results list
- Tap stat name → definition sheet (hardcode the definitions Python has)

**P5.2 — MLB Stats (MLB Stats API)**
- Separate `MLBStatsService` hitting `statsapi.mlb.com`
- 39 categories across hitting/pitching/fielding
- Parallel fetch using `async let` or `TaskGroup` for all categories at once
- `MLBStatisticsView` with section headers (Hitting / Pitching / Fielding)

---

### Phase 6: Polls and Rankings

**P6.1 — College rankings**
- `RankingsService.fetchRankings(sport:) async throws -> [Poll]`
- Polls endpoint: `{BASE_URL}/football/college-football/rankings`
- `PollsView`: Picker between AP Poll / Coaches Poll; List showing Rank/Team/Record/Points with movement indicators

---

### Phase 7: Additional Sports and Missing Features

**P7.1 — Add WNBA, NCAAH, NCAAWH to Sport enum**
- 3-line addition to `Sport.swift`
- NCAAH/NCAAWH ship with documented caveat: ESPN standings data is incomplete

**P7.2 — Score change notifications**
- `ScoreMonitor`: keeps a dict of watched game IDs → last known score
- On refresh, diff and post `UNUserNotificationCenter` notifications for backgrounded state
- `UIAccessibility.post(notification: .announcement, argument: "...")` for foreground state
- UI: long-press a game row → "Monitor this game" toggle, stored in `UserDefaults`

**P7.3 — Injuries in game detail**
- Extract `injuries[]` from summary response (it's already there in the API call)
- Display count in game detail header; tap → `InjuryDetailView` with player/position/status/type/details

**P7.4 — Officials in game detail**
- Extract `officials[]` from `gameInfo`
- Tap "Officials: N" → sheet showing ordered list of name + position

---

### Phase 8: Power Features

**P8.1 — MLB KitchenSink**
- New tab in `GameDetailView` for completed/live MLB games: "More"
- Sub-sections: Win Probability (chart, accessible as Audio Graph), Season Series, Key Articles

**P8.2 — Game wrap-up / share**
- Build summary string for a completed game (boxscore + plays summary + leaders)
- Share via `ShareLink` or `UIActivityViewController`

---

## Part 4: Files to Create / Modify

| File | Action | Phase |
|------|--------|-------|
| `Models/Sport.swift` | Add WNBA, NCAAH, NCAAWH | P7.1 |
| `Models/Game.swift` | Add `seasonType`, `venue`, `odds`, `broadcasts`, `drives` | P1.2 / P2.2 |
| `Models/News.swift` | Create | P2.1 |
| `Models/Standings.swift` | Add division grouping, expanded stat fields | P3.1 |
| `Services/ESPNAPIService.swift` | Date params, season type, news, drives, injuries, officials | Multiple |
| `Services/MLBStatsService.swift` | Create | P5.2 |
| `ViewModels/ScoresViewModel.swift` | Add `currentDate`, `currentWeek`, `seasonType` | P1.1 |
| `ViewModels/StandingsViewModel.swift` | Division grouping, expanded columns | P3.1 |
| `ViewModels/NewsViewModel.swift` | Create | P2.1 |
| `ViewModels/TeamScheduleViewModel.swift` | Create | P4.1 |
| `ViewModels/StatisticsViewModel.swift` | Create | P5.1 |
| `Views/ScoresView.swift` | Date/week navigation controls | P1.1 |
| `Views/GameDetailView.swift` | Venue, odds, broadcasts, injuries, officials, drives tab | P2 |
| `Views/PlaysView.swift` | `NFLDrivesView` | P2.2 |
| `Views/StandingsView.swift` | Division tabs, expanded columns | P3.1 |
| `Views/NewsView.swift` | Create | P2.1 |
| `Views/TeamScheduleView.swift` | Create | P4.2 |
| `Views/DatePickerView.swift` | Create | P1.3 |
| `Views/StatisticsView.swift` | Create | P5.1 |
| `Views/PollsView.swift` | Create | P6.1 |
| `Views/InjuryDetailView.swift` | Create | P7.3 |
| `Services/ScoreMonitorService.swift` | Create | P7.2 |

---

## Part 5: What Will NOT Be Ported

| Python Feature | Reason |
|----------------|--------|
| `winsound` / Windows UIA notifications | Platform-specific; iOS has better equivalents already called out above |
| HTML Game Wrap Up export | Replace with native `ShareLink` in Phase 8; HTML is browser-specific hack |
| `ESPNTextProcessor` control-char placeholders | ESPN API format; same resolution needed on iOS, but implement inline |
| `KitchenSinkDialog` UI layout | Concept ported; specific PyQt6 tab dialog is non-applicable |
| AccessibleTable 3-mode toggle (Table/Quick/Full) | Evaluate whether iOS SwiftUI `Grid` + `List` already covers this; if VoiceOver users need it, implement as accessibility-only setting |
| Soccer / EPL | Defer until all major sports done |
| `PitchExplorationDialog` 3×3 button grid | `PitchMapView` AudioGraph is already superior for VoiceOver |
| Background `QThread` loading pattern | iOS `async/await` is cleaner; not a port, already the iOS pattern |

---

## Part 6: Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| ESPN API changes / undocumented fields | High | Unit tests against cached API responses (`tests/fixtures/`) |
| statsapi.mlb.com rate limits | Medium | Cache responses 5 min; show stale data with timestamp |
| NFL drives array structure differs from plays | Medium | Audit live NFL game API response before building drive view |
| NBA season year off-by-one | Medium | Verify current season year at launch; store correct year |
| NCAAH standings always show 0-0 | Low | Document in-app; show "Standings unavailable" message |
| Super Bowl / postseason game ID lookup | High | Test manually with Super Bowl game ID; fix season type detection |
| Score monitoring battery drain | Medium | Minimum refresh interval 60s when monitoring; stop timer when app backgrounded and switch to push-style if possible |
| `drives[]` present for NFL but what about empty games? | Medium | Guard all collections; show "No drives available" fallback |

---

## Recommended Execution Order

1. **Phase 1** — Fix the broken stuff. Nothing matters if games don't load.
2. **Phase 2.1** — News. High visibility, relatively simple, makes the app feel real.
3. **Phase 2.2** — NFL Drives. Football is huge; football users need drives, not just flat plays.
4. **Phase 3** — Standings with divisions. The current flat list is embarrassing.
5. **Phase 4** — Team schedules. Deep-link from game detail to team — makes navigation feel connected.
6. **Phase 2 remainder** — Venue, Betting, Game info in detail.
7. **Phase 5** — Statistics. Complex but valuable.
8. **Phase 6** — Polls. NCAAF audience expects rankings.
9. **Phase 7** — Notifications, injuries, officials, missing sports.
10. **Phase 8** — Power features and polish.

Every phase ends with: (a) `xcodegen generate`, (b) full iOS Simulator build, (c) manual VoiceOver spot-check, (d) commit + push.
