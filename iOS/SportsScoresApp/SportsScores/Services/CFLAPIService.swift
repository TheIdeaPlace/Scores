//
//  CFLAPIService.swift
//  SportsScores
//
//  Data client for the Canadian Football League.
//
//  ESPN does not carry live CFL game data (its `football/cfl` scoreboard is
//  frozen at the 2022 season), so CFL is sourced from the public scoreboard
//  widget feed behind cfl.ca, which is powered by Genius Sports:
//
//    https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json   — full season
//    https://cflscoreboard.cfl.ca/json/scoreboard/squads.json   — teams + records
//
//  This feed is unofficial and undocumented, so it can change without notice.
//  It provides scores, schedule, live status, and win/loss records — but no
//  play-by-play, rosters, news, or statistics. The app degrades gracefully
//  where those are unavailable.
//
//  The two JSON documents describe the entire season in one fetch each, so a
//  short in-memory cache keeps date navigation and auto-refresh cheap.
//
//  Reading them is `CFLFeed`, below, apart from the fetching so it can be tested. Windows reads
//  the same feed in cfl.py, and tests/fixtures/cfl_grid.json holds the two to the same reading
//  (CFLGridTests.swift and tests/unit/test_cfl.py): change both together.
//

import Foundation

final class CFLAPIService {
    static let shared = CFLAPIService()

    private let roundsURL = URL(string: "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json")!
    private let squadsURL = URL(string: "https://cflscoreboard.cfl.ca/json/scoreboard/squads.json")!
    private let session: URLSession

    /// Cache lifetime. Short enough that live scores update on auto-refresh,
    /// long enough that navigating between days doesn't re-fetch repeatedly.
    private let cacheTTL: TimeInterval = 25

    private var cachedFeed: CFLFeed?
    private var cacheTimestamp: Date?

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        // Always pull a fresh copy when the cache has expired rather than a
        // stale CDN-cached response.
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session = URLSession(configuration: config)
    }

    // MARK: - Public API

    /// Games taking place on the given calendar day (local time), grouped exactly
    /// like every other sport so `ScoresView` can render them unchanged.
    func fetchGames(on date: Date) async throws -> [Game] {
        try await loadFeed().games(on: date)
    }

    /// Number of games scheduled on the given day — for the home-page badge.
    func gameCount(on date: Date) async -> Int {
        (try? await fetchGames(on: date))?.count ?? 0
    }

    /// Result of loading one round (week) of the CFL season.
    struct CFLRoundResult {
        let games: [Game]
        let roundIndex: Int      // 0-based index into the season's rounds
        let label: String        // e.g. "Week 2", "Preseason Week 1", "113th Grey Cup"
        let roundCount: Int
        let isCurrentRound: Bool
    }

    /// Games for a single round. CFL navigates by round/week rather than by day,
    /// because games are spread Thursday–Sunday and most calendar days are empty.
    ///
    /// - Parameter index: the round to load, or `nil` to resolve the current round
    ///   (the one in progress, or the next upcoming one if between weeks).
    func fetchRound(index: Int?) async throws -> CFLRoundResult {
        try await loadFeed().round(index: index)
    }

    /// East / West standings built from each team's win-loss-draw record.
    func fetchStandings() async throws -> [StandingsGroup] {
        try await loadFeed().standings()
    }

    /// All teams, sorted by name — for the Team Hub team picker.
    func fetchTeams() async throws -> [TransactionTeam] {
        try await loadFeed().teams()
    }

    /// Every game a team plays this season, oldest first — for the Team Hub schedule tab.
    func fetchSchedule(teamId: String) async throws -> [ScheduleGame] {
        try await loadFeed().schedule(teamId: teamId)
    }

    /// Team Hub Info-tab summary: record, division standing, and next game.
    func fetchTeamInfo(teamId: String) async throws -> TeamHubTeamInfo {
        try await loadFeed().teamInfo(teamId: teamId)
    }

    // MARK: - Feed loading + cache

    private func loadFeed() async throws -> CFLFeed {
        if let cached = cachedFeed, let stamp = cacheTimestamp,
           Date().timeIntervalSince(stamp) < cacheTTL {
            return cached
        }

        // Both documents fetch concurrently; decode once each is in.
        async let roundsData = fetch(roundsURL)
        async let squadsData = fetch(squadsURL)
        let feed = try CFLFeed.decode(rounds: try await roundsData, squads: try await squadsData)
        cachedFeed = feed
        cacheTimestamp = Date()
        return feed
    }

    private func fetch(_ url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        // The feed only serves browser-like clients reliably.
        request.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return data
    }
}

// MARK: - Reading the feed

/// The CFL's two files read into the app's models. No fetching, so the tests can give it the
/// real fixtures. cfl.py on Windows is the other half.
struct CFLFeed {
    let rounds: [CFLRound]
    let squads: [CFLSquad]

    static func decode(rounds: Data, squads: Data) throws -> CFLFeed {
        CFLFeed(rounds: try JSONDecoder().decode([CFLRound].self, from: rounds),
                squads: try JSONDecoder().decode([CFLSquad].self, from: squads))
    }

    // MARK: Division layout (East / West)

    /// CFL division membership keyed by team abbreviation (the feed's `shortName`).
    static let eastTeams: Set<String> = ["HAM", "MTL", "OTT", "TOR"]
    static let westTeams: Set<String> = ["BC", "CGY", "EDM", "SSK", "WPG"]

    static func divisionName(for abbreviation: String) -> String {
        westTeams.contains(abbreviation) ? "West Division" : "East Division"
    }

    // MARK: Games and weeks

    func games(on date: Date, calendar: Calendar = .current) -> [Game] {
        Self.byKickoff(allTournaments()
            .filter { calendar.isDate($0.tournament.parsedDate, inSameDayAs: date) }
            .map { makeGame(from: $0.tournament, seasonType: $0.seasonType) })
    }

    func round(index: Int?, now: Date = Date()) -> CFLAPIService.CFLRoundResult {
        guard !rounds.isEmpty else {
            return CFLAPIService.CFLRoundResult(games: [], roundIndex: 0, label: "", roundCount: 0, isCurrentRound: true)
        }

        let currentIdx = currentRoundIndex(now: now)
        let idx = min(max(index ?? currentIdx, 0), rounds.count - 1)
        let round = rounds[idx]
        let seasonType = Self.seasonType(for: round.type)
        let games = Self.byKickoff(round.visibleTournaments.map { makeGame(from: $0, seasonType: seasonType) })

        return CFLAPIService.CFLRoundResult(
            games: games,
            roundIndex: idx,
            label: round.displayName(index: idx),
            roundCount: rounds.count,
            isCurrentRound: idx == currentIdx
        )
    }

    /// Index of the round considered "current": the first round that hasn't
    /// finished yet (in progress or upcoming), or the final round if the season
    /// is over.
    ///
    /// A round ends at 23:59 UTC on its last day, and games kick off as late as 23:30 UTC, so a
    /// game is still being played after its round has "ended". A round with a game under way is
    /// current, or next week would show all evening with the last game live.
    func currentRoundIndex(now: Date = Date()) -> Int {
        if let i = rounds.firstIndex(where: { round in
            (round.endDateParsed ?? .distantFuture) >= now
                || round.visibleTournaments.contains { Self.gameStatus(for: $0).state == "in" }
        }) {
            return i
        }
        return rounds.count - 1
    }

    /// Two games at the same time go by id, so both apps list them in the same order.
    private static func byKickoff(_ games: [Game]) -> [Game] {
        games.sorted { $0.date != $1.date ? $0.date < $1.date : $0.id < $1.id }
    }

    // MARK: Standings and teams

    /// East / West standings built from each team's win-loss-draw record. Teams level on win
    /// percentage and wins go by name: the feed has no tiebreakers.
    func standings() -> [StandingsGroup] {
        var buckets: [String: [StandingsEntry]] = ["East Division": [], "West Division": []]

        for squad in squads where squad.id != 0 {
            let division = Self.divisionName(for: squad.abbreviation)
            buckets[division, default: []].append(standingsEntry(from: squad))
        }

        // Order East before West; sort each by win% then wins, and assign ranks.
        return ["East Division", "West Division"].compactMap { name in
            guard var entries = buckets[name], !entries.isEmpty else { return nil }
            entries.sort {
                if $0.stats.winPercent != $1.stats.winPercent { return $0.stats.winPercent > $1.stats.winPercent }
                if $0.stats.wins != $1.stats.wins { return $0.stats.wins > $1.stats.wins }
                return $0.team.displayName < $1.team.displayName
            }
            let ranked = entries.enumerated().map { idx, entry in
                StandingsEntry(rank: idx + 1, team: entry.team, stats: entry.stats)
            }
            return StandingsGroup(name: name, entries: ranked)
        }
    }

    func teams() -> [TransactionTeam] {
        squads
            .filter { $0.id != 0 }
            .map {
                TransactionTeam(
                    id: String($0.id),
                    location: nil,
                    name: nil,
                    abbreviation: $0.abbreviation,
                    displayName: $0.name,
                    color: nil,
                    logos: nil
                )
            }
            .sorted { $0.displayName < $1.displayName }
    }

    func schedule(teamId: String) -> [ScheduleGame] {
        allTournaments()
            .filter { String($0.tournament.homeSquad.id) == teamId || String($0.tournament.awaySquad.id) == teamId }
            .map { makeScheduleGame(from: $0.tournament, seasonType: $0.seasonType) }
            .sorted { $0.date != $1.date ? $0.date < $1.date : $0.id < $1.id }
    }

    func teamInfo(teamId: String, now: Date = Date()) throws -> TeamHubTeamInfo {
        guard let squad = squads.first(where: { String($0.id) == teamId && $0.id != 0 }) else {
            throw APIError.invalidResponse
        }

        // Division rank from the computed standings.
        var standingSummary: String?
        for group in standings() {
            if let idx = group.entries.firstIndex(where: { $0.team.id == teamId }) {
                standingSummary = "\(Self.ordinal(idx + 1)) in \(group.name)"
                break
            }
        }

        // Next scheduled game.
        var nextGame: TeamHubNextGame?
        if let upcoming = schedule(teamId: teamId).first(where: { !$0.isCompleted && !$0.isInProgress && $0.date > now }) {
            let isHome = upcoming.homeTeam.id == teamId
            let opponent = isHome ? upcoming.awayTeam : upcoming.homeTeam
            nextGame = TeamHubNextGame(
                gameId: upcoming.id,
                date: upcoming.date,
                opponentDisplayName: opponent.displayName,
                opponentAbbreviation: opponent.abbreviation,
                isHome: isHome
            )
        }

        return TeamHubTeamInfo(
            teamId: teamId,
            displayName: squad.name,
            abbreviation: squad.abbreviation,
            location: squad.name,
            color: nil,
            alternateColor: nil,
            primaryLogoURL: nil,
            overallRecord: squad.recordString,
            homeRecord: nil,
            awayRecord: nil,
            standingSummary: standingSummary,
            venueName: nil,
            venueCity: nil,
            coachName: nil,
            nextGame: nextGame
        )
    }

    // MARK: Mapping helpers

    /// Maps a season-type label (PRE/REG/POST) to the ESPN season-type
    /// convention used throughout the app (1 pre / 2 regular / 3 post).
    static func seasonType(for roundType: String) -> Int {
        switch roundType {
        case "PRE":  return 1
        case "POST": return 3
        default:     return 2
        }
    }

    /// Flattened (tournament, seasonType) pairs across every round.
    func allTournaments() -> [(tournament: CFLTournament, seasonType: Int)] {
        rounds.flatMap { round in
            round.visibleTournaments.map { ($0, Self.seasonType(for: round.type)) }
        }
    }

    /// Team id → "W-L" (or "W-L-D") record string, from squads. Squad 0 is a team not yet
    /// known, whose 0-0 isn't a record.
    var recordMap: [Int: String] {
        Dictionary(squads.filter { $0.id != 0 }.map { ($0.id, $0.recordString) },
                   uniquingKeysWith: { first, _ in first })
    }

    func makeGame(from t: CFLTournament, seasonType: Int) -> Game {
        let status = Self.gameStatus(for: t)
        let suppressScores = status.state == "pre"
        let records = recordMap

        func team(_ squad: CFLSquadScore) -> Game.Team {
            Game.Team(
                id: String(squad.id),
                name: squad.name,
                abbreviation: squad.shortName,
                displayName: squad.name,
                score: suppressScores ? nil : squad.score,
                record: records[squad.id],
                logo: nil
            )
        }

        return Game(
            id: String(t.id),
            name: "\(t.awaySquad.name) at \(t.homeSquad.name)",
            shortName: "\(t.awaySquad.shortName) @ \(t.homeSquad.shortName)",
            date: t.parsedDate,
            status: status,
            homeTeam: team(t.homeSquad),
            awayTeam: team(t.awaySquad),
            venue: nil,
            broadcasts: [],
            situation: nil,
            seasonType: seasonType
        )
    }

    /// A game being played says which quarter it's in ("third_quarter", with activePeriod 3).
    /// "playing" is what a round under way says, kept in case a game says it too.
    static let playingStatuses: Set<String> = [
        "first_quarter", "second_quarter", "third_quarter", "fourth_quarter", "overtime", "playing"
    ]

    /// The feed says "scheduled", then the quarter, "half_time" and "complete". Halftime is under
    /// way, with no period and the clock at 15:00, which isn't running. A status never seen is
    /// under way if it has a period or a clock.
    static func gameStatus(for t: CFLTournament) -> Game.GameStatus {
        let period = (t.activePeriod ?? 0) > 0 ? t.activePeriod : nil
        let clock = t.clock?.trimmingCharacters(in: .whitespacesAndNewlines)
        let runningClock = (clock?.isEmpty ?? true) ? nil : clock
        switch t.status {
        case "complete":
            return Game.GameStatus(state: "post", detail: "Final", period: nil, clock: nil, name: "STATUS_FINAL")
        case "half_time":
            return Game.GameStatus(state: "in", detail: "Halftime", period: nil, clock: nil, name: "STATUS_HALFTIME")
        case let status where playingStatuses.contains(status):
            var detail = "In Progress"
            if let period {
                detail = period > 4 ? "OT" : "Q\(period)"
                if let runningClock { detail += " \(runningClock)" }
            } else if let runningClock {
                detail = runningClock
            }
            return Game.GameStatus(state: "in", detail: detail, period: period,
                                   clock: runningClock, name: "STATUS_IN_PROGRESS")
        case "scheduled", "":
            return Game.GameStatus(state: "pre", detail: "Scheduled", period: nil, clock: nil, name: "STATUS_SCHEDULED")
        default:
            let words = t.status.replacingOccurrences(of: "_", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let detail: String = words.prefix(1).uppercased() + String(words.dropFirst())
            let state = (period != nil || runningClock != nil) ? "in" : "pre"
            return Game.GameStatus(state: state, detail: detail, period: nil, clock: nil,
                                   name: "STATUS_" + t.status.uppercased())
        }
    }

    func makeScheduleGame(from t: CFLTournament, seasonType: Int) -> ScheduleGame {
        let status = Self.gameStatus(for: t)
        let statusType: String
        switch status.state {
        case "post": statusType = "STATUS_FINAL"
        case "in":   statusType = "STATUS_IN_PROGRESS"
        default:     statusType = "STATUS_SCHEDULED"
        }
        let played = status.state != "pre"
        var game = ScheduleGame(
            id: String(t.id),
            date: t.parsedDate,
            name: "\(t.awaySquad.name) at \(t.homeSquad.name)",
            awayTeam: ScheduleGame.ScheduleTeam(
                id: String(t.awaySquad.id),
                abbreviation: t.awaySquad.shortName,
                displayName: t.awaySquad.name,
                score: played ? t.awaySquad.score : nil
            ),
            homeTeam: ScheduleGame.ScheduleTeam(
                id: String(t.homeSquad.id),
                abbreviation: t.homeSquad.shortName,
                displayName: t.homeSquad.name,
                score: played ? t.homeSquad.score : nil
            ),
            statusText: status.detail,
            statusType: statusType,
            seasonType: seasonType,
            venueName: nil
        )
        // Halftime is under way, which the status name alone wouldn't say.
        game.espnState = status.state
        game.espnCompleted = status.state == "post"
        return game
    }

    private func standingsEntry(from squad: CFLSquad) -> StandingsEntry {
        let games = squad.wins + squad.loss + squad.draw
        let winPercent = games > 0 ? (Double(squad.wins) + 0.5 * Double(squad.draw)) / Double(games) : 0
        let stats = StandingsEntry.StandingsStats(
            wins: squad.wins,
            losses: squad.loss,
            winPercent: winPercent,
            // The CFL's feed has no games back; a dash would be silent in VoiceOver.
            gamesBack: DivisionStandings.noFigure,
            streak: "-",
            record: squad.recordString,
            pointsFor: nil,
            pointsAgainst: nil,
            ties: squad.draw > 0 ? squad.draw : nil,
            otLosses: nil,
            nhlPoints: nil,
            avgPointsFor: nil,
            avgPointsAgainst: nil,
            homeRecord: nil,
            roadRecord: nil,
            lastTenRecord: nil,
            divisionRecord: nil,
            playoffSeed: nil,
            differential: nil
        )
        let team = StandingsEntry.TeamInfo(
            id: String(squad.id),
            name: squad.name,
            abbreviation: squad.abbreviation,
            displayName: squad.name,
            logo: nil
        )
        // Rank is assigned after sorting in standings().
        return StandingsEntry(rank: 0, team: team, stats: stats)
    }

    static func ordinal(_ n: Int) -> String {
        switch n {
        case 1: return "1st"
        case 2: return "2nd"
        case 3: return "3rd"
        default: return "\(n)th"
        }
    }
}

// MARK: - Raw JSON models

struct CFLRound: Decodable {
    let name: String?
    let type: String        // "PRE" | "REG" | "POST"
    let number: Int?
    let startDate: String?
    let endDate: String?
    let tournaments: [CFLTournament]

    /// End of the round's date window, used to resolve the current round.
    var endDateParsed: Date? { endDate.flatMap(parseCFLFeedDate) }

    var visibleTournaments: [CFLTournament] { tournaments.filter { !($0.isHidden ?? false) } }

    /// The feed has always named its weeks; "Week N" if it ever doesn't, as on Windows.
    func displayName(index: Int) -> String {
        if let name, !name.isEmpty { return name }
        return "Week \(index + 1)"
    }
}

struct CFLTournament: Decodable {
    let id: Int
    let date: String
    let status: String      // "scheduled" | "first_quarter"... | "half_time" | "complete"
    let homeSquad: CFLSquadScore
    let awaySquad: CFLSquadScore
    let activePeriod: Int?
    let clock: String?
    let winner: Int?
    let isHidden: Bool?

    /// Parsed kickoff time. The feed uses ISO-8601 with an explicit offset,
    /// e.g. "2026-06-12T00:30:00+00:00".
    var parsedDate: Date { parseCFLFeedDate(date) ?? Date() }
}

/// Parse a CFL feed timestamp. The feed uses ISO-8601 with an explicit offset
/// ("2026-06-12T00:30:00+00:00"); a couple of fallbacks cover minor variants.
func parseCFLFeedDate(_ s: String) -> Date? {
    let fmt = DateFormatter()
    fmt.locale = Locale(identifier: "en_US_POSIX")
    let formats = [
        "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
        "yyyy-MM-dd'T'HH:mmZZZZZ",
        "yyyy-MM-dd'T'HH:mm:ss'Z'"
    ]
    for f in formats {
        fmt.dateFormat = f
        if let d = fmt.date(from: s) { return d }
    }
    return ISO8601DateFormatter().date(from: s)
}

struct CFLSquadScore: Decodable {
    let id: Int
    let name: String
    let shortName: String
    let score: Int?
}

struct CFLSquad: Decodable {
    let id: Int
    let name: String
    let abbreviation: String
    let wins: Int
    let draw: Int
    let loss: Int

    /// "W-L" or "W-L-D" when there are draws.
    var recordString: String {
        draw > 0 ? "\(wins)-\(loss)-\(draw)" : "\(wins)-\(loss)"
    }
}
