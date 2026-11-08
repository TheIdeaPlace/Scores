## What's New in Version 1.2.0

Listen to the game on the radio, follow the games you care about in a Monitoring section, and on Windows, racing
and the CFL. Both apps now read the same data in more places, and a lot of things that were wrong now aren't.

### Windows

**Listen to the game**
- For the NFL, NBA, NHL, and college football and basketball (SEC, Big Ten, ACC, Big 12 and Notre Dame), Alt+L
  on a game lists where to hear it: each team's radio, then SiriusXM, NFL+, NBA League Pass, the Varsity Network
  and others. Each opens in your browser, and you sign in there if it asks. It's in a league's scores list,
  Live Scores and game details, in Team Hub as Listen on the Radio, and each of those leagues ends with Game Radio,
  every team and its station.
- The listen feature in Sports Scores is intended to give you likely options to stream a game. Direct linking to
  the audio stream or in some cases a game-specific page is not supported at this time.

**Monitoring**
- Live Scores has a Monitoring section at the top. Alt+M adds a game to it, from Live Scores or from today's
  games in a league, and Alt+M on a monitored game takes it off. Score changes are no longer spoken
  automatically.

**New sports**
- **Racing:** Formula 1, IndyCar and NASCAR Cup, from Racing on the home list. Each series has the race (entry
  list, running order or results), the schedule with winners, standings and news; Formula 1 also has its
  sessions, and drivers' and constructors' standings.
- **CFL:** from CFL on the home list. Scores by week, East and West standings, teams and each team's season.

**Football**
- **Go to Season** (Ctrl+G) opens any NFL season back to 2001 or college season back to 2005, with ESPN's own
  week names: Wild Card, Divisional Round, Super Bowl, Bowls. Ctrl+G, Home, Enter comes back to this week.
- **Drives** credit a return touchdown to the team that scored, and give the points actually scored, such as
  "TD 6pts" when there's no extra point.
- **Bowls & Playoffs:** each heading is a row you land on, with a count. The playoff's first round has its own
  heading, and the list is named.

**Games and teams**
- **NHL:** during play, a live game's details have an On the ice row; Enter lists each team's players.
- **MLB:** a game's details have its win probability (by inning, every play and the biggest swings) and the
  season series between the two teams.
- **Team Hub** has a Stats tab (Alt+A): the team's own leaders, or where it ranks in the league. An unbeaten
  team's record shows.
- **Favorite team cards** on Home read the team's schedule: last night's result, the next game, and the score
  and situation while it's playing.

**Stats, polls and leaders**
- **Definitions** (Alt+D in Statistics) are ESPN's own, and each is the right one: a pitcher's Strikeouts is the
  pitcher's.
- **Polls:** every college football poll ESPN publishes, and each cell names its team.
- **Soccer leaders** open in about a second instead of seven or eight. Liga MX follows the torneo being played,
  and switches to the Clausura in January.

**Golf, teams and transactions**
- **Golf:** in Schedule, Enter on any tournament this season opens its leaderboard, and there's a News tab.
- **Teams** come from ESPN's team list, so none go missing in the off-season. College hockey and college
  basketball list Division I.
- **Transactions** is one list, newest first, that keeps loading older ones back to 2001, with Go to Month
  (Ctrl+G). Soccer transfers read as sentences instead of blank rows.

**Fixed**
- Every menu the app builds is announced as it opens, on its first item, instead of waiting for an arrow key.
- Live Scores headings say how many games they hold, as the iPhone's do: "Live games, 5", "NHL, 3".
- Closing a dialog no longer leaves its text behind. JAWS used to say a closed dialog's instruction line again
  every time you came back to the window or went back a screen, for example "Press Enter or double-click a
  headline to open in your browser". 1.1.1 did this too.
- Screen readers no longer read out decoration: the dashes and equals signs around section rows such as
  "News Headlines", and symbols such as stars and emoji. Section rows and headings are bold instead, and symbols
  that meant something are words: "Game story:", "Scoring play:", "(up 3)", "Remove from Favorites".
- Enter on an upcoming or finished game in Live Scores opens it.
- Pitch audio: Alt+S on an at-bat plays its pitches, a new Alt+S replaces one still playing, and closing the
  plays stops it.
- Injury Report cells read the player, the column and the value.
- NHL expanded standings read each value under its own heading.

### iPhone

- **Listen to the Game:** a VoiceOver action and press-and-hold item on games in Scores and Live Scores, a menu on a game's details, a radio button in Team Hub, and Game Radio in The Bench. Each place opens in Safari or its own app. The listen feature in Sports Scores is intended to give you likely options to stream a game. Direct linking to the audio stream or in some cases a game-specific page is not supported at this time.
- **Monitoring:** a Monitoring section at the top of Live Scores. Use the Monitor action on a game to add it, and Stop Monitoring to take it off. Nothing is spoken when a score changes.
- **Bowls & Playoffs:** every bowl and playoff game in one list, from a button on College Football's Scores tab, by round.
- **NHL On the Ice:** a live game's Info tab shows who is on the ice for each team, with an Update button.
- **Golf:** the schedule says who won each tournament, and a tournament in progress stays on Live Scores if a refresh fails.
- **Transactions:** one list, newest first, that loads older ones as you go, with Jump to Month. Soccer transfers read as sentences.
- **Polls:** every college football poll, chosen from a Poll menu.
- **Your Default view setting** now applies to every table screen.
- **VoiceOver no longer reads emoji names** in Live Scores headings, such as the golf flag and each sport's icon.
- **Fixed:** Formula 1 loads during a race weekend; a pitcher's Strikeouts, NFL interceptions and punt returns have the right definitions; a wild card row's Full List says its Record; and MLB win probability rounds correctly and doesn't give away later results.

### Windows known issues

- On long lists, screen readers can give the wrong item count, because the list only reports the rows on screen.
  Table view gives the true row and total. This is a bug in Qt 6, fixed in Qt 6.13:
  [QTBUG-149577](https://qt-project.atlassian.net/browse/QTBUG-149577).
- JAWS reads each tab twice as you arrow along tabs.
- A football game's Drives aren't announced as a real tree: expanded and collapsed aren't said, and drives
  inside a quarter don't read a level.

---

**Platforms:** Windows 10 or later; iPhone through TestFlight
