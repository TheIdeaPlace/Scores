# Sports Scores — TestFlight Tester Guide

Sports scores app covering 10 leagues: MLB, NFL, NBA, NHL, NCAA Football/Basketball (men's/women's), WNBA, NCAA Hockey. Live data from ESPN's API.

## App Layout — Three Tabs

The app is organized into three bottom tabs:

| Tab | Icon | What's here |
|---|---|---|
| **Scores** | Court icon | Home sports list, Live Scores, all sport/league scores |
| **The Bench** | Waveform icon | Venue audio tours for all sports |
| **Settings** | Gear icon | Team name pronunciation, home page customization, exploration options |

---

## Scores Tab

### Home Screen

Opens on a sports list with a date navigation bar at the top. **Live Scores — All Sports** is always the first row. Below it, each sport you've enabled appears in your custom order.

**Date bar**: Use left/right arrows to move through dates (football moves by week). Tap **Today** to jump back to the current date/week. Pull down to refresh.

Tapping a sport opens that sport's scores page, already on the same date you're viewing on the home screen. Navigating back from a game detail always returns you to that date — not today.

### Scores Screen (per sport)

Games group into: **In Progress**, **Upcoming**, **Completed**. Upcoming games show time first, then day and date (e.g. *7:00 PM Thu 3/12*), then TV network if available.

**Scores tab**: date/week navigation bar, game list.  
**Standings / News / Stats** tabs: load independently.  
**Polls tab**: visible for NCAAF, NCAAM, NCAAWB, NCAAH, NCAAWH.

**Venues tab**: visible for the ten main leagues, not soccer or CFL. Select a venue for its details.

Tap the clock icon (top-right) to set auto-refresh: 1 minute, 2 minutes, 5 minutes, or Manual.

**Game detail** — tap any game, then swipe between tabs: Box Score, Plays/Drives, Info (leaders/injuries/venue), More (MLB-only).

**Score monitoring**: Swipe left on any game row → tap **Monitor**. Receive notifications when the score changes.

### Soccer

Soccer appears as a single **Soccer** row on the home screen (all leagues combined). Tapping opens the Soccer Hub, which shows Live Soccer plus individual league rows (Premier League, MLS, Champions League, etc.). Each league goes into its own standard scores screen.

---

## The Bench Tab

The Bench is the hub for all venue audio tours. Five sports are available:

| Row | Tour name |
|---|---|
| MLB Stadiums | All 30 parks with real wall distances |
| NFL Football Field | 120 yards, yard lines, hash marks, goal posts |
| NHL Hockey Rink | 200 ft, blue lines, zones, creases |
| NBA Basketball Court | 94 ft, paint, 3-point arc, free throw line |
| Soccer Pitch | 105 m × 68 m, penalty areas, center circle, goals |

### Two-Screen Tour Flow

Each venue tour is now two screens:

**Screen 1 — Info page**: Facts and dimensions for that sport. Baseball also shows a stadium picker (choose from all 30 MLB parks) and the park's notable features. A **"Touch the [Field/Court/Rink/Pitch]"** button appears in the top-right corner of the navigation bar.

**Screen 2 — Touch canvas**: Tap "Touch the [Field/Court/Rink/Pitch]" to arrive here. The canvas fills nearly the entire screen for maximum touch area. The status bar at the bottom shows your current location as you drag.

### How the Audio Tour Works

**Drag your finger** across the canvas. Continuous audio changes with terrain:
- **Fair territory** — soft, smooth (grass/ice/hardwood)
- **Warning track / penalty areas** — coarser, textured
- **Out of bounds / foul territory** — rough

Sound pans left and right to match your horizontal position. Lifting your finger announces your zone. Haptic pulse fires at zone boundaries (yard lines, blue lines, 3-point arc, etc.).

**Baseball specifics**: Each of the 30 MLB stadiums has real wall distances. The info page lets you pick the park before heading to the canvas. The canvas title updates to that park's name.

**Test ideas**:
- Baseball: Compare Fenway Park (Green Monster, 37 ft left wall) vs. a symmetric park
- Football: Drag from end zone across the 50-yard line — listen for chimes every 5 yards
- Hockey: Cross the blue lines and find the goal crease
- Basketball: Move from the 3-point arc into the paint
- Soccer: Find the penalty spot and penalty area line

---

## Settings Tab

### VoiceOver Team Names

Controls how team names are announced when VoiceOver reads a game row. Options:

- **Abbreviation** — "LAD", "NYY"
- **City** — "Los Angeles", "New York"
- **Nickname** — "Dodgers", "Yankees"
- **Full name** — "Los Angeles Dodgers", "New York Yankees"

A live example shows exactly what VoiceOver will say for the Milwaukee Brewers with each setting selected.

### Home Page Sports

Customize which sports appear on the Scores home screen and in what order:

- **Drag to reorder** — grab the handle on any sport row and drag it to a new position. With VoiceOver: use the **Move up**, **Move down**, **Move to top**, **Move to bottom** custom actions from the rotor.
- **Show/hide toggle** — tap the eye icon (or use the **Toggle visibility** custom action) to hide a sport entirely. Hidden sports are still available; they just won't appear on the home screen.
- **Live Scores** is always locked at the top and cannot be moved or hidden.

### Stadium Exploration

Controls VoiceOver's direct touch behavior on the tour canvas:

- **On (default)**: Double-tap the canvas to activate, then drag freely. VoiceOver is silenced during the drag so audio is uninterrupted.
- **Off**: Canvas uses the standard VoiceOver double-tap-and-hold passthrough instead.

---

## MLB Pitch Zone Explorer

Open any MLB game with play-by-play data. In the **Plays** tab, tap **Explore Zone** next to the Strike Zone Map.

**Drag your finger** across pitch locations. Tones encode:
- **Height** → musical note (high pitch = high note, low = low note)
- **Horizontal position** → stereo pan (inside = batter's side, outside = opposite)
- **Velocity** → tone duration (fastball = short, changeup = longer)

Pentatonic scale keeps notes harmonious. Lifting the finger announces: pitch number, type, velocity, location, result, and count.

**Alternative navigation**: Flick up/down with VoiceOver to step through pitches one by one.

Arrows navigate between at-bats. **All at-bats** toggle overlays the entire game.

---

## Testing Checklist

- [ ] Navigate dates on the home screen then tap a sport — confirm sport view opens on the same date
- [ ] Navigate to a previous day, open a game, go back — confirm you return to that previous day (not today)
- [ ] Open games in different states (upcoming/live/completed), check all tabs load
- [ ] Verify standings, news, stats populate for several sports
- [ ] Tap team name in game detail → opens team schedule
- [ ] Set auto-refresh to 1 minute during a live game, verify it refreshes
- [ ] Monitor a game via swipe-left → verify notifications fire when score changes
- [ ] Soccer: home screen row → Soccer Hub → individual league → scores
- [ ] The Bench: tap a sport → read info page → tap "Touch the [Field]" → explore canvas
- [ ] Baseball tour: pick two different stadiums from the info page, compare wall distances
- [ ] Settings: change team name preference → return to scores → verify VoiceOver reads new format
- [ ] Settings: hide a sport → confirm it disappears from home screen
- [ ] Settings: reorder sports → confirm new order persists after backgrounding app
- [ ] Settings: toggle Direct Touch off → verify VoiceOver passthrough works on canvas

## Known Quirks

- **Spring training** (Feb–Mar): seasontype 1. Regular season starts late March.
- **NBA/WNBA**: season years use year+1 (2025-26 = 2026).
- **NCAA Hockey**: data sometimes incomplete.

## Feedback

Note bugs, confusion, or slowness. For exploration features: Does spatial audio work? Can you distinguish pitch locations and stadium zones by sound? Does the two-screen tour flow feel natural? Send feedback through TestFlight.