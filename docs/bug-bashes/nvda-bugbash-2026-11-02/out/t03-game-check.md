# Screen reader check: t03-game

Speech from NVDA's speech log (exact text). A logged utterance is what NVDA sent to its voice; the next key can cut it off, so the log shows what was sent, not that all of it was heard.

**5 of 5 expectations met.**

## line 3: `x`

-   7.49 s: Sports Scores window
-   7.50 s: League Selection List list List of available sports leagues and live scores
-   7.53 s: Live Scores - All Sports
-  19.01 s: NFL
-  21.10 s: Scores List list List of games and scores for the selected date or week
-  21.11 s: Loading scores...
-  22.16 s: Upcoming, 1 game
-  33.22 s: Bears (5-2) at Seahawks (4-3) (Mon 11/2 7:15PM)

## line 11: `k {ENTER}`

-  36.22 s: Game Details List list List of detailed information about the selected game
-  36.24 s: Loading game details...
-  36.81 s: Seattle Seahawks (Home)
- **PASS** (line 13) says `Game Details List`
- **PASS** (line 15) matches `\((Home|Away)\)`

## line 16: `n t`

-  48.20 s: NFL, Chicago Bears at Seattle Seahawks - Sports Scores
- **PASS** (line 18) matches `NFL, .+ at .+ - Sports Scores`

## line 19: `k {DOWN}`

-  51.34 s: Record: 4-3
- **PASS** (line 21) says `Record:`

## line 22: `k {ESC}`

-  54.42 s: Scores List list List of games and scores for the selected date or week
-  54.44 s: Loading scores...
-  54.95 s: Upcoming, 1 game
- **PASS** (line 24) says `Scores List`

