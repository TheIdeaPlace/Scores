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

    /// A league's venues. See `VenueCacheStore`.
    private let venueCache = VenueCacheStore()

    private convenience init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.init(session: URLSession(configuration: config))
    }

    /// The app uses `shared`. Tests pass a session that answers from fixtures.
    init(session: URLSession) {
        self.session = session
        self.teamStatsStore = TeamStatsStore(session: session, webBaseURL: webAPIBaseURL,
                                             siteBaseURL: baseURL, coreBaseURL: coreAPIBaseURL)
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
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        // ESPN saying it has nothing there, as on Windows. Any other failure says so.
        if httpResponse.statusCode == 400 || httpResponse.statusCode == 404 { return [] }
        guard httpResponse.statusCode == 200 else { throw APIError.unexpectedStatus(httpResponse.statusCode) }

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

    // MARK: - Postseason (Bowls & Playoffs)

    /// The URL for every game of the current postseason: the request the Windows app's
    /// Bowls & Playoffs makes, `seasontype=3` with the coverage `groups=` and `limit=`.
    func postseasonURLString(for sport: Sport, ncaafCoverage: NCAAFCoverage? = nil) -> String {
        let params = ["seasontype=3"] + collegeScoreboardParams(for: sport, coverage: ncaafCoverage)
        return "\(baseURL)/\(sport.apiPath)/scoreboard?" + params.joined(separator: "&")
    }

    /// Every bowl and playoff game in one list, with each game's name and round.
    ///
    /// `seasontype=3&groups=90` is always empty (see `ncaafFBSRetry`), so with All Division I
    /// coverage the FBS request that follows is the one that brings the games. Unlike
    /// `ncaafFBSRetry`, a failure of that second request throws: it's the real answer here,
    /// and a failure mustn't read as no bowl games.
    func fetchPostseasonGames(for sport: Sport,
                              ncaafCoverage: NCAAFCoverage? = nil) async throws -> [PostseasonGame] {
        let urlString = postseasonURLString(for: sport, ncaafCoverage: ncaafCoverage)
        var response = try await postseasonScoreboard(urlString)
        if response.events.isEmpty, sport == .ncaaf,
           (ncaafCoverage ?? NCAAFCoverage.stored) != .fbs {
            let fbs = urlString.replacingOccurrences(
                of: "groups=\(NCAAFCoverage.allDivisionI.espnGroupsID)",
                with: "groups=\(NCAAFCoverage.fbs.espnGroupsID)")
            response = try await postseasonScoreboard(fbs)
        }
        return try PostseasonList.games(from: response)
    }

    /// One postseason scoreboard. A 400 or 404 is ESPN saying it has nothing, as in
    /// `fetchGames`; anything else that isn't a 200 throws.
    private func postseasonScoreboard(_ urlString: String) async throws -> ScoreboardResponse {
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        if http.statusCode == 400 || http.statusCode == 404 {
            return ScoreboardResponse(events: [], week: nil, season: nil, leagues: nil)
        }
        guard http.statusCode == 200 else { throw APIError.unexpectedStatus(http.statusCode) }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(ScoreboardResponse.self, from: data)
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

    /// The standings request for a sport. Without a group, college football is FBS alone,
    /// while the scoreboard shows FCS games too. The parameter is singular here:
    /// `/standings` ignores the scoreboard's `groups=`.
    func standingsURLString(for sport: Sport, coverage: NCAAFCoverage? = nil) -> String {
        let urlString = "\(standingsBaseURL)/\(sport.apiPath)/standings"
        guard sport == .ncaaf else { return urlString }
        return "\(urlString)?group=\((coverage ?? NCAAFCoverage.stored).espnGroupsID)"
    }

    func fetchStandings(for sport: Sport) async throws -> [StandingsGroup] {
        let urlString = standingsURLString(for: sport)
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
        if sport.isSoccer {
            return apiResponse.groupsWithEntries.map { StandingsGroup(soccerTable: $0) }
        } else if DivisionMapper.hasDivisions(sport) {
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

    /// Everything ESPN has for one team's season, in date order, for the schedule screen and
    /// Team Hub. A season that fails to load throws, so it can't read as an empty one, and
    /// the same for a part of it: a list with no playoffs, and no sign why, looks complete.
    ///
    /// Only a 400 or 404 means ESPN has nothing there, as on Windows in
    /// espn_api.get_team_schedule. For a preseason or postseason, that leaves out only that
    /// part. For a regular season or soccer results it throws `APIError.invalidResponse`, for
    /// which the view models read as no schedule, and not as an off-season or a failure.
    ///
    /// `lenient` is for a caller that can use whatever part loaded, and throws only when
    /// nothing did.
    func fetchTeamSeasonSchedule(teamId: String, sport: Sport, season: Int,
                                 lenient: Bool = false) async throws -> [ScheduleGame] {
        if sport.usesSoccerSchedule {
            return try await fetchSoccerTeamSchedule(teamId: teamId, sport: sport, season: season, lenient: lenient)
        }

        var lists: [[ScheduleGame]] = []
        var failure: Error?
        var anyFailure: Error?
        await withTaskGroup(of: (Int, Result<[ScheduleGame], Error>).self) { group in
            for seasonType in TeamScheduleQueries.seasonTypes {
                group.addTask { [self] in
                    do {
                        let query = TeamScheduleQueries.seasonType(seasonType, season: season)
                        let page = try await fetchTeamSchedulePage(teamId: teamId, sport: sport, query: query)
                        return (seasonType, .success(page.events.compactMap { $0.toScheduleGame() }))
                    } catch {
                        return (seasonType, .failure(error))
                    }
                }
            }
            for await (seasonType, result) in group {
                switch result {
                case .success(let games):
                    lists.append(games)
                case .failure(let error):
                    anyFailure = anyFailure ?? error
                    let mayLeaveOut = seasonType != 2 && error.isNothingThere
                    if !mayLeaveOut && failure == nil { failure = error }
                }
            }
        }
        if lenient {
            if lists.isEmpty, let anyFailure { throw anyFailure }
        } else if let failure {
            throw failure
        }
        return TeamScheduleQueries.merged(lists)
    }

    /// Results, plus the games to come if this is the current season. See `TeamScheduleQueries`.
    /// Past the results, ESPN saying it has nothing there leaves that part out. Anything else
    /// throws, because a schedule with its games to come missing would look complete.
    private func fetchSoccerTeamSchedule(teamId: String, sport: Sport, season: Int,
                                         lenient: Bool) async throws -> [ScheduleGame] {
        func games(_ query: String) async throws -> [ScheduleGame] {
            do {
                let page = try await fetchTeamSchedulePage(teamId: teamId, sport: sport, query: query)
                return page.events.compactMap { $0.toScheduleGame() }
            } catch let error where error.isNothingThere || (lenient && !error.isCancellation) {
                return []
            }
        }

        var lists: [[ScheduleGame]] = []
        var espnSeason: Int?
        var resultsFailure: Error?
        do {
            let results = try await fetchTeamSchedulePage(teamId: teamId, sport: sport,
                                                          query: TeamScheduleQueries.soccerResults(season: season))
            lists.append(results.events.compactMap { $0.toScheduleGame() })
            espnSeason = results.season?.year
        } catch let error where lenient && !error.isCancellation {
            resultsFailure = error
        }
        let next = TeamScheduleQueries.afterSoccerResults(season: season,
                                                          currentSeason: sport.currentSeasonYear,
                                                          espnSeason: espnSeason)
        if let earlier = next.earlierResults {
            lists.append(try await games(TeamScheduleQueries.soccerResults(season: earlier)))
        }
        if next.fixtures {
            lists.append(try await games(TeamScheduleQueries.soccerFixtures))
        }
        if let resultsFailure, lists.allSatisfy(\.isEmpty) { throw resultsFailure }
        return TeamScheduleQueries.merged(lists)
    }

    private func fetchTeamSchedulePage(teamId: String, sport: Sport, query: String) async throws -> TeamScheduleAPIResponse {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams/\(teamId)/schedule?\(query)"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        // Only these two mean ESPN has nothing there. A 403, a 429 or a 5xx says nothing about
        // the schedule. Windows reads them the same way, in espn_api._schedule_answer.
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 400 || status == 404 { throw APIError.invalidResponse }
        guard status == 200 else { throw APIError.unexpectedStatus(status) }

        return try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: data)
    }

    // MARK: - Fetch League Leaders (Phase 5)

    /// A league's player leaders, the first `limit` of each list. They come from the same place
    /// as on Windows wherever ESPN has it (`Sport.hasSiteLeaders`), with its qualifying minimums.
    func fetchLeagueLeaders(for sport: Sport, limit: Int = 10) async throws -> [LeagueLeaderCategory] {
        guard sport.hasSiteLeaders else {
            return try await fetchCoreLeaders(for: sport, limit: limit, onlyTeam: nil)
        }
        return try await fetchSiteLeaders(for: sport, teamId: nil).map { $0.keepingFirst(limit) }
    }

    /// The regular season ESPN says is the latest, as on Windows: `get_player_statistics`. A new
    /// regular season can start with nobody on the list yet, or be a 404 for now, so that means
    /// the one before. Neither existing is a failure rather than nothing to show.
    private func fetchSiteLeaders(for sport: Sport, teamId: String?) async throws -> [LeagueLeaderCategory] {
        let season = try await fetchCurrentSeason(sport: sport).regularSeasonYear
        let latest = try await requestSiteLeaders(for: sport, season: season, teamId: teamId)
        let categories = Self.leaderCategories(from: latest, oneTeam: teamId != nil)
        guard categories.isEmpty else { return categories }
        let previous = try await requestSiteLeaders(for: sport, season: season - 1, teamId: teamId)
        guard latest != nil || previous != nil else { throw APIError.invalidResponse }
        return Self.leaderCategories(from: previous, oneTeam: teamId != nil)
    }

    /// The most rows a list has on both apps, and what to ask for when ESPN won't give that many.
    /// `/leaders` answers 500 far more often the more it's asked for. It can be a retry away, or
    /// last for minutes at one limit while a smaller one works, and a shorter list beats none.
    /// Leaving out region and lang makes the 500s much likelier. On Windows: `_fetch_leaders`.
    static let siteLeadersLimit = 20
    static let siteLeadersSmallerLimits = [10, 5]

    /// A season's regular season leaders, or nil if ESPN has no such season. Without `seasontype`,
    /// a finished season's answer is its postseason. The second try at the full list gets a
    /// throwaway parameter, since ESPN can cache a 500 for up to 30 seconds.
    private func requestSiteLeaders(for sport: Sport, season: Int, teamId: String?) async throws -> SiteLeadersResponse? {
        let attempts: [(Int, Bool)] = [(Self.siteLeadersLimit, false), (Self.siteLeadersLimit, true)]
            + Self.siteLeadersSmallerLimits.map { ($0, false) }
        var lastStatus = 0
        for (limit, freshAnswer) in attempts {
            var items = [
                URLQueryItem(name: "region", value: "us"),
                URLQueryItem(name: "lang", value: "en"),
                URLQueryItem(name: "season", value: String(season)),
                URLQueryItem(name: "seasontype", value: "2"),
                URLQueryItem(name: "limit", value: String(limit)),
            ]
            if let teamId { items.append(URLQueryItem(name: "team", value: teamId)) }
            if freshAnswer {
                try await Task.sleep(nanoseconds: 1_000_000_000)
                items.append(URLQueryItem(name: "_", value: String(Int(Date().timeIntervalSince1970 * 1000))))
            }
            var components = URLComponents(string: "https://site.web.api.espn.com/apis/site/v3/sports/\(sport.apiPath)/leaders")
            components?.queryItems = items
            guard let url = components?.url else { throw APIError.invalidURL }

            let (data, response) = try await session.data(for: URLRequest(url: url, timeoutInterval: 15))
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if status == 200 { return try JSONDecoder().decode(SiteLeadersResponse.self, from: data) }
            if status == 404 { return nil }
            lastStatus = status
            if status < 500 { break }
        }
        throw APIError.unexpectedStatus(lastStatus)
    }

    /// `/leaders` lists these lowest first, and everything else highest first.
    private static let lowIsGoodLeaders: Set<String> = ["avgGoalsAgainst", "ERA", "WHIP", "opponentAvg"]

    /// No qualifying minimum in practice: 2026's list opens with 13 players on .000, catchers and
    /// outfielders among them. Windows leaves it out too.
    private static let leadersNotShown: Set<String> = ["opponentAvg"]

    /// A team's answer has these as well, repeating its yards lists with the same players.
    private static let repeatedForOneTeam: Set<String> = ["passingLeader", "rushingLeader", "receivingLeader"]

    /// The leaders up to the first who breaks the category's direction. ESPN can follow its
    /// qualified players with everyone else: on Nov 4, 2026, NCAAM field goal percentage read
    /// 71.4, 64.3, 55.6, 50.0, 46.2, 42.9, then 100.0 fourteen times. Those aren't the next best.
    private static func leadersInOrder(key: String, _ leaders: [SiteLeadersResponse.Leader]) -> [SiteLeadersResponse.Leader] {
        var kept = [SiteLeadersResponse.Leader]()
        var last: Double?
        for leader in leaders {
            if let value = leader.value {
                if let last, lowIsGoodLeaders.contains(key) ? value < last : value > last { break }
                last = value
            }
            kept.append(leader)
        }
        return kept
    }

    /// The first text that says something.
    private static func firstText(_ candidates: String?...) -> String? {
        candidates.compactMap { $0 }.first { !$0.isEmpty }
    }

    /// `/leaders` to the lists the app shows, in ESPN's order, which is best first even for a stat
    /// where low is good. A preseason is nothing to show: an NFL user in August would read it as
    /// the real thing. A league's ratings can be there with nobody rated, such as the WNBA's
    /// Player Efficiency Rating, where the leaders all read 0.0: that isn't a list of leaders.
    /// On Windows this is `_parse_leaders`, and tests/fixtures/leader_lists_grid.json holds both.
    ///
    /// `oneTeam` is an answer for one team, which Windows has no screen for. It has qualified
    /// players first and then everyone else, and a team's tab shows them all, so its list isn't
    /// cut where the numbers turn back up: that would lose a real player, such as Tyler Herro on
    /// 20.5 points, listed after a teammate on 5.6.
    static func leaderCategories(from response: SiteLeadersResponse?, oneTeam: Bool = false) -> [LeagueLeaderCategory] {
        guard let response, response.requestedSeason?.type?.type != 1 else { return [] }
        return (response.leaders?.categories ?? []).compactMap { category -> LeagueLeaderCategory? in
            let key = firstText(category.name) ?? "unknown"
            guard !leadersNotShown.contains(key), !(oneTeam && repeatedForOneTeam.contains(key)) else { return nil }
            let leaders = oneTeam ? (category.leaders ?? []) : leadersInOrder(key: key, category.leaders ?? [])
            guard leaders.contains(where: { ($0.value ?? 0) != 0 }) else { return nil }

            let rows = leaders.compactMap { leader -> (name: String, team: String, value: String)? in
                guard let name = firstText(leader.athlete?.displayName, leader.athlete?.fullName, leader.athlete?.shortName) else {
                    return nil
                }
                let value = leaderDisplayValue(category: key, value: leader.value, displayValue: leader.displayValue)
                return (name, firstText(leader.team?.abbreviation, leader.team?.displayName) ?? "", value.isEmpty ? "-" : value)
            }
            guard !rows.isEmpty else { return nil }

            let ranks = sharedRanks(rows.map(\.value))
            return LeagueLeaderCategory(
                name: key,
                displayName: firstText(category.displayName) ?? key.capitalized,
                leaders: zip(ranks, rows).map { rank, row in
                    LeagueLeaderCategory.LeagueLeaderEntry(
                        rank: rank, displayValue: row.value, athleteName: row.name, teamAbbreviation: row.team
                    )
                },
                seasonLabel: leadersSeasonLabel(response.requestedSeason, oneTeam: oneTeam)
            )
        }
    }

    /// Each value's rank, best first: one level with the one before shares its rank, and the next
    /// rank counts them, so 1, 1, 3. `/leaders` has no rank of its own.
    static func sharedRanks(_ values: [String]) -> [Int] {
        var rank = 0
        var previous: String?
        return values.enumerated().map { position, value in
            if value != previous {
                rank = position + 1
                previous = value
            }
            return rank
        }
    }

    /// "2026-27 Regular Season", the same words Windows uses. Asked for a past college football
    /// season's regular season, ESPN answers with type 3, the numbers running through the bowl
    /// games, so "Season" says what they are. One team's list says what its ranks are, since
    /// the same words on the league's list mean the league.
    private static func leadersSeasonLabel(_ season: SiteLeadersResponse.Season?, oneTeam: Bool) -> String? {
        let type = season?.type?.type == 3 ? "Season" : season?.type?.name
        let label = [season?.displayName, type].compactMap { $0 }.joined(separator: " ")
        guard oneTeam else { return label.isEmpty ? nil : label }
        return label.isEmpty
            ? "Ranked within this team, qualified players first"
            : "\(label), ranked within this team, qualified players first"
    }

    /// The core API, for the leagues with no `/leaders`. Its leaders have no qualifying minimum,
    /// and need each name looked up. `onlyTeam` is for a caller that will keep just that team's
    /// rows: the other rows' names aren't looked up.
    private func fetchCoreLeaders(for sport: Sport, limit: Int, onlyTeam: String?) async throws -> [LeagueLeaderCategory] {
        // Extract league from apiPath (e.g., "basketball/nba" → "nba")
        let league = sport.apiPath.components(separatedBy: "/").last ?? sport.rawValue.lowercased()
        let sportType = sport.apiPath.components(separatedBy: "/").first ?? "unknown"

        // Soccer goes by ESPN's own idea of the season, as on Windows, which also names it for the
        // list. The others go by the current season year (the winter sports use the year+1 format).
        let current: CurrentSeasonResponse? = sport.isSoccer ? try await fetchCurrentSeason(sport: sport) : nil
        let seasonYear = current?.year ?? sport.currentSeasonYear

        // The regular season, this year's or the most recent. Never a preseason: the app has
        // nowhere to say so. Soccer files its whole league season under type 1.
        let seasonType = sport.isSoccer ? 1 : 2
        let seasonsToTry = [seasonYear, seasonYear - 1, seasonYear - 2]

        for season in seasonsToTry {
            do {
                let categories = try await fetchLeadersForSeason(
                    sportType: sportType,
                    league: league,
                    season: season,
                    seasonType: seasonType,
                    limit: limit,
                    onlyTeam: onlyTeam
                )
                if !categories.isEmpty {
                    guard sport.isSoccer else { return categories }
                    let label = await seasonName(sportType: sportType, league: league, season: season, current: current)
                    return categories.map {
                        LeagueLeaderCategory(name: $0.name, displayName: $0.displayName, leaders: $0.leaders, seasonLabel: label)
                    }
                }
            } catch let error as URLError {
                // Another season won't get through a stalled network either, 30 seconds a try.
                throw error
            } catch {
                // A failed list says so rather than showing last season's, as on Windows.
                if sport.isSoccer { throw error }
                continue
            }
        }

        // No data found for any season
        return []
    }
    
    /// What ESPN calls this season, such as "2025-26 English Premier League". `current` is the
    /// core API's current one, so only an earlier season takes a request. If that fails, the year
    /// still says it isn't this season's. On Windows: `_core_season_name`.
    private func seasonName(sportType: String, league: String, season: Int, current: CurrentSeasonResponse?) async -> String {
        if let current, current.year == season, let name = current.displayName { return name }
        guard let url = URL(string: "\(coreAPIBaseURL)/\(sportType)/leagues/\(league)/seasons/\(season)"),
              let (data, response) = try? await session.data(for: URLRequest(url: url, timeoutInterval: 10)),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let answer = try? JSONDecoder().decode(CurrentSeasonResponse.self, from: data),
              let name = answer.displayName else {
            return String(season)
        }
        return name
    }

    /// A team's own players in each stat category, ranked among themselves. `/leaders` takes a
    /// team, which answers with up to 20 of its players, and every category it has anyone in.
    /// The league's list wouldn't do: 20 rows of it had no Blackhawks in any category. The leagues
    /// without it get the core API's top 100 across the league, filtered to this team.
    func fetchLeagueLeadersForTeam(teamId: String, teamAbbreviation: String, sport: Sport) async throws -> [LeagueLeaderCategory] {
        if sport.hasSiteLeaders {
            return try await fetchSiteLeaders(for: sport, teamId: teamId).map { category in
                LeagueLeaderCategory(
                    name: category.name,
                    displayName: category.displayName,
                    leaders: category.leaders.map { entry in
                        LeagueLeaderCategory.LeagueLeaderEntry(
                            rank: entry.rank,
                            displayValue: entry.displayValue,
                            athleteName: entry.athleteName,
                            teamAbbreviation: ""   // all of them are on this team
                        )
                    },
                    seasonLabel: category.seasonLabel
                )
            }
        }
        let all = try await fetchCoreLeaders(for: sport, limit: 100, onlyTeam: teamAbbreviation)
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

    /// Returns this team's rank in each stat category. The Core API's per-team statistics say which
    /// stats a team has and their values, for the regular season, this year's or the most recent:
    /// never a preseason, which the app has nowhere to say. Soccer files its whole league season
    /// under type 1. The ranks come from the league's `byteam` list where it has the stat, so
    /// they're what the league list says.
    func fetchTeamStatRankings(teamId: String, sport: Sport) async throws -> [TeamStatRanking] {
        let league = sport.apiPath.components(separatedBy: "/").last ?? sport.rawValue.lowercased()
        let sportType = sport.apiPath.components(separatedBy: "/").first ?? "unknown"
        let seasonYear = sport.currentSeasonYear
        let seasonType = sport.isSoccer ? 1 : 2

        // The same list the league list has, so the second of them to ask for gets it from the
        // store. Not having it only costs the ranks that come from it, unless the network has
        // stalled: the core API wouldn't get through either, and that's one timeout before Retry
        // appears rather than two.
        var leagueStats: TeamStatsByTeamResponse?
        if sport.hasTeamStats {
            do {
                leagueStats = try await teamStatsStore.payload(for: sport)
            } catch let error as URLError {
                throw error
            } catch {
                leagueStats = nil
            }
        }

        for season in [seasonYear, seasonYear - 1] {
            let urlString = "\(coreAPIBaseURL)/\(sportType)/leagues/\(league)/seasons/\(season)/types/\(seasonType)/teams/\(teamId)/statistics"
            guard let url = URL(string: urlString) else { continue }
            do {
                let (data, response) = try await session.data(from: url)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { continue }
                let apiResponse = try JSONDecoder().decode(CoreTeamStatisticsResponse.self, from: data)
                // Only if it's the same numbers, or the rank would be for others. A past college
                // football list is type 3 through the bowls, where these are type 2: Alabama's
                // 3,551 passing yards in 2025 are 11th, and that list has 3,953, 6th.
                let sameSeason = leagueStats.flatMap { $0.requestedSeason?.year == season && $0.isRegularSeason ? $0 : nil }
                let rankings = buildTeamStatRankings(
                    from: apiResponse,
                    teamId: teamId,
                    sport: sport,
                    league: sameSeason.map { LeagueTeamStats($0, sport: sport) }
                )
                if !rankings.isEmpty { return rankings }
            } catch let error as URLError {
                // Another season won't get through a stalled network either, 30 seconds a try.
                throw error
            } catch {
                continue
            }
        }
        return []
    }

    private func buildTeamStatRankings(
        from response: CoreTeamStatisticsResponse,
        teamId: String,
        sport: Sport,
        league: LeagueTeamStats?
    ) -> [TeamStatRanking] {
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

        // A rank past the end of the league is against cross-split or individual-player pools in
        // ESPN's data, not team against team: NFL kick return fair catch percentage reads 200th.
        // Without a list the team is on to say how many teams there are, 34 is more than any pro
        // league has, and 400 more than Division I. Montana is in FCS, and college football's list
        // is FBS, so its ranks aren't out of that list's size: ESPN has its tackles Tied-363rd.
        let listed = league.flatMap { list in list.teams.contains { $0.team.id == teamId } ? list : nil }
        let leagueSize = listed?.teams.count
        let highestRank = leagueSize ?? (sport.isCollegeSport ? 400 : 34)
        let outOf = sport.isCollegeSport ? leagueSize : nil

        var rankings: [TeamStatRanking] = []
        for category in response.splits?.categories ?? [] {
            guard let sectionName = category.displayName, sectionName != "Fielding" else { continue }
            for stat in category.stats ?? [] {
                guard
                    let name = stat.name, !excluded.contains(name),
                    let displayName = stat.displayName,
                    let displayValue = stat.displayValue,
                    displayValue != "0", displayValue != "0.0"
                else { continue }

                let rank: Int
                let rankDisplay: String
                if let section = category.name,
                   let standing = listed?.standing(ofTeam: teamId, section: section, stat: name) {
                    rank = standing.rank
                    rankDisplay = TeamStatRanks.display(rank: rank, tied: standing.tied, outOf: outOf)
                } else {
                    // A stat only this feed has, with ESPN's rank for it. Its Tied-1st is usually
                    // everyone level on nothing.
                    guard
                        let espnRank = stat.rank, espnRank <= highestRank,
                        let espnDisplay = stat.rankDisplayValue,
                        !espnDisplay.isEmpty, espnDisplay != "?", espnDisplay != "Tied-1st"
                    else { continue }
                    rank = espnRank
                    rankDisplay = outOf.map { "\(espnDisplay) of \($0)" } ?? espnDisplay
                }

                rankings.append(TeamStatRanking(
                    sectionName: sectionName,
                    categoryDisplayName: displayName,
                    teamValue: displayValue,
                    leagueRank: rank,
                    rankDisplay: rankDisplay,
                    leagueSize: leagueSize
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
        return buildTeamLeaderCategories(
            from: LeagueTeamStats(response, sport: sport),
            specs: specs,
            limit: limit,
            seasonLabel: response.seasonLabel
        )
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
        "3PointMadePerGame":    "avgThreePointFieldGoalsMade",
        "defensiveReboundsPerGame": "avgDefensiveRebounds",
        "offensiveReboundsPerGame": "avgOffensiveRebounds",
        "quarterbackRating":    "QBRating",
    ]

    private func buildTeamLeaderCategories(
        from league: LeagueTeamStats,
        specs: [TeamStatSpec],
        limit: Int,
        seasonLabel: String?
    ) -> [LeagueLeaderCategory] {
        guard !league.teams.isEmpty else { return [] }

        return specs.compactMap { spec -> LeagueLeaderCategory? in
            let ranked = league.ranked(
                section: spec.section,
                stat: spec.stat,
                opponent: spec.split == .opponent,
                higherIsBetter: spec.higherIsBetter
            )
            guard !ranked.isEmpty else { return nil }

            let leaders = ranked.prefix(limit).map { entry in
                LeagueLeaderCategory.LeagueLeaderEntry(
                    rank: entry.rank,
                    displayValue: entry.row.display,
                    athleteName: entry.row.team.abbreviation ?? entry.row.team.displayName ?? "—",
                    teamAbbreviation: "",
                    teamNames: LeagueLeaderCategory.TeamNameSet(
                        displayName: entry.row.team.displayName ?? entry.row.team.abbreviation ?? "—",
                        name: entry.row.team.name ?? entry.row.team.displayName ?? "",
                        abbreviation: entry.row.team.abbreviation ?? ""
                    )
                )
            }
            return LeagueLeaderCategory(
                name: spec.key,
                displayName: spec.title,
                leaders: Array(leaders),
                isTeamCategory: true,
                seasonLabel: seasonLabel
            )
        }
    }

    private func fetchLeadersForSeason(
        sportType: String,
        league: String,
        season: Int,
        seasonType: Int,
        limit: Int = 50,
        onlyTeam: String? = nil
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
        let categories = Self.coreLeaderLists(apiResponse)

        // Collect all unique $ref URLs across all categories, so each is only asked for once.
        // The teams come first, since `onlyTeam` needs them to tell which athletes matter.
        // NOTE: ESPN Core API $refs use http://, which iOS ATS blocks. Upgrade to https://.
        var teamRefs = Set<String>()
        for category in categories {
            for leader in category.leaders ?? [] {
                if let ref = leader.team?.ref { teamRefs.insert(secureURL(ref)) }
            }
        }
        let stallWatch = StallWatch()
        let teams = await resolveRefs(teamRefs, as: CoreTeamResponse.self, stallWatch: stallWatch)

        var athleteRefs = Set<String>()
        for category in categories {
            for leader in category.leaders ?? [] {
                guard let ref = leader.athlete?.ref else { continue }
                if let onlyTeam, leader.team?.ref.flatMap({ teams[secureURL($0)]?.abbreviation }) != onlyTeam {
                    continue
                }
                athleteRefs.insert(secureURL(ref))
            }
        }
        let athletes = await resolveRefs(athleteRefs, as: CoreAthleteResponse.self, stallWatch: stallWatch)

        // A soccer row whose name or team couldn't be had says so and keeps its place. But a
        // network that stalled partway, or most of them not coming, means ESPN isn't answering, so
        // it fails rather than showing a screen of those. On Windows: `_core_player_statistics`.
        let isSoccerLeagueList = sportType == "soccer" && onlyTeam == nil
        if isSoccerLeagueList {
            let stalled = await stallWatch.hasStalled
            if stalled || athletes.isEmpty || athletes.count * 2 < athleteRefs.count || teams.count * 2 < teamRefs.count {
                throw APIError.invalidResponse
            }
        }

        // Build results using the resolved caches
        return categories.map { category in
            let rows = category.leaders ?? []
            let displays = rows.map { Self.coreLeaderValue(category: category.name, leader: $0) }
            let ranks = Self.sharedRanks(displays)
            let leaders = rows.enumerated().map { index, leader -> LeagueLeaderCategory.LeagueLeaderEntry in
                // A blank cell would be silent in VoiceOver. Windows says the same.
                let entityTeam = leader.team?.ref.flatMap { teams[secureURL($0)]?.abbreviation }
                    ?? (isSoccerLeagueList ? SoccerTableRow.noStatus : "")
                let entityName: String
                if let ref = leader.athlete?.ref {
                    // Not the team's name if this lookup failed: that reads as if a team led.
                    entityName = athletes[secureURL(ref)]?.displayName ?? "—"
                } else if let ref = leader.team?.ref, let team = teams[secureURL(ref)] {
                    entityName = team.displayName ?? "—"
                } else {
                    entityName = "—"
                }

                return LeagueLeaderCategory.LeagueLeaderEntry(
                    rank: ranks[index],
                    displayValue: displays[index],
                    athleteName: entityName,
                    teamAbbreviation: entityTeam
                )
            }
            return LeagueLeaderCategory(
                name: category.name ?? "",
                displayName: category.displayName ?? category.name?.capitalized ?? "",
                leaders: leaders
            )
        }
    }

    private static func coreLeaderValue(category: String?, leader: CoreLeadersAPIResponse.CoreCategory.CoreLeader) -> String {
        let value = leaderDisplayValue(category: category, value: leader.value, displayValue: leader.displayValue)
        // A bare dash isn't spoken at VoiceOver's default punctuation level.
        return value.isEmpty ? SoccerTableRow.noStatus : value
    }

    /// The lists to show from a core API answer, in ESPN's order. A rating with nobody rated isn't
    /// a list of leaders, such as the WNBA's Player Efficiency Rating, where they all read 0.0. A
    /// list that repeats an earlier one is left out: soccer's goalsLeaders and goals are both
    /// called Goals, with the same players in the same order, and read the same once their text
    /// is a number. A list that differs in any row stays. On Windows: `core_leader_lists`, and
    /// tests/fixtures/soccer_grid.json holds both.
    static func coreLeaderLists(_ response: CoreLeadersAPIResponse) -> [CoreLeadersAPIResponse.CoreCategory] {
        func rows(_ category: CoreLeadersAPIResponse.CoreCategory) -> [[String]] {
            (category.leaders ?? []).map {
                [$0.athlete?.ref ?? "", $0.team?.ref ?? "", coreLeaderValue(category: category.name, leader: $0)]
            }
        }
        var kept = [CoreLeadersAPIResponse.CoreCategory]()
        for category in response.categories ?? [] {
            guard (category.leaders ?? []).contains(where: { ($0.value ?? 0) != 0 }) else { continue }
            let repeated = kept.contains { $0.displayName == category.displayName && rows($0) == rows(category) }
            if !repeated { kept.append(category) }
        }
        return kept
    }

    /// Upgrade a Core API $ref URL from http:// to https:// so iOS ATS allows the connection.
    private func secureURL(_ ref: String) -> String {
        ref.hasPrefix("http://") ? "https://" + ref.dropFirst(7) : ref
    }

    /// How a league leader's number reads. ESPN's displayValue is the right text for most
    /// stats, 38.3 for 38.2857, and these are where it isn't. On Windows this is
    /// game_labels.leader_display_value, and tests/fixtures/leader_display_grid.json holds both.
    ///  - Baseball's is a stat line ("179-567, 42 HR, 3B, ..."), for every category.
    ///  - A fraction gets rounded away: 7.5 sacks reads 8, a 137.3 quarterback rating reads 137.
    ///  - Three-point and college free throw percentages are fractions: 0.6154 reads 0.6. A save
    ///    percentage is one too, but reads as one: .945.
    ///  - Season totals read as if they were averages: 268 points reads 268.0.
    static func leaderDisplayValue(category: String?, value: Double?, displayValue: String?) -> String {
        let display = (displayValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard let number = value else { return display }
        let name = (category ?? "").lowercased()
        let isWhole = number == number.rounded()

        let threePlaces = ["avg", "ops", "onbasepct", "slugavg", "opponentavg", "savepct"].contains(name)

        guard display.range(of: #"^[+-]?[\d,]*\.?\d+$"#, options: .regularExpression) != nil else {
            if threePlaces {
                let text = String(format: "%.3f", number)
                return text.hasPrefix("0.") ? String(text.dropFirst()) : text
            }
            if isWhole && !["era", "whip"].contains(name) {
                return String(Int(number))
            }
            return String(format: "%.2f", number)
        }

        if ["points", "doubledouble"].contains(name) && isWhole {
            return String(Int(number))
        }
        if name.contains("pct"), !threePlaces, (0...1).contains(number),
           let shown = Double(display.replacingOccurrences(of: ",", with: "")), shown <= 1 {
            return String(format: "%.1f", number * 100)
        }
        if !display.contains(".") && !isWhole {
            return String(format: "%.1f", number)
        }
        return display
    }

    /// Runs `operation` on every item, at most `limit` at a time, in no particular order.
    /// One team's stats tab can have a thousand references. Sent all at once, the wait for a
    /// free connection counts against the request's timeout.
    static func concurrentMap<Item: Sendable, Output: Sendable>(
        _ items: [Item],
        limit: Int,
        _ operation: @escaping @Sendable (Item) async -> Output
    ) async -> [Output] {
        await withTaskGroup(of: Output.self) { group in
            var remaining = items[...]
            for _ in 0..<min(max(limit, 1), items.count) {
                let item = remaining.removeFirst()
                group.addTask { await operation(item) }
            }
            var outputs = [Output]()
            outputs.reserveCapacity(items.count)
            for await output in group {
                outputs.append(output)
                if let next = remaining.popFirst() {
                    group.addTask { await operation(next) }
                }
            }
            return outputs
        }
    }

    /// The most Core API references asked for at once. 125 took about 4 seconds at 8.
    static let maxConcurrentRefRequests = 8

    /// How many connection failures in a row, with no answer between them, mean the network
    /// has stalled. Two rounds of `maxConcurrentRefRequests`, so about a minute at 30 seconds
    /// each, rather than 18 minutes of asking for every name in the league.
    static let refFailuresBeforeGivingUp = maxConcurrentRefRequests * 2

    /// Counts connection failures in a row across one list's references. Past the limit, the
    /// rest aren't asked for, and those rows read "—".
    private actor StallWatch {
        private var failuresInARow = 0

        var hasStalled: Bool {
            failuresInARow >= ESPNAPIService.refFailuresBeforeGivingUp
        }

        func answered() {
            failuresInARow = 0
        }

        func failed() {
            failuresInARow += 1
        }
    }

    /// Resolve a set of Core API $ref URLs, some at a time. Returns a dictionary mapping each
    /// original ref URL string to the decoded response object. One that still fails after
    /// `fetchRef`'s retry is left out rather than failing the whole batch, and its row reads "—".
    private func resolveRefs<T: Decodable & Sendable>(
        _ refs: Set<String>,
        as type: T.Type,
        stallWatch: StallWatch
    ) async -> [String: T] {
        let results = await Self.concurrentMap(Array(refs), limit: Self.maxConcurrentRefRequests) { ref in
            (ref, await self.fetchRef(ref, as: type, stallWatch: stallWatch))
        }
        var cache = [String: T]()
        for (ref, result) in results {
            if let result { cache[ref] = result }
        }
        return cache
    }

    /// One Core API reference, with a second try if ESPN or the connection fails: a name
    /// missing from a row of leaders is worth one more request. A 404 won't change, so it's
    /// final. So is a timeout, which has already taken 30 seconds of someone's wait.
    private func fetchRef<T: Decodable>(_ ref: String, as type: T.Type, stallWatch: StallWatch) async -> T? {
        guard let url = URL(string: ref) else { return nil }
        for attempt in 0..<2 {
            guard await !stallWatch.hasStalled else { return nil }
            if attempt > 0 {
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
            do {
                let (data, response) = try await session.data(from: url)
                await stallWatch.answered()
                guard let status = (response as? HTTPURLResponse)?.statusCode else { continue }
                if status == 200 {
                    return try? JSONDecoder().decode(T.self, from: data)
                }
                if status < 500 && status != 429 {
                    return nil
                }
            } catch {
                await stallWatch.failed()
                if (error as? URLError)?.code == .timedOut {
                    return nil
                }
            }
        }
        return nil
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

    // MARK: - Venues

    /// A month of college basketball is up to 19 MB. A year would be no better: ESPN stops
    /// at the first 1000 games of any query, so a year of the NBA ends in April.
    private static let venueScoreboardLimit = 1000

    /// What gets a league's whole month of games. College football follows the coverage setting.
    func venueQuery(for sport: Sport, coverage: NCAAFCoverage? = nil) -> String {
        switch sport {
        case .ncaaf:
            return collegeScoreboardParams(for: .ncaaf, coverage: coverage).joined(separator: "&")
        case .ncaam, .ncaawb:
            return "groups=\(Self.collegeBasketballGroupID)&limit=\(Self.venueScoreboardLimit)"
        default:
            return "limit=\(Self.venueScoreboardLimit)"
        }
    }

    func venueScoreboardURLString(for sport: Sport, month: String, coverage: NCAAFCoverage? = nil) -> String {
        "\(baseURL)/\(sport.apiPath)/scoreboard?dates=\(month)&\(venueQuery(for: sport, coverage: coverage))"
    }

    /// A league's venues and home teams. Takes a request or two, the same as Windows' in
    /// services/venue_service.py.
    ///
    /// An empty list means ESPN answered and had nothing. If it never answered this throws,
    /// because "no venues" would be untrue. A month with a server error doesn't lose the
    /// list, as the month before stands in for it, but only for now: that isn't cached, so
    /// opening it again gives the month it missed another chance.
    func fetchVenues(for sport: Sport, now: Date = Date(), ignoringCache: Bool = false) async throws -> [LeagueVenue] {
        guard sport.hasVenues else { return [] }
        let cacheKey = "\(sport.rawValue)|\(venueQuery(for: sport))"
        if !ignoringCache, let cached = await venueCache.venues(forKey: cacheKey) {
            return cached
        }
        let months = VenueRules.months(for: sport, on: now)
        var failed = false
        for month in months {
            let events: [VenueScoreboard.Event]
            do {
                events = try await venueEvents(for: sport, month: month)
            } catch let error as URLError {
                if error.code == .cancelled { throw CancellationError() }
                // With no network an older month won't answer either, and asking would only
                // make the message later.
                if Self.meansNoNetwork(error.code) { throw VenuesError.espnDidNotAnswer }
                failed = true
                continue
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                failed = true
                continue
            }
            let venues = LeagueVenue.venues(from: events, in: sport)
            if !venues.isEmpty {
                if !failed { await venueCache.store(venues, forKey: cacheKey) }
                return venues
            }
        }
        if failed { throw VenuesError.espnDidNotAnswer }
        return []
    }

    /// The same failures Windows stops at: a timeout, or no connection to be had. Something
    /// else going wrong with one month, such as a connection lost partway through its
    /// download, is that month's failure, and the month before can stand in.
    private static func meansNoNetwork(_ code: URLError.Code) -> Bool {
        switch code {
        case .timedOut, .notConnectedToInternet, .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed,
             .secureConnectionFailed, .dataNotAllowed, .internationalRoamingOff:
            return true
        default:
            return false
        }
    }

    private func venueEvents(for sport: Sport, month: String) async throws -> [VenueScoreboard.Event] {
        guard let url = URL(string: venueScoreboardURLString(for: sport, month: month)) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard http.statusCode == 200 else { throw APIError.unexpectedStatus(http.statusCode) }
        return try JSONDecoder().decode(VenueScoreboard.self, from: data).events
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
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        // ESPN saying it has nothing there, as on Windows and in fetchGames. Any other failure says so.
        if http.statusCode == 400 || http.statusCode == 404 {
            return GolfTournamentResult(tournament: nil, calendar: [])
        }
        guard http.statusCode == 200 else { throw APIError.invalidResponse }

        let decoder = JSONDecoder()
        // Golf date strings omit seconds ("2026-04-09T04:00Z") — use lenient parser
        let apiResponse = try decoder.decode(GolfScoreboardResponse.self, from: data)

        let calendar = apiResponse.leagues?.first?.calendar.compactMap { entry -> GolfCalendarEntry? in
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

        // The race itself: Formula 1's first competition is Practice 1, and its event's status
        // can say Final the day before the race. racing.py picks the same one.
        let competition = eventAPI.competitions.first { $0.type?.abbreviation == "Race" }
            ?? eventAPI.competitions.last
        let status = competition?.status?.type ?? eventAPI.status.type
        let canceled = status.state == "post" && !status.completed

        var broadcasts: [String] = []
        for name in competition?.broadcasts?.flatMap(\.names) ?? [] where !broadcasts.contains(name) {
            broadcasts.append(name)
        }

        // By order, anyone without one after in ESPN's order. Before the race there's no order at
        // all, and the field is an entry list with no positions.
        let competitors = canceled ? [] : (competition?.competitors ?? [])
            .enumerated()
            .sorted { ($0.element.order ?? Int.max, $0.offset) < ($1.element.order ?? Int.max, $1.offset) }
            .map { pair -> RaceCompetitor in
                let c = pair.element
                return RaceCompetitor(
                    id: c.id,
                    position: status.state == "pre" ? nil : c.order,
                    driverName: c.athlete?.displayName ?? "Unknown driver",
                    shortName: c.athlete?.shortName ?? "—",
                    nationality: c.athlete?.flag?.alt ?? ""
                )
            }

        let raceDate = competition?.date ?? eventAPI.date
        let date = Self.racingDate(raceDate) ?? parseESPNDateString(raceDate) ?? Date()

        return RaceEvent(
            id: eventAPI.id,
            name: eventAPI.name,
            date: date,
            statusState: status.state,
            statusDescription: status.description,
            completed: status.completed,
            broadcasts: broadcasts,
            competitors: competitors
        )
    }

    /// ESPN's racing times, "2026-11-08T17:00Z", as the UTC times they are. parseESPNDateString
    /// reads that Z as a plain letter and the time as local, which would put a 1 PM Eastern race
    /// at 5 PM wherever the phone is; golf's placeholder hours rely on that, so it stays.
    private static let racingDateFormatters: [DateFormatter] = ["yyyy-MM-dd'T'HH:mmX", "yyyy-MM-dd'T'HH:mm:ssX"].map {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(identifier: "UTC")
        df.dateFormat = $0
        return df
    }

    static func racingDate(_ s: String) -> Date? {
        for formatter in racingDateFormatters {
            if let date = formatter.date(from: s) { return date }
        }
        return nil
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

    /// ESPN's team list stops at 50 unless told otherwise, and college leagues run past that.
    func teamsURLString(for sport: Sport) -> String {
        "\(baseURL)/\(sport.apiPath)/teams?limit=1000"
    }

    /// Fetches all teams for a sport, in ESPN's order.
    ///
    /// College football's `/teams` is every team ESPN knows, 762 across all divisions, with
    /// nothing on a team to say which and no parameter to narrow it. Its standings are the one
    /// request that lists just the teams in the coverage setting, so if they fail this throws
    /// rather than listing Division III to someone who chose FBS only.
    func fetchTeamsForSport(sport: Sport) async throws -> [TransactionTeam] {
        if sport == .ncaaf {
            let teams = try await fetchConferencesWithTeams(for: sport).flatMap(\.teams)
            guard !teams.isEmpty else { throw APIError.invalidResponse }
            return teams
        }
        let urlString = teamsURLString(for: sport)
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
        let urlString = standingsURLString(for: sport)
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        let groups = try JSONDecoder().decode(ConferencesAPIResponse.self, from: data).conferenceGroups

        // Only return conference groups if we have a meaningful number of teams.
        // Sports like NCAAH have conference structure but near-empty standings data —
        // in that case return [] so the caller falls back to fetchTeamsForSport.
        let totalTeams = groups.reduce(0) { $0 + $1.teams.count }
        return totalTeams >= 20 ? groups : []
    }

    // MARK: - Team Hub: Team Info

    /// A team page's record and standing, from its regular season, as Standings has them.
    ///
    /// `/teams/{id}` with no season answers with whatever the league is doing now. In the WNBA
    /// playoffs that read the Lynx, 33-11 and first, as 0-2 and 8th, and the teams left out as
    /// 0-0. In the MLB playoffs the record holds and the standing doesn't. College hockey's has
    /// no record at all, any time of year.
    ///
    /// Only these two come from the season asked for. Its `nextEvent` is wrong: the Nets' game
    /// tomorrow reads as one in January, and in MLB's off-season there isn't one.
    ///
    /// If the regular season can't be had, the answer with no season stands only when the league
    /// is in its regular season, when it's the same thing. Otherwise no record beats a wrong one.
    /// A cancelled request throws, so the next call asks again instead of keeping a page with
    /// no record. Soccer's team page is already the league season, and has no season type 2,
    /// and that goes for the World Cups, which `isSoccer` leaves out.
    /// `get_team_info` on Windows has the same rules.
    ///
    /// `unavailable` says a failure cost the page its record, which a league with no record
    /// to show doesn't. `season` is nil if there was no asking, or no answer.
    private func teamHubRecordAndStanding(
        teamId: String,
        sport: Sport,
        team: TeamInfoAPIResponse.TeamInfoTeamData
    ) async throws -> (record: TeamInfoAPIResponse.TeamInfoRecord?, standing: String?,
                       unavailable: Bool, season: CurrentSeasonResponse?) {
        if sport.usesSoccerSchedule { return (team.record, team.standingSummary, false, nil) }
        let season: CurrentSeasonResponse
        do {
            season = try await fetchCurrentSeason(sport: sport)
        } catch let error where error.isCancellation {
            throw error
        } catch {
            return (nil, nil, true, nil)
        }
        var regular: TeamInfoAPIResponse.TeamInfoTeamData?
        var failed = false
        do {
            regular = try await fetchRegularSeasonTeam(teamId: teamId, sport: sport, year: season.regularSeasonYear)
        } catch let error where error.isCancellation {
            throw error
        } catch {
            failed = !error.isNothingThere
        }
        let fallback = season.isRegularSeason ? team : nil
        let record = regular?.record?.items?.isEmpty == false ? regular?.record : fallback?.record
        return (record, regular?.standingSummary ?? fallback?.standingSummary,
                failed && record?.items?.isEmpty != false, season)
    }

    /// A standing as a team page says it. College hockey says "1st" of every team, whatever its
    /// record, and of nothing. The NBA's and WNBA's conferences aren't divisions.
    private func shownStanding(_ standing: String?) -> String? {
        guard let standing, standing.contains(" in ") else { return nil }
        return standing.replacingOccurrences(of: " Conference Division", with: " Conference")
    }

    /// The team page itself has the usual 30 seconds, and the page waits for these two as well,
    /// so a stalled ESPN doesn't get to hold it up for much longer. Windows does the same.
    private static let teamRecordRequestTimeout: TimeInterval = 8

    private func fetchCurrentSeason(sport: Sport) async throws -> CurrentSeasonResponse {
        let path = sport.apiPath.components(separatedBy: "/")
        guard path.count == 2,
              let url = URL(string: "\(coreAPIBaseURL)/\(path[0])/leagues/\(path[1])/season") else {
            throw APIError.invalidURL
        }
        let request = URLRequest(url: url, timeoutInterval: Self.teamRecordRequestTimeout)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(CurrentSeasonResponse.self, from: data)
    }

    private func fetchRegularSeasonTeam(
        teamId: String,
        sport: Sport,
        year: Int
    ) async throws -> TeamInfoAPIResponse.TeamInfoTeamData {
        let urlString = "\(baseURL)/\(sport.apiPath)/teams/\(teamId)?season=\(year)&seasontype=2"
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }
        let request = URLRequest(url: url, timeoutInterval: Self.teamRecordRequestTimeout)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        // 400 and 404 say ESPN has nothing there, and anything else is a failure.
        if http.statusCode == 400 || http.statusCode == 404 { throw APIError.invalidResponse }
        guard http.statusCode == 200 else { throw APIError.unexpectedStatus(http.statusCode) }
        return try JSONDecoder().decode(TeamInfoAPIResponse.self, from: data).team
    }

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
        let source = try await teamHubRecordAndStanding(teamId: teamId, sport: sport, team: t)

        // Primary logo: prefer rel "default", fall back to first
        let logoURL: URL? = t.logos?
            .first(where: { $0.rel?.contains("default") == true })
            .flatMap { URL(string: $0.href) }
            ?? t.logos?.first.flatMap { URL(string: $0.href) }

        // Record items
        let items = source.record?.items ?? []
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

        // Only the fallback: franchise.venue is years out of date for some teams and
        // missing for others, so TeamHubViewModel.teamVenue prefers the team's home games.
        let venue = t.franchise?.venue
        let venueName = venue?.fullName
        let venueCity = venue?.address?.city

        // Next game from nextEvent[0]
        var nextGame: TeamHubNextGame?
        if let ev = t.nextEvent?.first,
           let comp = ev.competitions?.first,
           !comp.isCalledOff {
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
            standingSummary: shownStanding(source.standing),
            venueName: venueName,
            venueCity: venueCity,
            coachName: nil,  // populated by fetchTeamRoster
            nextGame: nextGame,
            recordUnavailable: source.unavailable,
            recordIsRegularSeasonOnly: sport.isCollegeSport && source.season?.isRegularSeason == false
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

    // MARK: - Team Hub: News

    /// News for a specific team. A team with none has none, as on Windows, rather than the
    /// league's stories under its name.
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
        return apiResponse.articles.map { NewsItem(from: $0) }
    }

    // MARK: - Team Hub: Schedule (current season, for Info + Schedule tabs)

    /// Fetches the current season schedule for a team. Returns games sorted by date.
    func fetchTeamHubSchedule(teamId: String, sport: Sport) async throws -> [ScheduleGame] {
        try await fetchCurrentOrLastSeason(teamId: teamId, sport: sport, lenient: false)
    }

    /// The same for a favorite's card, which only needs the last and next games: a request
    /// failing for the preseason shouldn't cost it the regular season it does have.
    func fetchFavoriteCardSchedule(teamId: String, sport: Sport) async throws -> [ScheduleGame] {
        try await fetchCurrentOrLastSeason(teamId: teamId, sport: sport, lenient: true)
    }

    /// The season in progress, see Sport.seasonYear(containing:). ESPN publishes a new
    /// season's schedule some weeks after the last one ends, so in that gap, the NFL in March
    /// or the WNBA in January, it's empty and the season that just finished stands in.
    /// A failure throws before it gets that far. TeamScheduleViewModel does the same.
    private func fetchCurrentOrLastSeason(teamId: String, sport: Sport, lenient: Bool) async throws -> [ScheduleGame] {
        let season = sport.currentSeasonYear
        let games = try await fetchTeamSeasonSchedule(teamId: teamId, sport: sport, season: season, lenient: lenient)
        if !games.isEmpty { return games }
        return try await fetchTeamSeasonSchedule(teamId: teamId, sport: sport, season: season - 1, lenient: lenient)
    }

    /// The regular season of whichever season ESPN has for this team, by asking for none.
    /// `currentSeasonYear` rolls forward before ESPN has that schedule. A soccer league's
    /// season type is its own number, so 2 finds nothing there and the default is the
    /// league season.
    func regularSeasonScheduleURL(teamId: String, sport: Sport) -> String {
        let query = sport.isSoccer ? "" : "?seasontype=2"
        return "\(baseURL)/\(sport.apiPath)/teams/\(teamId)/schedule\(query)"
    }

    func fetchRegularSeasonSchedule(teamId: String, sport: Sport) async throws -> [ScheduleGame] {
        guard let url = URL(string: regularSeasonScheduleURL(teamId: teamId, sport: sport)) else {
            throw APIError.invalidURL
        }
        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: data)
            .events.compactMap { $0.toScheduleGame() }
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
