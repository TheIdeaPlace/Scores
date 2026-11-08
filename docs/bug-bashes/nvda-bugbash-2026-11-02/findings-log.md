# Running log (raw notes; POSSIBLE-BUGS.md is written from this)

Build: Scores 1.0.0 release installer, VM ClaudeTesting, NVDA 2026.2, Central time.

## Oct 21 replay: 44 of 48, same four failures
- t04: Standings dialog opens on the tab, not the table.
- t04: "Switched to Quick List View." doubles.
- t05: "Automatic refresh disabled" never spoken.
- t06: Enter doesn't press Home Page Settings; Space does.
- Also still seen: Back from a game lands on the first header; Back from league lands on Live Scores.

## Confirmed in speech
- [data] NFL standings: Streak reads N/A (Buffalo; check all teams). clip t04-standings
- [data] NCAAM slate full: 182 of 182 spoken at 18:13. NOT a bug. clip d1-ncaam
- [wording] Delayed game not started: "Charleston Southern Buccaneers 0 at South Florida Bulls 0 [Delayed]", filed under In Progress. clip d1-ncaam
- [wording] Live play text cut mid-name: "Christian Thomas makes layup (Stephon Rosch...". clip d1-ncaam
- [data] No rank on rows: Florida is #1 in the feed, row says "Florida Gators". clip d1-ncaam
- [data] Neutral site games read "at": feed "MIA VS FLA" (neutralSite true), row "Miami Hurricanes 36 at Florida Gators 46". clip d1-ncaam

## Added 18:50: slates and live detail walks
- NOT a bug: slate counts all match the feed: NCAAM 182, NCAAWB 164, NBA 15, NHL 4, NFL 14, NCAAF 124. d1-* clips. (NCAAWB: 2 games matched twice; check.)
- [data] Odds: "odds: No data available" on OKC@CLE, VGK@BOS, UAB-MCN, HARV@MINN; each has pickcenter lines (CLE -4.5, O/U 229.5). g-*-live.
- [data] TV: VGK@BOS "broadcasts: No networks listed"; summary and scoreboard have NESN, Scripps, NHL Net. Also UAB-MCN YouTube, HARV-MINN B1G+. OKC@CLE "No data available": summary [] but scoreboard has NBCSN.
- [data] Injuries: "2 injury report(s) available" counts teams; OKC@CLE has 7 players, VGK@BOS has 1.
- [data] Officials never shown: 3 to 4 in gameInfo.officials, no row. Attendance: check on finals.
- [data] Neutral site: "McNeese Cowboys (Home)" at Rock Hill SC; neutralSite true.
- [wording] Labels are code names: "odds:", "broadcasts:", "gameInfo:". gameInfo repeats Venue.
- [wording] Title inconsistent: "NCAAM, End of Period, UAB Blazers at McNeese Cowboys" vs "NBA, Oklahoma City Thunder at Cleveland Cavaliers": status in one, frozen.
- [wording] Status "End of Period" and "Game Time: End of 2nd Half" at 99-78: ended game listed under In Progress with no sign it's over (check a later feed: was state in?).
- [focus] Back from a game: "In Progress, 84 games" header, row lost, every league. g-*-live.
- Not claimed: "Record: 0-0" on college games; feed was consistent at that time for an opener; check on a played team.
- Run note: run.sh edited during batch 1 gave one bash syntax error line at 18:23; d1-nfl and later clips completed normally.

## Box score, NFL (Kelly's report), clip box-nfl-gb, CAR @ GB 401873023
- [data] CONFIRMED: 0 of 89 player rows, 0 of 50 team stats spoken; ESPN has them all (out/box-nfl-gb-box.md).
- Dialog: "=== Carolina Panthers Team Statistics ===", tabs "Carolina Panthers Stats", "Green Bay Packers Stats". Both empty. Tab goes tab > Close > tab; no table; no "no data" message.
- Mode keys and F6 do nothing (no table). Ctrl+Tab moves tabs. F5 closes and reopens on tab 1 (position lost).

## NCAAWB nicknames
- [data] CONFIRMED: "Panthers at Ospreys [Postponed]", "Crimson 59 at Golden Gophers 75": NCAAWB rows use nicknames only; NCAAM uses full names. clips d1-ncaawb, g-ncaawb-live.

## Box score, NCAAM, clip box-ncaam (Virginia Lynchburg at VMI, Table mode)
- [data] Tabs: "<Team> Stats" (empty), "<Team> Unknown", for each team. CONFIRMED by speech.
- [data] Player tab: 5 rows of 16 (W5 confirmed).
- [focus] Open: focus stays on the first, empty tab (no table to focus).
- [keyboard] Tab from a player tab lands on the "<Team> Unknown grouping" wrapper. 74 s of Down, Home, Ctrl+Home, End, PgUp, Right: all silent. Needs a second Tab. Mode keys work at the wrapper.
- [keyboard] Mode keys silent on the tab bar and Close.
- [speech] "Switched to" grows without limit: 5 copies heard. Re-read on every switch with instructions.
- [speech] Table row speech: "Player, Donovan Peterson data item 1 row 1 Player column 1".
- [focus] Ctrl+Tab from a list: nameless "grouping"; tab name not spoken, and the mode of the other tab differs.
- [keyboard] F6: nothing, 5 presses.
- [data] No totals row, no team stats anywhere. Rows after 5: end of list silent.
- Run note: saved-mode runs before 19:20 are void: reset wrote a BOM, app silently used defaults. Fixed; re-run. (Settings file with a BOM loses all settings silently: minor app finding, settings.py:35-39.)

## Live NFL, clips dr-nfl-live, pl-nfl-live (CHI at SEA)
- [data] Duplicate drive, live: "[DRIVE] Chicago Bears: 16 plays, 79 yards, 8:11" row 2 and row 5, "(3 drives)". Same ESPN quirk as iOS finding 9.
- [focus] Drives dialog opens on "Export Game Log Button button", not the tree. Tab needed. Doubled word.
- [speech] Emoji markers spoken or sent: "pin [DRIVE]", "lightning Kickoff"; "[PUNT]" brackets. Check by ear.
- [data] CONFIRMED W6 in UI: tonight's game reads "Tue, Nov 03: vs Chicago Bears - 8:08 - 1st" in Team Hub schedule.
- [speech] Team Hub roster Down reads only "#, 88": number, no name. Opens "#, Loading roster...".
- [keyboard] TO VERIFY: Alt+P, Alt+S in Drives dialog appear to open the System menu ("System Alt+Space"), then arrows walk Restore, Move, Size. Could be the key driver. Football has no audio; K4.
- Run wrong: pl-nfl-live: NFL has no Plays row; type-ahead stayed on the first row and Enter opened Team Hub. Team Hub speech kept as incidental evidence. NFL plays are under Drives.

## iOS (ios-check/REPORT.md): top two verified directly at 19:35
- 401918849 has athlete {shortName only}: decode failure, whole game detail lost. 29 of 145 played NCAAWB.
- dates=A-B returns 400; dates=2026&week=8&seasontype=2 returns 200: iOS week arrows broken (#70).

## Live plays (pl-ncaam-live Army at Duke, pl-nhl-live VGK at BOS, pl-nba-live)
- [data] CONFIRMED W13: NCAAM halves "1st Quarter", "2nd Quarter". CONFIRMED W8: "Jaden Ellis subbing out for Army ... at the rim", "Army Timeout ... at the rim", "Start game ... at the rim", rebounds, jump balls: "232 with a location" of 232ish. Turnovers "from three" (ESPN location of the turnover, check). Real shots read right.
- Plays dialog opens on the tree (good). NHL dialog announces Export button first, then the tree.
- NOT a bug: hockey clock counts up: ESPN's own clock.displayValue.
- [speech] Context menu "Play Audio Options window". Tree description "organized by period and drive/inning" on all sports.
- Tab order Close, Export, Play Audio, Tree.

## Live Scores K9 (k9-live)
- [speech] CONFIRMED: NVDA re-reads the current row at every refresh, about every 60 s (64.6, 124.3, 181.2, 244.4, 304.6, 364.4 s), idle.
- [focus] Row and focus survive refresh (good). Back from a game: lands on "=== LIVE GAMES ===", row lost.
- [speech] Alt+M: row re-read with " - monitoring"; nothing else. Next refresh drops " - monitoring" (244.4). 
- [speech] Separators spoken: "=== LIVE GAMES ===", "--- NBA ---".
- [wording] Cut text: "Josh Hart bad pass turnover (Chaney Johnson...".

## Box score, saved modes (box-ncaam-m1, -m2), box-ncaam-t
- GOOD: saved Quick List and Full List open with data; mode carries across dialogs; row kept across switches; column returns to 0 per design; Table cell speech right.
- [keyboard] Long names: tab bar has "Scroll Right button" as a Tab stop: tab, Scroll Right, wrapper, table: 3 Tabs to data.
- [speech] Table col 1 walk says "Player, Kaden Butler data item 2 row 2"; Player repeated by the app's own text.
- [speech] List arrival "not selected" on first focus (no current row until focus), second read OK.

## Box score, other leagues (box-nba, box-nhl, box-ncaaf, box-ncaah, box-ncaawh, box-ncaawb)
- NHL (TB at NSH), NCAAF: two empty Stats tabs, no player tabs. CONFIRMED.
- NCAAH, NCAAWH: "Boxscore Details dialog", "Boxscore Tabs grouping", unnamed "tab control", no tabs, no message. Tab only Close. CONFIRMED.
- Postponed game (Panthers at Ospreys) offers Boxscore: same empty tab control. CONFIRMED.

## To check next
- See the plan's charters.
