# Screen reader check: t04-standings

Speech from NVDA's speech log (exact text). A logged utterance is what NVDA sent to its voice; the next key can cut it off, so the log shows what was sent, not that all of it was heard.

**8 of 10 expectations met.**

## line 3: `x`

-   5.42 s: Sports Scores window
-   5.43 s: League Selection List list List of available sports leagues and live scores
-   5.45 s: Live Scores - All Sports
-  17.33 s: NFL
-  19.41 s: Scores List list List of games and scores for the selected date or week
-  19.42 s: Loading scores...
-  22.19 s: Upcoming, 1 game
-  31.41 s: --- Fantasy Cheatsheet ---
-  33.44 s: --- NFL Draft ---
-  33.46 s: --- Venues ---
-  33.48 s: --- Transactions ---
-  33.52 s: --- Teams ---
-  33.55 s: --- Statistics ---
-  33.58 s: --- Standings ---

## line 18: `k {ENTER}`

-  37.24 s: NFL Standings dialog
-  37.25 s: Division Standings grouping Team standings by division, use arrow keys to navigate between divisions
-  37.26 s: AFC East tab control
-  37.27 s: AFC East tab
- **PASS** (line 20) says `Division Standings`
- **FAIL** (line 22) says `AFC East Standings` — not said

## line 23: `k {TAB}`

-  51.68 s: AFC East Standings grouping AFC East Standings table showing team records and statistics. Multiple view modes available: Alt+V to cycle views, Alt+T for table, Alt+Q for quick list, Alt+F for full list.
- **PASS** (line 25) says `AFC East Standings`

## line 26: `k %q`

-  54.94 s: AFC East Standings - Quick List list Switched to Quick List View. AFC East Standings table showing team records and statistics in quick list format. Use up/down arrow keys to navigate, Alt+V to cycle views, Alt+T for table view.
-  55.00 s: 1, Buffalo Bills, 6, 1, 0, 0.857, —, N/A, 233, 181, +52, 0-1, 1
- **PASS** (line 28) says `Quick List`
- **PASS** (line 29) says `Buffalo Bills`

## line 30: `k %f`

-  57.83 s: AFC East Standings - Full List list Switched to Full List View. AFC East Standings table showing team records and statistics in detailed list format with headers. Use up/down arrow keys to navigate, Alt+V to cycle views, Alt+T for table view.
-  57.85 s: Pos: 1; Team: Buffalo Bills; W: 6; L: 1; T: 0; PCT: 0.857; GB: —; Streak: N/A; PF: 233; PA: 181; Diff: +52; Div Rec: 0-1; Seed: 1
- **PASS** (line 32) says `Full List`
- **PASS** (line 33) says `Team: Buffalo Bills`

## line 34: `k %t`

-  60.96 s: AFC East Standings table Switched to Table View. AFC East Standings table showing team records and statistics. Use up/down/left/right arrow keys to navigate cells, Tab to enter or exit table. Alt+V to cycle views, Alt+Q for quick list, Alt+F for full list.
-  61.00 s: Buffalo Bills, Pos, 1 data item 1 row 1 Pos column 1
- **PASS** (line 36) says `AFC East Standings`

## line 38: `k %q`

-  63.97 s: AFC East Standings - Quick List list Switched to Quick List View. Switched to Quick List View. AFC East Standings table showing team records and statistics in quick list format. Use up/down arrow keys to navigate, Alt+V to cycle views, Alt+T for table view.
-  63.99 s: 1, Buffalo Bills, 6, 1, 0, 0.857, —, N/A, 233, 181, +52, 0-1, 1
- **FAIL** (line 40) doesn't say `Switched to Quick List View. Switched to` — said, but shouldn't be

## line 41: `k {ESC}`

-  68.20 s: Scores List list List of games and scores for the selected date or week
-  68.22 s: --- Standings ---
- **PASS** (line 43) says `Scores List`

