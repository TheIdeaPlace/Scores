//
//  RacingGridTests.swift
//  SportsScoresTests
//
//  tests/fixtures/racing_grid.json holds both apps to the same reading of ESPN's racing
//  answers: which competition is the race, its status and date, whether its field is results
//  or an entry list, the winner, and the standings. tests/unit/test_racing.py holds racing.py
//  on Windows to the same file. The answers go through the app's own requests, from the real
//  fixtures in tests/fixtures/espn.
//

import XCTest
@testable import SportsScores

private final class StandInRacing: URLProtocol {
    static let lock = NSLock()
    static var body = Data()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let body = Self.lock.withLock { Self.body }
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class RacingGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Event: Decodable {
            let fixture: String
            let name: String
            let date: String
            let state: String
            let status: String
            let completed: Bool
            let broadcasts: [String]
            let kind: String
            let winner: String
            let count: Int
            let first: [[String]]
        }
        struct Standings: Decodable {
            let fixture: String
            let groups: [Group]
        }
        struct Group: Decodable {
            let name: String
            let constructors: Bool
            let count: Int
            let first: [[String]]
        }
        let events: [Event]
        let standings: [Standings]
    }

    private func grid() throws -> Grid {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/racing_grid.json")
        return try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
    }

    private func service(answering fixture: String) throws -> ESPNAPIService {
        let body = try Fixtures.data(fixture)
        StandInRacing.lock.withLock { StandInRacing.body = body }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInRacing.self]
        return ESPNAPIService(session: URLSession(configuration: config))
    }

    /// The series a fixture is for, by the end of its name.
    private func series(_ fixture: String) -> Sport {
        if fixture.contains("_f1") { return .formulaOne }
        if fixture.contains("_irl") { return .indyCar }
        return .nascarCup
    }

    private let utc: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    func testEveryRaceReadsAsTheSharedGridSays() async throws {
        let cases = try grid().events
        XCTAssertEqual(cases.count, 3)
        for item in cases {
            let found = try await service(answering: item.fixture).fetchRaceEvent(for: series(item.fixture))
            let event = try XCTUnwrap(found, item.fixture)
            XCTAssertEqual(event.name, item.name, item.fixture)
            XCTAssertEqual(utc.string(from: event.date), item.date, item.fixture)
            XCTAssertEqual(event.statusState, item.state, item.fixture)
            XCTAssertEqual(event.statusDescription, item.status, item.fixture)
            XCTAssertEqual(event.isCompleted, item.completed, item.fixture)
            XCTAssertEqual(event.broadcasts, item.broadcasts, item.fixture)
            XCTAssertEqual(event.kind, item.kind, item.fixture)
            XCTAssertEqual(event.winner?.driverName ?? "", item.winner, item.fixture)
            XCTAssertEqual(event.competitors.count, item.count, item.fixture)
            let first = event.competitors.prefix(3).map {
                [$0.position.map(String.init) ?? "", $0.driverName, $0.nationality]
            }
            XCTAssertEqual(first, item.first, item.fixture)
        }
    }

    func testEveryStandingsReadsAsTheSharedGridSays() async throws {
        let cases = try grid().standings
        XCTAssertEqual(cases.count, 3)
        for item in cases {
            let groups = try await service(answering: item.fixture).fetchRacingStandings(for: series(item.fixture))
            XCTAssertEqual(groups.map(\.name), item.groups.map(\.name), item.fixture)
            for (group, expected) in zip(groups, item.groups) {
                XCTAssertEqual(group.id == "constructors", expected.constructors, expected.name)
                XCTAssertEqual(group.entries.count, expected.count, expected.name)
                let first = group.entries.prefix(3).map { [String($0.rank), $0.name, $0.nationality, $0.points] }
                XCTAssertEqual(first, expected.first, "\(item.fixture) \(expected.name)")
            }
        }
    }

    /// The race not yet run lists its field with no `order`, which used to fail the whole
    /// decode, so Formula 1 said it couldn't load the race all through a race weekend.
    func testAFieldWithNoOrderStillDecodes() async throws {
        let event = try await service(answering: "racing_scoreboard_f1.json").fetchRaceEvent(for: .formulaOne)
        XCTAssertEqual(event?.competitors.count, 22)
        XCTAssertTrue(event?.competitors.allSatisfy { $0.position == nil } ?? false)
    }
}
