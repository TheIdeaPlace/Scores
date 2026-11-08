# Running log, college football bug bash, Sat Nov 7, 2026

Build: Scores 1.1.1 release installer (daa093a), VM ClaudeTesting on SURFACEPRO7, NVDA 2026.2, Central time.
Settings reset before every clip (college football coverage: default, all Division I).

## Rig notes (not app findings)
- VM was attached to the External Wi-Fi switch while this PC was on Ethernet: 169.254 address, no network. Moved it to External Ethernet.
- OneDrive toasts stole focus; reset.ps1 now kills OneDrive and turns toasts off.
- Another session switched the main Scores folder to branch listen-to-the-game mid-clip; runs now come from worktree .claude/worktrees/bugbash on main.
- Once, about 13:30, vmtest's UIA queries into Scores took 50-60 s and a clip hung for 15 min (Drives). Not reproduced: four open/close cycles of Drives stayed at the 11 s baseline. Seen once, not reported.

## s1-ncaaf-slate (12:50): league view, Week 10, every row
- NOT a bug: 124 of 124 Division I games, 42 live, 69 upcoming, 13 final, matching the feed's week board. "Week 10" matches ESPN's week number.
- NOT a bug: ranks on rows ("#9 BYU Cougars 20 at #3 Utah Utes 14"), "vs" on the neutral-site final (Central Michigan vs Eastern Michigan), Final/OT.
- [wording] After a touchdown the live row's play is only the extra point: "Oklahoma State Cowboys 28 at Kansas State Wildcats 7 | (S. Keltner KICK) 0:50 Q1", "Fordham ... | (B. Henderson KICK) 12:06 Q2". ESPN's lastPlay is the PAT; the touchdown itself isn't said.
- [wording] Halftime rows: "... | End of Half. 0:00 Q2 (Halftime)": three ways of saying halftime.
- [wording] Play text cut at 60 characters mid-word: "rush middle for 2 yards gain to...", "pass complete short right to #16...".

## g1-live-details (12:58): Duke at NC State, live
- NOT a bug: Back from the game lands on the same game row (was broken in the Nov 2 bash).
- [data] No live situation in Game Details: no down, distance, possession or field position, though the list row has them.
- [wording] "Score: Wolfpack: 3 - Blue Devils: 17": nicknames, home first, under the title "Duke Blue Devils at NC State Wolfpack".
- Not a bug: no Officials row; ESPN's college summary has none (officials: 0).
- F5 on game details lands on the first row ("NC State Wolfpack (Home)") rather than where you were.

## g2-drives, g3-drives-q2 (13:52, 14:00): Drives tree, Duke at NC State
- [speech] Expanding or collapsing a quarter or drive says nothing (Right on "Quarter 3 collapsed": silence; Left to collapse: silence).
- [speech] Drives inside a quarter, and plays inside a drive, read "level 1" with row numbers running on (Kickoff "row 4 level 1" under Quarter 3; a play "row 8 level 1"). Issue #139, now seen with NVDA.
- [data] WRONG TEAM CREDITED: "[TD 7pts] NC State Wolfpack: 5 plays, 37 yards, 0:26". NC State missed a 50-yard field goal and Duke returned it 100 yards for a touchdown (score 31-3, NC State never scored a TD). ESPN gives NC State's drive result "TD"/"Touchdown"; the app takes the badge and the team from the drive. The plays' scores (homeScore/awayScore) show who scored.
- [wording] Each play reads its clock twice: "[3:04] [1 & 10 from NCSU 19] (+2 yards) (03:07) Shotgun ...".
- [focus] F5 in Drives closes and reopens the dialog: back on Quarter 1, everything collapsed, and the dialog announced again.
- `n t` in the Drives dialog reads the main window's title, not "Drives Details".

## g4-box (14:10): box score, Duke at NC State, live
- NOT a bug: 16 tables plus Team Stats as a list; Enter opens one; cells read "Walker Eget, C/ATT, 21/30"; Totals row; Alt+Q, Alt+F, Alt+T; Ctrl+Tab to the next table; Escape back to the list on the same row; Escape again to the Boxscore row.
- [speech] Each table opening speaks two long descriptions, the grouping's and the table's, about 50 words: "Duke Blue Devils Passing grouping ... Multiple view modes available: Alt+V to cycle views, Alt+T for table ..." then "Duke Blue Devils Passing table ... Use up/down/left/right arrow keys ...".
- `n t` again reads the main window's title in the dialog.

## l1-live-monitor (14:16): Live Scores, monitoring (type-ahead landed on a women's basketball game)
- [speech] THE FOCUSED ROW IS REREAD ON EVERY TIMER REFRESH, unchanged: at 64, 124, 184 and 244 s, "Alabama State Lady Hornets at West Georgia Wolves - 32-35 (Halftime) | End of 2nd Quarter - monitoring", once a minute, same text. Kelly's skipped Windows check 6 from 1.1.1. Likely cause: _refresh_rows_in_place sets every row's UserRole data on each refresh (scores.py:1184) even when the text is unchanged; Qt reports the item changed and NVDA rereads the focus.
- [wording] Score alert lists home first after "away at home": "Alabama State Lady Hornets at West Georgia Wolves: West Georgia Wolves 37 - Alabama State Lady Hornets 32".
- Score alert and row update were both spoken (row first, then the alert): two utterances for one score change.

## l2-live-football (14:30): Live Scores, monitoring Arkansas at Auburn
- NOT a bug: score alert on Arkansas's field goal; Back from the game returns to the same row, monitoring kept, "Loading live scores..." then the row.
- [wording] Alert home first again: "Arkansas Razorbacks at Auburn Tigers: Auburn Tigers 9 - Arkansas Razorbacks 13".
- [listen] The focused live football row is read in full on every 1-minute refresh, because its play text changes each time (about 25 words a minute). Correct by the rule "speak when the text changes", but heavy; Kelly to judge.
- [wording] "(A. McPherson PAT MISSED)" as the play: same PAT-only text as s1.

## o1-overtime (14:35): Towson 43 at Sacred Heart 40, Final/2OT
- NOT a bug: row "[Final/2OT]", Game Time "Final/2OT", Drives has "OT" and "2OT" nodes.
- [data] "TD 7pts" is said for every touchdown: Towson's walk-off touchdown in 2OT was 6 points (40-37 to 43-40, no try), Auburn's after "PAT MISSED" too.
- [data] Wrong team again, from the summary: Sacred Heart's kickoff drive is "Touchdown", but Towson's J.Zollar returned the kickoff 99 yards (14-21 from 7-21). The app would say "[TD 7pts] Sacred Heart Pioneers". Same cause as Duke's field goal return.
- [wording] Unmapped badge "[FUMBLE RETURN TD]" (raw ESPN result) next to mapped ones like "[TD 7pts]".

## l3-final (14:29-14:44): monitoring Texas at Missouri in its last two minutes
- Run cut off: vmtest stops a command after 900 s, and the clip was 16 minutes. Speech taken from NVDA's own log (clips/nvda-log-1530.txt). The game went final after the cut, so "what is said at the final" is still untested.
- Same once-a-minute full reread of the focused row as l2 (text changed each time).
- [wording] The score alert carries ranks the row doesn't: alert "Texas Longhorns at Missouri Tigers: #18 Missouri Tigers 20 - #7 Texas Longhorns 34", row "Texas Longhorns 34 at Missouri Tigers 20 | ...". Home first again.
- [wording] PAT-only play again: "(G. Spetic KICK)" for two refreshes after Texas's touchdown.

## l4-ot-final: monitoring Arkansas 23 at Auburn 26 through the final
- [speech] No alert when a monitored game ends: the focused row's text changed to "Arkansas Razorbacks 23 at Auburn Tigers 26 [Final] - monitoring" and was read because focus was on it. On any other row nothing would be said. Score alerts exist, a "final" alert doesn't.
- [speech] CONFIRMED with identical text: the final row, unchanged, was read again at every refresh for six more minutes (304, 424, 484, 544, 604 s ...). Same cause as l1.
- Monitoring stays on, and the row stays in Live Scores, after the final.

## g6-scheduled-wrap: Miami at Notre Dame (scheduled), Texas at Missouri (final)
- [data] TWO START TIMES FOR ONE GAME: the row says "(Sat 11/7 6:30PM)" (Central, the VM's zone); Game Details says "Game Time: Sat, November 7th at 7:30 PM EST". The details row isn't converted to local time.
- NOT a bug: scheduled details rows (records, Status: Scheduled, Venue, Weather 41°F, Betting Line ND -7, O/U 54.5, TV NBC); Back lands on the same game.
- Game Wrap Up: "Game Wrap Up dialog Game Wrap Up opened in your default web browser. OK button". In the VM, Edge's first-run page then took over, so the rest of the clip was lost (rig, not reported). Kelly to judge on a real PC whether the message box after the browser opens is in the way.

## g7-bowls-news: Bowls & Playoffs, league News
- [speech] The Bowls list has no name: NVDA says just "list" (scores.py:12278, no setAccessibleName).
- [speech] SECTION HEADERS CAN'T BE REACHED: the headers are made unselectable (scores.py:12364, NoItemFlags), so Down skips them. Only the first, "=== Championship ===", is heard (it has focus at open). Down then goes National Championship, Orange Bowl semifinal, Sugar Bowl semifinal, Fiesta Bowl quarterfinal with no "Semifinals" or "Quarterfinals" said, so the semifinals sound like they're under Championship.
- [data] CFP first-round games are filed under "Other Bowls": ESPN gives them competition type 1 ("STD") with the note "College Football Playoff First Round Game"; the code only looks for "first round" when the type is 42 (scores.py:12348-12356). Code and feed checked; the walk didn't reach them.
- [focus] Bowls opens with focus on the unselectable header ("list item focused", no "selected").
- League News opens with no row selected ("... not selected"), as in the game's News.
- Hypothesis, not seen today: Live Scores sorts upcoming games by display text ("Sat 11/7 6:30PM"), so a 10:00 PM game sorts before 6:30 PM (scores.py:1272). No upcoming game today had a two-digit hour to show it.

## k1-league-keys and vmtest checks: league view keyboard
- NOT a bug: F5 keeps the row (on a game and on a header); Tab cycles list, Back, Previous Week, Next Week, Refresh; Shift+Tab reverses; Enter and Space both press Previous/Next Week and focus returns to the list; from Home, Escape returns to the NCAAF row.
- Minor: launched with --ncaaf, Escape lands on "Live Scores - All Sports", not NCAAF.
- [keyboard] TYPE-AHEAD CAN'T FIND A RANKED TEAM BY NAME (vmtest focus): typing "Alabama Crim" lands on "Alabama A&M Bulldogs 3 at Prairie View A&M ..." and "Georgia Bull" on "Georgia State Panthers ...", because the ranked rows start "#5 Alabama Crimson Tide", "#2 Georgia Bulldogs". Typing "#5" works, but you have to know the rank.
- [data] Stale situation at halftime: "Alabama A&M Bulldogs 3 at Prairie View A&M Panthers 14 | No Huddle-Shotgun ... 0:00 Q2 | 3rd & 12 at PV 14 (Halftime)": a down and distance at halftime. And "Georgia State 26 (RZ) at App State 17 | End of 3rd quarter. 13:33 Q4": last play a minute and a half old. Both ESPN's data as given.

## d2-polls: Polls & Rankings
- NOT a bug: tabs CFP Rankings, AP Poll, AFCA Coaches Poll, FCS Coaches Poll, AFCA Div II...; Ctrl+Tab; Escape back to the --- Polls --- row.
- [speech] A cell's row context is the rank number, not the team: "1, Team, Miami Hurricanes", then down the Previous column "2, Previous, NR", "3, Previous, NR": the team is never said.
- [wording] CFP Rankings has an empty Points column: "1, Points," (the CFP has no points). Quick List reads the gap: "3, Utah Utes, 8-0, , NR".
- [speech] Each poll tab opens with two long descriptions (grouping and table), as in the box score.

## d4-weeks: Alt+P / Alt+N
- NOT a bug: Week 9, 8, back to 10, 11...15, Bowls, CFP; title changes each time; week said each time. Weeks 11 and 12 both have 130 games, as ESPN does.
- [speech] Past the last week (CFP), four Alt+N presses say nothing: the "last week of the season" text never reaches speech.
- [wording] "Week: Bowls", "Week: CFP" (title "NCAAF, Week: CFP - Sports Scores").
- Each step reads "Loading scores..." then the first section header, then the week: three utterances.
- Rig: a Windows activation toast spoke mid-clip at Week: CFP.

## d5-teamhub: Teams > ACC > Miami Hurricanes
- NOT a bug: conference list, ACC table sorted by wins, Team Hub tabs, Alt+S opens the schedule on today's game ("Sat, Nov 07: @ Notre Dame Fighting Irish - 11/7 - 6:30 PM CST (Notre Dame Stadium)"), Escape back to the Teams table.
- [speech] Teams table cells have no row context: "7 data item Wins column 2", "1 data item Losses column 3": which team isn't said.
- [wording] Roster's description doubles: "Team roster. Alt+V to cycle view modes.. Multiple view modes available: Alt+V to cycle views ...".
- "Name, Loading roster..." is read as the first cell before the roster arrives.
- [data] CONFIRMED (vmtest tree): an unbeaten team's Team Hub header has no record. Miami (8-0): only "Team: Miami Hurricanes"; SMU: "Team: SMU Mustangs" and "(7-2)". scores.py:8338 `elif wins and losses:` treats 0 losses as no record. A winless team would lose it too.

## d6-stats: Statistics
- NOT a bug: categories list, Passing Yards table "Braden Atkinson, Value, 2977", Alt+D definitions, Escape steps back; Team Statistics list and a table.
- [focus] Choosing Player or Team Statistics, and Escaping back, briefly lands on the league list: "Scores List list ... --- Statistics ---" is spoken between the two dialogs each time.
- [wording] Team column is the abbreviation: "Braden Atkinson, Team, ORST".

## d3-standings: --ncaaf-standings
- NOT a bug: conference list, SoCon table with row context, Full List, Ctrl+Tab to the next conference, Escape to the list, Escape to Home.
- Not app-wrong (see next line).

## g5-bigdetails: Alabama at LSU, live (Leaders, Standings, News)
- NOT a bug: Leaders tabs per team, cells "Rushing Yards, Player, Dilin Jones", "Rushing Yards, Value, 5 CAR, 21 YDS"; Ctrl+Tab to the other team; in-game Standings opens the SEC; Escape back to each row.
- [wording] The game's News row opens league stories, not this game's: "No. 5 UCLA turns up the speed late ...", "Columbia Lions vs. Harvard Crimson: Full Highlights". ESPN's summary has no article for the game and sends "NCAAF News"; the row still says "News" under the game.
- [wording] In-game standings use ESPN's short headers: "Georgia, OVER, 7-1"; team "Georgia", not the full name.
- [focus] News opens with no row selected: "... not selected", then Tab says "focused" without "selected".
- TV reads "Disney+, ERADM" (ESPN's short names).
- No Injuries row for this game.

## h1, h2: Home Page Settings and FBS only
- NOT a bug: Settings tab order (list, Move up, Move down, Reset, coverage combo, updates check box, OK, Cancel); Enter in the combo presses OK and saves; FBS only gives 22 live games and the conference list ends at FBS Independents.
- [focus] The settings dialog opens with no sport selected: "NFL not selected checked".
- [wording] The coverage description says "around 200 games a week"; this week has 124 for all of Division I.

## d3 note
- Not app-wrong: "Pos" follows ESPN's own order, which is by overall record, so Chattanooga (5-1 in conference) is below Mercer (4-1). ESPN's API orders it the same way. Kelly may still want "Pos" renamed or conference order.
