//
//  DivisionStandingsGridTests.swift
//  SportsScoresTests
//
//  DivisionStandings.swift against tests/fixtures/division_standings_grid.json, the grid
//  division_standings.py on Windows is held to, and the standings request that uses it.
//

import XCTest
@testable import SportsScores

private struct DivisionGrid: Decodable {
    struct Label: Decodable { let name: String; let label: String }
    struct GamesBack: Decodable { let about: String; let games_back: String }
    struct Order: Decodable { let about: String; let order: [String] }
    struct Group: Decodable, Equatable {
        let name: String
        let conference: String
        let teams: [String]
        let games_back: [String]
    }
    struct Tree: Decodable { let about: String; let groups: [Group] }
    struct Fixture: Decodable { let fixture: String; let groups: [Group] }

    let labels: [Label]
    let games_back: [GamesBack]
    let order: [Order]
    let trees: [Tree]
    let fixtures: [Fixture]
}

/// Answers every request with `body` and keeps the URL asked for.
private final class StandInDivisions: URLProtocol {
    static var body = Data()
    static var requested: [URL] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        Self.requested.append(url)
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class DivisionStandingsGridTests: XCTestCase {
    private typealias Entry = DivisionStandings.Entry

    private var raw: Data {
        get throws {
            try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/division_standings_grid.json"))
        }
    }

    private func grid() throws -> DivisionGrid {
        try JSONDecoder().decode(DivisionGrid.self, from: raw)
    }

    /// The grid's own JSON for one section, so each case's input decodes as ESPN's would.
    private func rawCases(_ key: String) throws -> [[String: Any]] {
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
        return try XCTUnwrap(object[key] as? [[String: Any]])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ value: Any) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: value))
    }

    private func shown(_ groups: [DivisionStandings.Group]) -> [DivisionGrid.Group] {
        groups.map { group in
            DivisionGrid.Group(name: group.name, conference: group.conference,
                               teams: group.entries.map(\.team.abbreviation),
                               games_back: group.entries.map(DivisionStandings.gamesBack))
        }
    }

    func testLabels() throws {
        let cases = try grid().labels
        XCTAssertGreaterThan(cases.count, 5)
        for item in cases {
            XCTAssertEqual(DivisionStandings.label(item.name), item.label, item.name)
        }
    }

    func testGamesBack() throws {
        let cases = try grid().games_back
        let inputs = try rawCases("games_back")
        XCTAssertEqual(cases.count, inputs.count)
        for (item, input) in zip(cases, inputs) {
            let entry = try decode(Entry.self, try XCTUnwrap(input["entry"]))
            XCTAssertEqual(DivisionStandings.gamesBack(entry), item.games_back, item.about)
        }
    }

    func testOrder() throws {
        let cases = try grid().order
        let inputs = try rawCases("order")
        XCTAssertEqual(cases.count, inputs.count)
        for (item, input) in zip(cases, inputs) {
            let entries = try decode([Entry].self, try XCTUnwrap(input["entries"]))
            XCTAssertEqual(DivisionStandings.standingOrder(entries).map(\.team.abbreviation), item.order, item.about)
        }
    }

    func testTrees() throws {
        let cases = try grid().trees
        let inputs = try rawCases("trees")
        XCTAssertEqual(cases.count, inputs.count)
        for (item, input) in zip(cases, inputs) {
            let root = try decode(APIStandingsGroup.self, try XCTUnwrap(input["data"]))
            XCTAssertEqual(shown(DivisionStandings.groups(root)), item.groups, item.about)
        }
    }

    func testRealAnswers() throws {
        let cases = try grid().fixtures
        XCTAssertGreaterThanOrEqual(cases.count, 5)
        for item in cases {
            let response = try JSONDecoder().decode(APIStandingsResponse.self, from: Fixtures.data(item.fixture))
            XCTAssertEqual(shown(DivisionStandings.groups(response.root)), item.groups, item.fixture)
        }
    }

    // MARK: - The request, end to end

    private func standings(_ fixture: String, sport: Sport) async throws -> [StandingsGroup] {
        StandInDivisions.body = try Fixtures.data(fixture)
        StandInDivisions.requested = []
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StandInDivisions.self]
        return try await ESPNAPIService(session: URLSession(configuration: config)).fetchStandings(for: sport)
    }

    func testEachProLeagueAsksByDivision() async throws {
        for (sport, fixture) in [(Sport.nfl, "standings_NFL_divisions.json"), (.nba, "standings_NBA_divisions.json"),
                                 (.nhl, "standings_NHL_divisions.json"), (.mlb, "standings_MLB_divisions.json")] {
            _ = try await standings(fixture, sport: sport)
            let query = StandInDivisions.requested.first?.query
            XCTAssertEqual(query, "level=3", "\(sport)")
        }
    }

    func testAnNFLDivisionLeaderIsNotGamesBack() async throws {
        // The bug: the conference figure had Denver 0.5 back of Buffalo while it led the AFC West.
        let groups = try await standings("standings_NFL_divisions.json", sport: .nfl)
        XCTAssertEqual(groups.map(\.name), ["AFC East", "AFC North", "AFC South", "AFC West",
                                            "NFC East", "NFC North", "NFC South", "NFC West"])
        let west = try XCTUnwrap(groups.first { $0.name == "AFC West" })
        XCTAssertEqual(west.entries.map(\.team.abbreviation), ["DEN", "KC", "LV", "LAC"])
        XCTAssertEqual(west.entries.map(\.stats.gamesBack), ["-", "0.5", "3", "6.5"])
        let north = try XCTUnwrap(groups.first { $0.name == "AFC North" })
        XCTAssertEqual(north.entries.map(\.team.abbreviation), ["PIT", "CIN", "CLE", "BAL"])
        XCTAssertEqual(north.entries.map(\.stats.gamesBack), ["-", "-", "1.5", "2.5"])
    }

    func testTheNBAsDivisionsAreInStandingOrder() async throws {
        let groups = try await standings("standings_NBA_divisions.json", sport: .nba)
        let central = try XCTUnwrap(groups.first { $0.name == "Central" })
        XCTAssertEqual(central.entries.map(\.team.abbreviation), ["DET", "CLE", "IND", "CHI", "MIL"])
        XCTAssertEqual(central.entries.map(\.stats.gamesBack), ["-", "2.5", "4.5", "6.5", "7.5"])
        // The NBA's level=3 answer has no overall record stat, so it comes from wins and losses.
        XCTAssertEqual(central.entries.first?.stats.record, "8-3")
        XCTAssertFalse(groups.flatMap(\.entries).contains { $0.stats.record == "-" })
    }

    func testTheNHLKeepsItsDivisionNames() async throws {
        let groups = try await standings("standings_NHL_divisions.json", sport: .nhl)
        XCTAssertEqual(groups.map(\.name), ["Atlantic", "Metropolitan", "Central", "Pacific"])
        let utah = groups.flatMap(\.entries).first { $0.team.displayName.hasPrefix("Utah") }
        XCTAssertNotNil(utah)
        XCTAssertTrue(groups.first { $0.name == "Central" }?.entries.contains { $0.team.id == utah?.team.id } ?? false)
    }

    func testConferencesOnlyStillListEveryTeam() async throws {
        // If ESPN ever ignores level=3, the conferences are the groups rather than nothing.
        let groups = try await standings("standings_NFL.json", sport: .nfl)
        XCTAssertEqual(groups.map(\.name), ["American Football Conference", "National Football Conference"])
        XCTAssertEqual(groups.flatMap(\.entries).count, 6)
    }

    func testAStatWithNoTextKeepsItsTeam() throws {
        let json = #"{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[{"name":"wins","value":3}]}"#
        let entry = try JSONDecoder().decode(Entry.self, from: Data(json.utf8))
        XCTAssertEqual(StandingsEntry(fromAPIEntry: entry).stats.wins, 3)
    }

    func testOneUnreadableChildKeepsItsSiblings() throws {
        let json = #"{"name":"League","children":[3,{"name":"East","standings":{"entries":[{"team":{"id":"1","name":"A","abbreviation":"A","displayName":"A"},"stats":[]}]}}]}"#
        let root = try JSONDecoder().decode(APIStandingsGroup.self, from: Data(json.utf8))
        XCTAssertEqual(DivisionStandings.groups(root).map(\.name), ["East"])
    }
}
