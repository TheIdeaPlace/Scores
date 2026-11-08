# Sports Scores iOS: ESPN conformance check, 2 November 2026

Data-level only. No Swift compiled or run, nothing tried on a device. Each finding is the Swift source re-stated in Python (`tools\ios_conformance.py`, `--selftest` passes 16 decoder-rule cases) and applied to real ESPN payloads. Raw numbers: `results.json`. Failing payloads saved here. Paths relative to `iOS/SportsScoresApp/SportsScores`. Saved from the check agent's hand-back.

## Verdict

- Scoreboards decode everywhere.
- Game details fail to decode for women's college basketball: 29 of 145 played games.
- Football week navigation fails: ESPN answers its query with HTTP 400.
- Box scores decode elsewhere, but much of what they show is wrong or blank. Hockey is worst.

## Games checked (943 summaries, 20261024 to 20261102)

| League | Summaries | post (postponed) | in | pre | Decode failures |
|---|---|---|---|---|---|
| NCAAM | 135 | 28 (10) | 85 | 22 | 0 |
| NCAAWB | 170 | 57 (6) | 94 | 19 | **29** |
| NBA | 82 | 67 (3) | 6 | 9 | 0 |
| WNBA | 28 | 28 | 0 | 0 | 0 |
| NHL | 80 | 65 (1) | 2 | 13 | 0 |
| NCAAH | 94 | 74 | 0 | 20 | 0 |
| NCAAWH | 81 | 61 | 0 | 20 | 0 |
| NFL | 41 | 26 | 0 | 15 | 0 |
| NCAAF | 232 | 212 | 0 | 20 | 0 |

Scheduled games topped up from following days. NFL live: 401873036 only. WNBA walked back to reach 28. Most postponed games are from Jan 24-26, 2026. Scoreboards: 120 calls near the window, 48 outside, 132 saved snapshots with 7,184 events.

## Findings

1. **Decode failure: NCAAWB game details (29 games).** `boxscore.players[*].statistics[*].athletes[*].athlete.displayName`, keyNotFound. `Models/GameDetails.swift:456`, `let displayName: String`. The athlete has only `shortName` (e.g. `{"links": [], "shortName": "J. Loubens"}`), `active:false`, `stats:[]`; 39 rows. 21 of 94 live, 8 of 51 finals; all still failed refetched at 18:50. Not only small schools: South Carolina 401918849 (final), Temple, Richmond, Liberty, Missouri State. No other league (NCAAM 0 of 103). Effect: `Services/ESPNAPIService.swift:706` throws, `ViewModels/GameDetailViewModel.swift:34`, `Views/GameDetailView.swift:42-45` replace everything below the header with an error and Retry. Box Score, Plays, Info all lost. Likely fix: optional or fall back to shortName; decode per athlete leniently. IDs: 401913855, 401929155, 401928536, 401927989, 401916035, 401909681, 401927484, 401916210, 401929300, 401926040, 401921077, 401920334, 401919708, 401918722, 401918581, 401918446, 401913675, 401912988, 401912504, 401928020, 401921232, 401918849, 401929054, 401929798, 401927514, 401921305, 401927980, 401927972, 401928203.
2. **Request failure: football week navigation, HTTP 400.** `Services/ESPNAPIService.swift:358` sends `dates=A-B`; `ViewModels/ScoresViewModel.swift:198-206` for every explicit week (arrows 243, 267) and historical seasons. All ranges returned 400 `{"code":400,"message":"Failed to get events endpoint."}`, 100+ calls. "Failed to load games"; only the current week loads. Windows already moved (`espn_api.py:460`, `:1503`). Replacement `dates=2026&week=8&seasontype=2` (NFL 14), `dates=2025&week=5&seasontype=2` (14), `dates=2026&week=9&seasontype=2&groups=90&limit=400` (NCAAF 115) returned 200 and pass. Issue #70 covers this. Also range, untested: `fetchGamesRange` (`:549`, World Cup), `fetchTransactions` (`:1348`).
3. **Hockey Essential blank or nearly so; may vary per launch.** `Views/BoxScoreView.swift:626-628`: ESPN groups forwards, defenses, skaters, goalies; profile keys skater, goalie (`:696-697`), so falls to `essentialPlayerStats.values.first`, and Swift seeds dictionary hashing per process. `:630` lowercases the column, not the set, so plusMinus, shotsAgainst never match. Skater set picked: Forwards G, A; Defenses G, A; Skaters blank; Goalies blank. Goalie set: Forwards, Defenses, Skaters blank; Goalies SV% only. Blank page is EmptyView (`:494-496`). All Stats correct; Skaters blank in both modes (0 athletes).
4. **College hockey box scores blank: 9 tabs, no message (135 of 135 finals).** ESPN sends `statistics: []` and 4 groups with 0 athletes. `BoxScoreView.swift:69-79` builds 8 player tabs plus Team Stats. "Box score not available" (`:110`) needs `teams` empty, never true in 943. Same pattern: NFL 49 of 520 pages, NCAAF 522 of 4,240 with no athletes.
5. **Every basketball player tab "Unknown".** `Models/GameDetails.swift:443`; `BoxScoreView.swift:29`, "NIU Unknown". 730 pages: NCAAM 226, NCAAWB 302, NBA 146, WNBA 56.
6. **Football Essential.** Kicking blank always (`FG, PCT, LONG, XP, PTS` matches no set). fumbles, defensive, interceptions, kickReturns, puntReturns, kicking, punting hit `values.first`; profile key `defense` doesn't match `defensive`. Defense shows TD or SACKS, PD, never TOT, SOLO. Passing lacks `C/ATT`. "Kickreturns", "Puntreturns" (`GameDetails.swift:443`); `text` not decoded. No football athlete has `position`, so Quick List labels "Name ()" (`BoxScoreView.swift:573`, `:585`). " Team ()" pseudo-athlete NCAAF, 271 rows.
7. **Essential team stats miss most rows.** `BoxScoreView.swift:665-693`, `:352-354`. Football shows firstDowns, totalYards, turnovers (lost passYards/netPassingYards, rushYards/rushingYards, penalties/totalPenaltiesYards, timeOfPossession/possessionTime). Basketball assists, steals, blocks, turnovers (lost shooting, rebounds/totalRebounds). NHL hits, takeaways, powerPlayGoals, giveaways (lost shots/shotsTotal, blocks/blockedShots, faceoffWinPercentage/faceoffPercent, powerPlayAttempts/powerPlayOpportunities, penaltyKillPercentage/penaltyKillPct). Basketball player Essential: MIN, PTS, REB, AST, TO, STL, BLK; no shooting at all.
8. **Pre-game and postponed.** Scheduled: Essential Team Stats blank in NFL, NCAAF, NBA, NCAAM, NCAAWB; NHL one row; All Stats shows season averages unlabelled. Postponed: `GameDetailView.swift:213-217` shows 0 to 0 from header (401927045, 401810499, 401803179). `flatTeamStats` uses `teams.first` only (`:348`), blank if first team empty (401927465 has one empty side; not counted which).
9. **Live football: current drive twice.** `drives.previous` already holds it; `GameDetails.swift:287-291` appends `current`, duplicate row and ForEach id (`PlaysView.swift:992`). 401873036, three passes.
10. **Rows with no stats.** NCAAM 1,241 of 3,280, NCAAWB 1,159 of 4,123, NBA 378 of 1,885, WNBA 166 of 702. `didNotPlay`, `reason` not decoded. Quick List "Name (G), " (`:585`).
11. **Totals never shown.** Not in `PlayerStatGroup`. NBA 140 of 146 pages, NFL Passing 52 of 52.
12. **All Stats: NFL `interceptions` twice,** duplicate ForEach ids (`:386`, `:415`, `:437`).

## Checked and fine

- Scoreboard decode in every state, including small schools. Silent-failure risk not seen (`LiveScoresViewModel.swift:48-51` would drop a sport and print).
- The Windows box score bug doesn't apply: all athletes shown; `names ?? labels` works; flat stats read.
- Header and value alignment: stats full length or empty; bounds-checked; no crash path seen.
- Play decode: 25,189 NCAAM, 52,396 NCAAWB, 32,504 NBA, 11,146 WNBA, 20,290 NHL plays. But plays share one decode with the box score, so finding 1 takes NCAAWB plays down too.
- Drives: 5,023 NCAAF, 558 NFL. Leaders, injuries, odds, officials, news, win probability, season series, rosters, header, situation decode.

## Could not verify

- Anything on a device, including real decode, screen content, VoiceOver and error wording.
- Per-launch behaviour in 3 and 6 rests on Swift's hash seeding; no launch observed.
- No canceled games. No live NCAAF, NCAAH, NCAAWH, WNBA; one live NFL, two NHL. No WNBA scheduled.
- Finding 1's rate is one evening, early season.
- Only `try?` paths not modelled in depth (`APILeague.calendar`, `PlayCoordinate.x/y`, `HeaderCompetitor.score`).
- Not covered: MLB, soccer, standings, team schedules, other endpoints.
