The Windows NVDA bug bash (PRs #119 and #120, Nov 2-3) included a check of the iOS app against real ESPN data. This issue is everything iOS needs from that work. It is written to hand to an agent: work through it, then stop at the handoff at the end.

**Nothing here has been seen on a device.** No Swift was compiled or run when these were found. Each finding comes from the Swift source re-stated in Python and applied to real ESPN payloads. Confirm each against the code before changing it. Line numbers are from `b8ff30f`, and paths are under `iOS/SportsScoresApp/SportsScores` unless they say otherwise.

## Sources

These are on Kelly's PC, in `C:\Users\kelly\OneDrive\testing\scores\`:

| File | What it is |
|---|---|
| `nvda-bugbash-2026-11-02\ios-check-REPORT.md` | The full iOS report. **Read this first.** It has counts, game ids and what was ruled out |
| `moreaudio\nvda-bugbash-2026-11-02\tools\ios_conformance.py` | The checker: stdlib Python, run with `python -I`, `--selftest` for its own 16 cases. Its model of the Swift types must be updated with your changes |
| `moreaudio\nvda-bugbash-2026-11-02\ios-check\` | `results.json`, and failing payloads such as `NCAAWB-401918849.json` |
| `nvda-bugbash-2026-11-02\data-audit-REPORT.md` | The Windows data audit. Useful for part 3 |

In the repo: `tests/fixtures/espn/` has real payloads per sport, and `INDEX.txt` says what each one shows. `box_score.py` and `game_labels.py` show how Windows solved the same shapes.

## Part 1: the two that break screens

- [ ] **NCAAWB games fail to open.** 29 of 145 played games in the sample, about 1 in 5.
  - `boxscore.players[*].statistics[*].athletes[*].athlete.displayName` is required (`Models/GameDetails.swift:456`), but some athletes carry only `shortName`: `{"links": [], "shortName": "J. Loubens"}`. These rows have `active:false` and `stats:[]`.
  - One such player makes the whole decode throw (`Services/ESPNAPIService.swift:706`), and `Views/GameDetailView.swift:42-45` replaces everything with an error and Retry. Box Score, Plays and Info are all lost, and Retry can't help.
  - Not only small schools: South Carolina `401918849` (final) is one. I re-checked that payload directly.
  - Fall back to `shortName`, and decode athletes leniently so one bad row can never fail a game. Look for the same risk in other non-optional fields.
- [ ] **Football week navigation fails** (#70). `Services/ESPNAPIService.swift:358` sends `dates=A-B`, which ESPN now answers with HTTP 400. `ViewModels/ScoresViewModel.swift:198-206` uses it for both arrows and historical seasons, so only the current week loads. I re-checked the 400 directly.
  - Use `dates=2026&week=8&seasontype=2`, plus `groups=90&limit=400` for NCAAF. Those returned 200 and pass the scoreboard schema. Windows made this change already (`espn_api.py`, search for `dates=`).
  - `fetchGamesRange` (`:549`, World Cup bracket) and `fetchTransactions` (`:1348`) also use ranges and weren't tested.

## Part 2: box scores that decode but show the wrong thing

- [ ] **Hockey Essential is blank or nearly blank.** ESPN's groups are `forwards`, `defenses`, `skaters`, `goalies`; the profile keys are `skater` and `goalie` (`Views/BoxScoreView.swift:626-628`, `:696-697`), so nothing matches and it falls to `values.first`. That depends on Swift's per-launch dictionary order, so which tabs are blank may change per launch (from the language rules, not observed). `:630` lowercases the column but not the set, so `plusMinus` and `shotsAgainst` never match.
- [ ] **College hockey: 9 tabs, all blank, no message** (135 of 135 finals). ESPN sends no data. "Box score not available" (`:110`) needs `teams` to be empty, which it never is. Show the message when there's nothing to show, and don't build tabs for groups with no athletes. The same empty pages appear in NFL (49 of 520) and NCAAF (522 of 4,240).
- [ ] **Every basketball player tab says "Unknown"** (`Models/GameDetails.swift:443`, `BoxScoreView.swift:29`), 730 pages. Basketball groups have neither `type` nor `name`. Windows calls these "Players".
- [ ] **Football Essential.** Kicking is always blank. `defense` doesn't match ESPN's `defensive`, and unmatched groups fall to `values.first`. Passing has no `C/ATT`. "Kickreturns" and "Puntreturns" come from `.capitalized`; ESPN's `text` isn't decoded. Quick List reads "Name ()" because football has no positions (`:573`, `:585`), and NCAAF has a " Team ()" row (271 rows).
- [ ] **Essential team stats miss most of their rows.** Profile names don't match the payload (`:665-693`): `passYards` vs `netPassingYards`, `rushYards` vs `rushingYards`, `rebounds` vs `totalRebounds`, `shots` vs `shotsTotal`, and so on. The report has the full list. Basketball's default box score has no shooting at all, in player or team tables.
- [ ] **Scheduled and postponed games.** Essential Team Stats is blank for scheduled games in most leagues, and All Stats shows season averages with nothing saying so. Postponed games show 0 to 0 once details load (`GameDetailView.swift:213-217`). `flatTeamStats` takes rows from `teams.first` only (`:348`), so an empty first team blanks the page.
- [ ] **Live football repeats the current drive.** `drives.previous` already holds it, and `GameDetails.swift:287-291` appends `current` anyway, which also gives a duplicate `ForEach` id. Windows skips `current` when its id is in `previous`.
- [ ] **Players with no stats.** `didNotPlay` and `reason` aren't decoded, and Quick List reads "Name (G), ". Windows shows "Did not play".
- [ ] **No totals.** `totals` isn't in `PlayerStatGroup`, though nearly every basketball and football group has it. Windows adds a Totals row.
- [ ] **NFL `interceptions` appears twice** in All Stats, with duplicate `ForEach` ids (`:386`, `:415`, `:437`).

## Part 3: Windows fixes iOS was never checked for

The iOS check covered scoreboards and game details only. These were wrong on Windows because of ESPN's data, so iOS may have the same problem. CLAUDE.md calls this the main source of drift. **Check each one, fix what applies, and say which didn't.**

- [ ] **Standings.** ESPN repeats `wins` and others once per split, with the same `name` and a different `type`; reading by name gets the last split. Windows read UTSA as 0-0 (true 7-1). Read by `type` (`total`, `vsconf`, `streak`). See `parse_college_standings` in `espn_api.py`.
- [ ] **Standings structure.** The Sun Belt nests a level deeper. Women's college hockey has entries at the root with no children. NHL: Utah is `UTAH`, not `ARI`, and teams rank by points.
- [ ] **Schedule dates.** ESPN's dates are UTC, so stripping the zone shows evening games a day late (60% of timed games on Windows). Honour `timeValid:false`, where the UTC date is the right one.
- [ ] **After midnight.** Asking for the new date loses games still being played: at 12:12 AM Eastern, three live NBA games vanished on Windows. Windows treats the scoreboard day as last night's until 5 AM (`scoreboard_today` in `game_labels.py`). Check Live Scores and league views.
- [ ] **Period names.** NCAAM has halves. Overtimes are OT, 2OT, 3OT. Football OT isn't "Quarter 5". Shootout attempts aren't goals.
- [ ] **Game details.** Betting lines are in `pickcenter`, not `odds` (overlaps #105). TV is `media.shortName`, and a summary's own list can be empty when its header has one. Injury counts should count players, not teams. Attendance 0 means unknown.
- [ ] **Rows.** Full names in NCAAWB and college hockey, not "Huskies 2 at Huskies 4". AP ranks. "vs", and no "(Home)", at a neutral site (`neutralSite`). No "0 at 0" on a delayed game that hasn't started.
- [ ] **Team hub.** Rosters: ESPN sends floats, `77.0` inches. News: `/teams/{id}/news` returned nothing for 14 of 14 teams, while `/news?team={id}` works. `nextEvent` can be the game just played. Venue is under `franchise.venue`; NHL records need OT losses.
- [ ] **Made-up data.** Windows had invented statistics and venues as fallbacks. Confirm iOS has none.

## Part 4: the one change that spans both platforms

- [ ] **College basketball plays falsely read "at the rim".** ESPN uses `(25, 0)` as a placeholder. It's accepted as a real location, so every substitution, free throw, timeout, jump ball and rebound reads "at the rim" and adds a false tone to period playback. That's 63% of located plays in NCAAM, 62% in NCAAWB and 2.5% in the NBA.
  - **Treat exactly `(25, 0)` as no location, for basketball only.** Hockey's coordinates are centred on the rink, so `(25, 0)` is a real spot there.
  - Before settling on that, check it against the fixtures. In `plays_NCAAM_401845838_3OT.json` and `plays_NCAAWB_401911736.json`, the only shooting plays at `(25, 0)` are made free throws. Real layups cluster at `y=2`.
  - Also look at fouls, which aren't normalised on Windows: 1,017 NCAAM fouls read like "deep, 66 feet out".
  - **CLAUDE.md requires `play_geometry.py` and `Services/PlayAudioGeometry.swift` to change in the same commit, with identical output.** So this one includes the Python: update `play_geometry.py`, `tests/fixtures/play_geometry_grid.json`, `tests/unit/test_play_geometry_parity.py` and the Python tests. Check the Swift against the same grid by hand, since iOS has no test target. `has_coordinate` currently takes no league, so its callers on Windows need checking too.
  - Remove the Known Issues entry in `CHANGELOG.md`.

Apart from this, leave the Windows code alone.

## How to work

- Take a branch from `main`, then a PR. Update `iOS/SportsScoresApp/USER_GUIDE.md` and `CHANGELOG.md` for anything a user would notice.
- **Prove it compiles.** There's no Swift on the PC. Run the `iOS Build Check` workflow on the branch (`gh workflow run`, it accepts manual dispatch): it compiles for the simulator without signing or uploading. Don't call anything done until that's green.
- **Re-run `ios_conformance.py`** against live ESPN data after updating its model, and report the before and after. The Windows suite must stay green, which also enforces version sync.
- Get an independent review from the `code-reviewer` subagent. VoiceOver is a full part of it. Fix what it finds, and say what you skipped and why.
- Merge once CI passes. Merging to main is routine.

**Don't**, without Kelly saying so:
- Change `VERSION`, `MARKETING_VERSION` or `version.py`, or push a `v*` tag. **One three-part tag releases both apps, and the Windows release is waiting on this work.**
- Upload to TestFlight. Ask first. Note #112: the commit-count build number can collide after a squash merge; `ios-release.yml` has a build number override.

## Handoff

Stop and send one push notification when the work is merged. Give Kelly:
1. What was fixed, what didn't apply and what's left, in the terms of the lists above.
2. A short VoiceOver list of what to try and what to hear. It should cover: an NCAAWB game that used to fail (`401918849`), football week arrows, an NHL box score, a college hockey final (`401904823`), an NBA box score's tabs and Totals, and a live football game's drives.
3. Whether the app is ready for a shared version with Windows.

Kelly returns to the Windows session after this, to choose a version and release.

## Not in this issue

#95, #99, #109, #110 and #112 are separate work, and the rest of #105 beyond betting lines. Note them if you touch them, but don't expand into them. The iOS check didn't cover MLB or soccer, and there were no live NCAAF, college hockey or WNBA games to check, with one live NFL game and two NHL.
