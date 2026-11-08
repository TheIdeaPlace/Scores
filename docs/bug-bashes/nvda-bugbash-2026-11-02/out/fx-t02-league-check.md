# Screen reader check: fx-t02-league

Speech from NVDA's speech log (exact text). A logged utterance is what NVDA sent to its voice; the next key can cut it off, so the log shows what was sent, not that all of it was heard.

**10 of 10 expectations met.**

## line 3: `x`

-   2.68 s: Sports Scores window
-   2.69 s: League Selection List list List of available sports leagues and live scores
-   2.71 s: Live Scores - All Sports
-  14.66 s: NFL

## line 7: `k {ENTER}`

-  16.82 s: Scores List list List of games and scores for the selected date or week
-  16.85 s: Loading scores...
-  18.52 s: Completed, 14 games
-  18.52 s: Week 8
- **PASS** (line 9) says `Scores List`
- **PASS** (line 11) matches `(games?|No games found)`

## line 12: `n t`

-  28.77 s: NFL, Week 8 - Sports Scores
- **PASS** (line 14) matches `NFL, Week \d+ - Sports Scores`

## line 15: `k {DOWN}`

-  31.98 s: Panthers 19 at Packers 27 [Final]
- **PASS** (line 17) matches `\bat\b`

## line 18: `k {TAB}`

-  35.00 s: Back (Alt+B) button
- **PASS** (line 20) says `Back (Alt+B)`

## line 21: `k {TAB}`

-  37.48 s: Previous Week (Alt+P) button
- **PASS** (line 23) says `Previous Week (Alt+P)`

## line 24: `k {TAB}`

-  40.03 s: Next Week (Alt+N) button
- **PASS** (line 26) says `Next Week (Alt+N)`

## line 27: `k {TAB}`

-  42.56 s: Refresh button
- **PASS** (line 29) says `Refresh`
- **PASS** (line 30) doesn't say `Go to Date`

## line 31: `k {ESC}`

-  45.16 s: League Selection List list List of available sports leagues and live scores
-  45.18 s: NFL
- **PASS** (line 33) says `League Selection List`

