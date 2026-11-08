# Scores for Windows: data-layer audit, 2026-11-02

Scope: nine football, hockey and basketball leagues, repo at b8ff30f (1.0.0). Saved from the audit agent's hand-back; its evidence is in `out\`, scripts in `scripts\`, fixtures (39 files, 2.4 MB) in `fixtures\` with `INDEX.txt`. No window opened; pytest not run; repo untouched.

Labels: CONFIRMED (real function on live ESPN data, or a stated simulated failure). MODELLED (logic is in a Qt method, re-implemented; needs the UI run). NOT A BUG (ruled out).

Sample: 26 to 33 finals per league (`out\sample_ids.json`), newest finals plus up to 8 OT or shootout games, so OT is over-represented. Scoreboards 2026-10-24 to 2026-11-02, 874 games.

## 1. Wrong or invented data

- **W1. Fabricated player stats, reachable. CONFIRMED.** espn_api.py:4076-4078 falls back to `_get_sample_statistics_data` (4559-4727); loader scores.py:8171-8172. NBA: 10 invented rows ("Luka Doncic (DAL) 32.4 Points Per Game", "Andre Drummond (CHI)") under "Recent Performance Leaders". NCAAH, NCAAWH: "Sample Stat (General Stats)", Sample Player 1 (TEAM1) 100. On network failure every league gets invented rows: NFL "Tom Brady TB 5316", NHL "Connor McDavid 150", others "Sample Player 1". `out\s04_stats.txt`, `out\s09_misc.txt`.
- **W2. NCAAF standings show the wrong split for every team. CONFIRMED.** ESPN repeats `wins` per split; espn_api.py:2874-2875 keys on `name`, last wins (`vsusarankedteams`). 124 of 124 not overall, 124 of 124 PCT 0.000. UTSA 0-0 (true 7-1); Wisconsin 2-0 .000 (true 5-3). 2025 replay: 121 of 122 match neither overall nor conference. `out\s03_standings.txt`, `s03b_collision.txt`, `s15_verify.txt`.
- **W3. NCAAM, NCAAWB W/L/PCT are conference-only, unlabelled. CONFIRMED.** espn_api.py:2935-2936, 2996-2997. 2025-26 replay 365 of 365, 363 of 363; UMBC 14-2, overall 24-9. Today 28 NCAAM and 78 NCAAWB teams that have played read 0-0 (Notre Dame men, true 1-0).
- **W4. NCAAWH standings: all 47 teams 0-0. CONFIRMED.** Entries at root; espn_api.py:3149, 3159 count children, fall to 0-0 list 3205-3234. Yale true 2-1-1, Clarkson 10-2-0.
- **W5. Basketball box scores list only the five on the floor at the end. MODELLED.** scores.py:3372 skips `active:false`; kept rows exactly 5.0 per team. NBA 33 finals: 396 of 724 who played dropped, 3592 of 7587 points. WNBA 28: 248 of 528, 1628 of 4588. NCAAM 33: 385 of 715, 2442 of 5255. NCAAWB 33: 367 of 685, 2151 of 4424 (keeps 5.4; two games have no `active`). NBA 401909285 Lakers tab: 4 of 95 points; Doncic's 37 gone. `out\s02_box_games.csv`.
- **W6. Schedule dates are the UTC date; evening games read a day late. CONFIRMED.** espn_api.py:500-501, 677-678; `date`, `date_display`, `is_today` (587, 720). Wrong day of timed games: NBA 214 of 254, NHL 193 of 264, NCAAH 62 of 90, WNBA 9 of 14, NCAAM 75 of 122, NCAAWB 47 of 122, NFL 12 of 48, NCAAF 7 of 45, NCAAWH 8 of 90; all 627 of 1049 (60%). Same in Central, Eastern, Pacific. Wisconsin men vs Denver tonight reads "Tue, Nov 03"; Packers vs Falcons Thu Sep 24 reads "Fri, Sep 25". `is_today` false for tonight, so scores.py:8548-8553 won't bold or focus. A fix must honour `timeValid:false` (TBD at 05:00Z). `out\s05b_dates.txt`.
- **W7. Game Wrap Up turns linked names into literal `\1`. MODELLED.** scores.py:5960, 5963 replacement `r'\\1'`. 167 of 167 stories, 2262 occurrences. NBA 401909906: `LOS ANGELES -- \1 had 45 points ... leading the \1 to a 131-125 victory over the \1`. Separately text_utils.py:21 rewrites IDs in URLs to `[Player Name]` (CONFIRMED, 1383 times, 147 of 167 stories), not visible today. `out\s14_wrapup.txt`, `s13_final.txt`.
- **W8. NCAA basketball play locations mostly false. CONFIRMED.** play_geometry.py:90-102 accepts ESPN's (25, 0) placeholder. Share of located plays: NCAAM 10475 of 16609 (63%), NCAAWB 10328 of 16573 (62%), NBA 283 of 11480 (2.5%). Every NCAAM substitution (4782), free throw (1395), timeout, jump ball, end of period reads "at the rim". Inflates "N with a location", adds tones to Alt+S (scores.py:4864-4890). 1017 NCAAM fouls read like "deep, 66 feet out". Real shots good: 3-pointers read three or deep 98.4% to 100%. `out\s08b_probe.txt`.
- **W9. NHL standings columns shifted, order wrong. Row MODELLED, order CONFIRMED.** accessible_table.py:626 vs 731-739, 773-780, all 32 rows. Montreal OTL=0.714, PCT=0.5, GB=N/A, Streak=20, Pts=2. models/standings.py:74 sorts by point percentage: Montreal (20) Pos 1 over Boston (21). "GB" is points/2 (espn_api.py:2838).
- **W10. Utah outside its division. CONFIRMED.** espn_api.py:2758 keeps ARI, no UTAH. Utah alone in "Western Conference" tab; Central has 7.
- **W11. League team-stat rankings partial, out of order. Fetch CONFIRMED, sort MODELLED.** espn_api.py:3669 default `/teams` page: NCAAM 50 of 362, NCAAWB 50 of 362, NCAAF 34 of 762. scores.py:11627-11632: "2,168" fails float, ranks 0 (NFL 517, NCAAF 565, NHL 112 values). All descending, so Interceptions and Sacks rank worst first.
- **W12. "2 injury report(s) available" counts teams. CONFIRMED.** espn_api.py:1825; wrong in 120 of 129 games. NFL 401873035 has 10 players. The dialog itself is right.
- **W13. Period and goal labels. MODELLED.** NCAAM halves "1st Quarter", "2nd Quarter" 33 of 33 (scores.py:4226-4238). NCAAM OT, 2OT, 3OT all "OT" (7 games 2OT, 2 of them 3OT, 401845838). NHL shootouts scores.py:4136-4146 sums scoreValue: 7 of 9 disagree with linescore; 401803303 "SO (3 goals)" against 1, tree total 7 over final 5. Football OT drives "Quarter 5", "Quarter 6" (scores.py:3712): 4 of 26 NFL, 8 of 33 NCAAF.
- **W14. Team hub. CONFIRMED.** NFL "Next game" is the game just played for 11 of 12 on Monday evening; Packers "vs Carolina, Thu, Oct 29" (espn_api.py:4772-4792; checked only Monday). NHL record drops OT losses 12 of 12. WNBA offseason record is the playoff record: Lynx "0-2".
- **W15. Rosters read as decimals. CONFIRMED.** espn_api.py:4820-4822: all 22 non-empty rosters: `6.0'5.0"`, `325.0 lbs`.
- **W16. "Attendance: 0" stated as fact. CONFIRMED.** NCAAH 33 of 33, NCAAWH 33 of 33, NCAAWB 10 of 33, NCAAM 5 of 33 (espn_api.py:2021-2022).
- **W17. Time zones away from Central. CONFIRMED, zone simulated.** timezone_utils.py:170-176 adds 1 in DST the wrong way. Summer: Eastern reads Central (1 h off), Mountain reads Eastern, Pacific reads Central (2 h off). Arizona, Alaska, Hawaii, non-US wrong. Winter right for the main four. Central works only because the failed lookup defaults to Central, so Kelly and the VM won't see this. Date never rolls: `11/3 - 12:30 AM EST` becomes `11/3 - 11:30 PM CST`. timezone_utils.py:106 uses today's offset. `out\s10_tz.txt`.
- **W18. Fabricated venues on failure. CONFIRMED by simulation.** services/venue_service.py:82-84, 157-231. NFL only Lambeau and AT&T; NBA only "Staples Center"; `get_venue_details` raises AttributeError. 3 s timeout; responses took 0.7 to 0.9 s, so rare.
- **W19. Delayed game under In Progress with "0 at 0". CONFIRMED.** models/game.py:19-25, espn_api.py:149-151. NCAAM 401911374.
- **W20. Bowls & Playoffs never categorises. MODELLED.** scores.py:12729-12738, 12795-12796 compare `type.id` to ints; ESPN sends strings. 48 of 48 in "Other Bowls", 46 of 46 for 2025. 2025 feed labels most playoff games '1', so fixing the type alone won't sort that season.
- **W21. Football weekday guess. CONFIRMED, low reach.** models/game.py:72-77, wrong year for January dates viewed in May and July.

## 2. Missing data

- **M1. Box score content. MODELLED.** Team tabs empty everywhere (scores.py:3281-3296): NFL 52 of 52, NCAAF 66 of 66, NBA 66 of 66, WNBA 56 of 56, NCAAM 66 of 66, NCAAWB 64 of 64, NHL 66 of 66. Groups skipped at scores.py:3350: NFL 26 finals, 471 groups, 2154 rows, 0 player tabs; NCAAF 33, 573, 2716, 0; NHL 33, 198, 1258, 0. All 254 basketball player tabs "<Team> Unknown" (3346). College hockey: no ESPN box data; Boxscore opens zero tabs. `out\s02_box.txt`.
- **M2. NFL, NHL have no player statistics. CONFIRMED.** espn_api.py:4295, 4497 call `.items()` on a list; AttributeError swallowed at 4080. ESPN has 16 and 9 categories.
- **M3. NCAAF teams absent from Standings and Teams. CONFIRMED.** espn_api.py:2863 reads one level. All 14 Sun Belt gone (124 rows vs 138); all 128 FCS absent though Scores defaults to all of Division I.
- **M4. WNBA half-built. Menu MODELLED, schedule CONFIRMED.** scores.py:1658 no Standings, Statistics, Teams, Transactions, Venues; main.py no flags. espn_api.py:364 ±30 days: Lynx 0 of 49, Aces 3 of 53, Valkyries 11 of 58. `season=` ignored. Issue #71. `_get_standings_original` returns playoff records (unreached).
- **M5. NFL, NCAAF schedules omit preseason and postseason. CONFIRMED.** espn_api.py:401, 410. Bills 2025 miss 2 playoff games; Troy 2025 its bowl.
- **M6. Game detail rows that never appear (306 summaries).** TV: ESPN 287, app 0, espn_api.py:1814-1821 reads `names`, summary sends `media.shortName` (CONFIRMED). Betting, O/U: 199, 0, espn_api.py:1806-1811 reads empty `odds`, data in `pickcenter` (CONFIRMED). Officials: 184, 0, scores.py:2533 omits raw_details so 2825 false (MODELLED). Standings: opens "Standings data available"; no branch at scores.py:2345-2375, `_add_standings_table_to_layout` never called (MODELLED).
- **M7. Streak, record columns. CONFIRMED.** Streak N/A (espn_api.py:2482, 2610, 2809, 2896, 2957, 3018, 3087; models/standings.py:45). ESPN has it NFL 32 of 32, NBA 30 of 30, NHL 32 of 32, NCAAF 124 of 124. NCAAH hides ties for 18 of 62 (Niagara 5-4-1 reads 5-4). College hockey one table with Pos across conferences (scores.py:8991).
- **M8. Team hub blanks. CONFIRMED.** Venue, Division, Conference, Head Coach blank for all sampled (espn_api.py:4747-4770).
- **M9. Venues. CONFIRMED.** services/venue_service.py:17-25 no key for ncaam, ncaawb, ncaah, ncaawh, wnba; four have a menu row ending "No venue data". `home_teams` empty; capacity, surface never loaded.
- **M10. Names and context on rows. CONFIRMED.** espn_api.py:1582. NCAAWB, NCAAH, NCAAWH nickname only. "Huskies 2 at Huskies 4 [Final]" (401821221), one of 37 same-name rows. AP ranks never shown; neutral reads "at".
- **M11. Silent partial schedules. CONFIRMED.** espn_api.py:384, 430. A failed regular-season request returned Bucks' 5 preseason games with no error; total failure `[]`.
- **M12. Team hub News always empty. CONFIRMED.** espn_api.py:4839 `/teams/{id}/news` 0 articles for 14 of 14 teams; `/news?team={id}` returned 8 to 15. Loader scores.py:8888; favorite card 8740. How team-specific `/news?team=` is wasn't checked.
- **M13. College hockey plays, rosters. CONFIRMED, mostly upstream.** Summary has zero plays 66 of 66. Web fallback espn_api.py:1691-1741 got HTTP 202 with `x-amzn-waf-action: challenge` from this PC; returned nothing 24 of 24. Rosters empty NCAAWH 3 of 3, NCAAH 2 of 3. NCAA transactions empty, menu offers them.

## 3. Wording

- "[End of Period]" drops "End of 2nd" (models/game.py:184-186).
- Preseason polls "NR" for all 100 Previous cells in NCAAM, NCAAWB (scores.py:9195).
- Generic stats raw floats ("2977.0"), "Recent Performance Leaders" for season totals.
- "OT2" vs ESPN's "2OT" (NCAAWB).
- Schedule finals drop OT ("W 42-40" for Final/3OT, scores.py:8523-8533).

## 4. Ruled out (NOT A BUG)

- Scores coverage matches ESPN, 9 leagues, 10 days, 874 games, 0 missing; college hockey no page cap (largest day 28).
- Football week counts right; calendar resolves; `game_section` right for every status seen; Final/OT and Final/SO preserved.
- College hockey "0 at 0 [Final]": ESPN itself reports 0-0 (401822028).
- "Goals" menu for basketball is dead code (`_get_stat_categories`, `_on_stat_selected`, `_load_stat_data_for_category`, scores.py:11695; `StatisticsDialog` never instantiated).
- Regular-season schedules complete in NFL, NCAAF, NBA, NHL, NCAAM, NCAAWB, NCAAH, NCAAWH, including small schools.
- `_get_team_record` returns (0, 0) for "6-2-1" but only WNBA and exception fallbacks reach it.
- NFL, NBA division maps right; NFL Div Rec matches 32 of 32; NFL, NBA, NHL W, L, T, OTL, points match.
- News: 0 of 180 league descriptions altered; `[Player Name]` needs a 6-digit number (`$1500000` in a pure test), latent; team articles unsampled because of M12.
- No defect: rankings, draft (round 1 only), fantasy cheatsheet (structure only), leaders, Injuries dialog, transactions (`datetime` not imported, so `except` at 4892, 5103; same date results).
- `dates=` day boundary: late games appear on the Central date (401909880, 401920409).
- NHL, WNBA coordinates in range. `_parse_boxscore_data` baseball names unused by UI.

## 5. Could not check

- Qt-only logic is modelled; needs the UI run.
- Web gamepackage play shape: WAF blocks this PC, may differ elsewhere.
- STATUS_CANCELED, SUSPENDED, pre-game DELAYED not seen live, ran synthetically (`out\s06_scores.txt`). Hockey multi-OT labels not in sample.
- `attendance:null` raises, would give "gameInfo: Error formatting data" (direct call), but 0 of 306 had it.
- Live Scores (`get_live_scores_all_sports`) not run.
- Nov 2 scoreboards are evening snapshots; ESPN moved during the run.

## 6. Test coverage that would have caught each defect

CI runs only `tests/unit`; 8 of 9 files in `tests/fixtures` are 0 bytes. "Extract" means moving logic out of the Qt class first, as `play_geometry.py` was. Fixtures in `fixtures\`.

| Defect | Fixture | Assertion |
|---|---|---|
| W1 | statistics_NBA, statistics_NCAAH, raising `_http_get` | no row from the sample table; sample function deleted |
| W2, W3 | standings_NCAAF, NCAAM, NCAAWB | W-L equals `overall`; stats read by `type` |
| W4 | standings_NCAAWH | Yale is 2-1-1 |
| M3 | standings_NCAAF | Sun Belt teams present |
| W5, M1 (extract) | box_*.json | NBA rows are all who played; NFL has a passing tab; team tab has rows; no "Unknown" tab |
| W6 | schedule_NBA_15, schedule_NFL_9 | 00:00Z-03:00Z games carry prior local date; TBD unchanged; `is_today` right |
| W7 (extract) | a story with `<a>` | contains the player name, no backslash-1 |
| W8 | plays_NCAAM_401845838_3OT, plays_NCAAWB_401911736, plays_NBA_401909906 | no location for substitution, timeout, free throw at (25, 0); NBA unaffected |
| W9, W10 (extract) | standings_NHL | row zips with headers; order by points; Utah in Central |
| W11 | statistics_*, team page | "2,168" sorts numerically; team count equals league |
| W12, M6 | details_NFL_pieces | injuries equal players; TV is "NBC"; betting from pickcenter |
| W13 (extract) | plays_NCAAM_401845838_3OT, plays_NHL_401892616_SO, drives_NCAAF_2OT | "1st Half", "2OT", "3OT"; SO goals equal linescore; "OT", not "Quarter 5" |
| W14, M8 | team_NHL_utah | record has OT losses; venue from franchise |
| W15 | roster_NFL_9, roster_NBA_15 | `6'5"`, `325 lbs` |
| W16 | details_NCAAH_pieces | no "Attendance: 0" |
| W17 | none (pure) | zone table, summer and winter; rollover date |
| W19, section 3 | scoreboard_events_by_status | Delayed has no "0 at 0"; End of Period names the period |
| W20 | bowls_NCAAF | title game under Championship |
| M2 | statistics_NFL, statistics_NHL | categories returned, no exception |
| M4, M5, M11 | schedule_WNBA_8, raising `_http_get` | WNBA uses team endpoint; NFL includes seasontype 3; failure raises |
| M10 | scoreboard_events_by_status | NCAAWB row has display names |
| M12 | not saved yet; capture `/news?team=` | team news returns articles |

## 7. Top 15 to confirm in the NVDA run (Central dates)

1. NBA box (W5, M1): Oct 30 Lakers at Warriors 401909285: 5 Lakers rows, 4 points, no Doncic; empty Stats; "Los Angeles Lakers Unknown".
2. NFL box (M1): Nov 1 Eagles at Commanders 401873035: two empty tabs. Same NCAAF 401856835, NHL 401892628.
3. College boxes (W5, M1): NCAAM Nov 2 St. Francis (IL) at UIC 401928858: 5 rows per team. NCAAH 401923148: zero tabs.
4. NBA stats (W1): Statistics > Player > "Points Per Game (Scoring)": "Luka Doncic (DAL) 32.4".
5. College hockey stats (W1): NCAAH Statistics > Player: "Sample Stat", "Sample Player 1 (TEAM1) 100".
6. NFL stats (M2, W11): Player "No player statistics available"; Team "Passing Yards (Passing)" wrong order.
7. NCAAF standings (W2, M3): Big Ten Wisconsin 2-0 PCT 0.000 (true 5-3); ACC Miami 0-0 (true 8-0); no Sun Belt tab.
8. NCAAM, NCAAWH standings (W3, W4): ACC Notre Dame 0-0 (true 1-0); NCAAWH all 0-0 (Yale true 2-1-1).
9. NHL standings (W9, W10): Atlantic, Montreal OTL 0.714, PCT 0.5, GB N/A, Streak 20, Pts 2; Pos 1 over Boston; "Western Conference" tab has only Utah.
10. Schedule dates (W6): NCAAM Teams Wisconsin: Denver "Tue, Nov 03", not bold, no focus. Bucks "Tue, Oct 06" for Oct 5. Packers "Fri, Sep 25".
11. Wrap Up (W7): NBA 401909906: "\1 had 45 points".
12. Play labels, locations (W8, W13): NCAAM 401928858: "1st Quarter"; substitution "at the rim"; nearly every play located. NCAAM 401845838 (Feb 7): "OT" three times. NHL 401803303 (Mar 1): "SO (3 goals)".
13. Game details (M6, W12): NFL 401873035: no TV, Officials, Betting; "Injuries: 2 injury report(s)" (10 players); Standings opens "Standings data available".
14. Team hub (W14, W15, M8, M12): Packers `6.0'5.0"`, `325.0 lbs`; Next game already played; no Venue, Division, Coach; News empty.
15. Menus, Bowls (M4, W20, M9): WNBA no Standings, Statistics, Teams. Valkyries from 401918311: 11 of 58. NCAAF Bowls only "Other Bowls". NCAAM Venues "No venue data available".
