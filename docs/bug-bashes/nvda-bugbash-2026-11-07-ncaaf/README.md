# College football bug bash, Saturday, November 7, 2026

**Build:** Scores 1.1.1, installed from the release installer (`Scores-1.1.1-Setup.exe`, daa093a).
**Where:** test VM ClaudeTesting on the Surface, NVDA 2026.2 with its default voice, Central time.
**When:** 12:30 to 4:15 PM, with 40 to 54 Division I games live at any one time.
**How:** every screen reachable for college football, driven with real keys, and NVDA's speech logged per key. The settings were reset before every clip, and the data was checked against ESPN's feed for the same minute (a snapshot every 3 minutes).

Everything here is NVDA. Nothing in it says how JAWS behaves.

## Results

| Area | Clip | Result |
|---|---|---|
| Whole week in the league view | s1-ncaaf-slate | 124 of 124 games, matching ESPN: 42 live, 69 upcoming, 13 final. Ranks, "vs" at a neutral site and Final/OT all right. |
| A live game's details | g1-live-details | All rows read. Back returns to the same game, which was broken in the Nov 2 bash. Findings 6 and 13. |
| Drives tree | g2, g3, o1 | Findings 1, 2, 9 and 10. |
| Box score | g4-box | Works: table list, cells with player and column, three views, Ctrl+Tab, Team Stats. Finding 16. |
| Leaders, in-game standings, news | g5-bigdetails | Work. Finding 14. |
| Live Scores and monitoring | l1, l2, l3, l4 | Score alerts fire, and Back keeps the row and monitoring. Findings 3, 4, 5 and 11. |
| Double overtime (Towson 43, Sacred Heart 40, Final/2OT) | o1-overtime | Row, Game Time and the OT and 2OT nodes are right. Findings 2 and 10. |
| Polls | d2-polls | Finding 8. |
| Week stepping, Week 8 to the CFP | d4-weeks | Works, and the week is said each time. Finding 12. |
| Teams and Team Hub | d5-teamhub | Finding 7, and no team in Teams table cells (finding 8). |
| Statistics | d6-stats | Works. Finding 15. |
| Standings, including FBS only | d3, h2 | Work. FBS only gives 22 live games and ends at FBS Independents. |
| Scheduled game, Bowls, league news | g6, g7 | Findings 5 and 6. |
| League view keys | k1 | F5 keeps your row, Tab cycles, Enter and Space press the week buttons. Finding 11. |

## Findings, most serious first

Each finding was heard in a clip, or seen in the VM's UI tree where it says so. The file and line numbers are in 1.1.1.

**1. The wrong team gets credit for a return touchdown.** In Drives, Duke at NC State reads "[TD 7pts] NC State Wolfpack: 5 plays, 37 yards, 0:26". NC State never scored a touchdown (the game was 31-3): they missed a 50-yard field goal and Duke ran it back 100 yards. Sacred Heart's kickoff drive has the same problem in the summary: Towson returned that kickoff 99 yards. ESPN marks the kicking team's drive "TD". The app takes the badge and the team from the drive (`scores.py:3568-3600`), but each play's score shows who actually scored. (g3-drives-q2; ESPN summaries 401858286 and 401866682)

**2. Every touchdown is "TD 7pts".** Towson's walk-off touchdown in double overtime was 6 points, since no extra point is tried. Auburn's touchdown after "PAT MISSED" was also 6. The badge is fixed text (`scores.py:3576`). (o1-overtime)

**3. Live Scores reads the row you're on again at every refresh, even when nothing changed.** This answers the 1.1.1 Windows check you skipped. A monitored final, "Arkansas Razorbacks 23 at Auburn Tigers 26 [Final] - monitoring", was read every minute for six minutes with the same text. The same happened at halftime on another game. The likely cause is that each refresh writes every row's data back (`scores.py:1184`) even when the text is the same, and Qt reports that as a change to the focused row. On a live football row the text really does change every minute, so you hear about 25 words a minute there; that part follows the rule, but it's heavy. (l1, l4; l2, l3)

**4. Nothing is said when a monitored game ends.** Score alerts fire, but there is no alert for a final. You hear "[Final]" only if your focus happens to be on that row. Monitoring also stays on after the final. (l4-ot-final)

**5. One game, two start times.** Miami at Notre Dame's row says "(Sat 11/7 6:30PM)" in local time. Its details say "Game Time: Sat, November 7th at 7:30 PM EST", which isn't converted (`scores.py:3100`). (g6)

**6. You can't reach the Bowls & Playoffs headings, and the first-round games are filed wrong.**
- The headings can't be selected (`scores.py:12364`), so Down skips them. After "=== Championship ===" you hear the semifinals and a quarterfinal with no heading in between, so they sound like part of Championship.
- The list has no name; NVDA says just "list" (`scores.py:12278`).
- ESPN gives the four CFP first-round games type 1, and the code looks for "first round" only on type 42, so they go under "Other Bowls" (`scores.py:12348-12356`). I checked this in the code and the feed; the walk didn't reach those rows.
(g7)

**7. An unbeaten team's Team Hub header has no record.** Miami at 8-0 shows only "Team: Miami Hurricanes", while SMU shows "(7-2)". The check `elif wins and losses:` treats 0 losses as no record (`scores.py:8338`), so a winless team loses it too. (VM UI tree)

**8. Two tables never say whose row you're on.**
- Polls give the rank as row context: "1, Team, Miami Hurricanes", then down the Previous column "2, Previous, NR", "3, Previous, NR" (`accessible_table.py:37`, used by the polls table).
- Teams tables give none: "7 data item Wins column 2".
- The CFP poll also has an empty Points column, which Quick List reads as "3, Utah Utes, 8-0, , NR". (d2, d5)

**9. Drives: expanding and collapsing say nothing, and every row reads level 1.** Right on "Quarter 3 collapsed" is silent. Drives inside a quarter, and plays inside a drive, read "row 4 level 1", "row 8 level 1", with row numbers running on. This is issue #139 heard with NVDA, and it matches what you found. (g2, g3)

**10. Drives: smaller things.**
- A play's clock is read twice: "[3:04] [1 & 10 from NCSU 19] (+2 yards) (03:07) Shotgun ...".
- F5 closes and reopens the dialog, back at Quarter 1 with everything collapsed.
- "[FUMBLE RETURN TD]" is ESPN's own text, next to the app's own badges such as "[TD 7pts]".

**11. Type-ahead can't find a ranked team by name.** In the league view, "Alabama Crim" lands on Alabama A&M and "Georgia Bull" on Georgia State. Ranked rows start "#5 Alabama Crimson Tide", so you have to know the rank to type it. (VM focus)

**12. Going past the last week is silent.** After Week: CFP, four presses of Alt+N say nothing. The "last week of the season" text goes only into the label (`scores.py:2534`). Weeks also read "Week: Bowls" and "Week: CFP". (d4)

**13. A live game's details have no down, distance or possession,** though its row in the list does. The score reads home first, by nickname, under an "away at home" title: "Score: Wolfpack: 3 - Blue Devils: 17". (g1)

**14. Score alerts read home first, and carry ranks the row doesn't.** For example "Texas Longhorns at Missouri Tigers: #18 Missouri Tigers 20 - #7 Texas Longhorns 34", while the row says "Texas Longhorns 34 at Missouri Tigers 20". Alerts take teams in ESPN's order, home first (`scores.py:1476-1478`). Live Scores' live rows have no ranks; the league view's rows do. (l1-l3)

**15. Moving between the two Statistics dialogs briefly lands on the league list.** Choosing Player or Team Statistics, and coming back, says "Scores List list ... --- Statistics ---" in between. (d6)

**16. Wording.**
- After a touchdown, a live row's play is only the extra point: "Oklahoma State Cowboys 28 at Kansas State Wildcats 7 | (S. Keltner KICK)". "(A. McPherson PAT MISSED)" and "(G. Spetic KICK)" read the same way. That's ESPN's last play, but the touchdown itself is never said.
- Halftime reads "End of Half. 0:00 Q2 (Halftime)".
- A game's News row opens league stories, not that game's ("No. 5 UCLA turns up the speed late ...").
- Every table and poll tab opens with two long descriptions, about 50 words.
- News, Bowls and Settings open with no row selected ("not selected").
- The coverage setting says "around 200 games a week"; this week has 124.
- Roster's description says "Alt+V to cycle view modes" twice.

**Checked and not a bug:**
- The slate counts. Weeks 11 and 12 both really have 130 games.
- No Officials row: ESPN's college summaries have no officials.
- Standings "Pos" follows ESPN's own order, which is by overall record. You may still want conference order.

**Not seen, from reading the code:** Live Scores sorts upcoming games by their display text, so a 10:00 PM game would come before 6:30 PM (`scores.py:1272`). No game today had a two-digit evening hour to show it.

## For you to check by ear

1. Live Scores, resting on one row for three minutes, with JAWS and then NVDA. Do you hear the row again at each refresh (finding 3)? Is a live football row read in full every minute too much?
2. With a monitored game, move to another row and wait for it to end. Is anything said (finding 4)?
3. Drives with JAWS: does it say expanded or collapsed, and levels (finding 9, #139)?
4. Do the long table descriptions bother you with JAWS, or does JAWS skip them?
5. Game Wrap Up on your PC: it opens the browser and then shows a "Game Wrap Up opened in your default web browser" box with OK. Is that box in the way? In the VM, Edge's first-run page took over, so I couldn't judge it.
6. Is a live row's play cut at 60 characters ("pass complete short right to #16...") too short to be useful?

## Files

- `out\`: one check report per clip, every key with what NVDA said after it.
- `steps\`: the steps files, which can be re-run against a later build.
- `findings-log.md`: the running log. The raw recordings, ESPN snapshots and builds were in the OneDrive testing folder and were cleared on Nov 7, 2026; the issues filed from this report (#202, #203, #204) carry what they needed.

## Rig notes

None of these are app findings.
- The VM was attached to the Wi-Fi switch while this PC was on Ethernet, so it had no network. I moved it to the Ethernet switch.
- OneDrive and Windows notifications took focus, so the reset step now turns them off.
- Another session switched the main Scores folder to a branch mid-run, so the clips ran from a worktree on main.
- vmtest stops any command after 15 minutes, which cut one clip (l3). Its speech came from NVDA's own log.
- Once, Scores answered UI queries slowly for a few minutes. Four tries didn't repeat it, so it isn't reported.
