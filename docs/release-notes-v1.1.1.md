## What's New in Version 1.1.1

Soccer leagues on Windows have their tables, the iPhone has Venues and the rest of a game's details, and when
ESPN doesn't answer, both apps say so rather than looking empty.

### Windows

**Soccer**
- Soccer leagues have Standings, Statistics and Teams. Standings read position, games played, wins, draws,
  losses, goals for and against, goal difference, points, and where a place leads, such as Champions League
  or Relegation. MLS has a tab for each conference, and the Champions League and Europa League show their
  league phase. The CONCACAF Champions Cup is all knockout, so its Standings say it has no table, and Teams
  still lists its teams.
- Soccer leaders: goals, assists, shots, cards, fouls, passes and saves, up to 20 players each, from the same
  place as the iPhone.

**When ESPN doesn't answer**
- Every screen says so in a plain sentence: "ESPN isn't providing scores right now. Try again in a minute." It
  used to read as "No games found" or "No news", or read out the text of a network error.
- A league's list still offers News, Standings and its other sections when only the scores failed. Enter on
  that row, or F5, tries again.
- A refresh that fails keeps what's showing, and says so once if you asked for it. In Live Scores, refreshes on
  the timer stay quiet unless a game you're monitoring is affected, and a league that fails keeps the games it
  last showed, with a row at the end naming it.
- In Transactions, a team list that fails says so, and F5 tries again and says when it worked.
- Opening a World Cup no longer says "Something went wrong" once its first phase is over.

**Fixed**
- College basketball fouls read and sound where they happened. A foul under the basket read "deep, 78 feet
  out", with a note on the wrong side. It now reads "at the rim", and pans the same way as a shot from there.
- NBA standings read the season ESPN calls current.
- A football game's wrap up names its quarters: Quarter 1 and OT, not Period 1.
- The college football setting is called "College football coverage", since it also decides the standings and
  teams you see. Your choice is kept.

### iPhone

- **Venues:** the ten leagues Windows has Venues for have a Venues tab, with the same list: stadiums and arenas with their city, state and home teams, in all three views. Selecting one shows its details.
- **College hockey polls,** men's and women's, as on Windows.
- **Soccer standings read as soccer:** games played, wins, draws, losses, goals, goal difference, points and where a place leads. MLS is in rank order, and a cup with no table says so. Leaders list Goals and Assists once, and players level on a number share a rank.
- **A game's Info tab** has weather, attendance, the division standings of both teams, a Scoring Summary for football, and an injury's type, detail and return date. A finished game has its Game Story.
- **College basketball fouls** read and sound where they happened, not at the far end of the court.
- **When ESPN doesn't answer,** Live Scores and Live Soccer say so, with Retry, rather than "No games scheduled today". VoiceOver stays on Retry, says "Retrying", then the error if it failed again. A failed pull to refresh keeps News, Polls and Standings on screen, and says so.
- **Fixed:** coming back to a game no longer reloads the screen and loses VoiceOver's place, View All on Stats reads once, a team with no news says so rather than showing league stories, and a poll with no points no longer reads 0.
- **Coverage:** the college football setting is called Coverage, since it also decides the standings and teams you see. Your choice is kept.

### Windows known issues

- On long lists, screen readers can give the wrong item count, because the list only reports the rows on screen.
  Table view gives the true row and total. We believe this is a bug in Qt 6, the toolkit the Windows app is built
  on: [QTBUG-149577](https://qt-project.atlassian.net/browse/QTBUG-149577).
- JAWS reads each tab twice as you arrow along tabs.
- A football game's Drives aren't announced as a real tree: expanded and collapsed aren't said, and drives
  inside a quarter don't read a level.

---

**Platforms:** Windows 10 or later; iPhone through TestFlight
