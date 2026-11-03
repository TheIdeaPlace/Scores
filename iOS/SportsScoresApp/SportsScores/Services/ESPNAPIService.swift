//
//  ESPNAPIService.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

class ESPNAPIService {
    static let shared = ESPNAPIService()
    
    private let baseURL = "https://site.api.espn.com/apis/site/v2/sports"
    /// Standings uses a different ESPN API base path (v2, not site/v2)
    private let standingsBaseURL = "https://site.api.espn.com/apis/v2/sports"
    /// Core API for leaders/statistics and week calendar data
    private let coreAPIBaseURL = "https://sports.core.api.espn.com/v2/sports"
    /// Web API — the only ESPN host that serves league-wide team statistics
    private let webAPIBaseURL = "https://site.web.api.espn.com/apis/common/v3/sports"
    private let session: URLSession

    // MARK: - Caches (historical season data)

    /// Season calendars and week date ranges. Held by an actor because these
    /// methods are non-isolated and run concurrently — see `ScheduleCacheStore`.
    private let scheduleCache = ScheduleCacheStore()

    /// League team statistics and stat definitions. Held by an actor because
    /// stat headings request definitions concurrently — see `TeamStatsStore`.
    private let teamStatsStore: TeamStatsStore

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        let session = URLSession(configuration: config)
        self.session = session
        self.teamStatsStore = TeamStatsStore(session: session, baseURL: webAPIBaseURL)
    }

    // MARK: - Core API league name helper

    /// Returns the ESPN Core API league identifier for a football sport.
    private func coreLeagueName(for sport: Sport) -> String {
        sport == .nfl ? "nfl" : "college-football"
    }

    // MARK: - College football scoreboard parameters

    /// ESPN's college football scoreboard *doubles* `limit` internally on any
    /// query it accepts: limit=5 returns 10 events, limit=50
    /// returns 100. The effective (post-doubling) value must stay at or below
    /// 1000 — past that the page size collapses to 25, so limit=501 is worse than
    /// limit=250. 400 clears a 209-game Division I week and leaves the doubled
    /// value at 800, comfortably inside the ceiling.
    private static let ncaafScoreboardLimit = 400

    /// ESPN's "NCAA Division I" group for college basketball. Unlike football
    /// there is no FBS/FCS-style split to choose between — 52 is the root, 50 is
    /// Division I and 51 is everything that is not — so this needs no user
    /// setting, just the parameter. Without it a day returns roughly a seventh of
    /// the slate (145 men's games become 21, 122 women's become 4).
    private static let collegeBasketballGroupID = "50"

    /// Basketball does not double `limit` the way college football does, and
    /// honours it exactly, so this is a straight ceiling on a day's games.
    private static let collegeBasketballLimit = 400

    /// Extra scoreboard query parameters that give a college sport its full slate.
    /// Empty for every other sport, which ESPN already returns in full.
    ///
    /// `groups=` picks the division. Without it college football collapses to 25
    /// featured games when undated and to FBS-only when dated, and college
    /// basketball returns only a handful of featured games. `limit=` then lifts
    /// the page size far enough to hold the result.
    ///
    /// College hockey needs neither: `groups=` returns nothing there and the
    /// plain call already carries the full slate.
    private func collegeScoreboardParams(for sport: Sport,
                                         coverage: NCAAFCoverage?) -> [String] {
        switch sport {
        case .ncaaf:
            let coverage = coverage ?? NCAAFCoverage.stored
            return ["groups=\(coverage.espnGroupsID)", "limit=\(Self.ncaafScoreboardLimit)"]
        case .ncaam, .ncaawb:
            return ["groups=\(Self.collegeBasketballGroupID)",
                    "limit=\(Self.collegeBasketballLimit)"]
        default:
            return []
        }
    }

    /// Refetches an empty college football scoreboard as FBS, returning nil when
    /// no retry applies or the retry also comes back empty.
    ///
    /// ESPN returns *zero* events for a week-indexed postseason query under
    /// `groups=90` — `seasontype=3&groups=90` is empty where `groups=80` has all
    /// 46 bowl games — so once ESPN rolls the current week into the postseason,
    /// the undated scoreboard call would blank out entirely. Since `groups=90`
    /// is otherwise a strict superset of `groups=80`, an empty all-Division-I
    /// response is never legitimately better than the FBS one, and retrying
    /// costs nothing when the slate really is empty.
    private func ncaafFBSRetry(sport: Sport,
                               coverage: NCAAFCoverage?,
                               eventCount: Int,
                               urlString: String) async -> ScoreboardResponse? {
        guard sport == .ncaaf, eventCount == 0 else { return nil }
        guard (coverage ?? NCAAFCoverage.stored) != .fbs else { return nil }

        let fbsURLString = urlString.replacingOccurrences(
            of: "groups=\(NCAAFCoverage.allDivisionI.espnGroupsID)",
            with: "groups=\(NCAAFCoverage.fbs.espnGroupsID)")
        guard let url = URL(string: fbsURLString) else { return nil }
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let retry = try? decoder.decode(ScoreboardResponse.self, from: data),
              !retry.events.isEmpty else { return nil }
        return retry
    }
    
    // MARK: - Fetch Games (non-football, optional date)

    func fetchGames(for sport: Sport,
                    date: Date? = nil,
                    ncaafCoverage: NCAAFCoverage? = nil) async throws -> [Game] {
        var params: [String] = []
        if let date = date {
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyyMMdd"
            params.append("dates=\(fmt.string(from: date))")
        }
        params += collegeScoreboardParams(for: sport, coverage: ncaafCoverage)

        var urlString = "\(baseURL)/\(sport.apiPath)/scoreboard"
        if !params.isEmpty { urlString += "?" + params.joined(separator: "&") }
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else { throw APIError.invalidResponse }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        var apiResponse = try decoder.decode(ScoreboardResponse.self, from: data)
        if let retry = await ncaafFBSRetry(sport: sport, coverage: ncaafCoverage,
                                           eventCount: apiResponse.events.count,
                                           urlString: urlString) {
            apiResponse = retry
        }
        let seasonType = apiResponse.season?.type ?? 2
        return try apiResponse.events.map { try Game(from: $0, seasonType: seasonType) }
    }

    // MARK: - Fetch Football Games (week-based navigation)

    struct FootballScoreboardResult {
        let games: [Game]
        let week: Int
        let weekLabel: String
        let seasonType: Int
        let season: Int
        /// The season calendar ESPN embedded in the response, when present.
        /// Only the live-season call returns one.
        var calendar: SeasonCalendar? = nil
    }

    /// Fetches the **live** football scoreboard, letting ESPN resolve which
    /// season, season type, and week are current.
    ///
    /// No `week=`/`seasontype=` params are sent on purpose: ESPN ignores
    /// `season=` whenever `week=` is present and serves the *previous* season
    /// instead, which during the preseason means the last completed regular
    /// season shows up in place of the games about to be played.  Explicit weeks
    /// go through `fetchFootballWeek` and its date-range query instead.
    func fetchFootballGames(for sport: Sport,
                            ncaafCoverage: NCAAFCoverage? = nil) async throws -> FootballScoreboardResult {
        var urlString = "\(baseURL)/\(sport.apiPath)/scoreboard"
        let params = collegeScoreboardParams(for: sport, coverage: ncaafCoverage)
        if !params.isEmpty { urlString += "?" + params.joined(separator: "&") }
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else { throw APIError.invalidResponse }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        var apiResponse = try decoder.decode(ScoreboardResponse.self, from: data)
        if let retry = await ncaafFBSRetry(sport: sport, coverage: ncaafCoverage,
                                           eventCount: apiResponse.events.count,
                                           urlString: urlString) {
            apiResponse = retry
        }
        let resolvedSeasonType = apiResponse.season?.type ?? 2
        let resolvedSeason = apiResponse.season?.year ?? Calendar.current.component(.year, from: Date())
        let resolvedWeek = apiResponse.week?.number ?? 1
        let games = try apiResponse.events.map { try Game(from: $0, seasonType: resolvedSeasonType) }

        // Cache the embedded calendar so week navigation within the live season
        // needs no further Core API round-trips.
        let calendar = seasonCalendar(from: apiResponse, sport: sport, season: resolvedSeason)
        if let calendar = calendar {
            await scheduleCache.store(calendar, forKey: "\(sport.rawValue)-\(resolvedSeason)")
            await scheduleCache.storeWeekRanges(from: calendar)
        }

        // ESPN's live `week` block carries only a number; prefer the calendar's
        // label so preseason weeks read "Hall of Fame Weekend" rather than "Week 1".
        let weekLabel = calendar?.week(resolvedWeek, seasonType: resolvedSeasonType)?.label
            ?? apiResponse.week?.text
            ?? "Week \(resolvedWeek)"

        return FootballScoreboardResult(
            games: games,
            week: resolvedWeek,
            weekLabel: weekLabel,
            seasonType: resolvedSeasonType,
            season: resolvedSeason,
            calendar: calendar
        )
    }

    // MARK: - Embedded scoreboard calendar

    /// Builds a `SeasonCalendar` from the `leagues[].calendar` block of a
    /// football scoreboard response. Returns nil when the block is absent or
    /// carries no playable season types (e.g. the off-season entry only).
    private func seasonCalendar(from response: ScoreboardResponse,
                                sport: Sport,
                                season: Int) -> SeasonCalendar? {
        guard let sections = response.leagues?.first?.calendar, !sections.isEmpty else { return nil }

        var types: [SeasonTypeInfo] = []
        for section in sections {
            guard let type = section.value.flatMap(Int.init) else { continue }
            // Season type 4 is ESPN's "Off Season" bucket — never navigable.
            guard (1...3).contains(type) else { continue }

            let weeks: [WeekInfo] = (section.entries ?? []).compactMap { entry in
                guard let number = entry.value.flatMap(Int.init),
                      let start = entry.startDate.flatMap(parseESPNDateString),
                      let end   = entry.endDate.flatMap(parseESPNDateString) else { return nil }
                return WeekInfo(number: number,
                                label: entry.label ?? "Week \(number)",
                                startDate: start,
                                endDate: end)
            }
            guard !weeks.isEmpty else { continue }
            types.append(SeasonTypeInfo(type: type, weekCount: weeks.count, weeks: weeks))
        }

        guard !types.isEmpty else { return nil }
        return SeasonCalendar(sport: sport, season: season, seasonTypes: types.sorted { $0.type < $1.type })
    }

    // MARK: - Historical Football Calendar (Core API)

    /// Fetches the season calendar from the ESPN Core API for a specific football
    /// season year.  Returns a `SeasonCalendar` describing which season types
    /// (preseason / regular / postseason) exist and how many weeks each has.
    ///
    /// Results are cached in memory so repeated calls for the same sport+season
    /// cost nothing after the first fetch.
    func fetchFootballCalendar(sport: Sport, season: Int) async throws -> SeasonCalendar {
        let cacheKey = "\(sport.rawValue)-\(season)"
        if let cached = await scheduleCache.calendar(forKey: cacheKey) { return cached }

        let league = coreLeagueName(for: sport)

        // Fetch week counts for all three season types in parallel.
        async let preCount  = fetchWeekCount(league: league, season: season, seasonType: 1)
        async let regCount  = fetchWeekCount(league: league, season: season, seasonType: 2)
        async let postCount = fetchWeekCount(league: league, season: season, seasonType: 3)

        let (pre, reg, post) = await (preCount, regCount, postCount)

        var types: [SeasonTypeInfo] = []
        if pre  > 0 { types.append(SeasonTypeInfo(type: 1, weekCount: pre)) }
        if reg  > 0 { types.append(SeasonTypeInfo(type: 2, weekCount: reg)) }
        if post > 0 { types.append(SeasonTypeInfo(type: 3, weekCount: post)) }

        let calendar = SeasonCalendar(sport: sport, season: season, seasonTypes: types)
        await scheduleCache.store(calendar, forKey: cacheKey)
        return calendar
    }

    /// Returns the number of weeks in a given season type, or 0 on error / missing data.
    private func fetchWeekCount(league: String, season: Int, seasonType: Int) async -> Int {
        let urlString = "\(coreAPIBaseURL)/football/leagues/\(league)/seasons/\(season)/types/\(seasonType)/weeks?limit=100"
        guard let url = URL(string: urlString) else { return 0 }
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200 else { return 0 }
        struct WeeksResponse: Decodable { let count: Int? }
        return (try? JSONDecoder().decode(WeeksResponse.self, from: data))?.count ?? 0
    }

    // MARK: - Football Week Games (week-addressed scoreboard)

    /// Fetches games for one explicit week of a football season, live or historical.
    ///
    /// `dates=YEAR` is what picks the season: the scoreboard's `season=` is ignored
    /// when `week=` is also passed, while `dates=2025&week=5` serves the 2025
    /// season's week 5 and `dates=2026&week=1&seasontype=3` the January 2027 games.
    /// This replaced a `dates=START-END` range, which ESPN began rejecting with a
    /// 400 in September 2026. `seasontype` matters because week numbers restart
    /// within each season type.
    ///
    /// The Core API is only asked for the week's label, so losing it costs the
    /// label rather than the games. The label is cached, so navigating back and
    /// forth between weeks is cheap.
    func fetchFootballWeek(
        sport: Sport,
        season: Int,
        seasonType: Int,
        week: Int,
        ncaafCoverage: NCAAFCoverage? = nil
    ) async throws -> FootballScoreboardResult {
        let weekCacheKey = "\(sport.rawValue)-\(season)-\(seasonType)-\(week)"
        var weekLabel = await scheduleCache.weekRange(forKey: weekCacheKey)?.text

        if weekLabel == nil,
           let weekRange = await fetchWeekRange(sport: sport, season: season,
                                                seasonType: seasonType, week: week) {
            await scheduleCache.store(weekRange, forKey: weekCacheKey)
            weekLabel = weekRange.text
        }

        var scoreboardParams = ["dates=\(season)", "week=\(week)", "seasontype=\(seasonType)"]
        scoreboardParams += collegeScoreboardParams(for: sport, coverage: ncaafCoverage)
        let scoreboardURLString =
            "\(baseURL)/\(sport.apiPath)/scoreboard?" + scoreboardParams.joined(separator: "&")
        guard let scoreboardURL = URL(string: scoreboardURLString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: scoreboardURL)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        var apiResponse = try decoder.decode(ScoreboardResponse.self, from: data)
        if let retry = await ncaafFBSRetry(sport: sport, coverage: ncaafCoverage,
                                           eventCount: apiResponse.events.count,
                                           urlString: scoreboardURLString) {
            apiResponse = retry
        }
        let games = try apiResponse.events.map { try Game(from: $0, seasonType: seasonType) }

        return FootballScoreboardResult(
            games: games,
            week: week,
            weekLabel: weekLabel ?? "Week \(week)",
            seasonType: seasonType,
            season: season
        )
    }

    /// One week's dates and label from the Core API, or nil if it can't be had.
    private func fetchWeekRange(sport: Sport, season: Int, seasonType: Int,
                                week: Int) async -> ScheduleCacheStore.WeekRange? {
        let league = coreLeagueName(for: sport)
        let urlString = "\(coreAPIBaseURL)/football/leagues/\(league)/seasons/\(season)/types/\(seasonType)/weeks/\(week)"
        guard let url = URL(string: urlString),
              let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }

        struct CoreWeek: Decodable {
            let startDate: String
            let endDate: String
            let text: String?
        }
        guard let coreWeek = try? JSONDecoder().decode(CoreWeek.self, from: data) else { return nil }
        let start = parseESPNDateString(coreWeek.startDate) ?? Date()
        let end = parseESPNDateString(coreWeek.endDate) ?? Date()
        return ScheduleCacheStore.WeekRange(start: start, end: end,
                                            text: coreWeek.text ?? "Week \(week)")
    }

    /// Parse an ESPN date string that may be formatted with or without seconds.
    /// ESPN typically returns `"2022-09-08T07:00Z"` (no seconds).
    private func parseESPNDateString(_ s: String) -> Date? {
        let formats = [
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm'Z'",
            "yyyy-MM-dd'T'HH:mmZ",
            "yyyy-MM-dd"
        ]
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        for fmt in formats {
            df.dateFormat = fmt
            if let d = df.date(from: s) { return d }
        }
        return nil
    }

    // MARK: - MLB Wild Card Standings

    /// ESPN's standings endpoint takes a `type=` parameter selecting which table
    /// it returns. `type=1` is the wild card view: the 12 non-division-leaders
    /// per league, with `playoffSeed` as the wild card rank and `gamesBehind` as
    /// games back of the last spot. The three teams present in the default
    /// standings but absent from `type=1` are exactly the division leaders.
    private static let mlbWildCardStandingsType = 1

    /// Number of wild card berths per league.
    private static let mlbWildCardSpots = 3

    /// The current wild card picture as two groups, "AL Wild Card" and
    /// "NL Wild Card".
    ///
    /// Each group is in display order: the three division leaders first (already
    /// holding a playoff spot), then the race in ESPN's published seed order,
    /// the top three of which hold the berths.
    func fetchMLBWildCardStandings() async throws -> [StandingsGroup] {
        let base = "\(standingsBaseURL)/\(Sport.mlb.apiPath)/standings"
        guard let raceURL = URL(string: "\(base)?type=\(Self.mlbWildCardStandingsType)"),
              let overallURL = URL(string: base) else { throw APIError.invalidURL }

        async let raceData = standingsPayload(from: raceURL)
        async let overallData = standingsPayload(from: overallURL)
        let (race, overall) = try await (raceData, overallData)

        return race.children.compactMap { raceLeague -> StandingsGroup? in
            let entries = raceLeague.standings.entries
            guard !entries.isEmpty else { return nil }

            let raceIDs = Set(entries.map(\.team.id))
            let leaders = overall.children
                .first { $0.name == raceLeague.name }?
                .standings.entries
                .filter { !raceIDs.contains($0.team.id) } ?? []

            let orderedLeaders = leaders
                .sorted { Self.mlbStatValue($0, "winPercent") > Self.mlbStatValue($1, "winPercent") }
                .map { entry -> StandingsEntry in
                    let division = DivisionMapper.division(for: .mlb,
                                                           abbreviation: entry.team.abbreviation)
                    return Self.mlbWildCardEntry(
                        entry,
                        position: "-",
                        status: division.map { "\($0) leader" } ?? "Division leader",
                        gamesBack: "-")
                }

            let orderedRace = entries
                .sorted { Self.mlbStatValue($0, "playoffSeed", default: 99)
                        < Self.mlbStatValue($1, "playoffSeed", default: 99) }
                .map { entry -> StandingsEntry in
                    let rank = Int(Self.mlbStatValue(entry, "playoffSeed"))
                    let status = (rank > 0 && rank <= Self.mlbWildCardSpots)
                        ? "Wild card \(rank)" : ""
                    return Self.mlbWildCardEntry(
                        entry,
                        position: rank > 0 ? "\(rank)" : "-",
                        status: status,
                        gamesBack: Self.mlbStat(entry, "gamesBehind") ?? "-")
                }

            let label = raceLeague.name.hasPrefix("American") ? "AL Wild Card" : "NL Wild Card"
            return StandingsGroup(name: label, entries: orderedLeaders + orderedRace)
        }
    }

    private func standingsPayload(from url: URL) async throws -> APIStandingsResponse {
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(APIStandingsResponse.self, from: data)
    }

    private typealias MLBStandingsEntry = APIStandingsGroup.APIStandings.APIStandingsEntry

    private static func mlbStat(_ entry: MLBStandingsEntry, _ name: String) -> String? {
        entry.stats.first { $0.name == name }?.displayValue
    }

    private static func mlbStatValue(_ entry: MLBStandingsEntry, _ name: String,
                                     default fallback: Double = 0) -> Double {
        entry.stats.first { $0.name == name }?.value ?? fallback
    }

    /// Builds a standings row from an ESPN entry, overriding games-back with the
    /// wild card figure — the shared initialiser prefers `divisionGamesBehind`,
    /// which is a different race entirely.
    private static func mlbWildCardEntry(_ entry: MLBStandingsEntry,
                                         position: String,
                                         status: String,
                                         gamesBack: String) -> StandingsEntry {
        var built = StandingsEntry(fromAPIEntry: entry)
        built.wildCard = WildCardStanding(position: position, status: status,
                                          gamesBack: gamesBack)
        built.stats = StandingsEntry.StandingsStats(
            wins: built.stats.wins,
            losses: built.stats.losses,
            winPercent: built.stats.winPercent,
            gamesBack: gamesBack,
            streak: built.stats.streak,
            record: "\(built.stats.wins)-\(built.stats.losses)",
            pointsFor: built.stats.pointsFor,
            pointsAgainst: built.stats.pointsAgainst,
            ties: built.stats.ties,
            otLosses: built.stats.otLosses,
            nhlPoints: built.stats.nhlPoints,
            avgPointsFor: built.stats.avgPointsFor,
            avgPointsAgainst: built.stats.avgPointsAgainst,
            homeRecord: built.stats.homeRecord,
            roadRecord: built.stats.roadRecord,
            lastTenRecord: built.stats.lastTenRecord,
            divisionRecord: built.stats.divisionRecord,
            playoffSeed: built.stats.playoffSeed,
            differential: built.stats.differential)
        return built
    }

    // MARK: - World Cup Group Standings

    func fetchWorldCupStandings(for sport: Sport) async throws -> [WorldCupGroup] {
        let urlString = "\(standingsBaseURL)/\(sport.apiPath)/standings"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else { throw APIError.invalidResponse }

        let apiResponse = try JSONDecoder().decode(WorldCupStandingsResponse.self, from: data)
        return apiResponse.children.map { WorldCupGroup(from: $0) }
    }

    // MARK: - World Cup Date-range Schedule

    /// Fetches all games within a date range — used by the bracket tab to load
    /// all matches for a tournament phase in one call.
    ///
    /// ESPN's scoreboard answers `dates=START-END` with a 400 (since September
    /// 2026) but still takes a month, so this fetches each month the range touches
    /// and trims to the range. A month holds far more than a phase, so the page
    /// size goes to ESPN's ceiling of 1000; past that it collapses to 25.
    ///
    /// The trim uses Eastern time, as ESPN's date boards do. Tournament phases are
    /// calendar days on that board; a kickoff's day on the device can differ, which
    /// would put a match in the wrong round or lose it.
    func fetchGamesRange(for sport: Sport, startDate: Date, endDate: Date) async throws -> [Game] {
        let dayFormat = DateFormatter()
        dayFormat.locale = Locale(identifier: "en_US_POSIX")
        dayFormat.dateFormat = "yyyyMMdd"
        let monthFormat = DateFormatter()
        monthFormat.locale = Locale(identifier: "en_US_POSIX")
        monthFormat.dateFormat = "yyyyMM"
        let firstDay = dayFormat.string(from: startDate)
        let lastDay = dayFormat.string(from: endDate)

        var months: [String] = []
        var cursor = startDate
        while monthFormat.string(from: cursor) <= monthFormat.string(from: endDate) {
            months.append(monthFormat.string(from: cursor))
            guard let next = Calendar.current.date(byAdding: .month, value: 1, to: cursor) else { break }
            cursor = next
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        var games: [Game] = []
        for month in months {
            let urlString = "\(baseURL)/\(sport.apiPath)/scoreboard?dates=\(month)&limit=1000"
            guard let url = URL(string: urlString) else { throw APIError.invalidURL }

            let (data, response) = try await session.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else { throw APIError.invalidResponse }

            let apiResponse = try decoder.decode(ScoreboardResponse.self, from: data)
            let seasonType = apiResponse.season?.type ?? 1
            games += try apiResponse.events.map { try Game(from: $0, seasonType: seasonType) }
        }
        let boardDayFormat = DateFormatter()
        boardDayFormat.locale = Locale(identifier: "en_US_POSIX")
        boardDayFormat.timeZone = TimeZone(identifier: "America/New_York")
        boardDayFormat.dateFormat = "yyyyMMdd"
        return games.filter {
            let day = boardDayFormat.string(from: $0.date)
            return firstDay <= day && day <= lastDay
        }
    }

    /// Fetches each event's official tournament match number (e.g. FIFA World Cup
    /// match 73–104) from the core API. The site scoreboard feed omits this, yet it
    /// is the only reliable way to order knockout matches: ESPN's bracket
    /// placeholders ("Round of 32 N Winner") reference the official match number,
    /// which is NOT the same as kickoff order or event-id order.
    /// Returns `[eventId: matchNumber]`; events without a number are omitted.
    func fetchMatchNumbers(for sport: Sport, eventIds: [String]) async -> [String: Int] {
        let parts = sport.apiPath.split(separator: "/")
        guard parts.count == 2 else { return [:] }
        let sportType = String(parts[0])
        let league    = String(parts[1])

        struct CoreEvent: Decodable {
            struct Competition: Decodable { let matchNumber: Int? }
            let competitions: [Competition]
        }

        return await withTaskGroup(of: (String, Int?).self) { group in
            for id in eventIds {
                group.addTask { [coreAPIBaseURL, session] in
                    let urlString = "\(coreAPIBaseURL)/\(sportType)/leagues/\(league)/events/\(id)?lang=en"
                    guard let url = URL(string: urlString) else { return (id, nil) }
                    do {
                        let (data, _) = try await session.data(from: url)
                        let decoded = try JSONDecoder().decode(CoreEvent.self, from: data)
                        return (id, decoded.competitions.first?.matchNumber)
                    } catch {
                        return (id, nil)
                    }
                }
            }
            var result: [String: Int] = [:]
            for await (id, number) in group {
                if let number { result[id] = number }
            }
            return result
        }
    }

    // MARK: - Fetch News

    func fetchNews(for sport: Sport, limit: Int = 25) async throws -> [NewsItem] {
        let urlString = "\(baseURL)/\(sport.apiPath)/news?limit=\(limit)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else { throw APIError.invalidResponse }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let apiResponse = try decoder.decode(NewsAPIResponse.self, from: data)
        return apiResponse.articles.map { NewsItem(from: $0) }
    }
    
    // MARK: - Fetch Standings
    func fetchStandings(for sport: Sport) async throws -> [StandingsGroup] {
        let urlString = "\(standingsBaseURL)/\(sport.apiPath)/standings"
        guard let url = URL(string: urlString) else {
            throw APIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let apiResponse = try decoder.decode(APIStandingsResponse.self, from: data)

        // If the sport has a division mapper, sub-divide the flat conference entries
        // into proper divisions (e.g. "AL East", "AFC North").  Otherwise fall back
        // to the conference-level groupings from the API.
        if DivisionMapper.hasDivisions(sport) {
            return groupByDivision(apiResponse.groupsWithEntries, sport: sport)
        } else {
            return try apiResponse.groupsWithEntries.map { try StandingsGroup(from: $0) }
        }
    }

    /// Collect all entries from every conference child, assign each to a division
    /// via DivisionMapper, then produce a sorted [StandingsGroup].
    private func groupByDivision(_ children: [APIStandingsGroup], sport: Sport) -> [StandingsGroup] {
        // Bucket entries by division name
        var buckets: [String: [StandingsEntry]] = [:]

        for child in children {
            for apiEntry in child.standings.entries {
                let abbr = apiEntry.team.abbreviation
                let divisionName = DivisionMapper.division(for: sport, abbreviation: abbr)
                                   ?? child.name   // fallback to conference name
                let entry = StandingsEntry(fromAPIEntry: apiEntry)
                buckets[divisionName, default: []].append(entry)
            }
        }

        // Sort entries within each division by win% descending, then wins descending.
        // The NHL ranks by points, which an overtime loss earns one of.
        for key in buckets.keys {
            buckets[key]?.sort {
                if sport == .nhl, $0.stats.nhlPoints != $1.stats.nhlPoints {
                    return ($0.stats.nhlPoints ?? 0) > ($1.stats.nhlPoints ?? 0)
                }
                if $0.stats.winPercent != $1.stats.winPercent {
                    return $0.stats.winPercent > $1.stats.winPercent
                }
                return $0.stats.wins > $1.stats.wins
            }
        }

        // Sort division groups by predefined order, unknown divisions appended last
        let order = DivisionMapper.divisionOrder(for: sport)
        var groups: [StandingsGroup] = []
        for divName in order {
            if let entries = buckets[divName], !entries.isEmpty {
                groups.append(StandingsGroup(name: divName, entries: entries))
            }
        }
        // Append any unmapped divisions alphabetically
        let unknown = buckets.keys.filter { !order.contains($0) }.sorted()
        for divName in unknown {
            if let entries = buckets[divName] {
                groups.append(StandingsGroup(name: divName, entries: entries))
            }
        }
        return groups
    }
    
    // MARK: - Fetch Game Details
    func fetchGameDetails(for gameId: String, sport: Sport) async throws -> GameDetails {
        let urlString = "\(baseURL)/\(sport.apiPath)/summary?event=\(gameId)"
        guard let url = URL(string: urlString) else {
            throw APIError.invalidURL
        }
        
        let (data, response) = try await session.data(from: url)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let details = try decoder.decode(GameDetails.self, from: data)
        
        return details
    }

    // MARK: - Fetch Team Schedule

    /// Fetch the schedule for a single team and season type.
    func fetchTeamSchedule(teamId: String, sport: Sport, season: Int, seasonType: Int) async throws -> [ScheduleGame] {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams/\(teamId)/schedule?season=\(season)&seasontype=\(seasonType)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let apiResponse = try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: data)
        return apiResponse.events.compactMap { $0.toScheduleGame() }
    }

    // MARK: - Fetch League Leaders (Phase 5)

    func fetchLeagueLeaders(for sport: Sport, limit: Int = 10) async throws -> [LeagueLeaderCategory] {
        // Extract league from apiPath (e.g., "basketball/nba" → "nba")
        let league = sport.apiPath.components(separatedBy: "/").last ?? sport.rawValue.lowercased()
        let sportType = sport.apiPath.components(separatedBy: "/").first ?? "unknown"

        // Get current season year (the winter sports use the year+1 format)
        let seasonYear = sport.currentSeasonYear

        // Get season types to try (MLB spring training in Feb-March uses type 1)
        let seasonTypes = getSeasonTypes(for: sport)

        // Try current season with all season types, then fallback to previous seasons
        let seasonsToTry = [seasonYear, seasonYear - 1, seasonYear - 2]

        for season in seasonsToTry {
            for seasonType in seasonTypes {
                do {
                    let categories = try await fetchLeadersForSeason(
                        sportType: sportType,
                        league: league,
                        season: season,
                        seasonType: seasonType,
                        limit: limit
                    )
                    if !categories.isEmpty {
                        return categories
                    }
                } catch {
                    // Continue to next season/type combination
                    continue
                }
            }
        }
        
        // No data found for any season
        return []
    }
    
    private func getSeasonTypes(for sport: Sport) -> [Int] {
        let now = Date()
        let calendar = Calendar.current
        let month = calendar.component(.month, from: now)
        
        // MLB: Spring training (type 1) in Feb-March, regular season (type 2) otherwise
        if sport == .mlb {
            if month >= 2 && month <= 3 {
                return [1, 2, 3] // Try spring training, then regular, then postseason
            }
            return [2, 3, 1] // Try regular, then postseason, then spring training
        }
        
        // Other sports: Regular season (2) first, then postseason (3)
        return [2, 3, 1]
    }
    
    /// Fetch league leaders filtered to players on a specific team.
    /// Fetches the top 100 across the league, then filters to players on this team.
    /// limit=100 covers virtually all qualified hitters/pitchers (MLB has ~60-80
    /// qualifiers per batting stat), so every team player with qualifying stats appears.
    /// Categories where this team has no players in the top 100 are dropped.
    func fetchLeagueLeadersForTeam(teamAbbreviation: String, sport: Sport) async throws -> [LeagueLeaderCategory] {
        let all = try await fetchLeagueLeaders(for: sport, limit: 100)
        return all.compactMap { category in
            let teamEntries = category.leaders
                .filter { $0.teamAbbreviation == teamAbbreviation }
                .enumerated()
                .map { idx, entry in
                    // Clear team column — all players are on the same team
                    LeagueLeaderCategory.LeagueLeaderEntry(
                        rank: entry.rank,
                        displayValue: entry.displayValue,
                        athleteName: entry.athleteName,
                        teamAbbreviation: ""
                    )
                }
            guard !teamEntries.isEmpty else { return nil }
            return LeagueLeaderCategory(name: category.name, displayName: category.displayName, leaders: teamEntries)
        }
    }

    /// Returns this team's rank in each stat category using the Core API
    /// per-team statistics endpoint, which provides real team-aggregate values
    /// (e.g. team ERA, team batting average) along with ESPN's rank display string.
    func fetchTeamStatRankings(teamId: String, sport: Sport) async throws -> [TeamStatRanking] {
        let league = sport.apiPath.components(separatedBy: "/").last ?? sport.rawValue.lowercased()
        let sportType = sport.apiPath.components(separatedBy: "/").first ?? "unknown"
        let seasonYear = sport.currentSeasonYear
        let seasonTypes = getSeasonTypes(for: sport)

        for season in [seasonYear, seasonYear - 1] {
            for seasonType in seasonTypes {
                let urlString = "\(coreAPIBaseURL)/\(sportType)/leagues/\(league)/seasons/\(season)/types/\(seasonType)/teams/\(teamId)/statistics"
                guard let url = URL(string: urlString) else { continue }
                do {
                    let (data, response) = try await session.data(from: url)
                    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { continue }
                    let apiResponse = try JSONDecoder().decode(CoreTeamStatisticsResponse.self, from: data)
                    let rankings = buildTeamStatRankings(from: apiResponse)
                    if !rankings.isEmpty { return rankings }
                } catch { continue }
            }
        }
        return []
    }

    private func buildTeamStatRankings(from response: CoreTeamStatisticsResponse) -> [TeamStatRanking] {
        // Stat names that are technical, trivial, or duplicate — hide from the user.
        let excluded: Set<String> = [
            "gamesPlayed", "teamGamesPlayed", "isQualified", "isQualifiedSteals",
            "isQualifiedCatcher", "isQualifiedPitcher", "playerRating", "pitcherRating",
            "batterRating", "MLBRating", "projectedHomeRuns", "WAR", "DWAR", "OWAR",
            "thirdInnings", "pitchesAsStarter", "pitchesPerStart", "gameScore",
            "pitchCount", "strikes", "strikesToPitchRatio", "pickoffAttempts",
            "runsCreated", "runsCreatedPer27Outs", "secondaryAvgMinusBA",
            "pinchAvg", "pinchHits", "pinchAtBats", "fullInnings", "partInnings",
            "catcherInterference", "gameWinningRBIs", "sacHits", "sacBunts",
            "sacFlies", "atBats", "plateAppearances", "pitches", "battersFaced",
            "thirdInningsPlayed", "saveOpportunitiesPerWin", "inheritedRunners",
            "inheritedRunnersScored", "blownSaves", "groundBalls", "flyBalls",
            "runSupportAvg", "groundToFlyRatio", "pitchesPerInning",
        ]

        var rankings: [TeamStatRanking] = []
        for category in response.splits?.categories ?? [] {
            guard let sectionName = category.displayName, sectionName != "Fielding" else { continue }
            for stat in category.stats ?? [] {
                guard
                    let name = stat.name, !excluded.contains(name),
                    let displayName = stat.displayName,
                    let displayValue = stat.displayValue,
                    let rank = stat.rank,
                    // Rank > 34 is impossible in any pro league (max 32 teams: NFL/NHL).
                    // Stats with higher ranks are ranked against cross-split or
                    // individual-player pools in ESPN's data — not team-vs-team.
                    rank <= 34,
                    let rankDisplay = stat.rankDisplayValue,
                    !rankDisplay.isEmpty, rankDisplay != "?",
                    displayValue != "0", displayValue != "0.0",
                    rankDisplay != "Tied-1st"
                else { continue }

                rankings.append(TeamStatRanking(
                    sectionName: sectionName,
                    categoryDisplayName: displayName,
                    teamValue: displayValue,
                    leagueRank: rank,
                    rankDisplay: rankDisplay
                ))
            }
        }
        return rankings
    }

    // MARK: - Fetch Team Leaders (league-wide team statistics)

    /// League-wide team statistics, one category per curated stat, teams ranked
    /// best-first.
    ///
    /// This does *not* use the Core API `leaders` endpoint: that endpoint only
    /// ever returns individual players (its `groups=50` team parameter is
    /// silently ignored), which is why the Teams tab used to show player
    /// numbers labelled with team abbreviations. Real team aggregates come from
    /// the `statistics/byteam` endpoint instead.
    func fetchTeamLeaders(for sport: Sport, limit: Int = 10) async throws -> [LeagueLeaderCategory] {
        let specs = TeamStatCatalog.specs(for: sport)
        guard !specs.isEmpty else { return [] }

        let response = try await teamStatsStore.payload(for: sport)
        return buildTeamLeaderCategories(from: response, specs: specs, limit: limit)
    }

    // MARK: - Stat Definitions

    /// Plain-English definition of a stat, or nil when ESPN publishes none.
    ///
    /// ESPN ships its own glossary text alongside the team statistics payload —
    /// a `descriptions` array parallel to each category's stat names — so both
    /// the Players and Teams tabs read definitions from the same document
    /// rather than from hand-written copy that would drift.
    func statDefinition(for statKey: String, sport: Sport) async -> String? {
        guard !TeamStatCatalog.specs(for: sport).isEmpty else { return nil }
        let definitions = await teamStatsStore.glossary(for: sport)
        if let exact = definitions[statKey] { return exact }
        return Self.playerStatAliases[statKey].flatMap { definitions[$0] }
    }

    /// Player-leader categories and team statistics use different keys for the
    /// same stat — basketball is the worst offender ("pointsPerGame" on the
    /// leaders endpoint, "avgPoints" in the team payload). Map the ones that
    /// differ so the Players tab gets definitions too. Keys with no team-level
    /// equivalent at all (PER, plus/minus, tackles) are simply absent, and
    /// those headings show no definition button.
    private static let playerStatAliases: [String: String] = [
        "pointsPerGame":        "avgPoints",
        "assistsPerGame":       "avgAssists",
        "reboundsPerGame":      "avgRebounds",
        "stealsPerGame":        "avgSteals",
        "blocksPerGame":        "avgBlocks",
        "turnoversPerGame":     "avgTurnovers",
        "foulsPerGame":         "avgFouls",
        "fieldGoalPercentage":  "fieldGoalPct",
        "FreeThrowPct":         "freeThrowPct",
        "3PointPct":            "threePointFieldGoalPct",
        "3PointsMadePerGame":   "avgThreePointFieldGoalsMade",
        "quarterbackRating":    "QBRating",
    ]

    private func buildTeamLeaderCategories(
        from response: TeamStatsByTeamResponse,
        specs: [TeamStatSpec],
        limit: Int
    ) -> [LeagueLeaderCategory] {
        let teams = qualifiedTeams(in: response)
        guard !teams.isEmpty else { return [] }

        // Stat name → column index, taken from the first metadata copy of each
        // category that actually carries the names array.
        var columns: [String: [String: Int]] = [:]
        for meta in response.categories ?? [] {
            guard let section = meta.name, let names = meta.names, !names.isEmpty,
                  columns[section] == nil else { continue }
            var index: [String: Int] = [:]
            // ESPN repeats a few stat keys within a category (NFL rushing lists
            // rushingYards twice); the first occurrence is the one to use.
            for (i, name) in names.enumerated() where index[name] == nil {
                index[name] = i
            }
            columns[section] = index
        }

        return specs.compactMap { spec -> LeagueLeaderCategory? in
            guard let index = columns[spec.section]?[spec.stat] else { return nil }
            let wantedSplit = spec.split == .opponent ? "900" : "0"

            var rows: [(value: Double, display: String, team: TeamStatsByTeamResponse.TeamStats.TeamInfo)] = []
            for team in teams {
                guard let category = (team.categories ?? []).first(where: {
                    $0.name == spec.section && ($0.splitId ?? "0") == wantedSplit
                }) else { continue }
                guard let value = category.values?[safe: index] ?? nil,
                      let display = category.totals?[safe: index] ?? nil,
                      !display.isEmpty, display != "-"
                else { continue }
                rows.append((value, display, team.team))
            }
            guard !rows.isEmpty else { return nil }

            rows.sort { spec.higherIsBetter ? $0.value > $1.value : $0.value < $1.value }

            let leaders = rows.prefix(limit).enumerated().map { index, row in
                LeagueLeaderCategory.LeagueLeaderEntry(
                    rank: index + 1,
                    displayValue: row.display,
                    athleteName: row.team.abbreviation ?? row.team.displayName ?? "—",
                    teamAbbreviation: "",
                    teamNames: LeagueLeaderCategory.TeamNameSet(
                        displayName: row.team.displayName ?? row.team.abbreviation ?? "—",
                        name: row.team.name ?? row.team.displayName ?? "",
                        abbreviation: row.team.abbreviation ?? ""
                    )
                )
            }
            return LeagueLeaderCategory(
                name: spec.key,
                displayName: spec.title,
                leaders: Array(leaders),
                isTeamCategory: true
            )
        }
    }

    /// Drops teams that have played far fewer games than the rest of the league.
    ///
    /// ESPN's college feeds include every team that faced a Division I opponent,
    /// so a Division II school with a single game can top a per-game category.
    /// Teams below half the league-leading games-played count are excluded.
    private func qualifiedTeams(in response: TeamStatsByTeamResponse) -> [TeamStatsByTeamResponse.TeamStats] {
        let teams = response.teams ?? []

        // Locate the games-played column. Its category and key vary by sport
        // (baseball "batting"/"gamesPlayed", hockey "general"/"games").
        var gamesColumn: (section: String, index: Int)?
        for meta in response.categories ?? [] {
            guard let section = meta.name, let names = meta.names else { continue }
            if let index = names.firstIndex(where: { $0 == "gamesPlayed" || $0 == "games" }) {
                gamesColumn = (section, index)
                break
            }
        }
        guard let gamesColumn else { return teams }

        func gamesPlayed(_ team: TeamStatsByTeamResponse.TeamStats) -> Double? {
            guard let category = (team.categories ?? []).first(where: {
                $0.name == gamesColumn.section && ($0.splitId ?? "0") == "0"
            }) else { return nil }
            return category.values?[safe: gamesColumn.index] ?? nil
        }

        let played = teams.compactMap(gamesPlayed)
        guard let mostGames = played.max(), mostGames > 0 else { return teams }
        let threshold = mostGames / 2
        return teams.filter { (gamesPlayed($0) ?? mostGames) >= threshold }
    }

    private func fetchLeadersForSeason(
        sportType: String,
        league: String,
        season: Int,
        seasonType: Int,
        limit: Int = 50
    ) async throws -> [LeagueLeaderCategory] {
        let urlString = "\(coreAPIBaseURL)/\(sportType)/leagues/\(league)/seasons/\(season)/types/\(seasonType)/leaders?limit=\(limit)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        
        // Return empty for 404 (no data for this season/type) so we can try next one
        if http.statusCode == 404 {
            return []
        }
        
        guard http.statusCode == 200 else { throw APIError.invalidResponse }
        
        let apiResponse = try JSONDecoder().decode(CoreLeadersAPIResponse.self, from: data)
        let categories = apiResponse.categories ?? []
        
        // Collect all unique $ref URLs across all categories so we can resolve
        // them all in parallel (one TaskGroup), not sequentially per leader.
        // Sequential resolution for MLB (20 cats × 10 leaders × 2 refs = 400 calls)
        // would exceed the 30-second URLSession timeout. Parallel cuts this to ~1-2s.
        // NOTE: ESPN Core API $refs use http://, which iOS ATS blocks. Upgrade to https://.
        var athleteRefs = Set<String>()
        var teamRefs    = Set<String>()
        for category in categories {
            for leader in category.leaders ?? [] {
                if let ref = leader.athlete?.ref { athleteRefs.insert(secureURL(ref)) }
                if let ref = leader.team?.ref    { teamRefs.insert(secureURL(ref)) }
            }
        }
        
        // Copy to immutable constants before concurrent use (Swift 6: var capture in async let is an error)
        let frozenAthleteRefs = athleteRefs
        let frozenTeamRefs    = teamRefs
        
        // Resolve all unique refs in parallel
        async let athleteTask = resolveRefs(frozenAthleteRefs, as: CoreAthleteResponse.self)
        async let teamTask    = resolveRefs(frozenTeamRefs,    as: CoreTeamResponse.self)
        let (athletes, teams) = await (athleteTask, teamTask)
        
        // Build results using the resolved caches
        return categories.map { category in
            let leaders = (category.leaders ?? []).enumerated().map { index, leader -> LeagueLeaderCategory.LeagueLeaderEntry in
                let entityTeam = leader.team?.ref.flatMap { teams[secureURL($0)]?.abbreviation } ?? ""
                let entityName: String
                if let ref = leader.athlete?.ref, let ath = athletes[secureURL(ref)] {
                    entityName = ath.displayName ?? "—"
                } else if let ref = leader.team?.ref, let team = teams[secureURL(ref)] {
                    entityName = team.displayName ?? "—"
                } else {
                    entityName = "—"
                }

                // MLB displayValue is a full stats-line (e.g. "9-17, 4 HR, 2B, 6 RBI...").
                // Use the numeric value field with smart formatting instead.
                let statDisplay: String
                if let v = leader.value {
                    statDisplay = formatLeaderStatValue(v)
                } else {
                    statDisplay = leader.displayValue ?? "-"
                }
                return LeagueLeaderCategory.LeagueLeaderEntry(
                    rank: index + 1,
                    displayValue: statDisplay,
                    athleteName: entityName,
                    teamAbbreviation: entityTeam
                )
            }
            return LeagueLeaderCategory(
                name: category.name ?? "",
                displayName: category.displayName ?? "",
                leaders: leaders
            )
        }
    }

    /// Upgrade a Core API $ref URL from http:// to https:// so iOS ATS allows the connection.
    private func secureURL(_ ref: String) -> String {
        ref.hasPrefix("http://") ? "https://" + ref.dropFirst(7) : ref
    }

    /// Format a raw numeric stat value for display in the leaders table.
    ///  - Values < 1.0  → 3-decimal batting-average style  (e.g. 0.331 → ".331")
    ///  - Whole numbers  → integer counting stat            (e.g. 4.0  → "4")
    ///  - Decimal ≥ 1   → 2-decimal rate stat              (e.g. 2.75 → "2.75")
    private func formatLeaderStatValue(_ value: Double) -> String {
        if value < 1.0 {
            // batting average / OBP / SLG / OPS-under-1 style
            let s = String(format: "%.3f", value)
            return s.hasPrefix("0.") ? String(s.dropFirst()) : s  // ".333" not "0.333"
        } else if value == floor(value) {
            // counting stat: HR, RBI, K, SB, W, etc.
            return "\(Int(value))"
        } else {
            // rate stat ≥ 1: ERA, WHIP, etc.
            return String(format: "%.2f", value)
        }
    }

    /// Resolve a set of Core API $ref URLs in parallel. Returns a dictionary
    /// mapping each original ref URL string to the decoded response object.
    /// Failed resolutions are silently dropped rather than failing the whole batch.
    private func resolveRefs<T: Decodable & Sendable>(
        _ refs: Set<String>,
        as type: T.Type
    ) async -> [String: T] {
        var cache = [String: T]()
        await withTaskGroup(of: (String, T?).self) { group in
            for ref in refs {
                group.addTask {
                    guard let url = URL(string: ref) else { return (ref, nil) }
                    let result = try? await {
                        let (data, response) = try await self.session.data(from: url)
                        guard let http = response as? HTTPURLResponse,
                              http.statusCode == 200 else { return nil as T? }
                        return try? JSONDecoder().decode(T.self, from: data)
                    }()
                    return (ref, result)
                }
            }
            for await (ref, result) in group {
                if let result { cache[ref] = result }
            }
        }
        return cache
    }

    // MARK: - Fetch Rankings / Polls (Phase 6)

    func fetchRankings(for sport: Sport) async throws -> [RankingsPoll] {
        let urlString = "\(baseURL)/\(sport.apiPath)/rankings"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw APIError.invalidResponse }
        let apiResponse = try JSONDecoder().decode(RankingsAPIResponse.self, from: data)
        return apiResponse.rankings.map { RankingsPoll(from: $0) }
    }

    // MARK: - Fetch Golf Tournament / Schedule

    /// Fetches the current or date-specific golf tournament for PGA or LPGA.
    ///
    /// - `startDate` nil → returns the currently featured tournament (no `?dates` param).
    /// - `startDate` provided → fetches the scoreboard for that date, which ESPN returns
    ///   the tournament active during that week.
    ///
    /// Always returns the full season calendar from `leagues[0].calendar` regardless
    /// of whether a tournament is active.
    func fetchGolfTournament(for sport: Sport, startDate: Date? = nil) async throws -> GolfTournamentResult {
        var urlString = "\(baseURL)/\(sport.apiPath)/scoreboard"
        if let date = startDate {
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyyMMdd"
            urlString += "?dates=\(fmt.string(from: date))"
        }
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let decoder = JSONDecoder()
        // Golf date strings omit seconds ("2026-04-09T04:00Z") — use lenient parser
        let apiResponse = try decoder.decode(GolfScoreboardResponse.self, from: data)

        let calendar = apiResponse.leagues.first?.calendar.compactMap { entry -> GolfCalendarEntry? in
            guard let start = parseESPNDateString(entry.startDate),
                  let end   = parseESPNDateString(entry.endDate) else { return nil }
            return GolfCalendarEntry(id: entry.id, name: entry.label, startDate: start, endDate: end)
        } ?? []

        let tournament = apiResponse.events.first.map {
            GolfTournament(from: $0, parseDate: { [weak self] s in self?.parseESPNDateString(s) })
        }

        return GolfTournamentResult(tournament: tournament, calendar: calendar)
    }

    // MARK: - Racing (F1, IndyCar, NASCAR Cup)

    /// Fetches the current or upcoming race event for a racing series.
    /// Returns nil when the ESPN scoreboard has no events (off-season).
    func fetchRaceEvent(for series: Sport) async throws -> RaceEvent? {
        let urlString = "\(baseURL)/\(series.apiPath)/scoreboard"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let api = try JSONDecoder().decode(RacingScoreboardResponse.self, from: data)
        guard let eventAPI = api.events.first else { return nil }

        let competition = eventAPI.competitions.first
        let broadcasts = competition?.broadcasts?.flatMap(\.names) ?? []
        let competitors = (competition?.competitors ?? [])
            .sorted { $0.order < $1.order }
            .map { c -> RaceCompetitor in
                RaceCompetitor(
                    id: c.id,
                    position: c.order,
                    driverName: c.athlete?.displayName ?? "—",
                    shortName: c.athlete?.shortName ?? "—",
                    nationality: c.athlete?.flag?.alt ?? ""
                )
            }

        let date = parseESPNDateString(eventAPI.date) ?? Date()
        let status = eventAPI.status.type

        return RaceEvent(
            id: eventAPI.id,
            name: eventAPI.name,
            date: date,
            statusState: status.state,
            statusDescription: status.description,
            broadcasts: broadcasts,
            competitors: competitors
        )
    }

    /// Fetches championship standings for a racing series.
    /// F1 returns two groups (Driver + Constructor); others return one.
    func fetchRacingStandings(for series: Sport) async throws -> [RacingStandingsGroup] {
        let urlString = "\(standingsBaseURL)/\(series.apiPath)/standings"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        let api = try JSONDecoder().decode(RacingStandingsResponse.self, from: data)
        return api.children.enumerated().compactMap { index, groupAPI -> RacingStandingsGroup? in
            guard let standingsData = groupAPI.standings else { return nil }

            let isConstructors = groupAPI.name.lowercased().contains("constructor")

            let entries: [RacingStandingsEntry] = standingsData.entries.compactMap { entry in
                let stats = Dictionary(
                    entry.stats.compactMap { s -> (String, String)? in
                        guard let name = s.name, let val = s.displayValue else { return nil }
                        return (name, val)
                    },
                    uniquingKeysWith: { first, _ in first }
                )
                guard let rankStr = stats["rank"], let rank = Int(rankStr) else { return nil }

                let points = stats["championshipPts"] ?? stats["points"] ?? "—"

                if isConstructors, let team = entry.team {
                    return RacingStandingsEntry(
                        id: team.id ?? "\(index)-\(rank)",
                        rank: rank,
                        name: team.displayName ?? team.abbreviation ?? "—",
                        shortName: team.abbreviation ?? "—",
                        nationality: "",
                        points: points
                    )
                } else if let athlete = entry.athlete {
                    return RacingStandingsEntry(
                        id: athlete.id ?? "\(index)-\(rank)",
                        rank: rank,
                        name: athlete.displayName ?? "—",
                        shortName: athlete.shortName ?? "—",
                        nationality: athlete.flag?.alt ?? "",
                        points: points
                    )
                }
                return nil
            }

            guard !entries.isEmpty else { return nil }
            let groupId = isConstructors ? "constructors" : "drivers-\(index)"
            return RacingStandingsGroup(id: groupId, name: groupAPI.name, entries: entries)
        }
    }

    // MARK: - NFL Draft

    func fetchDraft(year: Int) async throws -> DraftResponse {
        let urlString = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/draft?season=\(year)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(DraftResponse.self, from: data)
    }

    // MARK: - Transactions

    /// Fetches paginated transactions for a sport.
    /// - Parameters:
    ///   - sport: The sport/league to query.
    ///   - page: 1-based page index (default 1).
    ///   - limit: Transactions per page (default 25).
    ///   - dateRange: Optional `(start, end)` strings in `"yyyyMMdd"` format for `?dates=` filtering.
    func fetchTransactions(
        sport: Sport,
        page: Int = 1,
        limit: Int = 25,
        dateRange: (start: String, end: String)? = nil
    ) async throws -> TransactionResponse {
        var urlString = "\(baseURL)/\(sport.apiPath)/transactions?limit=\(limit)&page=\(page)"
        if let range = dateRange {
            urlString += "&dates=\(range.start)-\(range.end)"
        }
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(TransactionResponse.self, from: data)
    }

    /// Fetches all teams for a sport, sorted by display name.
    func fetchTeamsForSport(sport: Sport) async throws -> [TransactionTeam] {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        let parsed = try JSONDecoder().decode(TeamsAPIResponse.self, from: data)
        return parsed.sports.first?.leagues.first?.teams.map(\.team) ?? []
    }

    /// Fetches conferences with their member teams for college sports.
    /// Uses the standings endpoint which groups teams by conference.
    /// Returns an empty array if the sport has no usable conference structure
    /// (caller should fall back to fetchTeamsForSport).
    func fetchConferencesWithTeams(for sport: Sport) async throws -> [ConferenceGroup] {
        let urlString = "\(standingsBaseURL)/\(sport.apiPath)/standings"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        let decoded = try JSONDecoder().decode(ConferencesAPIResponse.self, from: data)

        // Build a helper to convert a raw entry's team into TransactionTeam
        func toTeam(_ t: ConferencesAPIResponse.APIConference.APIStandings.APIEntry.APITeam) -> TransactionTeam {
            let logos = t.logos?.map { logo in
                TransactionTeamLogo(href: logo.href, width: nil, height: nil, rel: logo.rel)
            }
            return TransactionTeam(
                id: t.id,
                location: t.location,
                name: t.name,
                abbreviation: t.abbreviation,
                displayName: t.displayName,
                color: t.color,
                logos: logos
            )
        }

        // Extract teams from a conference node, flattening sub-divisions (e.g. Sun Belt)
        func teamsFrom(_ conf: ConferencesAPIResponse.APIConference) -> [TransactionTeam] {
            var teams = conf.standings?.entries.map { toTeam($0.team) } ?? []
            for sub in conf.children ?? [] {
                teams += sub.standings?.entries.map { toTeam($0.team) } ?? []
            }
            return teams.sorted { $0.displayName < $1.displayName }
        }

        // Top-level conference children → one ConferenceGroup each
        if let conferences = decoded.children, !conferences.isEmpty {
            let groups = conferences.compactMap { conf -> ConferenceGroup? in
                let teams = teamsFrom(conf)
                guard !teams.isEmpty else { return nil }
                return ConferenceGroup(id: conf.id ?? conf.name, name: conf.name, teams: teams)
            }
            // Only return conference groups if we have a meaningful number of teams.
            // Sports like NCAAH have conference structure but near-empty standings data —
            // in that case return [] so the caller falls back to fetchTeamsForSport.
            let totalTeams = groups.reduce(0) { $0 + $1.teams.count }
            if totalTeams >= 20 { return groups }
        }

        // No usable conference data — caller will fall back to a flat team list.
        return []
    }

    // MARK: - Team Hub: Team Info

    /// Fetches team detail (colors, record, venue, next game, standing summary).
    func fetchTeamHubInfo(teamId: String, sport: Sport) async throws -> TeamHubTeamInfo {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams/\(teamId)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        let api = try JSONDecoder().decode(TeamInfoAPIResponse.self, from: data)
        let t = api.team

        // Primary logo: prefer rel "default", fall back to first
        let logoURL: URL? = t.logos?
            .first(where: { $0.rel?.contains("default") == true })
            .flatMap { URL(string: $0.href) }
            ?? t.logos?.first.flatMap { URL(string: $0.href) }

        // Record items
        let items = t.record?.items ?? []
        func recordSummary(matching description: String) -> String? {
            items.first(where: { $0.description?.lowercased().contains(description) == true })?.summary
        }
        // NFL record items have no description; `type` is the reliable marker.
        let totalItem = items.first(where: { $0.type == "total" })
            ?? items.first(where: { $0.description?.lowercased().contains("overall") == true })
        var overallRecord = totalItem?.summary
        var homeRecord = recordSummary(matching: "home")
        var awayRecord = recordSummary(matching: "away") ?? recordSummary(matching: "road")
        if sport == .nhl, let totalItem {
            // ESPN's NHL summary leaves out overtime losses, and it sends no home or
            // road items, only the numbers for them inside the total.
            func value(_ name: String) -> Int? {
                (totalItem.stats?.first(where: { $0.name == name })?.value).map { Int($0) }
            }
            func record(_ prefix: String) -> String? {
                guard let w = value("\(prefix)Wins"), let l = value("\(prefix)Losses") else { return nil }
                return "\(w)-\(l)-\(value("\(prefix)OtLosses") ?? 0)"
            }
            if let summary = totalItem.summary, let ot = value("otLosses"),
               summary.split(separator: "-").count == 2 {
                overallRecord = "\(summary)-\(ot)"
            }
            homeRecord = homeRecord ?? record("home")
            awayRecord = awayRecord ?? record("away")
        }

        // Venue from franchise
        let venue = t.franchise?.venue
        let venueName = venue?.fullName
        let venueCity = venue?.address?.city

        // Next game from nextEvent[0]
        var nextGame: TeamHubNextGame?
        if let ev = t.nextEvent?.first,
           let comp = ev.competitions?.first {
            // Identify which competitor is the opponent (not our team)
            let opponent = comp.competitors?.first(where: { $0.team?.id != teamId })
            let isHome = comp.competitors?.first(where: { $0.team?.id == teamId })?.homeAway == "home"
            if let opp = opponent?.team {
                let timeIsKnown = (ev.timeValid ?? comp.timeValid) != false
                let parsedDate = parseESPNDate(ev.date).map {
                    timeIsKnown ? $0 : ScoreboardDay.localNoon(onUTCDayOf: $0)
                }
                // `nextEvent` can still be the game just played.
                if let parsedDate = parsedDate,
                   timeIsKnown ? parsedDate > Date()
                               : parsedDate >= Calendar.current.startOfDay(for: Date()) {
                    nextGame = TeamHubNextGame(
                        gameId: ev.id,
                        date: parsedDate,
                        opponentDisplayName: opp.displayName ?? opp.abbreviation ?? "Opponent",
                        opponentAbbreviation: opp.abbreviation ?? "?",
                        isHome: isHome,
                        timeIsKnown: timeIsKnown,
                        isNeutralSite: comp.neutralSite ?? false
                    )
                }
            }
        }

        return TeamHubTeamInfo(
            teamId: t.id,
            displayName: t.displayName,
            abbreviation: t.abbreviation,
            location: t.location ?? t.displayName,
            color: t.color,
            alternateColor: t.alternateColor,
            primaryLogoURL: logoURL,
            overallRecord: overallRecord,
            homeRecord: homeRecord,
            awayRecord: awayRecord,
            standingSummary: t.standingSummary,
            venueName: venueName,
            venueCity: venueCity,
            coachName: nil,  // populated by fetchTeamRoster
            nextGame: nextGame
        )
    }

    // MARK: - Team Hub: Roster

    /// Fetches the current roster for a team, flattening position groups.
    /// Also returns the head coach name (first coach in the response).
    func fetchTeamRoster(teamId: String, sport: Sport) async throws -> (players: [RosterPlayer], coachName: String?) {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams/\(teamId)/roster"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }

        func coachNameFrom(_ coaches: [RosterAPIResponse.RosterCoach]?) -> String? {
            coaches?.first.flatMap { c in
                let name = [c.firstName, c.lastName].compactMap { $0 }.joined(separator: " ")
                return name.isEmpty ? nil : name
            }
        }

        func makePlayer(id: String, displayName: String?, jersey: String?,
                        positionAbbr: String?, age: Int?) -> RosterPlayer {
            RosterPlayer(
                id: id,
                jerseyNumber: jersey ?? "–",
                displayName: displayName ?? "Unknown",
                positionAbbreviation: positionAbbr ?? "–",
                age: age.map { String($0) } ?? "–"
            )
        }

        // Try grouped format first (MLB, NFL, NHL, NBA)
        if let api = try? JSONDecoder().decode(RosterAPIResponse.self, from: data) {
            let grouped: [RosterPlayer] = (api.athletes ?? []).flatMap { group in
                (group.items ?? []).map { a in
                    makePlayer(id: a.id, displayName: a.displayName,
                               jersey: a.jersey, positionAbbr: a.position?.abbreviation, age: a.age)
                }
            }
            if !grouped.isEmpty {
                return (grouped, coachNameFrom(api.coach))
            }
        }

        // Fall back to flat format (college sports — athletes is a direct array of players)
        if let flat = try? JSONDecoder().decode(FlatRosterAPIResponse.self, from: data) {
            let players: [RosterPlayer] = (flat.athletes ?? []).map { a in
                makePlayer(id: a.id, displayName: a.displayName,
                           jersey: a.jersey, positionAbbr: a.position?.abbreviation, age: a.age)
            }
            return (players, coachNameFrom(flat.coach))
        }

        return ([], nil)
    }

    // MARK: - Team Hub: News (team-filtered, falls back to league)

    /// Fetches news filtered to a specific team; falls back to league news if none returned.
    func fetchTeamNews(teamId: String, sport: Sport, limit: Int = 25) async throws -> [NewsItem] {
        let urlString = "\(baseURL)/\(sport.apiPath)/news?team=\(teamId)&limit=\(limit)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let apiResponse = try decoder.decode(NewsAPIResponse.self, from: data)
        let articles = apiResponse.articles.map { NewsItem(from: $0) }
        if !articles.isEmpty { return articles }
        // Fall back to league-wide news
        return try await fetchNews(for: sport, limit: limit)
    }

    // MARK: - Team Hub: Schedule (current season, for Info + Schedule tabs)

    /// Fetches the current season schedule for a team. Returns games sorted by date.
    func fetchTeamHubSchedule(teamId: String, sport: Sport) async throws -> [ScheduleGame] {
        // Season currently in progress — see Sport.seasonYear(containing:)
        let season = sport.currentSeasonYear
        let seasonTypes: [Int]
        if sport == .mlb {
            seasonTypes = [1, 2, 3]
        } else if sport.isFootball {
            seasonTypes = [1, 2, 3]
        } else {
            seasonTypes = [2, 3]
        }
        var allGames: [ScheduleGame] = []
        await withTaskGroup(of: [ScheduleGame].self) { group in
            for st in seasonTypes {
                group.addTask { [self] in
                    (try? await self.fetchTeamSchedule(
                        teamId: teamId,
                        sport: sport,
                        season: season,
                        seasonType: st
                    )) ?? []
                }
            }
            for await result in group {
                allGames.append(contentsOf: result)
            }
        }
        return allGames.sorted { $0.date < $1.date }
    }

    // MARK: - Multi-format date parser

    private func parseESPNDate(_ string: String) -> Date? {
        // Try full ISO8601 with seconds first, then without
        let formatsToTry = ["yyyy-MM-dd'T'HH:mmZ", "yyyy-MM-dd'T'HH:mm:ssZ"]
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        for format in formatsToTry {
            fmt.dateFormat = format
            if let d = fmt.date(from: string) { return d }
        }
        return ISO8601DateFormatter().date(from: string)
    }
}
