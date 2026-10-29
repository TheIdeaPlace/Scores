# ESPN data the app isn't using yet

Survey done 2026-10-29 against live ESPN endpoints, cross-checked against
`espn_api.py`, `scores.py` and `iOS/.../ESPNAPIService.swift`. Everything below
returned 200 with real data on the day of the survey. Nothing here is
implemented — this is a shopping list, roughly best-value first.

For endpoints already in use see `ESPN_API_GUIDE.md`.

Each item below is now tracked as an issue, filed 2026-10-29:

| Item | Issue |
|---|---|
| 1 — `byteam` on Windows | [#94](https://github.com/TheIdeaPlace/Scores/issues/94) |
| 1 — `byathlete` | [#95](https://github.com/TheIdeaPlace/Scores/issues/95) |
| 2 — player splits | [#96](https://github.com/TheIdeaPlace/Scores/issues/96) |
| 3 — `powerindex` | [#97](https://github.com/TheIdeaPlace/Scores/issues/97) |
| 4 — `predictor` | [#98](https://github.com/TheIdeaPlace/Scores/issues/98) |
| 5 — shot chart / rink map | [#99](https://github.com/TheIdeaPlace/Scores/issues/99) |
| 6 — futures odds | [#100](https://github.com/TheIdeaPlace/Scores/issues/100) |
| 7 — depth charts | [#101](https://github.com/TheIdeaPlace/Scores/issues/101) |
| 7 — NHL `onIce` | [#102](https://github.com/TheIdeaPlace/Scores/issues/102) |
| 7 — live `situation` | [#103](https://github.com/TheIdeaPlace/Scores/issues/103) |
| 7 — `statisticslog`, extra polls, `attendance` | [#104](https://github.com/TheIdeaPlace/Scores/issues/104) |
| 7 — iOS gaps Windows covers | [#105](https://github.com/TheIdeaPlace/Scores/issues/105) |

Item 5's play-level audio shipped on both platforms (`play_geometry.py`,
`Services/PlayAudioGeometry.swift`); [#99](https://github.com/TheIdeaPlace/Scores/issues/99)
covers the explorable shot chart that is still missing, and
[#106](https://github.com/TheIdeaPlace/Scores/issues/106) covers keeping the two
mappings from drifting.

## 1. League-wide stat tables in one call — `statistics/byteam` and `statistics/byathlete`

```
https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byteam?season=2026
https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byathlete?season=2026&limit=50&page=1
```

`byteam` returns every team's full season aggregates in a single response (NFL:
32 teams, 9 categories, 99 stat columns, 367 KB). The Windows app instead loops
`/{league}/teams` and fires one request per team through a 10–15 worker thread
pool (`_get_team_statistics`, espn_api.py:3352) — 32 requests where 1 would do.
**The iOS app already uses `byteam`** (`Services/TeamStatsStore.swift:120`, with
a comment at `ESPNAPIService.swift:892` explaining why it switched). This is
the clearest platform drift found, and fixing it on Windows is a straight
speed win.

`byathlete` is unused on *both* platforms. It is a paginated league-wide player
leaderboard with every category, far beyond the handful `/leaders` returns —
NBA 230 qualified players over 37 stat columns in `general` / `offensive` /
`defensive`. Confirmed working for NFL, NBA, NHL, WNBA, CFB, NCAAM and NCAAW.
Returns 0 athletes for college hockey, so keep the NCAAH/NCAAWH fallback.

## 2. Player splits — `athletes/{id}/splits`

```
https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/athletes/{athleteId}/splits
```

Unused on both platforms, and the single richest find. NFL returns 28 split
categories: `byDown`, `byQuarter`, `byHalf`, `byFieldPosition`, `byLocation`
(home/away), `byOpponent`, `byMonth`, `byDayOfWeek`, `byOutcome`,
`byVictoryMargin`, `byClose`, `byPtDiff`, `byDepthChart`, plus formation and
motion splits. Each split is a labelled row of stats against a shared `labels`
array (`CMP ATT YDS CMP% AVG TD INT LNG SACK RTG`) — i.e. already in the exact
shape `accessible_table.py` wants, so Table / Quick List / Full List all come
for free. A `season` filter exposes 2019–2026.

Also unused on the same athlete path: `/gamelog` (full game-by-game log with a
`glossary`), `/bio` (awards + team history), `/overview` (one 150 KB call
bundling gameLog, statistics, news, nextGame, fantasy).

## 3. FPI / BPI tables with playoff odds — `powerindex`

```
https://site.web.api.espn.com/apis/fitt/v3/sports/{sport}/{league}/powerindex?limit=40
```

Works for NFL, NBA, CFB and NCAAM. (400s for NHL — ESPN has no hockey BPI.)
Three categories per team:

- `fpi` — rating, EPA offense/defense/special teams, FPI rank, SOS rank,
  remaining-SOS rank, game-control rank, 7-day rank change
- `projections` — projected W/L, `probwinout`, `probwinconf`, `probwindiv`,
  `probmakeplayoffs`, `probmaketitlegame`, `probwintitle`
- `efficiencies` — total/offensive/defensive/special-teams efficiency, each
  with its league rank

Each category carries parallel `totals` (display strings, e.g. `"90.3%"`,
`"2nd"`) and `values` (floats) arrays, so it sorts properly and reads properly.
A "Playoff Picture" or "Power Index" view next to Standings is the obvious home.
Note the `glossary` has entries with no `abbreviation` key — guard for that.

## 4. Game predictor — `competitions/{id}/predictor`

```
https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eventId}/competitions/{competitionId}/predictor
```

Confirmed for NFL and CFB. Per side: `gameProjection` (win %), `teamChanceLoss`,
`teamChanceTie`, `matchupQuality` (projected competitiveness), `teamPredPtDiff`,
`teamOffEff` / `teamDefEff` / `teamSTEff` / `teamTotEff`, `teamAvgWp`,
`oppSeasonStrengthRating`. Most stats carry a `description`, so the screen
reader text can be generated rather than hardcoded. This is a pregame
counterpart to the in-game `winprobability` the Windows app already shows at
scores.py:7225 — `matchupQuality` in particular is a nice "is this game worth
watching tonight?" signal for the scores list.

## 5. Shot and rink coordinates — NBA, NCAAM and NHL plays

The `summary` endpoint's `plays[]` already carries spatial data the app ignores:

- **NBA / NCAAM**: every play has `coordinate {x, y}` plus `shootingPlay`,
  `pointsAttempted` and `scoreValue`. 491 plays in the sampled game.
- **NHL**: every play has `coordinate {x, y}` over the full rink (x roughly
  −100..100) plus `strength` (`Even Strength`, power play) — covering shots,
  missed shots, hits, takeaways and giveaways. 324 plays sampled.

This is the direct analogue of the MLB work in `pitch_exploration_dialog.py` /
`simple_audio_mapper.py` / `stereo_audio_mapper.py`: a keyboard-navigable,
sonified shot chart for basketball and a rink map for hockey. Probably the
highest-value accessibility feature on this list, since nobody else ships it.

Watch for the sentinel: dead coordinates come back as
`{x: -214748340, y: -214748365}` (int32 min scaled), e.g. on jump balls and
face-offs. Filter those out rather than plotting them at an edge.

## 6. Futures odds — `seasons/{year}/futures`

```
https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/2026/futures
```

Confirmed for NFL (22 markets), NHL (11), NBA (15) and CFB (15). NFL markets
include Regular Season MVP, OPOY, DPOY, both Rookie of the Year awards, Coach
of the Year, Comeback Player, and statistical leaders such as Most Passing
Yards — each a DraftKings price list keyed by `$ref` to an athlete or team, so
it needs an id→name resolve. Reads naturally as an awards-race view.

## 7. Smaller items

- **Depth charts** — `.../leagues/{league}/seasons/2026/teams/{teamId}/depthcharts`.
  Note the `seasons/{year}` segment: the path without it 404s. Returns
  formation groups (`Base 4-3 D`, `3WR 1TE`, `Special Teams`) with ranked
  athletes per position. Works for NFL and NBA. Unused on both platforms.
- **NHL `onIce`** — present in every NHL `summary`, unused on both platforms.
  Two entries (one per team) listing `athleteid` and `whereabouts`
  (`ROSTER_WHEREABOUTS_IN_PLAY`), i.e. who is on the ice right now. Useful
  during live games; needs a roster join for names.
- **Live situation** — `.../competitions/{id}/situation` gives `down`,
  `distance`, `yardLine`, `isRedZone`, `homeTimeouts` / `awayTimeouts` and
  `lastPlay` in a 393-byte response. Much cheaper to poll than the full
  scoreboard for a single followed game.
- **`statisticslog`** — `.../leagues/{league}/athletes/{id}/statisticslog?season=2026`,
  season-by-season career totals.
- **Extra college football polls** — `rankings` also returns the AFCA Coaches
  Poll, FCS Coaches Poll and AFCA Division II and III polls, not just AP Top 25.
- **`attendance`** — in both `scoreboard` competitions and `summary.gameInfo`;
  only 2 references in the Windows app, none on iOS.
- **iOS gaps that Windows already covers** — `againstTheSpread`, `pickcenter`
  and `scoringPlays` are all read in `scores.py` but not in the iOS app.

## Dead ends (don't retry)

| Endpoint | Result |
|---|---|
| `.../competitions/{id}/powerindex/{teamId}` | 404 — use `predictor` instead |
| `fitt/v3/.../qbr`, `.../types/2/qbr` | 404 / 400 — no public Total QBR feed found |
| `fitt/v3/.../bracketology`, `.../tournament/bracket` | 404 (checked out of season) |
| `teams/{id}/depthcharts` without `seasons/{year}` | 404 |
| `athletes/{id}/eventlog` | 500 |
| `.../seasons/{year}/teams/{id}/odds-records` | 404 |
| `hockey/nhl/powerindex` | 400 — no NHL BPI |
