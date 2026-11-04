//
//  LeagueLeadersTests.swift
//  SportsScoresTests
//
//  How a leader's number reads, against the grid Windows is also held to, and how many
//  requests a team's leaders take, against the real core API payload with a stand-in for ESPN.
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

    static func reset(leaders: Data) {
        lock.withLock {
            self.leaders = leaders
            requests = []
            failuresFirst = 0
            failureStatus = 503
            failures = [:]
        }
    }

    static var athleteRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/athletes/") } }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
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
        if text.contains("/leaders") {
            return (200, leaders)
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

final class LeagueLeadersRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private var realLeaders: CoreLeadersAPIResponse!

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
        let categories = try await service.fetchLeagueLeaders(for: .nba, limit: 3)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertFalse(names.contains("—"))
        let everyAthlete = Set(try XCTUnwrap(realLeaders.categories).flatMap { $0.leaders ?? [] }.compactMap { $0.athlete?.ref })
        XCTAssertEqual(StandInESPN.athleteRequests.count, everyAthlete.count)
    }

    func testOneTeamLooksUpOnlyItsOwnPlayers() async throws {
        let (team, athletes) = try aTeamAndItsAthletes()
        let categories = try await service.fetchLeagueLeadersForTeam(teamAbbreviation: team, sport: .nba)
        XCTAssertFalse(categories.isEmpty)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertFalse(names.contains("—"), "each of its own players should have a name")
        XCTAssertEqual(StandInESPN.athleteRequests.count, athletes.count, "only this team's players")
    }

    func testAOneOffFailureGetsANameOnTheSecondTry() async throws {
        StandInESPN.lock.withLock { StandInESPN.failuresFirst = 1 }
        let categories = try await service.fetchLeagueLeaders(for: .nba, limit: 3)
        XCTAssertFalse(categories.flatMap(\.leaders).map(\.athleteName).contains("—"))
    }

    func testAFailureThatLastsReadsAsADashWithoutLosingTheRow() async throws {
        StandInESPN.lock.withLock { StandInESPN.failuresFirst = 10 }
        let categories = try await service.fetchLeagueLeaders(for: .nba, limit: 3)
        let names = categories.flatMap(\.leaders).map(\.athleteName)
        XCTAssertFalse(names.isEmpty)
        XCTAssertTrue(names.allSatisfy { $0 == "—" })
    }

    func testANotFoundIsNotAskedAgain() async throws {
        StandInESPN.lock.withLock {
            StandInESPN.failuresFirst = 10
            StandInESPN.failureStatus = 404
        }
        _ = try await service.fetchLeagueLeaders(for: .nba, limit: 3)
        let requests = StandInESPN.athleteRequests
        XCTAssertEqual(requests.count, Set(requests).count)
    }
}
