**To do after the next release.** Kelly's decision: list this as a known issue in the release notes and fix it afterwards.

## The problem

College basketball fouls read and sound as if they happened at the far end of the court. A foul right under the basket reads like "deep, 66 feet out", plays a far-away tone, and pans to the wrong side. This affects both apps, in NCAAM and NCAAWB. The NBA isn't affected.

## What the data shows

In ten finals each from Nov 1-2, 2026, not counting the `(25, 0)` placeholder (PR #122):

| League | Fouls | Median distance from the baseline (`y`) | Past half court |
|---|---|---|---|
| NCAAM | 381 | 77 | 83% |
| NCAAWB | 355 | 77 | 80% |
| NBA | 420 | 5 | 0% |

Shots in the same games are normal: a median of 6 in both college leagues and 7 in the NBA, so only fouls are affected.

**The fouls look mirrored.** An and-one gives a known answer: a made shot and an opposing foul on the same clock, which should be in the same place. Across about 45 finals per college league and 7 NBA finals:

| League | And-ones | Same spot as sent | Exact after `x = 50 - x`, `y = 84 - y` |
|---|---|---|---|
| NCAAM | 122 | 0 | 93 (76%) |
| NCAAWB | 131 | 0 | 107 (82%) |
| NBA | 24 | 10 | 0 |

Foul then shot, for example: (25, 82) and (25, 2); (23, 84) and (27, 0); (22, 81) and (28, 3). The most common miss was one foot off in `y`.

So college fouls appear to be measured from the fouling player's side, while other plays are measured toward the basket the offense is attacking. That reading fits the numbers, but ESPN doesn't document any of it. College foul text is also only "Foul on X", with no type, where the NBA names the foul ("Shooting Foul").

## What isn't proven

- **Fouls with no shot.** And-ones only test a defender fouling a shooter. About 15-20% of college fouls already sit in the near half (`y <= 47`, median about 9). They could be offensive fouls, or defenders pressing full court, and the flip may be wrong for some of them.
- **Fouls by the team that shoots next.** Too few to read: 10 in NCAAM and 13 in NCAAWB, over 16 games each.
- **Why 84 rather than 94,** the court's length. It fits the pairs, but it isn't explained. `play_geometry.py` puts the basket at `(25, 3)`.
- **Other play types.** About 10% of college turnovers also sit past half court. They weren't looked at.

## Suggested fix

1. Settle the near-half fouls first. Check against who has the ball next, and the shot or free throw that follows.
2. Decide the rule, in this order of preference:
   - Flip all college fouls, if that holds up.
   - Flip only the far-half fouls, if the near-half ones turn out not to be mirrored.
   - Give college fouls no location, if neither is reliable. A foul with no location is better than a false one.
3. Change `play_geometry.py` and `Services/PlayAudioGeometry.swift` in the **same commit** with identical output, as CLAUDE.md requires, and add the cases to `tests/fixtures/play_geometry_grid.json`. Leave the NBA and WNBA alone. Check the WNBA first, since it wasn't in this sample.
4. Because the transform needs the play type, it can't be a function of `x` and `y` alone. See how PR #122 passed the league into `has_coordinate`.
5. Add an and-one test against a real saved play-by-play in `tests/fixtures/espn/`.
6. Remove the known issue from `CHANGELOG.md`.

Then listen under NVDA, JAWS and VoiceOver: a shooting foul on a layup should read as near the basket and pan the same way as the shot.

## Evidence

Scripts, read-only against ESPN, in `C:\Users\kelly\OneDrive\testing\scores\moreaudio\nvda-bugbash-2026-11-02\tools\`:

- `fouls_by_league.py`: the first table.
- `fouls_who_has_ball.py`: fouls by who shoots next, and the near-half count.
- `fouls_andone_gap.py`, `fouls_andone_exact.py`: the and-one comparison.

They read live ESPN data, so counts will move as dates change. They use dates from Nov 2026 and need adjusting to re-run later.

Related: #121, #122 (the `(25, 0)` placeholder), which found the same pattern as "84% of NCAAM and 80% of NCAAWB fouls sit past half court".
