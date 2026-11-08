# Missing data audit, both apps, Nov 3-4, 2026

Read-only audit at commit e133a3c. No UI was run and no Swift was built: iOS findings come from reading code plus ESPN URLs. Line numbers are as of that commit.

URL prefixes: SITE = site.api.espn.com/apis/site/v2/sports; STAND = site.api.espn.com/apis/v2/sports; CORE = sports.core.api.espn.com/v2/sports; WEB = site.web.api.espn.com/apis/common/v3/sports; V3 = site.web.api.espn.com/apis/site/v3/sports

## Decisions made so far

- **Football schedules:** show preseason and postseason, labelled, on both apps. iOS adds preseason for NBA, NHL and college to match Windows.
- **Windows leaders:** V3 `/leaders`, limit about 20, one retry on a 500, MLB Stats API stays. iOS stays on core and caps concurrency.
- **FCS:** standings and Teams follow the existing coverage setting.
- **Team stats on Windows:** keep every column, add a direction table for low-is-good stats. Shared catalog data if practical.
- **WNBA on Windows:** add the league rows and flags.
- **Not in this work:** Windows soccer standings, statistics and teams (file an issue). An iOS Venues screen awaits Kelly's decision.

## A. NFL/NCAAF schedules: preseason and postseason

**Windows, confirmed.** espn_api.py:409-426 asks only for `seasontype=2`. `get_team_schedule("NFL","26",season=2025)` gave 17 games and no Super Bowl. Alabama 2025 gave 13 and no playoff games.

**iOS, already right.** Asks for [1,2,3] for football (TeamScheduleViewModel.swift:52, ESPNAPIService.swift:1641). The drift: iOS skips preseason for NBA, NHL and college, while Windows includes it (espn_api.py:387).

**ESPN:** 1 preseason, 2 regular, 3 postseason, 4 empty.

| URL | Events |
|---|---|
| SITE/football/nfl/teams/26/schedule?season=2025&seasontype=3 | 3, including SEA VS NE, week "Super Bowl", note "Super Bowl LX" |
| .../teams/12/...season=2025&seasontype=1 | 3 |
| .../teams/12/...season=2025&seasontype=3 | 0 (missed the playoffs) |
| SITE/football/college-football/teams/333/schedule?season=2025&seasontype=3 | 2, note "College Football Playoff First Round Game" |
| same team, seasontype=1 | 0 |

No seasontype returns regular season only. FCS playoffs are filed under type 2 (NDSU's Dec 6, 2025 game is "Week 15", note "FCS Championship - Second Round"; its type 3 is empty).

**Fix, Windows:** ask for all three types for football; show the note or `week.text` in the row. Keep the failure behaviour pinned at test_schedule.py:189-197: a timeout reaches the caller today, and folding football into the existing `except: pass` loop would be a regression. Drop the bad fallback at espn_api.py:478-489.
**Fix, iOS:** add a bowl or round label if the model has room; it has `seasonType` but no name.

## B. Player leaders

**Windows, worse than described.** `/statistics` (espn_api.py:2788) reports `season.type=2` for NFL and NHL, but the values are preseason. NFL passing shows Joe Fagnano 509, 446, 434; CORE `.../seasons/2026/types/2/leaders` gives 2246, 2146, 2124, and `types/1` matches 509, 446, 434 exactly. NHL goals 4, 3, 3 against core 15, 13, 13. NCAAF and NCAAM match core. NBA has no leaders. WNBA gave 404 "Failed to retrieve league stats" both times. The response is 12-44 MB raw. scores.py:11258 and 11626 re-sort player lists descending, so ERA and goals-against read worst first (from reading the code).

**iOS, fine.** Core API, regular season first, then earlier seasons (ESPNAPIService.swift:761-797, 1065). Names resolved on a two-leader sample in NFL, NCAAF, WNBA, NCAAM, NCAAWB, NHL, MLB, EPL. Low-is-good order correct. Risks: `fetchLeagueLeadersForTeam` uses limit=100 with an uncapped task group (:821, :1173), 341 to 1174 requests for one team's stats tab. A failed lookup silently shows "—" (:1121). `formatLeaderStatValue` gives 38.29 where ESPN says 38.3, and a value under 1.0 reads ".900".

| Source | Requests | Depth | Coverage and problems |
|---|---|---|---|
| Core | 1 + refs. At limit=10, athletes+teams: NFL 114+31, NCAAF 104+76, NBA 95+30, WNBA 69+15, NCAAM 115+90, NCAAWB 116+89, NHL 54+24, MLB 106+29, EPL 73+20, MLS 67+27 | to 100 | NBA 125 refs took 4.14s at 8 workers. College hockey 404. Soccer works under types/1 only |
| V3 `/leaders` | 1, names and team inline | 24 worked, 25-100 returned 500 (one try each) | NFL, NCAAF, NBA, WNBA, NCAAM, NCAAWB, NHL, MLB. 404 for college hockey and soccer. NBA 81 KB wire, NFL limit=24 is 5.7 MB raw |
| byathlete (#95) | 1 per sorted category or page | large | Rows: NFL 47, NCAAF 174, NBA 313, NHL 818, NCAAWB 3611, NCAAM 40 qualified. 0 for college hockey and soccer |

V3 and byathlete default to postseason for WNBA and MLB today, so pass `season=Y&seasontype=2`. V3 failures: NCAAM with `season=2027&seasontype=2` gave 500 on the first try in two runs, then 200; `seasontype=2` alone gave 500 three times. V3 applies a qualified filter: NCAAM's points leader is Zander Carter 21.0, against core and `/statistics` Dior Johnson 41.0. No source has leaders for college hockey. V3 has about 30 calls of evidence; core had none of the failures seen in this audit.

**Fix, Windows:** V3 `/leaders`, limit=20, one retry on a 500, keep the MLB Stats API. Stop re-sorting player rows. Fix the "Recent Performance Leaders" header (scores.py:11196). Consider core as a fallback if V3 keeps failing. **Fix, iOS:** cap concurrency; fix the two format issues if confirmed.

## C. FCS teams

**Windows, confirmed.** espn_api.py:2285 sends no group: 138 teams, 12 conferences, no Big Sky. Teams uses the same call (scores.py:2013). The scoreboard defaults to groups=90, so users see FCS games but not the teams.
**iOS, same gap.** ESPNAPIService.swift:647 (standings) and :1406 (Team Hub conferences) send no group.

On `/standings` the parameter is singular `group=`; `groups=` is ignored.

| URL | Result |
|---|---|
| STAND/football/college-football/standings | FBS, 138 |
| ?group=80 | 138 |
| ?group=81 | FCS, 128, 15 conferences |
| ?group=90 | 266, 25 conferences |
| ?group=35 | D-II/III, 405 |

`/teams` ignores both parameters; default is the first 50 alphabetically across all divisions, limit=1000 gives 762. group=90 nests FBS and FCS, then conferences, with the Sun Belt one level deeper. The Windows parser handled it live: 266 rows, 25 divisions, Montana State 8-1 in Big Sky. NDSU is FBS in 2026, so don't use it as an FCS test team.

**Fix, Windows:** add `group=` from `NCAAF_COVERAGE_GROUPS`; key `DataCache` by coverage (scores.py:8708) or clear it on save (:394).
**Fix, iOS:** add the group in both places. `fetchConferencesWithTeams` flattens one level only (:1431) and would give two "conferences" named FBS and FCS, so make it recurse. `groupsWithEntries` already recurses (Standings.swift:241). Related: `fetchTeamsForSport` has no limit (:1391), and TransactionViewModel.swift:45 uses it, so college lists there are the first 50 only.

## D. League team-stat rankings

**Windows, confirmed.** espn_api.py:2505 calls /teams with no limit, so NCAAM has 50 teams; then one request per team (:2542). Sorted descending at scores.py:11275, 11445, 11570, so low-is-good stats rank worst first. #94's cited line is stale; the function is at :2493.

**iOS** already uses `byteam`: limit 500 college, 50 pro (TeamStatsStore.swift:57), direction correct through TeamStatCatalog.swift. Bugs: (1) sends no season or seasontype (TeamStatsStore.swift:120). ESPN defaults to postseason once a season ends, so WNBA shows 8 teams and MLB 12 with playoff stats; with `seasontype=2`, 15 and 30. (2) byteam returns at most 400 rows: NCAAM `season=2026` count 722, limit=500 gave 400, page 2 empty, 31 D-I teams lost. Today's count is 365, so this should hit later this season (extrapolated). (3) `fetchTeamStatRankings` hides rank > 34 (ESPNAPIService.swift:895), which hides nearly every college team's ranks.

**ESPN byteam:** WEB/.../statistics/byteam?limit=500. NCAAM default 50 of 365, 8 pages; limit=500 gives 365. NFL and NCAAF: limit=1000 collapses to 25, so use 500 everywhere. NFL `page=2` returned 500. `sort=offensive.avgTurnovers:asc` works; a desc plus an asc request covered 361 of 362 D-I teams on the past season. College football is FBS only (138), and `group`/`groups` are ignored. College hockey empty. EPL 500. Don't use ESPN's `ranks`: blank for NBA and NHL points/goals, NFL totalGiveaways rank 1 is the most giveaways, NCAAM ranks have gaps.

**Fix, Windows:** one byteam call, limit=500, reading `requestedSeason.type`; ask again with `seasontype=2` if it is 3; use the sort union when `pagination.count` exceeds rows; add a direction table; drop non-D-I as `qualifiedTeams` does. Possibly a shared `tests/fixtures/team_stat_catalog.json` with a parity test, like the play audio grid.
**Fix, iOS:** add the season type and sort union, decode `pagination`, lift the rank cap for college.

## E. Venues

**Windows, confirmed.** Venue counts, home teams 0 everywhere: NFL 38, NBA 40, MLB 28, NHL 37, NCAAF 160, NCAAM, NCAAWB, NCAAH and NCAAWH 0. Mapping at venue_service.py:17-25. limit=100 caps results (:47); the NBA November page hit it. `timeout=3`, and one failed month loses everything. Capacity and grass are never in scoreboard data.

**iOS:** no venues feature in any league. Only tours in The Bench, per-game venue, and Team Info.

**ESPN:** /teams has no venue. `/teams/{id}` `franchise.venue` exists only for NFL, NBA, NHL, MLB, and is stale for 11 teams against the most-used home venue: Nets Prudential, Warriors Oracle, Clippers crypto.com, Bucks BMO Harris, Kings Sleep Train; Bills old Highmark, Chargers Dignity Health, Rams Coliseum; Devils IZOD, Jets State Farm Arena; A's Oakland Coliseum. This affects Team Info on both apps (espn_api.py:2986, ESPNAPIService.swift:1506). CORE `/teams/{id}` has venue for college, WNBA and soccer, not MLB, and the Bucks are stale there too.

**Best source: the scoreboard, one request per league.** Home team = `homeAway=home` when not `neutralSite`.

| URL | Events | Venues | Home teams | Raw size |
|---|---|---|---|---|
| football/nfl?dates=2026&limit=1000 | 320 | 41 | 32 | 3 MB |
| basketball/nba?dates=2026&limit=1000 | 1000 | 41 | 30 | 14.5 MB |
| hockey/nhl?dates=2026&limit=1000 | 1000 | 38 | 32 | 20 MB |
| baseball/mlb?dates=2026&limit=1000 | 1000 | 55 | 30 | 18 MB |
| basketball/wnba?dates=2026&limit=1000 | 374 | 30 | 16 | 7 MB |
| college-football?dates=202610&groups=90&limit=400 | 566 | 272 | 266 | 8 MB |
| same with groups=80 | 291 | 141 | 138 | 4.5 MB |
| mens-college-basketball?dates=202611&groups=50&limit=1000 | 1000 | 387 | 360 | 11.6 MB |
| womens-college-basketball, same | 1000 | 366 | 354 | 11 MB |
| mens-college-hockey?dates=202611&limit=1000 | 224 | 64 | 60 | 0.6 MB |
| womens-college-hockey, same | 153 | 46 | 43 | 0.4 MB |

A year query is capped at the first 1000 events, so NBA `dates=2026` stops at about April. Prefer one in-season month per league, falling back to the previous season (only measured for college). CORE `/venues/{id}` can supply grass and indoor lazily for the details dialog (no capacity seen).

**Fix, Windows:** rewrite VenueService this way; Team Info prefers the venue of recent home games. **Fix, iOS:** fix the Team Info venue.

## F. WNBA and soccer

**Windows WNBA:** no rows at scores.py:1807, no flags in main.py (39-69, 80-90, 122-148). Plumbing exists: `get_standings` (espn_api.py:1639), StandingsDialog (scores.py:8776), SimpleTeamsDialog (:12070). `get_team_schedule("WNBA","8")` returns 0 today, because the last game (Sep 30) is outside the ±30 day window; `season=2024` also 0.

**Windows soccer:** `EPL season=2020` returned 8 current games stamped as past-season rows. No league sections, though Team Hub is reachable from a game.

**iOS WNBA:** Scores, Standings, News, Stats tabs (ScoresView.swift:50-57), Team Hub with a 5-year picker, Transactions, schedule with [2,3]. Team stats show only the 8 playoff teams (see D).

**iOS soccer, broken.** The standings row opens TeamScheduleView (DataTableView.swift:382), which asks for `seasontype` 2 and 3 (TeamScheduleViewModel.swift:53). Those return 0 for soccer, so it reads "No schedule data" in every soccer league (from code plus URLs). `isCompleted` tests only STATUS_FINAL (Schedule.swift:27), but soccer says STATUS_FULL_TIME.

**ESPN `/teams/{id}/schedule`:**

| League | Query | Events |
|---|---|---|
| WNBA 8 | no parameters | 49 (all types) |
| WNBA 8 | season=2025 type 2 / type 3 | 45 / 6 |
| WNBA 8 | season=2024 type 2 | 41 |
| Duke | season=2027 type 2 | 32 |
| Duke | season=2026 type 2 / type 3 | 34 / 4 |
| South Carolina women | 2027 type 2 / 2026 type 3 | 31 / 6 |
| Men's college hockey team 1 | 2027 type 2 | 30 |
| Arsenal EPL | season=2026 | 9 played |
| Arsenal EPL | fixture=true | 29 upcoming |
| Arsenal EPL | season=2025 | 38 |
| Arsenal EPL | seasontype=1 | same as no type |
| Arsenal UCL | season=2025 | 15, all stages |
| MLS Atlanta | season=2026 | 33 |
| MLS Atlanta | fixture=true (even with season=2026) | 14, all 2027 Sprint games |

`fixture=true` ignores `season`. Soccer needs results plus fixture for the current season, results only for a past one, and no seasontype.

**Schedule paths.** Windows dedicated endpoint: MLB, NBA, NHL, NCAAH, NCAAWH, NCAAM, NCAAWB [1,2,3]; NFL, NCAAF [2]. Windows scoreboard window: WNBA, all soccer, every other league (:375, :453). iOS: everything dedicated; MLB and football [1,2,3], all others [2,3], soccer included. #71's NCAAM/NCAAWB part is already fixed.

**Fix, Windows:** add WNBA to the [1,2,3] group; add a soccer branch, merged and de-duplicated by id; scoreboard only as a last resort; add the WNBA league rows and flags. **Fix, iOS:** give soccer its own branch; treat full-time as completed.

## Tests, fixtures and the validator

**Strict xfails that will flip (remove the marker):** test_known_gaps.py:103 (F; add a soccer sibling), :137 and :147 (E; keep `VenueService.leagues` as a dict or change the test), :94 if A removes the NCAAF fallback. `READ_AS_NOTHING` at :62 is built from `QUIET` in test_failure_paths.py:24-39 and covers player, team and league statistics and venues, so entries flip if B, D or E start raising.

**Tests pinning old behaviour:** test_schedule.py:34-38, 46-50, 110 (exact row dict, breaks if a label is added), 189-197, 204-206, 209-241. test_found_bugs.py:60-67. test_missing_fields.py:98, 120-123. test_game_labels.py:119. INDEX.txt rows 19-23, 27, 52.

**Shared fixtures:** FeedDecodingTests.swift:358 decodes `standings_{league}.json`, so add a new `standings_NCAAF_group90.json` rather than changing the old one. Others to add: schedule_NFL_26_post, schedule_NCAAF_333_post, schedule_EPL_359 (results and fixture), leaders_v3_NBA, byteam_NBA, byteam_NCAAM with pagination, a scoreboard with `neutralSite`. Fixtures must keep the fields ESPN sends: the iPhone's tests decode every `schedule_*` file, and a trimmed one failed CI.

**Validator (tools/validate_espn.py) additions:** V3 leaders per league, removing the gap at :127; a check that leaders are not preseason (compare core types 1 and 2); NCAAF `group=90` at 200+ teams with an FCS conference (:851); past-season postseason schedules (SEA, Alabama); soccer no-type, `fixture=true`, type 2 empty; replace `schedule_window` (:103, :121, :128, :943-950); byteam `requestedSeason.type` and a warning if count exceeds rows (:1097 uses limit=1 and can't see this); home teams from the scoreboard.

## Conflicts

A and F schedules both rewrite espn_api.py:357-689 and test_schedule.py: one change. B and D must be in sequence: shared `get_statistics` (:2808-2859), scores.py 11184-11638, validator 1046-1107. C alone: espn_api.py:2283-2317, scores.py:394 and :8706, ESPNAPIService.swift:646-671 and 1405-1455, Transaction.swift:83+. E alone: services/venue_service.py, scores.py 2084-2120 and 12234-12453, get_team_info (espn_api.py:2986), ESPNAPIService.swift:1505. WNBA rows: scores.py:1807 and main.py only. Expect small conflicts in test_known_gaps.py, test_failure_paths.py, INDEX.txt and validate_espn.py.

## Not verified

No UI run on either platform; no Swift built. The 400-row cap was measured only on past seasons. V3 and core reliability rest on one day's sample. The per-month scoreboard plan for pro leagues was not measured at limit=1000. The off-season default to postseason was seen for WNBA, MLB and NFL `season=2025`, not others. The rank > 34 hide on iOS and the Windows player re-sort come from reading code. Soccer checks covered EPL, MLS and UCL only.
