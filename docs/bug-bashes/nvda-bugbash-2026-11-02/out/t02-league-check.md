# Screen reader check: t02-league

Speech from NVDA's speech log (exact text). A logged utterance is what NVDA sent to its voice; the next key can cut it off, so the log shows what was sent, not that all of it was heard.

**10 of 10 expectations met.**

## line 3: `x`

-   7.33 s: Sports Scores window
-   7.34 s: League Selection List list List of available sports leagues and live scores
-   7.37 s: Live Scores - All Sports
-  19.32 s: NFL

## line 7: `k {ENTER}`

-  21.61 s: Scores List list List of games and scores for the selected date or week
-  21.62 s: Loading scores...
-  25.79 s: Upcoming, 1 game
- **PASS** (line 9) says `Scores List`
- **PASS** (line 11) matches `(games?|No games found)`

## line 12: `n t`

-  33.45 s: NFL - Sports Scores
- **PASS** (line 14) says `NFL - Sports Scores`

## line 15: `k {DOWN}`

-  36.59 s: Bears (5-2) at Seahawks (4-3) (Mon 11/2 7:15PM)
- **PASS** (line 17) matches `\bat\b`

## line 18: `k {TAB}`

-  39.62 s: Back (Alt+B) button
- **PASS** (line 20) says `Back (Alt+B)`

## line 21: `k {TAB}`

-  42.15 s: Previous Week (Alt+P) button
- **PASS** (line 23) says `Previous Week (Alt+P)`

## line 24: `k {TAB}`

-  44.74 s: Next Week (Alt+N) button
- **PASS** (line 26) says `Next Week (Alt+N)`

## line 27: `k {TAB}`

-  47.27 s: Refresh button
- **PASS** (line 29) says `Refresh`
- **PASS** (line 30) doesn't say `Go to Date`

## line 31: `k {ESC}`

-  49.87 s: League Selection List list List of available sports leagues and live scores
-  49.89 s: Live Scores - All Sports
- **PASS** (line 33) says `League Selection List`

