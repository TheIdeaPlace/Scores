# Changelog

All notable changes to the Scores application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Listen to the game.** For the NFL, NBA, NHL, and college football and basketball (the SEC, Big Ten,
  ACC, Big 12 and Notre Dame), Scores lists where to hear a game: each team's radio and the services that
  carry every game, such as SiriusXM. Each opens in your browser, or on the iPhone in the service's app;
  you sign in there if it asks.
  - Windows: Alt+L on a game in the scores list or Live Scores, or **Listen to the Game** in its
    context menu. Game details have a Listen row and button, Team Hub has **Listen on the Radio**, and each
    of these leagues' lists ends with **Game Radio**, every team and its station.
  - iPhone: a **Listen to the Game** VoiceOver action and context menu item on every game in Scores and
    Live Scores, a Listen to the Game menu on a game's details, a radio button in Team Hub, and
    **Game Radio** in The Bench.
  - Both apps read the same list, `radio_links.json`, and the nightly data check opens every link in it.

### Changed
- **Windows: monitoring is a section at the top of Live Scores.** Alt+M on a game adds it to Monitoring,
  where its row reads as it does below with the sport after it, and the game stays in its own section too.
  Alt+M also works on today's games on a sport's page. Alt+M on a Monitoring row takes it off and moves you
  to the next one. Monitoring lasts until you quit. Scores no longer reads out score changes on its own.
  The iPhone is to follow (#185).

### Fixed
- **Windows: Live Scores no longer reads the row you're on again when other games come and go.** Each
  time a game kicked off or finished, the list was rebuilt and the row you were on read out, so on a busy
  day a finished game you were resting on was read once a minute.
- **Windows: Enter on an upcoming or finished game in Live Scores opens it.** It did nothing before.
- **Windows: a context menu is announced as soon as it opens.** Shift+F10, the Applications key and
  Alt+L used to open a menu that JAWS and NVDA said nothing about until an arrow key was pressed. The app's own menus (a
  game's options, Listen to the Game, play and pitch audio, the Pitch Explorer's) now open on their
  first item. The standard Cut, Copy and Paste menu in a text field is still silent until an arrow key.

### In Progress
- **Game Wrap Up Feature**: ESPN text processing and game story extraction (under construction)
  - Core infrastructure implemented, text processing being refined
  - Game story text placeholders currently under investigation

## [1.1.1] - 2026-11-05

### Added
- **Soccer leagues on Windows have Standings, Statistics and Teams.** Standings read position, games
  played, wins, draws, losses, goals for and against, goal difference, points, and where a place leads,
  such as Champions League or Relegation. MLS has a tab for each conference. The Champions League and
  Europa League show their league phase. The CONCACAF Champions Cup is all knockout, so its Standings say
  it has no table, and its Teams still lists the teams.
- **Soccer leaders on Windows, from the same place as the iPhone.** Goals, assists, shots, cards, fouls,
  passes and saves, up to 20 players each, and they say which season they're from.
- **iPhone: weather on a game's details,** for the games ESPN has it: "Weather: 67°F".
- **iPhone: attendance on a game's details,** once there's a count: "Attendance: 68,739".
- **iPhone: standings in a game's Info tab,** the tables of the division or conference each team is in.
- **iPhone: a Game Story in a finished game's Info tab.** The row names the headline, and opens the
  whole story with a heading or paragraph to a swipe. Before the game, ESPN's preview leads the news list.
- **iPhone: a Scoring Summary in a football game's Info tab,** by quarter, with the team, clock and play.
- **iPhone: an injury's type, details and return date,** where ESPN gives them.
- **The iPhone has Venues, with the same list as Windows.** Each of the ten leagues Windows offers it
  for has a Venues tab, listing the stadiums and arenas with their city and state, indoor or outdoor
  where ESPN says, and their home teams. Selecting one shows its details. Both apps work out the list
  the same way, from the same months of games, so neutral sites, one-offs, preseason games and visits
  to non-Division I hosts aren't anyone's home on either. It has the three view modes, and if ESPN
  doesn't answer it says so, with a Retry button.
- **College hockey polls on iPhone.** Men's and women's college hockey now have the Polls tab, as they
  do on Windows.

### Changed
- **Soccer on iPhone shows what Windows shows.** Standings read position, games played, wins, draws,
  losses, goals, goal difference, points and where a place leads, in all three views, rather than
  baseball's win percentage and games back, with no draws or points. MLS is in rank order. A competition
  with no table says so.
- **Soccer leaders on iPhone match too.** Goals and Assists are listed once rather than twice. Players
  level on a number share a rank. View All has up to 20 players, not 50, and the list says which season
  it's from.
- **The college football setting is called Coverage.** It's "College football coverage" on Windows and in
  the iPhone's Scores filter, and "Coverage" under College Football in iPhone Settings, since it also
  decides the standings and teams you see. Your choice is kept.
- **A team with no news on iPhone says so,** as on Windows, rather than showing the league's stories under
  the team's name. NBA standings on Windows read the season ESPN calls current, as on iPhone.
- **VoiceOver reads the View All link on Stats once.**
- **iPhone: betting lines look in the same place first as Windows,** `odds` and then `pickcenter`, and
  pass over an empty line. An over/under of 0 isn't read.
- **iPhone: coming back to a game no longer reloads the screen.** It used to show the spinner, and lose
  VoiceOver's place, each time. It now refreshes quietly, and a failed refresh leaves what's showing.
- **A football game's wrap up on Windows names its quarters,** as on iPhone: Quarter 1 and OT, not Period 1.
- **Attendance sent as text can't lose a game's details on Windows.**

### Fixed
- **A poll with no points no longer reads as 0 points on iPhone.** Windows already left them blank.
- **A dialog with tabs or a list can't end the app as it's cleaned up.** Tests caught this, once in many
  runs, and it hasn't been seen in the app.
- **College basketball fouls read and sound where they happened, on Windows and iPhone.** A foul under
  the basket read "deep, 78 feet out", with a far away note on the wrong side, because ESPN's college
  feed mirrors most fouls to the far end. It now reads "at the rim", and pans the same way as the shot.
  Fouls already in the near half stay as they are. The NBA and WNBA were never affected.
- A request that fails now says so on every screen, in a plain sentence: "ESPN isn't providing scores right now. Try again in a minute." It used to read as "No games found" or "No news", or read out the text of a network error.
- A league's list still offers News, Standings and its other sections when only the scores failed. Enter on the failed row tries again, as does Refresh.
- A refresh that fails keeps what's showing, and says so once if you asked for it. Refreshes on the timer in Live Scores stay quiet, unless a game you're monitoring is affected, and then only the first time.
- In Live Scores, a league that fails keeps the games it last showed, with a row at the end naming it, and "Last updated" isn't changed by a refresh that got nothing.
- Opening a World Cup no longer says "Something went wrong" once its first phase is over.
- iPhone: Live Scores and Live Soccer say a failed request failed, with Retry, instead of "No games scheduled today". A league that fails keeps its games, and a note under the list names it.
- iPhone: failed requests use the same words as Windows. A pull to refresh that fails keeps News, Polls and Standings on the screen, and VoiceOver says so.
- In Live Scores, the row saying a league failed comes and goes without rereading the row you're on.
- A body from ESPN that's null or not what it should be says the request failed, rather than reading as no data. EPL standings with a null body no longer say there's no league table.
- One unreadable field no longer costs a screen its data: a transaction page with no page count keeps its rows, and a World Cup stat with no value keeps every group.
- One article that can't be cleaned keeps its own description, rather than costing a team's whole news tab.
- A draft with no list of picks isn't kept as an empty one, and leaders or team statistics with a null body don't step back to last season. A null team page or fantasy board says it failed too.
- iPhone: a league that keeps failing no longer leaves last night's games on Live Scores as live. They go when the day does, as on Windows.
- iPhone: Live Soccer asks for today's scoreboard, as Live Scores and Windows do. With no date ESPN can answer with a match days away.
- iPhone: Retry stays on the screen while it runs, and VoiceOver says "Retrying", then the error if it failed again.
- In Transactions, a team list that fails says so once, and F5 asks for it again and says when it worked.
- In a World Cup, an answer for a day you've moved on from no longer lands on the day you're on.
- Live Scores says "Not updated yet" until something has loaded, rather than a time.
- iPhone: a timer refresh on Live Scores or Live Soccer leaves an error or "No games scheduled today" on screen until it has something else to show, so VoiceOver stays on Retry. Retry itself shows progress.

## [1.1.0] - 2026-11-04

### Changed
- **Both apps read league leaders from the same place, with the same rules.** They could name
  different players for the same stat, because the iPhone read a feed with no qualifying minimums. It
  now reads the one Windows does, with the same ranks, so two players level both read 1st, and it says
  which season the numbers are from. Lists have up to 20 players on both apps. Soccer stays as it was,
  since ESPN has no such feed for it.
- **A team's Stats on iPhone lists that team's own players, ranked within the team.** It used to be
  whichever of them made the league's top 100, with their rank in the league. A team with nobody that
  high had nothing to show. Qualified players come first and then the rest, and the screen says so.
- **MLB leaders on Windows open in about 2 seconds, not 30.** They came from MLB's own feed, in a
  different order each time. They now come from the same place as every other league, on both apps, in
  a fixed order. There are 19 categories rather than 39. New ones include WAR and quality starts. Gone
  are doubles, triples, walks, innings pitched, complete games, shutouts, blown saves, fielding and
  some others.
- **The NFL Draft on Windows opens much faster.** It made a request or more for every pick, and now
  makes one for the whole draft, the same one as the iPhone. A team now reads as it was named that
  year, such as the Oakland Raiders in 2012. Focus stays where you are as you arrow through the rounds
  or the years, rather than jumping to the picks as each loads.
- **Colleges in the draft read in full on both apps,** such as Georgia State, not Georgia St.
- **Older drafts name their centers and kickers on both apps.** ESPN's list for those years left them
  out, so the iPhone showed no position for them.
- **Hockey games on Windows open with one less download.** Each one also fetched espn.com's web page for
  more plays, which has stopped giving any. The plays come from where the iPhone's do.
- **News lists are the same length on both apps,** up to 25 stories.

### Fixed
- **Player and Team Statistics are a list, and Enter opens the rankings.** The list no longer sits
  beside the results. Press Enter on a statistic to open its rankings in the list's place, and Escape
  or the Back button to come back to the same statistic. Ctrl+Tab goes on to the next one, the window
  title names what's open, and a statistic with nothing to rank says so. With a mouse, double-click a
  statistic to open it.
- **Player and Team Statistics results are a real table.** Alt+V, Alt+T, Alt+Q and Alt+F now work on
  them, as they do on every other table, and they open in your saved view. Player statistics have
  Rank, Player, Team and Value, and team statistics Rank, Team and Value. A row used to be one line
  of text, such as "1 Luka Doncic (LAL) 38.3". On any cell a screen reader now hears whose row it
  is: "Luka Doncic, Value, 38.3". Players level on a number now share a rank, as teams do: two
  players on 7.5 sacks are both 1st, where one used to read 1st and the other 2nd.
- **Switching a table's view stays on your row.** The new view could report the row it was last left
  on before moving to yours, so a screen reader might read the wrong row first.
- **A game's Leaders opens on Windows.** It showed only an error message, which a screen reader may
  not have read, for any game with leaders. Each team now has a tab with a table, in all three views,
  and focus lands on its first row. If the table ever can't be built, a row you can arrow to says so
  in a plain sentence.
- **Tab bars work from the keyboard the way Windows lists do, everywhere there are tabs.** Home and
  End go to the first and last tab, and Left and Right go round past the ends rather than stopping.
  With focus on the tabs, type a conference's first letter to go to it, and the same letter again
  goes on to the next one starting with it. Different letters typed quickly narrow it down, so S, U,
  N reaches Sun Belt. How quick is twice your Windows double-click time, about a second unless you've
  changed it. Letters typed in a table on a tab still go to the table.
- **Ctrl+Tab goes straight to the next tab's table.** Focus stopped on the Close button on the way, so
  a screen reader could say "Close, button" before the new table.
- **A tab keeps an ampersand in its name.** Texas A&M's tabs lost the & from their text, and Alt+M
  became a shortcut to one of them.
- **Tab from MLB's wild card tabs and the NFL Draft's rounds goes to what's on the tab, not to Close.**
- **More than eight tabs is now a list.** College football, men's and women's college basketball
  conferences in Standings and Teams, and football box scores, have a list instead of a long row of
  tabs. Press Enter on the one you want to open its table, and Escape or the Back button to come back
  to the list on the same row. Up and Down go round past the ends, Home, End and type-ahead find work
  as they do on tabs, and the window title names what's open. Eight or fewer stay as tabs.
- **The WNBA has Standings, Statistics, Teams, Transactions and Venues on Windows,** and `--wnba`,
  `--wnba-teams` and `--wnba-standings` go straight to them. The league view only had games and news.
  Its games back reads like the NBA's.
- **Team Hub shows a team's real record and standing, on Windows and iPhone.** During the WNBA
  playoffs the Lynx, 33-11 and first in the West, read 0-2 and 8th, and teams that missed the playoffs
  read 0-0. In the MLB playoffs the Dodgers read 5th in the division they won. It's now the regular
  season's record and standing, the same as Standings, in every league but soccer, whose team pages
  were already right. From the start of a college team's postseason until the next regular season,
  the record is labelled Regular Season, because Standings counts those postseason games and this
  doesn't: Michigan basketball's 2026 reads 31-3 here and 37-3 there. Favorites on Windows get the
  same record. If ESPN doesn't answer, the page says "Record not available right now" rather than
  risk showing the wrong one, and the rest of the page still loads. On iPhone, Favorites no longer
  asks ESPN for team details it never showed.
- **College hockey teams have a record in Team Hub, on both apps.** ESPN's team page had none for men's
  college hockey. "Standing: 1st", which ESPN says of every college hockey team, is gone.
- **The WNBA and college leagues tell a failure from no data in Standings and Teams on Windows.** If
  ESPN doesn't answer, or answers with an error, they say it isn't providing standings and to try
  again, rather than opening empty or listing the first 50 teams in the country. College football
  used to read that as no data, and now says the same. If ESPN answers and has none, they say
  there's no data. The window title also goes back to what it was after a standings error.
- **Stat definitions on Alt+D fit the league.** The WNBA and college basketball get the basketball
  list and college football the football one. They had a general list that included goals.
- **Screen readers no longer hear "division" for what isn't one.** Standings' tabs are "Standings",
  a Teams tab reads "Teams in Eastern Conference", and Team Hub says "1st in Western Conference" on
  both apps rather than "1st in Western Conference Division".
- **Team statistics on Windows rank the whole league, best first.** College basketball listed the
  first 50 teams of about 360, and every list ran highest to lowest, so the team with the most
  turnovers or the worst earned run average read as number one. Now the lowest comes first where
  low is good and teams level share a rank. College basketball ranks every Division I team who has
  played, and nobody else. College football ranks FBS teams only, because that's all ESPN lists. A
  list opens much faster, since it takes one request rather than one per team. The title and the
  list's name say which season it is, the same one as Player Statistics. What the opposing teams
  did is now there too, such as points allowed, and so is each team's differential.
  Windows and iPhone now use the same numbers, and ESPN doesn't give all of them this way, so
  about half of MLB's columns and a third of the NFL's are gone, with some from every other league:
  hit by pitch, caught stealing, runs created, passes defended, time of possession, plus/minus,
  game-winning goals, minutes and two-point numbers among them. If ESPN doesn't answer, the list
  says so and suggests trying again. In the first days of a new regular season, when ESPN may not
  have it yet, you get last season's list, and it says so. College hockey and soccer still have no
  team statistics, because ESPN has none.
- **Team statistics on iPhone are the whole regular season, out of season too, and say which season
  they are.** After a season ended, the WNBA listed its 8 playoff teams and MLB its 12, with playoff
  numbers. They now list all 15 and all 30, with regular season numbers, except a past college
  football season, whose numbers include the bowl games, as ESPN gives them, and which reads "2025
  Season". The Teams tab and View All name the season. College basketball keeps every Division I
  team late in the season, when ESPN's list runs past what it sends at once, and doesn't list a
  school outside Division I at any point. Teams level share a rank, and View All lists every team
  rather than the top 50. If ESPN fails in mid-season it says so rather than quietly showing last
  season's numbers.
- **A team's ranks on iPhone now match the league list.** They came from different places and
  often disagreed: a team could read 5th in assists on its page and 11th in the league. College
  teams had almost no ranks at all, because anything past 34th was hidden. Now 118th shows as
  "118th of 302", and the rank's color goes by the league's size: red no longer means anything past
  20th in a list of 300, and green is the WNBA's top quarter. An FCS team, or a past college football
  season, keeps ESPN's own rank, since the league list doesn't have those numbers. NBA teams gain
  their per game stats. A team's stats no longer fall back to its preseason or playoffs, and if the
  network fails it says so, and Retry works.
- **Venues on Windows now work for college basketball and college hockey, and name the home
  teams.** Those leagues always said "No venue data", and no league ever listed a home team. Each
  venue now says who plays there. Only a team's real homes are listed: not an arena used for a
  neutral site game, a preseason game or a one-off, and not a non-Division I school a college
  basketball team visited. If ESPN doesn't answer, it says so instead of saying there are no venues,
  and one month with a server error no longer loses the list.
- **The venue list only says what's known.** "Unknown Surface" is gone from every row, a venue
  ESPN says nothing about no longer reads "Outdoor", and a venue with no state no longer reads
  "City, Unknown".
- **Team Info shows where a team plays now, on Windows and iPhone.** ESPN's team page still had the
  Nets at Prudential Center and the Warriors at Oracle Arena. The venue now comes from the team's
  home games. Teams that had no venue at all, in college, the WNBA and soccer, now have one on both
  apps, and a World Cup team stays blank since its games are at tournament stadiums.
- **FCS teams are in college football standings and Teams, on Windows and iPhone.** You could see
  their games but not the teams: the Big Sky and 13 other conferences were missing. Standings and
  team lists now follow the "College football games shown" setting, so All Division I lists all 25
  conferences and FBS only lists the conferences you had before. With All Division I, the Sun Belt
  shows as one conference rather than East and West, because that's how ESPN answers. Changing the
  setting takes effect the next time you open them.
- **If ESPN can't give college football standings on Windows, Standings and Teams say so.** Standings
  used to list the first 50 teams in the alphabet from every division, Division III included, and
  Teams opened with nothing in it.
- **College teams past the first 50 appear in Transactions on iPhone.** The list stopped at 50, part
  way through the alphabet.
- **Utah is in the Central Division in the NHL standings on Windows.** 1.0.1 said it was, but ESPN
  spells it differently in standings than on its team page, so it stayed in a group of its own.
- **No more blank rows in Live Scores, Venue Details and the bowl list.** They were only spacing,
  and a screen reader stopped on each one to say "blank".
- **Player statistics on Windows are the regular season.** NFL and NHL leaders were preseason
  numbers shown as if they were the regular season: the NFL's passing leader read 509 yards, a
  preseason total, where the real leader has 2,246.
  The NBA and WNBA have leaders now. ERA, goals against and the like read best first rather than
  worst first, and the dialog says which season you're looking at. Lists go to 20 players, or fewer
  if that's all ESPN will give, down from 50. If ESPN won't answer at all, the
  dialog says so and suggests trying again in a minute. Between seasons you get the last regular
  season, except college football, whose last season runs through the bowl games and says "2025
  Season". College hockey and soccer say there are no leaders, since ESPN has none.
- **Team statistics on Windows say which season they're from,** if it's the same for every team,
  rather than claiming the full season. The window title has the season too.
- **League leaders on iPhone read as they should.** 38.3 points per game read 38.29, 0.9 steals
  read .900, and a plus-minus of -3 read -3.000. Half a sack and a passer rating keep their
  fractions, and a three-point percentage reads as a percentage. Windows now reads these the same.
  A player whose name won't load says "name unavailable" to VoiceOver, and a stat nobody has a
  number for, such as Player Efficiency Rating in the WNBA, is left out.
- **League leaders on iPhone are never preseason numbers.** In August, the NFL's fell through to
  the preseason with nothing to say so. Between seasons you now get last season's regular season,
  and MLB no longer shows spring training in February and March.
- **Times on Windows in summer.** Eastern and Pacific users fell through to Central, and Mountain
  users to Eastern.
- **A blank field from ESPN no longer reads out as "None"** in game details, or costs a whole list
  of games, news or a team's page.
- **Venue Details has its league lines.** A case mismatch kept them from ever appearing.
- **A football week on iPhone no longer fails to load because of one blank game.** ESPN's list for
  week 8 of college football in 2025 has an empty entry in it, which lost the whole week.
- **Team schedules on Windows have the whole football season.** The NFL and college football lists
  stopped at the regular season, so the Seahawks' 2025 had no Super Bowl. Preseason and postseason
  games are there now, and the row says what the game was: "Super Bowl LX", "SEC Championship",
  "Preseason Week 1". A bowl or Super Bowl at a neutral site reads "vs", not "@".
- **WNBA team schedules on Windows show the whole season, in any year.** They only looked a month
  either side of today, so out of season a team had no games at all, and past seasons showed nothing.
  Before a new season's schedule is out, the current season shows the last one, and the season list
  moves to say so, on Windows as on the iPhone's schedule screen. Team Hub on iPhone now does too.
- **Soccer team schedules on Windows show the season you picked.** Picking 2020 showed this season's
  games with old dates on them. A past season now shows its results, and the current one its results
  and the games to come. Finished matches read as a win, loss or tie with the score, not "FT".
- **Soccer team schedules work on iPhone.** They read "No schedule available" in every league.
- **The iPhone's team schedules match Windows.** The NBA, NHL, WNBA and college sports have their
  preseason games, and every sport's preseason and postseason games say what they were, except in
  the Table view's visible column. A game at halftime or in a delay reads as under way, and a
  postponed or canceled one says so, rather than giving its start time.
- **A tied game on iPhone no longer reads as a loss** in a team's Recent list and on its Info tab.
- **A past season on Windows that comes back empty stays empty.** College football used to show last
  year's games as if they were the season you asked for.
- **A team schedule that fails to load says so, on both apps.** Windows read "No games found", or
  left out the playoffs with no sign, when ESPN's server had a problem or a request timed out. It
  now says ESPN didn't answer, and coming back to the tab tries again. The iPhone read as no schedule
  or showed last season's games, and now says it couldn't load, with a Retry button. If games were
  already showing on iPhone they stay, with a note that they couldn't be refreshed. Leaving a screen
  mid-load on iPhone isn't counted as a failure.
- **A favorite's card on iPhone keeps its last and next games** when only part of the schedule loads.
- **A team's schedule on Windows opens somewhere useful when the season is over.** The current
  season opens on its last game, not its first preseason game. A past season still opens at its start.
- **Games in another year show the year.** On Windows, in every row. On iPhone, in Quick List and in
  what VoiceOver reads; the other views have it in the month heading. A season can cross new year.

## [1.0.1] - 2026-11-03

### Fixed
Found in a bug bash with NVDA on football, hockey and basketball.

- **Box scores work in every sport.** Football and hockey showed nothing, and basketball
  showed only the five players on the floor at the end. Every player is there now, under a
  tab named for the team and group ("Green Bay Packers Passing", "Duke Blue Devils Players"),
  with a Totals row, "Did not play" for those who sat out, and one Team Stats tab comparing
  both teams. The dialog opens in the first table. Games with no box score, such as all of
  college hockey, no longer offer one.
- **Tables are one Tab away.** Tab used to stop on an empty area where the arrow keys did
  nothing, and on the tab bar's scroll buttons. F6 moves between the tabs and the table.
  Alt+V, Alt+T, Alt+Q and Alt+F work from the tab bar. Enter works in Quick List and Full List.
  Switching views no longer repeats "Switched to..." more each time, and keeps your column.
- **College standings show the overall record.** They were showing a split, such as the
  record against ranked teams. All conferences are present, including the Sun Belt, with a
  conference record and a streak. Women's college hockey no longer reads 0-0 for everyone.
- **Standings streaks** are filled in for the NFL, NBA, NHL and college. NHL columns line up
  with their headings, teams rank by points, and Utah is in the Central Division.
- **No more invented statistics.** Some leagues showed made-up leaders ("Sample Player 1",
  years-old stars) as if real. NFL and NHL player statistics load again.
- **Schedule dates are right.** Evening games read as the next day. Today's game is
  marked as today again.
- **Game details** show betting lines, TV, officials, attendance and the number of injured
  players. A game's Standings row opens real tables. Rows no longer use internal names.
- **Period names.** Men's college basketball has halves, not quarters. Overtimes read OT, 2OT, 3OT
  in basketball and football, and shootout attempts no longer count as goals.
- **Late games stay put.** Until 5 AM, Live Scores and league views stay on last night's games,
  so a West Coast game no longer vanishes at midnight in the East.
- **Keeping your place.** Back returns to the game, date or week you came from. Monitoring
  a game survives a refresh and a visit to the game, and a score alert no longer ends in an error.
- **Enter presses the button that has focus,** everywhere. Enter on a list row no longer also
  presses a dialog's first button; opening a game from a team's schedule toggled the team as a
  favorite that way.
- **A crash in a dialog no longer closes the app.** Back from a game opened from a team's schedule
  did. An error like that is now written to `errors.log` next to the settings, and spoken.
- **The app really speaks now.** Announcements used to be a beep. The date or week is said as it
  changes and is in the window title. Live Scores no longer re-reads your row every refresh; it
  speaks only when the row's text changes.
- **Score rows** use full team names in women's college basketball and college hockey, show AP
  ranks, say "vs" at a neutral site, and don't read "0 at 0" for a delayed game that hasn't
  started. Live plays aren't cut off mid-name.
- **Team hub:** rosters read 6'5" and 325 lbs, name first, with venue and News filled in, and "next
  game" is no longer the game just played. Game Wrap Up no longer replaces names with "\1".
- **Plays and Drives** open in the tree. The same drive no longer appears twice in a live football
  game, and drive rows lost their emoji.
- **College basketball plays with no real location** no longer read "at the rim" or play a tone,
  on Windows or iOS. ESPN marks a substitution, timeout, free throw or rebound with one fixed spot
  under the basket. The NBA and WNBA use that spot for real tips and dunks, so they keep it.

### Fixed on iOS
The iOS side of the same bug bash.

- **Women's college basketball games open.** About one in five failed outright because of a single
  player with only a short name. One unreadable row or section can no longer take a whole game down.
- **Football week arrows work,** for past seasons too. So does the World Cup bracket. ESPN stopped
  accepting date ranges in September, which left only the current week and an empty bracket.
- **Box scores.** Every sport shows real columns under Essential Stats, including shooting in
  basketball, and team stats fill in. Tabs have names ("Players", "Defense", "Kick Returns"), and
  there's no tab for an empty group. Tables have a Totals row wherever ESPN sends one, which is every
  sport but hockey, and say "Did not play". College hockey says "Box score not available" instead of nine blank tabs.
- **Before a game,** the team table says it holds season stats. Postponed and delayed games no
  longer read 0 to 0.
- **Standings load in college football and men's college hockey,** which failed outright, and in
  women's college hockey, which was empty. College football shows real losses and percentages. The
  NHL has one group per division, including Utah, ranks by points and shows overtime losses. The
  Knicks are back in the Atlantic. Nobody reads "Rank: 0".
- **Late games stay put.** Until 5 AM, Live Scores, Soccer Live and the league screens stay on last
  night's games.
- **Game details and rows** show betting lines, TV on games opened from a schedule, AP ranks, and
  "vs" at a neutral site. A game with no set time says "Time TBD" on the right day.
- **Plays and drives.** A live football drive no longer appears twice. Overtimes read OT, 2OT.
  Shootouts don't show a false score, and "scoring" no longer counts missed college shots.
- **Team hub.** Overall records appear for the NFL, and NHL records include overtime losses. "Next"
  is never a game already played. The Field Tour button only appears for a park the app has.

### Known issues
- College basketball fouls read and sound as if they happened at the far end of the court, on
  Windows and iOS: a foul under the basket can read "deep, 66 feet out". See #123.

## [1.0.0] - 2026-10-29

### Added
- **Hear where a basketball or hockey play happened.** Alt+P on a play in the
  play-by-play plays a tone for where it was: the note says how far from the
  basket or the goal, and the stereo position says where across the court or the
  ice. Alt+S walks a whole period, Shift+F10 offers the same as a menu, and a
  Play Audio button does it with the mouse. Basketball (NBA, WNBA, NCAAM,
  NCAAWB) and hockey (NHL, NCAAH, NCAAWH); football and soccer plays carry no
  coordinates, so they have no audio.
  - Every play reads its location as part of its entry — "from three, left
    side", "near end, in the slot" — and each period heading says how many of
    its plays can be heard. Nothing is spoken over the tone itself.
  - Hockey sides are as seen facing the goal at that end, so mirror-image shots
    at the two ends do not sound alike.
  - Not every play has a location. Substitutions, timeouts, free throws and most
    face-offs arrive without one, so about a third of basketball plays and one
    in twenty hockey plays stay silent and say so.
- **iPhone: the same play audio**, as the "Play location" and "Play locations"
  VoiceOver actions on a play and on a period heading, or by tapping a play.

### Fixed
- **The MLB Pitch Audio button never appeared.** It was shown only when the
  sport was `baseball`, but the check it was given returns league keys like
  `MLB`, so the button was hidden on every game. Alt+P on a pitch had always
  worked; the button now shows with it.

### Changed
- **Moved to the TheIdeaPlace/Scores repository**, including the in-app updater,
  the installer and the docs.
- Dependency updates: pytz, the PyQt group and the Python group.

## [0.9.9.1] - 2026-10-10

A Windows-only update; the iPhone app stays at 0.9.9.

### Added
- **Windows: live games in a single sport's scores now show the current play,**
  as Live Scores does. Football shows the last play, clock, possession and down
  and distance; baseball shows runners, count, outs, batter and last play;
  other sports show the latest play. Before, the In Progress section showed only
  the score and clock.

### Fixed
- **Windows: NFL and college football live scores ran minutes behind** in a
  sport's own scores list, because ESPN's week-by-week scoreboard lags its
  daily one. Live games in a football week now come from today's scoreboard.
- **Windows: a live football game's clock was read twice** in Live Scores.
- **Windows: Live Scores read some scores backwards.** "Colts at Commanders -
  13-30" gave the home score first after an away-first name; scores now follow
  the team order. Games without a play no longer read their status twice.
- **Windows: F5 in a sport's scores list jumped back to the top.** It now stays
  on the game you were on.
- Updated Python dependencies, including urllib3 2.8.0.

## [0.9.9] - 2026-10-03

The first release of the Windows and iOS apps together: one version, one tag.

### Fixed
- **Windows: game details, Polls, Teams, Venues and Bowls & Playoffs froze the
  window while they downloaded.** All now load in the background. Opening a
  team's schedule from a game, and the `--<sport>-teams` / `--<sport>-standings`
  startup actions, do too.
- **Windows: pitch sounds blocked the keyboard while they played.** They now
  play on their own thread, in order.
- **Windows: a second update attempt failed with "Permission denied"** when the
  first attempt's installer was still open. Scores now says the installer is
  already open.
- **Windows: changing the TeamHub season or World Cup phase quickly** could show
  results for the one just left.
- **Windows: Game Wrap Up fetched a college football game** whatever the sport.
- **iOS: golf totals left out the round in progress**, and tied golfers showed
  as 1 and 2 instead of T1.

### Changed
- **A `v*` tag now releases both apps.** The iOS app takes its version from
  `VERSION` and uploads to TestFlight from the same tag as the Windows release,
  with the commit count as its build number.

## [0.9.8] - 2026-10-03

### Changed
- **Scores are grouped by game status.** A league's scores list showed games in
  ESPN's kickoff order, which on a college football Saturday mixed finals, live
  games and evening kickoffs. Games are now grouped as on iOS: In Progress
  (suspended games included), Upcoming, Completed, then Postponed / Cancelled.
  Each group opens with a header row giving its count ("Upcoming, 42 games").
  The arrow keys stop on the headers, and activating one does nothing.
- **Live Scores loads the way the iOS app does.** It made about 85 requests on a
  busy Saturday: every scoreboard twice, plus a full summary per live game for
  its latest play. It now makes one request per league for today, all at once,
  and reads the latest play from the scoreboard. About 5 seconds instead of more
  than a minute.
- **Golf in Live Scores** has its own section at the top, as on iOS: each
  tournament in progress with its round and top three, ties shown as T1. Enter
  opens the tour's leaderboard.

### Fixed
- **Live Scores - All Sports froze and never recovered on a busy day.** It loaded
  on the UI thread, and the refresh started the next load as soon as one
  finished. It now loads in the background, skips a refresh while one is
  running, and keeps your place in the list.
- **Golf tournaments in Live Scores read "Unknown at Unknown".**
- **Golf scores were wrong for golfers partway through a round.** ESPN's total
  leaves out the round in progress, so +1, -4 and -8 through 12 holes showed -3
  instead of -11. Totals are now added up from the round scores, in Live Scores
  and on the leaderboard. CUT, WD and DQ are unchanged.
- **League views and Statistics froze the window while loading.** Both now load
  in the background behind a "Loading..." row.
- **Crashes when leaving or reopening a screen mid-load** (Standings, Wild Card
  tabs, fantasy cheatsheet, favorite team cards).
- **ESPN requests had no timeout**, so one stalled response could hang the app.
  Every request now gives up after 15 seconds.

## [0.9.7] - 2026-09-27

### Fixed
- **NFL and college football showed "No games found" for every week.** ESPN's
  scoreboard stopped accepting a date range (`dates=YYYYMMDD-YYYYMMDD`) and now
  answers one with an error, for every sport. Football weeks were fetched by the
  week's date range, so every week, current or not, came back empty. Weeks are
  now requested by week number, season type and season year, which ESPN still
  honours, and preseason, postseason and bowl weeks all load again.
- **Team schedules for WNBA, college basketball and soccer, and the venue
  list,** used the same kind of date range and came back empty too. They now
  ask for one month at a time.

## [0.9.6] - 2026-09-20

### Fixed
- **NHL and the other winter sports were stuck on last season.** Team schedules
  asked ESPN for season 2026 — the 2025-26 season — because the season year was
  hardcoded rather than worked out from the date, so in September 2026 the NHL
  schedule showed the season that had already finished. The season year is now
  derived per sport: the winter sports (NHL, NBA, NCAA basketball and hockey)
  use the year their season ends in and roll over in July, once the previous
  season is done and the new schedule has been published; football stays on the
  previous year through January and February. The season picker follows, so it
  now leads with "2026-27 Season" instead of topping out at 2025-26, and NBA
  standings track the current season instead of the one frozen into the URL.

## [0.9.5] - 2026-09-01

### Added
- **MLB wild card standings.** The standings view could only show divisions, so
  the playoff race — the thing most people are actually tracking in September —
  was not visible anywhere. Two tabs, "AL Wild Card" and "NL Wild Card", now sit
  beside the six division tabs. Each shows its league's three division leaders
  followed by the 12-team wild card race, with the teams holding the three
  berths marked "Wild card 1/2/3" in a Status column rather than separated by a
  drawn line, so a screen reader speaks the playoff cut instead of relying on a
  visual boundary nobody can hear. The tabs load the first time they are opened,
  so the divisions view is never held up by the extra request.

  The data comes from ESPN's standings endpoint the app already calls, with
  `type=1`, which returns the wild card table directly. Division leaders are the
  three teams it omits. ESPN's published seed is used rather than a
  win-percentage sort, so teams tied on record land in a deterministic, official
  order — four pairs are tied as of this writing.

### Fixed
- **College football was missing most of the games played.** ESPN serves the two
  Division I halves separately through its `groups=` scoreboard parameter, and
  the app asked only for FBS (`groups=80`). That is a small fraction of an
  opening weekend, which is largely FCS: on Saturday 29 August the scoreboard
  showed 8 games out of the 48 Division I games actually played. Coverage is now
  a setting on the home page settings dialog — **All Division I (FBS and FCS)**,
  the new default at around 200 games a week, or **FBS only** at around 100.
  A team's own schedule always uses the widest coverage, since it is filtered
  down to that team anyway and FBS-only returned nothing at all for an FCS team.

  Requests also send `limit=400`. ESPN doubles that internally on undated
  queries and collapses the page to 25 games past an effective 1000, so a larger
  limit is worse than none; 400 clears a full Division I week either way.
  A week-indexed postseason query returns nothing at all under `groups=90`, so
  an empty college football response is retried as FBS — without that, the Bowls
  and Playoffs view came back empty.

- **College basketball was missing most of the games played**, the same ESPN
  `groups=` omission and proportionally worse. A Saturday in January returned 21
  of 145 men's Division I games and 4 of 122 women's. Both now ask for Division I
  explicitly. Basketball needs no coverage setting the way football does — ESPN
  has no FBS/FCS-style split below Division I for it — and college hockey needs
  no change at all, since `groups=` returns nothing there and the plain call is
  already complete.

- **College basketball team schedules were nearly empty.** They fell through to
  a 60-day scoreboard range that returned nothing without a division filter and,
  once one was added, stopped at the page limit — 400 games covering 12 days of
  the 61 requested. They now use the dedicated per-team endpoint, like every
  other league.

## [0.9.4] - 2026-08-13

### Fixed
- **Fantasy cheatsheet: the Rank column skipped numbers.** It showed ESPN's
  published rank, which orders a far larger pool than a fantasy board — roughly
  1,750 defensive players, 51 punters and the 32 "Team QB" slots. Sorted by
  rank, the board ran 1 to 2565 with 1,539 gaps in it, jumping 36 to 69 near the
  top and 519 to 978 further down. The column now counts the board itself: 1, 2,
  3 with nothing missing, in exactly the order ESPN puts them. ESPN's own number
  is still shown on the player details screen and in the CSV export, for anyone
  cross-referencing their site.

## [0.9.3] - 2026-08-10

### Fixed
- **Fantasy cheatsheet: the board was missing two-thirds of the players ESPN
  ranks.** The pool was capped at ESPN's overall draft rank, on the assumption
  that rank tracked draft relevance. It does not — Ricky Pearsall ranks 1507 and
  is rostered in a third of ESPN leagues, Tyreek Hill ranks 1899 — so the cap
  was hiding players people actually draft. The board now carries every active
  fantasy-position player ESPN publishes a rank for: 1,026 rather than 368.
  Players ESPN ranks nowhere, and players it flags as inactive, are still left
  out; every one of those is owned in 0.0% of leagues.
- **Fantasy cheatsheet: ADP no longer invents a draft position.** ESPN gives
  undrafted players a placeholder ADP just past the end of a real draft rather
  than omitting it — around 170 this season, shared by 826 of the 1,026 players.
  It read as a genuine draft slot, and because the placeholder is jittered in
  the third decimal it also broke the ADP sort: rows all displaying "170.0"
  ordered by invisible digits, putting deep camp bodies above real starters.
  Those players now show ADP as N/A and sort to the bottom by rank.
- **Fantasy cheatsheet: free agents are reachable.** The team filter gained a
  *Free Agents* entry — 212 players, including Tyreek Hill and Keenan Allen,
  previously findable only by accident.
- **Fantasy cheatsheet: filter controls are debounced** and the dialog is
  released when closed, so repeatedly opening the board no longer grows memory.

## [0.9.2] - 2026-08-09

### Added
- **Fantasy cheatsheet: rookie filters.** The position filter gains *Rookies*
  plus *Rookie QB / RB / WR / TE*. Rookies are identified from the fantasy feed
  itself — a player with no stat line from any earlier season — which also
  catches undrafted rookies that a draft-list lookup would miss.
- **Fantasy cheatsheet: export to CSV.** *Export to CSV* saves the whole board,
  not just what the filters currently show: both rank boards, player, position,
  team, rookie flag, injury, ADP, auction value, projected points in all three
  scoring formats, and whether you have marked the player drafted.

## [0.9.1] - 2026-08-09

### Added
- **Fantasy football cheatsheet**: a draft board on the NFL screen with every
  draftable player plus all 32 team defenses — ESPN consensus rank, average draft
  position, auction value and projected season points. Search by player or team,
  filter by position (including FLEX) or team, sort by any column, and switch
  between Standard, Half-PPR and PPR scoring without a refetch. Space marks a
  player drafted, *Hide drafted players* clears them off the board, and both the
  drafted set and the scoring format persist between sessions. Kickers and team
  defenses show no projection: ESPN's published numbers for those two positions
  are unusable, so the board shows N/A rather than a wrong number.

### Fixed
- **NFL preseason games and weeks now appear.** The NFL screen only ever showed
  regular-season weeks, so during August it opened on the September opener
  labelled "Week: 1" and there was no way to reach the preseason at all. Weeks
  are now resolved from ESPN's season calendar and carry their season type, the
  Previous/Next Week buttons roll over between preseason, regular season and
  postseason, and weeks are named as ESPN names them — "Hall of Fame Weekend",
  "Preseason Week 1", "Wild Card" — instead of a bare, ambiguous week number.
- **Football weeks no longer include the next week's games.** ESPN marks the end
  of a week at 23:59 Pacific, which reads as the following day in UTC; the extra
  day pulled the next week's Thursday games into the current week. Affected the
  regular season too, and was most visible in the preseason.

## [0.9.0] - 2026-08-05

### Added
- **Windows installer**: `Scores-<version>-Setup.exe`, a per-user install into
  `%LocalAppData%\Programs\Scores` that needs no administrator rights and adds a
  Start Menu shortcut (desktop shortcut optional). Built with Inno Setup from
  `installer/scores.iss`.
- **Automatic updates**: Scores checks GitHub for a newer release at startup and
  can download and install it for you; *Check for Updates* on the home page runs
  the same check on demand. The startup check can be turned off in Settings.
  Portable copies update too — the installer relocates them.
- **Code signing**: releases are Authenticode-signed with Azure Artifact Signing
  via GitHub OIDC, so downloads no longer trip SmartScreen.
- `build.py` builds both distributables (one-dir installer input plus the portable
  one-file exe) and is what CI runs.
- `docs/INSTALLER.md` documents the installer, the updater and the signing setup.

### Changed
- The application version now lives in `version.py`, and the release workflow
  refuses to build a `v*` tag that disagrees with it or with the VERSION file.

## [0.65.0] - 2025-12-14

### Added
- **NCAA Hockey Support**: Complete Men's and Women's Hockey coverage
  - NCAA Men's Hockey (NCAAH): 50 teams across 10+ conferences
  - NCAA Women's Hockey (NCAAWH): 44 teams with conference standings
  - Live games, scores, and play-by-play details
  - Full team listings with schedule navigation
  - Conference-based standings (Hockey East, Big Ten, ECAC, NCHC, CCHA, CHA, Atlantic Hockey America, etc.)
  - Hockey-specific record format handling (W-L-T)

- **Polls & Rankings Feature**: Official poll tracking for all NCAA sports
  - NCAA Football: CFP Rankings, CFP Seedings, AP Poll, Coaches Poll (4 polls)
  - NCAA Men's Basketball: AP Poll, Coaches Poll (2 polls)
  - NCAA Women's Basketball: AP Poll, Coaches Poll (2 polls)
  - NCAA Men's Hockey: USA Hockey Poll, USCHO Poll (2 polls)
  - NCAA Women's Hockey: USA Hockey Poll, USCHO Poll (2 polls)
  - Multi-tab interface for sports with multiple polls
  - Rank change indicators (↑/↓) showing movement from previous week
  - Displays rank, team, record, points, and previous rank
  - Accessible table format with keyboard navigation (Ctrl+Tab between polls)

### Changed
- **Enhanced League Name Display**: All league abbreviations now display with full, descriptive names
  - Main league selection screen shows complete sport names with gender designation
  - Live scores section headers use formatted league names
  - Window titles display full sport names in breadcrumb navigation
  - Applied to: NCAA Women's Hockey, NCAA Men's Hockey, NCAA Women's Basketball, NCAA Men's Basketball, NCAA Football

### Technical
- Added `get_rankings()` API endpoint integration for poll data
- Created `PollsDialog` component with multi-tab support
- Implemented hockey conference structure parsing
- Added `format_league_name()` utility function for consistent name formatting
- Internal API calls maintain efficient abbreviation codes for performance

## [0.55.0] - 2025-08-31

### 🚀 BREAKTHROUGH ACCESSIBILITY FEATURES
- **Dynamic Window Titles for Screen Readers**: **FIRST-IN-CLASS** window title management system
  - **Contextual Titles**: Window titles dynamically reflect user location in the application
  - **Screen Reader Optimized**: "MLB - Sports Scores", "MLB, Standings - Sports Scores", "Yankees vs Red Sox - MLB - Sports Scores"
  - **Hierarchical Navigation**: Most specific information first, following accessibility best practices
  - **Universal Coverage**: All views, dialogs, and navigation contexts included
  - **Cross-Platform**: Both desktop (PyQt6) and web (JavaScript) implementations
  - **Zero Breaking Changes**: Enhances existing functionality without disruption

- **Multiple View Modes for All Tables**: **INDUSTRY-FIRST** accessible data presentation system
  - **Three View Modes**: Table, Quick List, Full List for every tabular data display
  - **Universal Keyboard Shortcuts**: Alt+V (cycle), Alt+T (table), Alt+Q (quick), Alt+F (full)
  - **Seamless Focus Management**: Maintains position when switching between view modes
  - **Real-time Data Sync**: All views reflect live data updates immediately
  - **Universal Integration**: Automatically available for standings, statistics, leaders, box scores, injuries
  - **Screen Reader Optimized**: Proper ARIA attributes and view change announcements
  - **Zero Breaking Changes**: All existing functionality preserved and enhanced

### Added
- **Comprehensive Conference/Division Support**: Restored and expanded sports organization
  - College Football (NCAAF): Full conference tabs (SEC, Big Ten, Big 12, ACC, Pac-12, etc.)
  - College Basketball (NCAAB/NCAAM/NCAAW): Major conference support with priority ordering
  - WNBA: Eastern/Western conference organization
  - All sports now properly display natural divisions/conferences as tabs

- **Enhanced Accessibility Infrastructure**: Foundation improvements for screen reader support
  - Removed problematic view selector combo box that caused focus conflicts
  - Default expanded view for comprehensive data presentation
  - Improved Ctrl+Tab navigation between division tabs
  - Consistent keyboard navigation patterns across all table types

### Enhanced
- **Expanded Standings Feature**: Toggle between basic and expanded standings views
  - Basic View: Traditional 7-column standings (Position, Team, W, L, PCT, GB, Streak)
  - Expanded View: Sport-specific additional columns with advanced statistics
  - MLB Expanded: Runs For/Against, Run Differential, Home/Road Records, Playoff %, Magic Numbers
  - NFL Expanded: Points For/Against, Point Differential, Division Record, Playoff Seed
  - NBA Expanded: PPG, Opponent PPG, Point Differential, Division Win %, Playoff Seed
  - NHL Expanded: Points, OT Losses, Goals For/Against, Goal Differential, Playoff Seed
  - Toggle buttons in standings dialog for supported sports (MLB, NFL, NBA, NHL)

- **News Articles**: Increased news article retrieval from 6 to 20 articles per league
  - Added configurable limit parameter (max 50 articles available from ESPN)
  - Better news coverage with more comprehensive headlines
  - Maintains same user interface with enhanced content

### Fixed  
- **MLB Standings**: Fixed incorrect "American League" tab appearing alongside proper divisions
  - Corrected Chicago White Sox abbreviation mapping (CHW vs CWS)
- **Text Processing**: Enhanced ESPN news text name replacement and pattern detection
  - Now displays exactly 6 division tabs as expected

## [0.54.0-preview] - 2025-08-27

### Added
- **Venue Browsing Feature**: Complete stadium/venue exploration system
  - Browse stadiums and venues by league (NFL, MLB, NBA, NHL, NCAA Football)
  - Comprehensive venue details including capacity, surface type, location, and facts
  - Home team information for each venue
  - NCAAF venue support through proper college-football API mapping
- **Enhanced Team Navigation Infrastructure**: Robust system for navigating between games and team schedules
  - Smart team ID resolution with multiple fallback mechanisms
  - College football team mapping for major programs ensuring reliable navigation
  - Improved back navigation with context preservation
- **Automatic Timezone Conversion**: All game times converted to user's local timezone
  - ESPN timezone data processing and local time conversion
  - Cross-platform timezone handling with verification tools
- **UI Consistency Improvements**: Unified interface design across all dialogs
  - Venue details use consistent QListWidget format matching rest of application
  - Text-based indicators ([Indoor, Grass]) replacing emoji decorations
  - Clean "--- Section ---" headers for organized information display

### Changed
- **Venue Service Architecture**: New venue service with efficient API usage and smart caching
- **Code Organization**: Test and demo files properly organized in TheBench directory
- **Interface Design**: Standardized on list-based UI elements for consistency and accessibility

### Fixed
- **NCAAF Venue Access**: Added proper "ncaaf" to "college-football" league mapping
- **Case Sensitivity**: Fixed venue dialog league case sensitivity for reliable data access
- **Team Navigation**: Enhanced team ID resolution prevents navigation failures in college football

## [0.53.0-preview] - 2025-08-18

### Added
- **Statistics Feature**: Complete new statistics system for comprehensive sports analysis
  - Two-dialog interface: Choose Team/Player → Select statistic → View rankings
  - Multi-sport framework supporting MLB, NFL, NBA, NHL, NCAA Football
  - Professional-grade statistical categories with official data sources
  - Accessible design with full keyboard navigation and screen reader support
- **MLB Full Season Statistics**: Official MLB Stats API integration for baseball
  - 39 comprehensive statistical categories (vs 18 from ESPN)
  - Hitting statistics: 16 categories including advanced metrics (AVG, OPS, SB, etc.)
  - Pitching statistics: 15 categories with complete season data (ERA, Saves, etc.)
  - Fielding statistics: 8 categories for defensive analysis
  - Official MLB source with full season totals
  - Parallel loading for optimal performance (6x faster: 157ms vs 953ms)
- **Enhanced Baseball Information**: Improved game details and pitch location system
  - Pitch location validation with 85.4% strike zone accuracy
  - Enhanced game details display (venue, weather, broadcast info)
  - Better configuration options for game information fields
  - Cross-game validation with real umpire call analysis

### Fixed
- **Statistics Display**: Resolved "No player stats available for mlb" error
  - Fixed data format conversion between MLB API and UI expectations
  - Proper player name, stat value, and team information display
  - Seamless integration with existing statistics interface
- **MLB Data Quality**: Eliminated misleading limited-game statistics
  - Real season totals replacing recent performance samples
  - Complete statistical picture for informed analysis

### Changed
- **Statistics Architecture**: New comprehensive statistics system implementation
- **MLB Data Source**: ESPN API → Official MLB Stats API for baseball statistics
- **Data Coverage**: Recent games → Full season comprehensive statistics
- **Performance Optimization**: Enhanced concurrent request handling for statistics
- **User Interface**: Added Statistics menu option to all major sports

### Technical Details
- **Statistics Framework**: Scalable system ready for all major sports
- **MLB API Integration**: statsapi.mlb.com/api/v1/stats/leaders endpoints
- **No Authentication Required**: Public MLB API endpoints
- **Backward Compatibility**: All existing functionality preserved
- **Enhanced Error Handling**: Robust statistics processing and display

## [0.52.0-preview] - 2025-08-16

### Added
- **Live Scores Feature**: Real-time sports monitoring with auto-refresh capabilities
  - Multiple refresh intervals: 10s, 15s, 30s, 60s, 2min, 5min
  - Continuous background updates for live game tracking
  - Resource-efficient monitoring with pause/resume functionality
- **Scoring Drive Enhancement**: Visual identification system for football scoring plays
  - Touchdown indicators with "TD 7pts" badges
  - Field goal markers with "FG 3pts" badges  
  - Missed field goal, turnover, punt, and safety indicators
  - WCAG AA compliant color coding for accessibility
  - Enhanced drive summaries with scoring context
- **Enhanced Football Display**: Comprehensive game situation awareness
  - Hybrid format showing down/distance + drive statistics
  - Redzone indicators for teams in scoring position
  - Last play information for momentum context
  - Consistent team naming and score formatting
- **Command Line Options**: Quick access for power users
  - `--live`: Shorthand to launch Live Scores directly
  - `--live-scores`: Full command option for Live Scores mode
- **Multi-Platform Research**: Comprehensive analysis document for Mac and iOS expansion
- **Windows UIA Integration**: Enhanced accessibility with notification helpers

### Fixed
- **Score Display**: Resolved missing scores in football game listings
- **Team Naming**: Fixed inconsistent team name formatting across views
- **Navigation**: Improved startup parameter handling and validation
- **Memory Management**: Enhanced cleanup for long-running Live Scores sessions

### Changed
- **ESPN API Integration**: Enhanced data extraction for scoring drive detection
- **Performance**: Optimized real-time update processing and resource usage
- **Code Organization**: Improved project structure with comprehensive testing
- **Documentation**: Expanded guides for new features and implementation details

### Technical Details
- **NFL & NCAAF Support**: Scoring drive enhancement works with both professional and college football
- **Accessibility Compliance**: Full WCAG AA compliance for visual indicators
- **Background Processing**: Efficient real-time updates without blocking UI
- **Cross-Platform Planning**: Research completed for future Mac and iOS versions

### Build Artifacts
- `dist/Scores.exe` - Enhanced Windows executable (~43MB due to new features)
- Improved startup performance and resource management

## [0.51.0-preview] - 2025-08-15

### Added
- **Season Selection**: Enhanced team schedule dialogs with season dropdown for viewing historical data
- **Command Line Interface**: Comprehensive CLI options for direct navigation to specific sport sections
  - Game views: `--mlb`, `--nfl`, `--nba`, `--nhl`, `--ncaaf`
  - Teams views: `--mlb-teams`, `--nfl-teams`, etc.
  - Standings views: `--mlb-standings`, `--nfl-standings`, etc.
- **Accessibility Improvements**: 
  - Replaced QListWidget with AccessibleTable in teams dialogs for better screen reader support
  - Enhanced focus management in team schedule dialogs
  - Added proper accessible names and descriptions to UI components
- **Smart Navigation**: Enhanced team schedule dialogs now focus on today's games or next upcoming games
- **Visual Enhancements**: Today's games are highlighted with bold text and light yellow background

### Fixed
- **Team Name Display**: Fixed team names to show proper team nicknames instead of abbreviations
- **Date Display**: Enhanced date formatting for historical seasons to include year
- **Cache Management**: Cleaned up Python cache files from repository
- **Tab Accessibility**: Added setAccessibleName and setAccessibleDescription to all QTabWidget instances

### Changed
- **Schedule Loading**: Improved team schedule loading with background threading for better performance
- **Season Handling**: Enhanced season availability ranges for different sports leagues
- **UI Focus**: Improved focus management in schedule dialogs to highlight relevant games

### Technical Details
- **Enhanced CLI Support**: Full argument parsing with help documentation
- **Improved Data Display**: Better handling of historical vs current season data
- **Accessibility Standards**: Compliance improvements for screen reader compatibility

### Build Artifacts
- Same as 0.5.0: `dist/Scores.exe` - Standalone Windows executable
- Enhanced command line capabilities for power users

## [0.5.0-preview] - 2025-08-13

### Added
- Complete virtual environment setup with Python 3.13.6
- Comprehensive build system with PyInstaller
- Windows executable generation (standalone ~40MB)
- Enhanced build script (`build-enhanced.bat`) with error handling
- Minimal and complete requirements files
- Comprehensive build documentation (`BUILD_GUIDE.md`)
- Setup completion guide (`SETUP_COMPLETE.md`)

### Fixed
- Fixed `main.py` import issues - now works as alternative entry point
- Resolved PyQt6 6.9.1 compatibility
- Fixed dependency management with proper virtual environment isolation

### Changed
- Updated build process to use virtual environment
- Improved error handling in build scripts
- Enhanced documentation structure

### Technical Details
- **Python Version**: 3.13.6
- **GUI Framework**: PyQt6 6.9.1
- **HTTP Library**: requests 2.32.4
- **Build Tool**: PyInstaller 6.15.0
- **Target Platform**: Windows 10/11 (x64)

### Build Artifacts
- `dist/Scores.exe` - Standalone Windows executable
- `.venv/` - Isolated Python virtual environment
- `requirements.txt` - Complete dependency list
- `requirements-minimal.txt` - Essential dependencies only

### Installation
1. Download `Scores.exe` from releases
2. Run directly (no installation required)
3. For development: use virtual environment setup

### Known Issues
- Audio features require Windows sound system
- Application requires internet connection for ESPN API data
- First launch may take longer due to PyQt6 initialization

### Notes
This is a preview release focusing on build system improvements and deployment preparation. The core sports scoring functionality remains stable from previous versions.
