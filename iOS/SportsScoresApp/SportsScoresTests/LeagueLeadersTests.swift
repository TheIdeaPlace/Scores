//
//  LeagueLeadersTests.swift
//  SportsScoresTests
//
//  How a leader's number reads and what /leaders reads as, against the grids Windows is also
//  held to. What's asked of ESPN, against real payloads with a stand-in for it. The core API is
//  for the leagues with no /leaders, which college hockey stands for here, and for one soccer
//  team's players. Soccer's league lists come from /leaders with season types of their own.
//

import XCTest
@testable import SportsScores

final class LeaderDisplayValueGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Case: Decodable {
            let why: String
            let category: String
            let value: Double?
            let display: String?
            let reads: String
        }
        let cases: [Case]
    }

    func testEveryCaseMatchesTheSharedGrid() throws {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/leader_display_grid.json")
        let grid = try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
        XCTAssertGreaterThan(grid.cases.count, 30)
        for item in grid.cases {
            let reads = ESPNAPIService.leaderDisplayValue(category: item.category, value: item.value, displayValue: item.display)
            XCTAssertEqual(reads, item.reads, "\(item.category): \(item.why)")
        }
    }

    func testRealBaseballRowsReadAsNumbersNotStatLines() throws {
        let response = try JSONDecoder().decode(CoreLeadersAPIResponse.self, from: Fixtures.data("leaders_core_MLB.json"))
        let categories = try XCTUnwrap(response.categories)
        XCTAssertFalse(categories.isEmpty)
        for category in categories {
            for leader in category.leaders ?? [] {
                XCTAssertTrue(leader.displayValue?.contains(",") ?? false, "the fixture should have stat lines")
                let reads = ESPNAPIService.leaderDisplayValue(category: category.name, value: leader.value, displayValue: leader.displayValue)
                XCTAssertFalse(reads.contains(","), reads)
                XCTAssertFalse(reads.isEmpty)
            }
        }
    }
}

final class ConcurrentMapTests: XCTestCase {
    private actor Gauge {
        private var running = 0
        private(set) var most = 0

        func enter() {
            running += 1
            most = max(most, running)
        }

        func leave() {
            running -= 1
        }
    }

    func testNeverMoreThanTheLimitAtOnceAndEveryItemDone() async {
        let gauge = Gauge()
        let doubled = await ESPNAPIService.concurrentMap(Array(0..<40), limit: 3) { item -> Int in
            await gauge.enter()
            try? await Task.sleep(nanoseconds: 5_000_000)
            await gauge.leave()
            return item * 2
        }
        let most = await gauge.most
        XCTAssertLessThanOrEqual(most, 3)
        XCTAssertGreaterThan(most, 1, "it should still work in parallel")
        XCTAssertEqual(doubled.sorted(), (0..<40).map { $0 * 2 })
    }

    func testNothingToDo() async {
        let results = await ESPNAPIService.concurrentMap([Int](), limit: 3) { $0 }
        XCTAssertEqual(results, [])
    }

    func testFewerItemsThanTheLimit() async {
        let results = await ESPNAPIService.concurrentMap([7], limit: 3) { $0 }
        XCTAssertEqual(results, [7])
    }
}

/// Stands in for ESPN. The leaders are the real payload. A team's reference answers with
/// its id as its abbreviation, and an athlete's with its id as its name.
private final class StandInESPN: URLProtocol {
    static let lock = NSLock()
    static var leaders = Data()
    static var requests = [String]()
    /// How many times each athlete reference fails before it answers.
    static var failuresFirst = 0
    static var failureStatus = 503
    static var failures = [String: Int]()
    /// Every reference fails like a stalled network, rather than answering.
    static var referenceError: URLError.Code?
    /// The status of a leaders request, by its URL. 200 sends `leaders`.
    static var leadersStatus: (String) -> Int = { _ in 200 }
    /// ESPN's idea of the season, which one soccer team's list asks for first.
    static var season = Data(#"{"year":2026,"displayName":"2026-27 Stand-in League"}"#.utf8)

    static func reset(leaders: Data) {
        lock.withLock {
            self.leaders = leaders
            season = Data(#"{"year":2026,"displayName":"2026-27 Stand-in League"}"#.utf8)
            requests = []
            failuresFirst = 0
            failureStatus = 503
            failures = [:]
            referenceError = nil
            leadersStatus = { _ in 200 }
        }
    }

    static var athleteRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/athletes/") } }
    }

    static var leadersRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/leaders") } }
    }

    static var referenceRequests: [String] {
        lock.withLock { requests.filter { !$0.contains("/leaders") && !isSeason($0) } }
    }

    /// The season now, or one by its year: not a reference to look up.
    private static func isSeason(_ url: String) -> Bool {
        url.hasSuffix("/season") || url.range(of: #"/seasons/\d+$"#, options: .regularExpression) != nil
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        if let code = Self.lock.withLock({ () -> URLError.Code? in
            guard !url.absoluteString.contains("/leaders"), !Self.isSeason(url.absoluteString),
                  let code = Self.referenceError else { return nil }
            Self.requests.append(url.absoluteString)
            return code
        }) {
            client?.urlProtocol(self, didFailWithError: URLError(code))
            return
        }
        let (status, body) = Self.answer(url)
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    private static func answer(_ url: URL) -> (Int, Data) {
        lock.lock()
        defer { lock.unlock() }
        let text = url.absoluteString
        requests.append(text)
        let id = url.lastPathComponent
        if isSeason(text) {
            return text.hasSuffix("/season") ? (200, season) : (404, Data())
        }
        if text.contains("/leaders") {
            let status = leadersStatus(text)
            return (status, status == 200 ? leaders : Data())
        }
        if text.contains("/teams/") {
            return (200, Data(#"{"displayName":"Team \#(id)","abbreviation":"\#(id)"}"#.utf8))
        }
        if failures[text, default: 0] < failuresFirst {
            failures[text, default: 0] += 1
            return (failureStatus, Data())
        }
        return (200, Data(#"{"displayName":"Athlete \#(id)"}"#.utf8))
    }
}

/// Nothing gets through, not even the leaders.
private final class NoConnection: URLProtocol {
    static var count = 0

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        Self.count += 1
        client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
    }
}

final class LeagueLeadersRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private var realLeaders: CoreLeadersAPIResponse!
    private let soccer = Sport.soccerLeagues.first!

    override func setUpWithError() throws {
        let data = try Fixtures.data("leaders_core_NBA.json")
        realLeaders = try JSONDecoder().decode(CoreLeadersAPIResponse.self, from: data)
        StandInESPN.reset(leaders: data)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInESPN.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    private func teamId(ofRef ref: String?) throws -> String {
        try XCTUnwrap(URL(string: try XCTUnwrap(ref))?.lastPathComponent)
    }

    /// The first leader's team in the real payload, and every athlete leading for it.
    private func aTeamAndItsAthletes() throws -> (team: String, athletes: Set<String>) {
        let categories = try XCTUnwrap(realLeaders.categories)
        let first = try XCTUnwrap(categories.first?.leaders?.first)
        let team = try teamId(ofRef: first.team?.ref)
        var athletes = Set<String>()
        for category in categories {
            for leader in category.leaders ?? [] {
                if try teamId(ofRef: leader.team?.ref) == team {
                    athletes.insert(try XCTUnwrap(leader.athlete?.ref))
                }
            }
        }
        return (team, athletes)
    }

    func testTheWholeLeagueLooksUpEveryName() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertFalse(names.contains("—"))
        let everyAthlete = Set(try XCTUnwrap(realLeaders.categories).flatMap { $0.leaders ?? [] }.compactMap { $0.athlete?.ref })
        XCTAssertEqual(StandInESPN.athleteRequests.count, everyAthlete.count)
    }

    func testOneTeamLooksUpOnlyItsOwnPlayers() async throws {
        let (team, athletes) = try aTeamAndItsAthletes()
        let categories = try await service.fetchLeagueLeadersForTeam(teamId: "unused", teamAbbreviation: team, sport: soccer)
        XCTAssertFalse(categories.isEmpty)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertFalse(names.contains("—"), "each of its own players should have a name")
        XCTAssertEqual(StandInESPN.athleteRequests.count, athletes.count, "only this team's players")
    }

    func testAOneOffFailureGetsANameOnTheSecondTry() async throws {
        StandInESPN.lock.withLock { StandInESPN.failuresFirst = 1 }
        let categories = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        XCTAssertFalse(categories.flatMap(\.leaders).map(\.athleteName).contains("—"))
    }

    func testAFailureThatLastsReadsAsADashWithoutLosingTheRow() async throws {
        StandInESPN.lock.withLock { StandInESPN.failuresFirst = 10 }
        let categories = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertTrue(names.allSatisfy { $0 == "—" })
    }

    private var uniqueReferences: Int {
        let leaders = (realLeaders.categories ?? []).flatMap { $0.leaders ?? [] }
        return Set(leaders.compactMap { $0.athlete?.ref }).count + Set(leaders.compactMap { $0.team?.ref }).count
    }

    func testATimeoutIsNotAskedAgain() async throws {
        StandInESPN.lock.withLock { StandInESPN.referenceError = .timedOut }
        _ = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        let requests = StandInESPN.referenceRequests
        XCTAssertEqual(requests.count, Set(requests).count)
    }

    func testAStalledNetworkStopsAskingForTheRest() async throws {
        XCTAssertGreaterThan(uniqueReferences, ESPNAPIService.refFailuresBeforeGivingUp + ESPNAPIService.maxConcurrentRefRequests,
                             "the fixture should have enough references to show it")
        StandInESPN.lock.withLock { StandInESPN.referenceError = .timedOut }
        let categories = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        XCTAssertLessThan(StandInESPN.referenceRequests.count, uniqueReferences)
        XCTAssertTrue(categories.flatMap(\.leaders).allSatisfy { $0.athleteName == "—" }, "the rows are still there")
        XCTAssertFalse(categories.isEmpty)
    }

    func testALostConnectionIsAskedAgain() async throws {
        StandInESPN.lock.withLock { StandInESPN.referenceError = .networkConnectionLost }
        _ = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        let requests = StandInESPN.referenceRequests
        XCTAssertGreaterThan(requests.count, Set(requests).count)
    }

    func testALeadersRequestThatCannotConnectIsAnErrorNotAnotherSeason() async throws {
        let session: URLSession = {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [NoConnection.self]
            return URLSession(configuration: config)
        }()
        do {
            _ = try await ESPNAPIService(session: session).fetchLeagueLeaders(for: .ncaah)
            XCTFail("it should have thrown")
        } catch is URLError {
            XCTAssertEqual(NoConnection.count, 1)
        }
    }

    func testBetweenSeasonsIsLastSeasonsRegularSeasonNeverAPreseason() async throws {
        // A league with no /leaders. As in August: a preseason this year, and 404s for the rest.
        let thisYear = Sport.ncaah.currentSeasonYear
        StandInESPN.lock.withLock {
            StandInESPN.leadersStatus = { url in
                url.contains("/seasons/\(thisYear)/types/1/") || url.contains("/seasons/\(thisYear - 1)/types/2/") ? 200 : 404
            }
        }
        let categories = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        XCTAssertFalse(categories.isEmpty)
        let asked = StandInESPN.leadersRequests
        XCTAssertFalse(asked.contains { $0.contains("/types/1/") }, "\(asked)")
        XCTAssertFalse(asked.contains { $0.contains("/types/3/") }, "\(asked)")
        XCTAssertTrue(asked.last?.contains("/seasons/\(thisYear - 1)/types/2/") ?? false, "\(asked)")
    }

    // MARK: One soccer team's players, which /leaders can't give it

    func testOneSoccerTeamIsFiledUnderTypeOneForESPNsSeason() async throws {
        StandInESPN.lock.withLock { StandInESPN.season = Data(#"{"year":2031,"displayName":"2031-32 Stand-in"}"#.utf8) }
        _ = try await service.fetchLeagueLeadersForTeam(teamId: "unused", teamAbbreviation: "1", sport: soccer)
        XCTAssertTrue(StandInESPN.leadersRequests.first?.contains("/seasons/2031/types/1/") ?? false,
                      "\(StandInESPN.leadersRequests)")
    }

    func testOneSoccerTeamWithNoListYetMeansTheSeasonBefore() async throws {
        StandInESPN.lock.withLock { StandInESPN.leadersStatus = { $0.contains("/seasons/2026/") ? 404 : 200 } }
        let (team, _) = try aTeamAndItsAthletes()
        let categories = try await service.fetchLeagueLeadersForTeam(teamId: "unused", teamAbbreviation: team, sport: soccer)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertTrue(StandInESPN.leadersRequests.last?.contains("/seasons/2025/types/1/") ?? false)
    }

    func testAFailedSoccerTeamListSaysSoRatherThanShowingLastSeasons() async {
        StandInESPN.lock.withLock { StandInESPN.leadersStatus = { _ in 500 } }
        do {
            _ = try await service.fetchLeagueLeadersForTeam(teamId: "unused", teamAbbreviation: "1", sport: soccer)
            XCTFail("it should have thrown")
        } catch {
            XCTAssertEqual(StandInESPN.leadersRequests.count, 1, "no other season asked for")
        }
    }

    func testViewAllAsksForTheSameLengthAsWindows() {
        XCTAssertEqual(ESPNAPIService.siteLeadersLimit, 20)
    }

    // MARK: Nobody rated

    func testARatingWithNobodyRatedIsLeftOut() async throws {
        let data = try Fixtures.data("leaders_core_NCAAM_per.json")
        let raw = try JSONDecoder().decode(CoreLeadersAPIResponse.self, from: data)
        let per = try XCTUnwrap(raw.categories?.first { $0.name == "PER" })
        XCTAssertTrue((per.leaders ?? []).allSatisfy { $0.value == 0 }, "the fixture should show the problem")
        StandInESPN.reset(leaders: data)
        let names = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3).map(\.name)
        XCTAssertFalse(names.contains("PER"))
        XCTAssertTrue(names.contains("pointsPerGame"))
    }

    func testANotFoundIsNotAskedAgain() async throws {
        StandInESPN.lock.withLock {
            StandInESPN.failuresFirst = 10
            StandInESPN.failureStatus = 404
        }
        _ = try await service.fetchLeagueLeaders(for: .ncaah, limit: 3)
        let requests = StandInESPN.athleteRequests
        XCTAssertEqual(requests.count, Set(requests).count)
    }
}

// MARK: - Soccer, against the grid Windows is also held to

/// Answers a league's /standings with one fixture.
private final class StandInStandings: URLProtocol {
    static var body = Data()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class SoccerGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Table: Decodable {
            let fixture: String
            let groups: [Group]
        }
        struct Group: Decodable {
            let name: String
            let rows: [[String]]
        }
        struct Leaders: Decodable {
            let fixture: String
            let league: String
            let year: Int
            let season: String
            let lists: [List]
        }
        struct SeasonTypes: Decodable {
            let league: String
            let season: String
            let now: String
            let types: [Int]
            let why: String
        }
        struct List: Decodable {
            let title: String
            let rows: [Row]
        }
        struct Row: Decodable {
            let rank: Int
            let player: String
            let team: String
            let value: String
        }
        let headers: [String]
        let tables: [Table]
        let leaders: [Leaders]
        let seasonTypes: [SeasonTypes]
    }

    /// The grid's league names, which are Windows'.
    private static let sports: [String: Sport] = [
        "EPL": .soccerEPL, "MLS": .soccerMLS, "NWSL": .soccerNWSL, "La Liga": .soccerLaLiga,
        "Bundesliga": .soccerBundesliga, "Serie A": .soccerSerieA, "Ligue 1": .soccerLigue1, "UCL": .soccerUCL,
        "UEL": .soccerUEL, "Liga MX": .soccerLigaMX, "CONCACAF": .soccerCONCACAF,
    ]

    private func grid() throws -> Grid {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/soccer_grid.json")
        return try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
    }

    /// The real request, through the app's own choice of how to read a soccer league.
    private func standings(_ fixture: String) async throws -> [StandingsGroup] {
        StandInStandings.body = try Fixtures.data(fixture)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInStandings.self]
        return try await ESPNAPIService(session: URLSession(configuration: config)).fetchStandings(for: .soccerEPL)
    }

    func testTheHeadersAreTheSameInTheSameOrder() throws {
        XCTAssertEqual(SoccerTableRow.headers, try grid().headers)
    }

    func testEveryTableReadsAsTheSharedGridSays() async throws {
        let cases = try grid().tables
        XCTAssertGreaterThanOrEqual(cases.count, 6)
        for item in cases {
            let groups = try await standings(item.fixture)
            XCTAssertEqual(groups.map(\.name), item.groups.map(\.name), item.fixture)
            for (group, expected) in zip(groups, item.groups) {
                let rows = group.entries.map { $0.soccer?.cells(team: $0.team.displayName) ?? [] }
                XCTAssertEqual(rows, expected.rows, "\(item.fixture) \(expected.name)")
            }
        }
    }

    func testMLSGoesByESPNsRankNotTheOrderOfItsAnswer() async throws {
        let east = try await standings("standings_MLS.json")[0]
        let places = east.entries.compactMap { $0.soccer?.position }
        XCTAssertEqual(places, places.sorted())
        let raw = try JSONDecoder().decode(APIStandingsResponse.self, from: Fixtures.data("standings_MLS.json"))
        let answered = raw.groupsWithEntries[0].standings.entries.map { $0.team.displayName }
        XCTAssertNotEqual(east.entries.map(\.team.displayName), answered, "the fixture should show the problem")
    }

    func testAKnockoutCompetitionHasNoTable() async throws {
        let groups = try await standings("standings_CONCACAF.json")
        XCTAssertTrue(groups.isEmpty)
    }

    func testAllThreeViewsReadTheWholeRow() async throws {
        let groups = try await standings("standings_EPL.json")
        let arsenal = try XCTUnwrap(groups.first?.entries.first?.soccer)
        XCTAssertEqual(arsenal.cells(team: "ARS"), ["1", "ARS", "9", "8", "0", "1", "14", "5", "+9", "24", "Champions League"])
        XCTAssertEqual(arsenal.quickText(team: "Arsenal"), "1, Arsenal, 9, 8, 0, 1, 14, 5, +9, 24, Champions League")
        XCTAssertEqual(arsenal.fullText(team: "Arsenal"),
                       "Pos: 1; Team: Arsenal; GP: 9; W: 8; D: 0; L: 1; GF: 14; GA: 5; GD: +9; Pts: 24; Status: Champions League")
    }

    func testNoCellIsSilent() async throws {
        let rows = try await standings("standings_LigaMX.json").flatMap(\.entries).compactMap(\.soccer)
        XCTAssertFalse(rows.isEmpty)
        XCTAssertTrue(rows.allSatisfy { $0.status == SoccerTableRow.noStatus })
        XCTAssertTrue(rows.allSatisfy { row in row.cells(team: "X").allSatisfy { !$0.isEmpty } })
    }

    func testARankMissingIsItsPlaceInTheAnswer() throws {
        let json = #"{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[{"name":"wins","value":2,"displayValue":"2"}]}"#
        let entry = try JSONDecoder().decode(APIStandingsGroup.APIStandings.APIStandingsEntry.self, from: Data(json.utf8))
        XCTAssertEqual(SoccerTableRow(fromAPIEntry: entry, place: 7).position, 7)
        XCTAssertEqual(SoccerTableRow(fromAPIEntry: entry, place: 7).goalDifference, "0")
    }

    func testAGoalDifferenceWithNoTextReadsWithItsSign() throws {
        func row(_ value: Int) throws -> SoccerTableRow {
            let json = #"{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[{"name":"pointDifferential","value":\#(value),"displayValue":""}]}"#
            let entry = try JSONDecoder().decode(APIStandingsGroup.APIStandings.APIStandingsEntry.self, from: Data(json.utf8))
            return SoccerTableRow(fromAPIEntry: entry, place: 1)
        }
        XCTAssertEqual(try row(9).goalDifference, "+9")
        XCTAssertEqual(try row(-3).goalDifference, "-3")
    }

    func testANullNumberFallsBackToItsText() throws {
        let json = #"{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[{"name":"wins","value":null,"displayValue":"8"},{"name":"losses","value":null,"displayValue":"not a number"}]}"#
        let entry = try JSONDecoder().decode(APIStandingsGroup.APIStandings.APIStandingsEntry.self, from: Data(json.utf8))
        let row = SoccerTableRow(fromAPIEntry: entry, place: 1)
        XCTAssertEqual(row.wins, 8)
        XCTAssertEqual(row.losses, 0)
    }

    func testEveryLeagueInTheGridIsOneTheAppKnows() {
        XCTAssertEqual(Set(Self.sports.values), Set(Sport.soccerLeagues))
    }

    func testEveryListOfLeadersReadsAsTheSharedGridSays() throws {
        let cases = try grid().leaders
        XCTAssertGreaterThanOrEqual(cases.count, 4)
        for item in cases {
            let sport = try XCTUnwrap(Self.sports[item.league], item.league)
            let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Fixtures.data(item.fixture))
            let categories = ESPNAPIService.soccerLeaderCategories(from: response, sport: sport, year: item.year)
            XCTAssertEqual(categories.map(\.displayName), item.lists.map(\.title), item.fixture)
            for (category, expected) in zip(categories, item.lists) {
                XCTAssertEqual(category.seasonLabel, item.season, item.fixture)
                XCTAssertEqual(category.leaders.map(\.rank), expected.rows.map(\.rank), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.athleteName), expected.rows.map(\.player), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.teamAbbreviation), expected.rows.map(\.team), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.displayValue), expected.rows.map(\.value), "\(item.fixture) \(expected.title)")
            }
        }
    }

    func testEveryChoiceOfSeasonTypeIsAsTheSharedGridSays() throws {
        let cases = try grid().seasonTypes
        XCTAssertGreaterThanOrEqual(cases.count, 8)
        let iso = ISO8601DateFormatter()
        for item in cases {
            let sport = try XCTUnwrap(Self.sports[item.league], item.league)
            let season = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Fixtures.data(item.season))
            let now = try XCTUnwrap(iso.date(from: item.now), item.now)
            XCTAssertEqual(ESPNAPIService.soccerLeadersSeasonTypes(sport: sport, season: season, now: now), item.types,
                           "\(item.league) \(item.now): \(item.why)")
        }
    }

    func testASeasonWithNoTypesListedAsksForTheApertura() throws {
        let season = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Data(#"{"year":2026}"#.utf8))
        XCTAssertEqual(ESPNAPIService.soccerLeadersSeasonTypes(sport: .soccerLigaMX, season: season, now: Date()), [1])
        XCTAssertEqual(ESPNAPIService.soccerLeadersSeasonTypes(sport: .soccerLigaMX, season: nil, now: Date()), [1])
    }

    func testAnAperturaWithNoDateIsTakenAsStartedAndAClausuraWithNoneIsNot() throws {
        let json = #"{"year":2026,"types":{"items":[{"id":"1","name":"Torneo Apertura"},{"id":"5","name":"Torneo Clausura","startDate":"soon"},{"id":7,"name":"Torneo Clausura","startDate":"2027-01-01T05:00Z"}]}}"#
        let season = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Data(json.utf8))
        let february = try XCTUnwrap(ISO8601DateFormatter().date(from: "2027-02-01T00:00:00Z"))
        XCTAssertEqual(ESPNAPIService.soccerLeadersSeasonTypes(sport: .soccerLigaMX, season: season, now: february), [7, 1],
                       "an id ESPN writes as a number still counts")
    }

    func testAnOddSeasonTypeDoesNotLoseTheSeason() throws {
        let json = #"{"year":2026,"displayName":"2026-27","types":{"items":[null,{"id":{"x":1}},{"id":"1","startDate":"2026-06-01T04:00Z"}]}}"#
        let season = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Data(json.utf8))
        XCTAssertEqual(season.displayName, "2026-27")
        XCTAssertEqual(season.types?.items?.compactMap(\.id), [1])
    }

    func testOnlyLigaMXHasTorneos() throws {
        let season = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Fixtures.data("season_LigaMX.json"))
        XCTAssertEqual(ESPNAPIService.torneoLeagues, [.soccerLigaMX])
        XCTAssertEqual(ESPNAPIService.soccerLeadersSeasonTypes(sport: .soccerUCL, season: season, now: Date()), [1])
    }

    func testAStatusLosesESPNsStrayTab() throws {
        let json = #"{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[],"note":{"description":"Eliminated\t"}}"#
        let entry = try JSONDecoder().decode(APIStandingsGroup.APIStandings.APIStandingsEntry.self, from: Data(json.utf8))
        XCTAssertEqual(SoccerTableRow(fromAPIEntry: entry, place: 1).status, "Eliminated")
    }

    private func soccerLists(_ json: String, sport: Sport = .soccerEPL) throws -> [LeagueLeaderCategory] {
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        return ESPNAPIService.soccerLeaderCategories(from: response, sport: sport, year: 2026)
    }

    func testAListWithNoNameIsCalledByItsKey() throws {
        let lists = try soccerLists(#"{"leaders":{"categories":[{"name":"goals","leaders":[{"value":3,"displayValue":"3","athlete":{"displayName":"A"}}]}]}}"#)
        XCTAssertEqual(lists.first?.displayName, "Goals")
    }

    func testANameOrTeamMissingKeepsTheRowAndSaysSo() throws {
        let lists = try soccerLists(#"{"leaders":{"categories":[{"name":"goals","displayName":"Goals","leaders":[{"value":3,"displayValue":"3"},{"value":2,"displayValue":"","athlete":{"displayName":"B"},"team":{"abbreviation":"BBB"}}]}]}}"#)
        let rows = try XCTUnwrap(lists.first?.leaders)
        XCTAssertEqual(rows.map(\.athleteName), [ESPNAPIService.nameUnavailable, "B"])
        XCTAssertEqual(rows.map(\.teamAbbreviation), [SoccerTableRow.noStatus, "BBB"])
        XCTAssertEqual(rows.map(\.displayValue), ["3", "2"], "a value with no text reads as its number")
    }

    func testARepeatedSoccerListIsLeftOutAndOneThatDiffersStays() throws {
        let row = #"{"value":3,"displayValue":"3","athlete":{"displayName":"A"},"team":{"abbreviation":"T"}}"#
        let other = #"{"value":4,"displayValue":"4","athlete":{"displayName":"A"},"team":{"abbreviation":"T"}}"#
        let lists = try soccerLists(#"{"leaders":{"categories":[{"name":"goalsLeaders","displayName":"Goals","leaders":[\#(row)]},{"name":"goals","displayName":"Goals","leaders":[\#(row)]},{"name":"third","displayName":"Goals","leaders":[\#(other)]}]}}"#)
        XCTAssertEqual(lists.map(\.name), ["goalsLeaders", "third"])
    }

    func testOnlyLigaMXNamesItsTorneo() throws {
        let json = #"{"requestedSeason":{"displayName":"2026-27 Liga","type":{"type":14277,"name":"Torneo Apertura"}},"leaders":{"categories":[{"name":"goals","leaders":[{"value":3,"displayValue":"3"}]}]}}"#
        XCTAssertEqual(try soccerLists(json, sport: .soccerLigaMX).first?.seasonLabel, "2026-27 Liga Torneo Apertura")
        XCTAssertEqual(try soccerLists(json, sport: .soccerCONCACAF).first?.seasonLabel, "2026-27 Liga")
        let unnamed = #"{"leaders":{"categories":[{"name":"goals","leaders":[{"value":3,"displayValue":"3"}]}]}}"#
        XCTAssertEqual(try soccerLists(unnamed).first?.seasonLabel, "2026", "the year still says which season")
    }

    func testAListThatDiffersInARowStays() throws {
        let row = #"{"value":3,"displayValue":"3","athlete":{"$ref":"a"},"team":{"$ref":"t"}}"#
        let other = #"{"value":4,"displayValue":"4","athlete":{"$ref":"a"},"team":{"$ref":"t"}}"#
        let json = #"{"categories":[{"name":"goalsLeaders","displayName":"Goals","leaders":[\#(row)]},{"name":"goals","displayName":"Goals","leaders":[\#(row)]},{"name":"third","displayName":"Goals","leaders":[\#(other)]}]}"#
        let response = try JSONDecoder().decode(CoreLeadersAPIResponse.self, from: Data(json.utf8))
        XCTAssertEqual(ESPNAPIService.coreLeaderLists(response).map(\.name), ["goalsLeaders", "third"])
    }
}

// MARK: - /leaders

final class LeaderListGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Case: Decodable {
            let fixture: String
            let season: String?
            let categories: [Category]
        }
        struct Category: Decodable {
            let title: String
            let rows: [Row]
        }
        struct Row: Decodable {
            let rank: Int
            let player: String
            let team: String
            let value: String
        }
        let cases: [Case]
    }

    func testEveryRealAnswerReadsAsTheSharedGridSays() throws {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/leader_lists_grid.json")
        let grid = try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
        XCTAssertGreaterThanOrEqual(grid.cases.count, 7)
        for item in grid.cases {
            let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Fixtures.data(item.fixture))
            let categories = ESPNAPIService.leaderCategories(from: response)
            XCTAssertEqual(categories.map(\.displayName), item.categories.map(\.title), item.fixture)
            for (category, expected) in zip(categories, item.categories) {
                XCTAssertEqual(category.seasonLabel, item.season, item.fixture)
                XCTAssertEqual(category.leaders.map(\.rank), expected.rows.map(\.rank), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.athleteName), expected.rows.map(\.player), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.teamAbbreviation), expected.rows.map(\.team), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.displayValue), expected.rows.map(\.value), "\(item.fixture) \(expected.title)")
            }
        }
    }

    private struct TeamHubGrid: Decodable {
        struct Case: Decodable {
            let fixture: String
            let season: String
            let categories: [Category]
        }
        struct Category: Decodable {
            let title: String
            let rows: [Row]
        }
        struct Row: Decodable {
            let rank: Int
            let player: String
            let value: String
        }
        let players: [Case]
    }

    /// One team's answer, as Team Hub's Stats tab reads it on both apps.
    func testOneTeamReadsAsTheSharedTeamHubGridSays() throws {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/team_hub_stats_grid.json")
        let grid = try JSONDecoder().decode(TeamHubGrid.self, from: Data(contentsOf: url))
        XCTAssertGreaterThanOrEqual(grid.players.count, 3)
        for item in grid.players {
            let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Fixtures.data(item.fixture))
            let categories = ESPNAPIService.leaderCategories(from: response, oneTeam: true)
            XCTAssertEqual(categories.map(\.displayName), item.categories.map(\.title), item.fixture)
            for (category, expected) in zip(categories, item.categories) {
                XCTAssertEqual(category.seasonLabel, item.season, item.fixture)
                XCTAssertEqual(category.leaders.map(\.rank), expected.rows.map(\.rank), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.athleteName), expected.rows.map(\.player), "\(item.fixture) \(expected.title)")
                XCTAssertEqual(category.leaders.map(\.displayValue), expected.rows.map(\.value), "\(item.fixture) \(expected.title)")
            }
        }
    }

    func testAListWithNoRealMinimumIsLeftOut() throws {
        let row = #"{"value":0,"displayValue":"1.0 IP","athlete":{"displayName":"A"}},{"value":0.25,"displayValue":"60 IP","athlete":{"displayName":"B"}}"#
        let json = #"{"leaders":{"categories":[{"name":"opponentAvg","displayName":"Opp","leaders":[\#(row)]},{"name":"ERA","displayName":"ERA","leaders":[\#(row)]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        XCTAssertEqual(ESPNAPIService.leaderCategories(from: response).map(\.name), ["ERA"])
    }

    func testANullCategoryOrRowDoesNotLoseTheList() throws {
        let json = #"{"leaders":{"categories":[null,{"name":"sacks","displayName":"Sacks","leaders":[null,{"value":3,"displayValue":"3","athlete":{"displayName":"B"}}]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        XCTAssertEqual(ESPNAPIService.leaderCategories(from: response).first?.leaders.map(\.athleteName), ["B"])
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("leaders") {
            let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(contentsOf: file))
            XCTAssertFalse(ESPNAPIService.leaderCategories(from: response).isEmpty, file.lastPathComponent)
        }
    }

    func testAPreseasonIsNothingToShow() throws {
        let json = #"{"requestedSeason":{"displayName":"2026","type":{"type":1,"name":"Preseason"}},"leaders":{"categories":[{"name":"sacks","displayName":"Sacks","leaders":[{"value":3,"displayValue":"3","athlete":{"displayName":"A"}}]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        XCTAssertTrue(ESPNAPIService.leaderCategories(from: response).isEmpty)
    }

    func testARatingWithNobodyRatedIsLeftOut() throws {
        let json = #"{"leaders":{"categories":[{"name":"PER","displayName":"PER","leaders":[{"value":0,"displayValue":"0.0","athlete":{"displayName":"A"}}]},{"name":"sacks","displayName":"Sacks","leaders":[{"value":3,"displayValue":"3","athlete":{"displayName":"A"}}]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        XCTAssertEqual(ESPNAPIService.leaderCategories(from: response).map(\.name), ["sacks"])
    }

    func testAListStopsAtTheFirstWhoBreaksItsDirection() throws {
        let row = { (value: Double) in #"{"value":\#(value),"displayValue":"\#(value)","athlete":{"displayName":"P\#(value)"}}"# }
        let highFirst = [71.4, 64.3, 100.0, 100.0].map(row).joined(separator: ",")
        let lowFirst = [1.8, 2.1, 0.5].map(row).joined(separator: ",")
        let json = #"{"leaders":{"categories":[{"name":"fieldGoalPercentage","displayName":"FG","leaders":[\#(highFirst)]},{"name":"ERA","displayName":"ERA","leaders":[\#(lowFirst)]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        let categories = ESPNAPIService.leaderCategories(from: response)
        XCTAssertEqual(categories[0].leaders.count, 2)
        XCTAssertEqual(categories[1].leaders.count, 2)
    }

    func testPlayersLevelOnANumberShareARank() {
        XCTAssertEqual(ESPNAPIService.sharedRanks(["7.5", "7.5", "7", "7", "6.5"]), [1, 1, 3, 3, 5])
        XCTAssertEqual(ESPNAPIService.sharedRanks([]), [])
    }

    func testAnOddValueDoesNotLoseTheList() throws {
        let json = #"{"leaders":{"categories":[{"name":"sacks","displayName":"Sacks","leaders":[{"value":"n/a","displayValue":"3","athlete":{"displayName":"A"}},{"value":3,"displayValue":"3","athlete":{"displayName":"B"}}]}]}}"#
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Data(json.utf8))
        XCTAssertEqual(ESPNAPIService.leaderCategories(from: response).first?.leaders.count, 2)
    }
}

/// Stands in for ESPN's /leaders and its idea of the season.
private final class StandInSiteLeaders: URLProtocol {
    static let lock = NSLock()
    static var leaders = Data()
    static var seasonYear = 2027
    static var seasonType = 2
    static var requests = [URL]()
    /// The status of a /leaders request, by its URL. 200 sends `leaders`.
    static var leadersStatus: (URL) -> Int = { _ in 200 }
    static var leadersAnswer: ((URL) -> Data)?

    static func reset(leaders: Data) {
        lock.withLock {
            self.leaders = leaders
            seasonYear = 2027
            seasonType = 2
            requests = []
            leadersStatus = { _ in 200 }
            leadersAnswer = nil
        }
    }

    static var leadersRequests: [URL] {
        lock.withLock { requests.filter { $0.path.hasSuffix("/leaders") } }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let (status, body): (Int, Data) = Self.lock.withLock {
            Self.requests.append(url)
            if url.path.hasSuffix("/season") {
                return (200, Data(#"{"year":\#(Self.seasonYear),"type":{"type":\#(Self.seasonType)}}"#.utf8))
            }
            let status = Self.leadersStatus(url)
            guard status == 200 else { return (status, Data()) }
            return (200, Self.leadersAnswer?(url) ?? Self.leaders)
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class SiteLeadersRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private let nobodyYet = Data(#"{"requestedSeason":{"displayName":"2026-27","type":{"type":2}},"leaders":{"categories":[]}}"#.utf8)

    override func setUpWithError() throws {
        StandInSiteLeaders.reset(leaders: try Fixtures.data("leaders_v3_NBA.json"))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInSiteLeaders.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    private func query(_ url: URL, _ name: String) -> String? {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == name }?.value
    }

    func testItAsksWhatWindowsAsks() async throws {
        _ = try await service.fetchLeagueLeaders(for: .nba)
        let url = try XCTUnwrap(StandInSiteLeaders.leadersRequests.first)
        XCTAssertEqual(url.host, "site.web.api.espn.com")
        XCTAssertEqual(url.path, "/apis/site/v3/sports/basketball/nba/leaders")
        XCTAssertEqual(query(url, "region"), "us")
        XCTAssertEqual(query(url, "lang"), "en")
        XCTAssertEqual(query(url, "season"), "2027")
        XCTAssertEqual(query(url, "seasontype"), "2")
        XCTAssertEqual(query(url, "limit"), "20")
        XCTAssertNil(query(url, "team"))
    }

    func testEveryLeagueWindowsHasLeadersForAsksThere() async throws {
        for sport: Sport in [.nfl, .ncaaf, .nba, .wnba, .ncaam, .ncaawb, .nhl, .mlb] {
            StandInSiteLeaders.lock.withLock { StandInSiteLeaders.requests = [] }
            _ = try await service.fetchLeagueLeaders(for: sport)
            XCTAssertEqual(StandInSiteLeaders.leadersRequests.first?.host, "site.web.api.espn.com", sport.rawValue)
        }
    }

    func testNamesComeFromTheAnswerWithNoLookups() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertFalse(categories.flatMap(\.leaders).map(\.athleteName).contains("—"))
        let lookups = StandInSiteLeaders.lock.withLock {
            StandInSiteLeaders.requests.filter { !$0.path.hasSuffix("/leaders") && !$0.path.hasSuffix("/season") }
        }
        XCTAssertEqual(lookups, [])
    }

    func testItSaysWhichSeason() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Regular Season")
    }

    func testTheLimitCutsTheListAndKeepsTheSeason() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .nba, limit: 1)
        XCTAssertTrue(categories.allSatisfy { $0.leaders.count == 1 })
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Regular Season")
    }

    func testAPreseasonMeansLastSeason() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.seasonType = 1 }
        _ = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertEqual(query(try XCTUnwrap(StandInSiteLeaders.leadersRequests.first), "season"), "2026")
    }

    func testAPlayoffOrOffSeasonIsStillItsOwnYear() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.seasonType = 4 }
        _ = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertEqual(query(try XCTUnwrap(StandInSiteLeaders.leadersRequests.first), "season"), "2027")
    }

    func testANewSeasonWithNobodyOnTheListMeansLastSeason() async throws {
        let empty = nobodyYet
        let real = StandInSiteLeaders.lock.withLock { StandInSiteLeaders.leaders }
        StandInSiteLeaders.lock.withLock {
            StandInSiteLeaders.leadersAnswer = { url in url.absoluteString.contains("season=2027") ? empty : real }
        }
        let categories = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(StandInSiteLeaders.leadersRequests.map { self.query($0, "season") }, ["2027", "2026"])
    }

    func testANewSeasonThatIsA404MeansLastSeason() async throws {
        StandInSiteLeaders.lock.withLock {
            StandInSiteLeaders.leadersStatus = { $0.absoluteString.contains("season=2027") ? 404 : 200 }
        }
        let categories = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertFalse(categories.isEmpty)
    }

    func testNeitherSeasonExistingIsAFailureNotNoData() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.leadersStatus = { _ in 404 } }
        do {
            _ = try await service.fetchLeagueLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {}
    }

    func testAFailureIsTriedAgainFreshThenStepsDown() async throws {
        StandInSiteLeaders.lock.withLock {
            StandInSiteLeaders.leadersStatus = { $0.absoluteString.contains("limit=10") ? 200 : 500 }
        }
        let categories = try await service.fetchLeagueLeaders(for: .nba)
        XCTAssertFalse(categories.isEmpty)
        let asked = StandInSiteLeaders.leadersRequests
        XCTAssertEqual(asked.map { self.query($0, "limit") }, ["20", "20", "10"])
        XCTAssertNil(query(asked[0], "_"))
        XCTAssertNotNil(query(asked[1], "_"), "ESPN can cache a 500")
    }

    func testFailingAtEveryLimitIsAFailure() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.leadersStatus = { _ in 500 } }
        do {
            _ = try await service.fetchLeagueLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch {
            XCTAssertEqual(StandInSiteLeaders.leadersRequests.map { self.query($0, "limit") }, ["20", "20", "10", "5"])
        }
    }

    func testARefusalIsNotAskedAgain() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.leadersStatus = { _ in 403 } }
        do {
            _ = try await service.fetchLeagueLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch {
            XCTAssertEqual(StandInSiteLeaders.leadersRequests.count, 1)
        }
    }

    func testOneTeamAsksForThatTeamAndClearsTheTeamColumn() async throws {
        let categories = try await service.fetchLeagueLeadersForTeam(teamId: "13", teamAbbreviation: "LAL", sport: .nba)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(query(try XCTUnwrap(StandInSiteLeaders.leadersRequests.first), "team"), "13")
        XCTAssertTrue(categories.flatMap(\.leaders).allSatisfy { $0.teamAbbreviation.isEmpty })
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Regular Season, ranked within this team, qualified players first")
    }

    func testOneTeamsLabelSaysWhatItsRanksAre() async throws {
        StandInSiteLeaders.reset(leaders: try Fixtures.data("leaders_v3_team_NFL_3.json"))
        let categories = try await service.fetchLeagueLeadersForTeam(teamId: "3", teamAbbreviation: "CHI", sport: .nfl)
        XCTAssertEqual(categories.first?.seasonLabel, "2025 Regular Season, ranked within this team, qualified players first")
    }

    // MARK: Real answers for one team

    private func oneTeam(_ fixture: String) throws -> [LeagueLeaderCategory] {
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Fixtures.data(fixture))
        return ESPNAPIService.leaderCategories(from: response, oneTeam: true)
    }

    func testOneTeamKeepsThePlayersBehindItsQualifiedOnes() throws {
        let points = try XCTUnwrap(try oneTeam("leaders_v3_team_NBA_14.json").first { $0.name == "pointsPerGame" })
        XCTAssertTrue(points.leaders.map(\.athleteName).contains("Tyler Herro"))
        XCTAssertEqual(points.leaders.count, 13)
    }

    func testTheLeagueRuleWouldHaveLostThem() throws {
        let response = try JSONDecoder().decode(SiteLeadersResponse.self, from: Fixtures.data("leaders_v3_team_NBA_14.json"))
        let points = try XCTUnwrap(ESPNAPIService.leaderCategories(from: response).first { $0.name == "pointsPerGame" })
        XCTAssertFalse(points.leaders.map(\.athleteName).contains("Tyler Herro"))
    }

    func testOneTeamsOnBasePercentageReadsAsOne() throws {
        let onBase = try XCTUnwrap(try oneTeam("leaders_v3_team_MLB_30.json").first { $0.name == "onBasePct" })
        XCTAssertEqual(onBase.leaders.first?.displayValue, ".360")
    }

    func testOneTeamDoesNotRepeatItsYardsLists() throws {
        XCTAssertEqual(try oneTeam("leaders_v3_team_NFL_3.json").map(\.name), ["passingYards", "sacks"])
    }

    func testOneTeamsRanksShareATieBelowTheTop() throws {
        let sacks = try XCTUnwrap(try oneTeam("leaders_v3_team_NFL_3.json").first { $0.name == "sacks" })
        XCTAssertEqual(Array(sacks.leaders.map(\.rank).prefix(6)), [1, 2, 3, 4, 5, 5])
    }

    func testALeagueWithNoLeadersThereNeverAsksThere() async throws {
        StandInSiteLeaders.lock.withLock { StandInSiteLeaders.leadersStatus = { _ in 404 } }
        _ = try await service.fetchLeagueLeaders(for: .ncaah)
        XCTAssertFalse(StandInSiteLeaders.leadersRequests.contains { $0.host == "site.web.api.espn.com" })
    }
}

// MARK: - Soccer's /leaders, as on Windows

/// Stands in for ESPN's soccer /leaders, its season now and a season by its year.
private final class StandInSoccerLeaders: URLProtocol {
    static let lock = NSLock()
    static var requests = [URL]()
    static var season = Data()
    static var seasonStatus = 200
    /// A season asked for by its year: its answer, or a 404 if there's none.
    static var seasonsByYear = [Int: (Int, Data)]()
    /// A /leaders answer, by its URL.
    static var leaders: (URL) -> (Int, Data) = { _ in (404, Data()) }

    static func reset(season: Data, leaders: Data) {
        lock.withLock {
            requests = []
            self.season = season
            seasonStatus = 200
            seasonsByYear = [:]
            self.leaders = { _ in (200, leaders) }
        }
    }

    static var leadersRequests: [URL] {
        lock.withLock { requests.filter { $0.path.hasSuffix("/leaders") } }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let (status, body): (Int, Data) = Self.lock.withLock {
            Self.requests.append(url)
            if url.path.hasSuffix("/season") { return (Self.seasonStatus, Self.season) }
            if url.path.contains("/seasons/"), let year = Int(url.lastPathComponent) {
                return Self.seasonsByYear[year] ?? (404, Data())
            }
            return Self.leaders(url)
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class SoccerLeadersRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private let iso = ISO8601DateFormatter()

    override func setUpWithError() throws {
        StandInSoccerLeaders.reset(season: try Fixtures.data("season_EPL.json"), leaders: try Fixtures.data("leaders_v3_EPL.json"))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInSoccerLeaders.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    private func query(_ url: URL, _ name: String) -> String? {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == name }?.value
    }

    /// (season, season type, limit) of each /leaders request.
    private var asked: [[String?]] {
        StandInSoccerLeaders.leadersRequests.map { [query($0, "season"), query($0, "seasontype"), query($0, "limit")] }
    }

    private func answer(_ fixture: String) throws -> (Int, Data) {
        (200, try Fixtures.data(fixture))
    }

    private func date(_ text: String) throws -> Date {
        try XCTUnwrap(iso.date(from: text))
    }

    func testItAsksWhatWindowsAsksInOneRequestWithTheNamesInside() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .soccerEPL, limit: 20)
        let url = try XCTUnwrap(StandInSoccerLeaders.leadersRequests.first)
        XCTAssertEqual(url.host, "site.web.api.espn.com")
        XCTAssertEqual(url.path, "/apis/site/v3/sports/soccer/eng.1/leaders")
        XCTAssertEqual(query(url, "region"), "us")
        XCTAssertEqual(query(url, "lang"), "en")
        XCTAssertEqual(asked, [["2026", "1", "20"]])
        let requests = StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.requests }
        XCTAssertEqual(requests.count, 2, "the season and the list")
        let first = try XCTUnwrap(categories.first?.leaders.first)
        XCTAssertEqual([first.athleteName, first.teamAbbreviation, first.displayValue], ["Erling Haaland", "MNC", "9"])
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 English Premier League")
        XCTAssertEqual(categories.count, 10, "goals and assists are each listed twice")
    }

    func testTheLimitCutsTheListAndKeepsTheSeason() async throws {
        let categories = try await service.fetchLeagueLeaders(for: .soccerEPL, limit: 1)
        XCTAssertTrue(categories.allSatisfy { $0.leaders.count == 1 })
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 English Premier League")
    }

    func testALeagueInItsPlayoffsStillAsksForTypeOne() async throws {
        let season = try Fixtures.data("season_NWSL.json")
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.season = season }
        _ = try await service.fetchLeagueLeaders(for: .soccerNWSL)
        XCTAssertEqual(asked, [["2026", "1", "20"]])
        XCTAssertEqual(StandInSoccerLeaders.leadersRequests.first?.path, "/apis/site/v3/sports/soccer/usa.nwsl/leaders")
    }

    func testTheSeasonComesFromESPNNotTheCalendar() async throws {
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.season = Data(#"{"year":2031}"#.utf8) }
        _ = try await service.fetchLeagueLeaders(for: .soccerEPL)
        XCTAssertEqual(asked.first?.first, "2031")
    }

    func testNoListYetMeansTheSeasonBefore() async throws {
        let real = try answer("leaders_v3_EPL.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.leaders = { url in url.absoluteString.contains("season=2026") ? (404, Data()) : real }
        }
        let categories = try await service.fetchLeagueLeaders(for: .soccerEPL)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(asked.map { $0[0] }, ["2026", "2025"])
        let requests = StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.requests }
        XCTAssertFalse(requests.contains { $0.path.contains("/seasons/") }, "only Liga MX needs an earlier season's types")
    }

    func testAnAnswerWithNobodyOnItAlsoMeansTheSeasonBefore() async throws {
        let empty = try answer("leaders_v3_LigaMX_clausura_empty.json")
        let real = try answer("leaders_v3_EPL.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.leaders = { url in url.absoluteString.contains("season=2026") ? empty : real }
        }
        let categories = try await service.fetchLeagueLeaders(for: .soccerEPL)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(asked.map { $0[0] }, ["2026", "2025"])
    }

    func testThreeSeasonsOfNothingIsAnHonestNothing() async throws {
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.leaders = { _ in (404, Data()) } }
        let categories = try await service.fetchLeagueLeaders(for: .soccerEPL)
        XCTAssertTrue(categories.isEmpty)
        XCTAssertEqual(asked.map { $0[0] }, ["2026", "2025", "2024"])
    }

    func testAFailedListSaysSoRatherThanShowingLastSeasons() async {
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.leaders = { _ in (500, Data()) } }
        do {
            _ = try await service.fetchLeagueLeaders(for: .soccerCONCACAF)
            XCTFail("it should have thrown")
        } catch {
            XCTAssertEqual(asked.map { $0[2] }, ["20", "20", "10", "5"])
            XCTAssertEqual(Set(asked.map { $0[0] }), ["2026"], "no other season asked for")
        }
    }

    func testA500IsTriedAgainFreshThenStepsDownTo10() async throws {
        let real = try answer("leaders_v3_EPL.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.leaders = { url in url.absoluteString.contains("limit=10") ? real : (500, Data()) }
        }
        let categories = try await service.fetchLeagueLeaders(for: .soccerNWSL)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(asked.map { $0[2] }, ["20", "20", "10"])
        let urls = StandInSoccerLeaders.leadersRequests
        XCTAssertNil(query(urls[0], "_"))
        XCTAssertNotNil(query(urls[1], "_"), "ESPN can cache a 500")
    }

    func testTheSeasonFailingIsAFailure() async {
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.seasonStatus = 500 }
        do {
            _ = try await service.fetchLeagueLeaders(for: .soccerUCL)
            XCTFail("it should have thrown")
        } catch {
            XCTAssertTrue(StandInSoccerLeaders.leadersRequests.isEmpty)
        }
    }

    // MARK: Liga MX's torneos (#178)

    private func ligaMX() throws {
        StandInSoccerLeaders.reset(season: try Fixtures.data("season_LigaMX.json"),
                                   leaders: try Fixtures.data("leaders_v3_LigaMX.json"))
    }

    func testTheAperturaIsTypeOneAndSaysSo() async throws {
        try ligaMX()
        let categories = try await service.fetchSoccerLeaders(for: .soccerLigaMX, now: try date("2026-11-07T12:00:00Z"))
        XCTAssertEqual(asked, [["2026", "1", "20"]])
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Liga BBVA MX Torneo Apertura")
    }

    func testAClausuraWithNobodyOnItYetMeansTheAperturaBeforeIt() async throws {
        try ligaMX()
        let empty = try answer("leaders_v3_LigaMX_clausura_empty.json")
        let apertura = try answer("leaders_v3_LigaMX.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.leaders = { url in url.absoluteString.contains("seasontype=5") ? empty : apertura }
        }
        let categories = try await service.fetchSoccerLeaders(for: .soccerLigaMX, now: try date("2027-01-02T12:00:00Z"))
        XCTAssertEqual(asked, [["2026", "5", "20"], ["2026", "1", "20"]])
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Liga BBVA MX Torneo Apertura")
    }

    func testBeforeTheAperturaItIsLastSeasonsClausuraWhateverItsNumber() async throws {
        try ligaMX()
        let lastSeason = try answer("season_LigaMX_2025.json")
        let clausura = try answer("leaders_v3_LigaMX_2025_clausura.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.seasonsByYear = [2025: lastSeason]
            StandInSoccerLeaders.leaders = { url in url.absoluteString.contains("seasontype=8") ? clausura : (404, Data()) }
        }
        let categories = try await service.fetchSoccerLeaders(for: .soccerLigaMX, now: try date("2026-05-31T12:00:00Z"))
        XCTAssertEqual(asked, [["2025", "8", "20"]])
        XCTAssertEqual(categories.first?.seasonLabel, "2025-26 Liga BBVA MX Torneo Clausura")
    }

    func testAnEarlierSeasonNotComingSaysSo() async throws {
        try ligaMX()
        StandInSoccerLeaders.lock.withLock { StandInSoccerLeaders.seasonsByYear = [2025: (500, Data())] }
        do {
            _ = try await service.fetchSoccerLeaders(for: .soccerLigaMX, now: try date("2026-05-31T12:00:00Z"))
            XCTFail("it should have thrown")
        } catch {
            XCTAssertTrue(asked.isEmpty)
        }
    }

    func testAtMostThreeListsAreAskedFor() async throws {
        try ligaMX()
        let empty = try answer("leaders_v3_LigaMX_clausura_empty.json")
        let lastSeason = try answer("season_LigaMX_2025.json")
        StandInSoccerLeaders.lock.withLock {
            StandInSoccerLeaders.seasonsByYear = [2025: lastSeason]
            StandInSoccerLeaders.leaders = { _ in empty }
        }
        let categories = try await service.fetchSoccerLeaders(for: .soccerLigaMX, now: try date("2027-02-01T12:00:00Z"))
        XCTAssertTrue(categories.isEmpty)
        XCTAssertEqual(asked.map { [$0[0], $0[1]] }, [["2026", "5"], ["2026", "1"], ["2025", "8"]])
    }
}
