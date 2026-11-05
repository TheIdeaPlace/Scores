# Sports Scores — iOS User Guide

This guide covers all features of the Sports Scores iOS app, including the audio and accessibility features.

---

## Getting Around

### Tab Bar

The app has three tabs at the bottom of the screen:

| Tab | What's there |
|-----|--------------|
| **Scores** | Sports list and scores — the home page |
| **The Bench** | Team Hub, venue audio tours, NFL Draft, Transaction Hub |
| **Settings** | Preferences and display options |

### Scores Tab (Home Screen)

The home page opens a list of sports. Select any sport to open its scores and standings. The first row — **Live Scores** — shows current games across all sports at once.

A date navigation bar sits at the top of the home screen. Use the left and right arrows (**Previous Day** and **Next Day** in VoiceOver) to move one day at a time, or select **Today** to jump back to the current date.

Available sports (exact list depends on your Settings):

- MLB Baseball
- NFL Football
- NBA Basketball
- NHL Hockey
- NCAA Football
- NCAA Men's Basketball
- NCAA Women's Basketball
- WNBA Basketball
- NCAA Men's Hockey
- NCAA Women's Hockey
- Soccer (hub — EPL, MLS, Champions League, and more)
- Golf (hub — PGA Tour and LPGA Tour)

Soccer and Golf open a hub screen with their own league list. Both can be shown or hidden from the home page in Settings.

#### Soccer Hub

The Soccer hub mirrors the main home screen but scoped to soccer leagues. It has its own date bar, a **Live Soccer** row for all leagues combined, and individual rows for each league.

#### Golf Hub

The Golf hub shows PGA Tour and LPGA Tour. Each tour leads to a leaderboard view for the current or most recent tournament.

---

### Sport Screen

Each sport screen has five tabs along the bottom:

| Tab | Contents |
|-----|----------|
| **Scores** | Games for the selected date or week, grouped by status |
| **Standings** | Division or conference standings |
| **News** | Recent news and headlines |
| **Stats** | League statistical leaders |
| **Polls** | AP and Coaches polls — college sports only, when available |

Select any game row to open its detail view.

#### Date Navigation (Scores tab)

A date bar sits below the navigation title. Select the left or right arrows (**Previous Day** / **Next Day**, or **Previous Week** / **Next Week** for football in VoiceOver) to move one day at a time (or one week for football). Select **Today** to return to the current date. Select the date itself to open a calendar picker.

For **NFL and NCAA Football**, the bar shows a week number instead of a calendar date.

#### Game Sections

Games on the Scores tab are grouped into three sections:

- **In Progress** — games currently being played
- **Upcoming** — games scheduled later today or this week
- **Completed** — games that have finished

Only sections with games are shown.

#### Auto-Refresh

A clock icon in the toolbar controls how often scores refresh automatically. Options: 1 minute, 2 minutes, 5 minutes, and manual. Pull down on the list to refresh at any time.

#### Table View Modes

Many screens that show statistics, standings, rosters, or box scores have a view-mode button in the toolbar. Three modes are available:

| Mode | Format |
|------|--------|
| **Table View** | Traditional grid with columns and rows; VoiceOver can navigate by row and column |
| **Quick List** | Each row as a comma-separated line — compact and fast to scan |
| **Full List** | Each field on its own line with its header label — most context per item |

The default mode is set in Settings. You can change it per screen using the toolbar button without affecting the default.

---

### Game Detail Screen

The game header shows both teams, the score, and the current status. For MLB games, a small walking-figure button next to the venue name opens the **Field Tour** for that stadium. A share button appears in the toolbar for completed games.

Game detail has up to four tabs:

| Tab | Contents |
|-----|----------|
| **Box Score** | One tab per team and stat group (such as "BOS Players" or "GB Kicking"), then the team comparison. Tables have a Totals row wherever ESPN sends one (every sport but hockey), and a player who sat out reads "Did not play". Before a game, the team table holds season stats and says so |
| **Plays** or **Drives** | Play-by-play (basketball, hockey, baseball) or drive summaries (football) |
| **Info** | Game leaders, injuries, officials, venue, news |
| **More** | Win probability, season series — MLB only |

#### Play-by-Play

For timed sports (basketball, hockey, NFL), plays are grouped by period and ordered within each period. Each play shows what happened, the game clock, and the score at that moment.

For MLB, plays are pitch-level. When pitch coordinate data is available, an **Explore Zone** button appears at the top of the Plays tab. See the **Strike Zone Explorer** section below.

---

## Team Hub

Team Hub lives in **The Bench** tab. It lets you explore any team across all sports, bookmark your favorites, and see live game updates at a glance.

### Browsing Teams

Select a sport from the list. College sports (NCAA Football, Basketball, Hockey) first show a conference picker; professional sports go straight to the team list. Select any team to open its detail screen.

### Team Detail

A team's detail screen has five tabs:

| Tab | Contents |
|-----|----------|
| **Info** | Team overview: record, standing, upcoming game, venue, head coach |
| **Roster** | Full roster in a table — Name, number, position, age |
| **News** | Recent headlines |
| **Schedule** | Full season schedule with results |
| **Transactions** | Recent player moves, signings, and releases |

A star button in the top-right corner adds or removes the team from your favorites.

### Favorites

When you have favorites, they appear as cards at the top of the Team Hub screen, above the sport browser. Each card shows:

- The team name and sport
- Live game score with inning/period/clock — for baseball this includes pitcher, batter, base runners, count, and outs
- The most recent completed game result
- The next scheduled game
- Up to two recent news headlines (select a headline to open the full article)

Select the team name on a card to open the full team detail screen.

#### Reordering Favorites

**Press and hold** any favorites card to bring up the context menu, which has:

- Move Up
- Move Down
- Move to Top
- Move to Bottom

Options that don't apply — for example, Move Up when the team is already first — are not shown.

**VoiceOver:** With VoiceOver on, swipe to a favorites card and open the Actions rotor. The same four move actions appear there, and only the ones that apply are present.

#### Removing a Favorite

Use the context menu on a card (press and hold), or with VoiceOver open the Actions rotor and activate **Remove from Favorites**.

---

## The Bench

The Bench tab is the home for deeper exploration tools.

### Venue Audio Tours

Each tour displays a scale drawing of a real sports venue. Drag your finger across the canvas and the app plays continuous terrain-based audio. When you lift your finger, VoiceOver announces the zone name and distance or location. A haptic pulse fires when you cross a zone boundary.

**VoiceOver usage:** The canvas is a direct-touch area. You can configure the activation method in Settings under Stadium Exploration. With Direct Touch on, double-tap the canvas to activate it, then drag freely — VoiceOver is silenced during the drag. With Direct Touch off, swipe to focus the canvas, then use the VoiceOver double-tap-and-hold passthrough gesture.

Available tours:

**MLB Stadiums** — All 30 MLB parks with real wall distances. A picker at the top lets you choose the stadium. Park details (location, year opened, roof type) and exact wall distances are listed below the canvas. The three terrain surfaces are:

| Surface | Sound character |
|---------|----------------|
| Fair territory (grass) | Soft, smooth swish — high frequencies removed, like wind through grass |
| Warning track (cinder/gravel) | Coarser, with a slight crunch |
| Foul territory (hard surface) | Rough, full-spectrum scrape |

Stereo panning follows your finger: left field sounds left, right field right, center field centered.

You can also open the field tour for the specific stadium from a game's header — select the walking-figure button next to the venue name.

**NFL Football Field** — 120-yard field with yard lines, hash marks, and goal posts.

**NHL Hockey Rink** — 200-foot rink with zones, blue lines, and creases.

**NBA Basketball Court** — 94-foot court with the paint, 3-point arc, and free throw line.

**Soccer Pitch** — 105 m × 68 m pitch with center circle, penalty areas, and goals.

### Strike Zone Explorer

The Strike Zone Explorer has two modes:

**Standalone (from The Bench):** An educational tool with the standard strike zone dimensions — 17 inches wide, approximately 24 inches tall for a 6-foot batter. Drag anywhere on the zone to hear a tone that encodes pitch height (higher position = higher note) and horizontal position (inside/outside = stereo pan). When you lift your finger, the app announces "Strike" or "Ball" and the location using body-part references (at the knees, belt high, at the letters). A batter-hand toggle flips the inside/outside labels.

**Live pitch data (from a game's Plays tab):** When viewing an MLB game with pitch coordinate data, select **Explore Zone** in the Plays tab. This overlays real pitch locations from the game.

**How the audio encodes pitch location:**

- **Height** → musical note on an A-minor pentatonic scale. Higher in the zone = higher note.
- **Horizontal position** → stereo pan. Inside = panned toward the batter's side. Outside = panned away.
- **Pitch velocity** (when available) → note duration. Harder pitch = shorter, crisper note. Slower pitch = longer, more sustained.

**Two ways to navigate (live pitch data mode):**

1. **Drag to explore** — drag your finger around the zone. Audio plays for coordinates under your finger. When you lift, VoiceOver announces a full pitch summary: pitch number, type, velocity, location, result, and count.

2. **Flick up/down** — with the canvas focused in VoiceOver, flick up or down to step through pitches one at a time. Audio plays for each pitch. The value field updates with the current pitch (e.g., "Pitch 3 of 7: Four-seam FB").

An at-bat navigation bar below the canvas lets you move between at-bats or view all pitches from the full game overlaid at once.

### NFL Draft

Browse NFL draft picks by year and round. Select the year from a menu and the round using the segmented control. Each pick shows the selection number, team, player name, position, and college.

### Transaction Hub

Browse player moves, signings, and releases across all sports. Select a sport, then a team, to see that team's recent transactions.

---

## Settings

Settings is the third tab. Changes take effect immediately.

### VoiceOver Team Names

Controls how team names are read throughout the app. Four options:

- **Abbreviation** — "BOS", "NYY"
- **City** — "Boston", "New York"
- **Nickname** — "Red Sox", "Yankees"
- **Full Name** — "Boston Red Sox", "New York Yankees"

An example for the Milwaukee Brewers is shown below the picker so you can hear exactly what each option sounds like before committing.

### Table Default

Sets the default view mode for all tables (standings, roster, box score, stats). Choose from Table View, Quick List, or Full List. You can always override this per screen without changing the default.

### Home Page Sports

Shows the full list of sports that can appear on the home screen. For each sport you can:

- **Toggle** to show or hide it on the home screen
- **Drag** (or use the Move Up/Down/Top/Bottom VoiceOver actions) to reorder the list

Soccer and Golf are hub sports — they can be toggled on or off but not reordered relative to the main list.

### Stadium Exploration

**Use Direct Touch** — controls how VoiceOver interacts with the venue tour canvas.

- **On:** Double-tap the canvas to activate it. You can then drag freely. VoiceOver is silenced during the drag.
- **Off:** Swipe to focus the canvas, then use the VoiceOver double-tap-and-hold passthrough gesture to drag.

---

## VoiceOver

The app is built for VoiceOver. Some behaviors to know:

- **Game rows** combine all sub-elements into one VoiceOver element. Reading order: away team, away score, home team, home score, game status.
- **Section headers** (In Progress, Upcoming, Completed) have the heading trait, so you can jump between them with the Headings rotor.
- **Play-by-play rows** read as: what happened, clock, score.
- **Date controls** in toolbars support swipe up/down to increment or decrement the date without opening the picker.
- **Tables** in Table View mode use the data-table accessibility protocol. VoiceOver announces row and column position, and you can navigate by row or column using the rotor.
- **Quick List and Full List** modes present each row as a single element — no column navigation, just straight reading order.
- **Favorites reordering** — open the Actions rotor on any favorites card. Move Up, Move Down, Move to Top, and Move to Bottom appear when they apply.
- **Sports reordering in Settings** — open the Actions rotor on any sport row in Settings. The same four move actions are available.
- **Team Hub** favorites cards show a full live game label for baseball: pitcher name, batter name, base runners, count, and outs.

---

## Data Notes

All data comes from ESPN's public API. A few things to know:

- **MLB Spring Training** runs February–March. During that window, the app defaults to spring training games. Regular season starts in late March.
- **NBA and WNBA** season years follow the second year of the season (2025–26 season shows as 2026).
- **NCAA Hockey** data from ESPN is sometimes incomplete — ESPN sends no box score at all for college hockey, so the Box Score tab says so.
- Game times are shown in your device's local time zone. A game with no set time reads **Time TBD**.
- **"Today" lasts until 5 AM.** Until then, Live Scores and the league screens stay on last night's games, because a West Coast game can run well past midnight in the East.
- **College basketball plays** with no real location, such as substitutions and free throws, have no location or tone. ESPN doesn't say where they happened.

