//
//  RadioLinksGridTests.swift
//  SportsScoresTests
//
//  RadioLinks.swift against tests/fixtures/radio_links_grid.json, the grid
//  radio_links.py on Windows is held to, and the app's bundled copy of the links file.
//

import XCTest
@testable import SportsScores

private struct RadioGrid: Decodable {
    struct Expected: Decodable, Equatable {
        let label: String
        let url: String
    }
    struct GameCase: Decodable {
        let name: String
        let league: String
        let away_id: String
        let away_name: String
        let home_id: String
        let home_name: String
        let expected: [Expected]
    }
    struct TeamCase: Decodable {
        let name: String
        let league: String
        let team_id: String
        let team_name: String
        let expected: [Expected]
    }
    struct DirectoryCase: Decodable {
        let league: String
        let expected_names: [String]
        let expected_link_counts: [Int]
    }
    struct CoversCase: Decodable {
        let league: String
        let expected: Bool
    }
    let game_cases: [GameCase]
    let team_cases: [TeamCase]
    let directory_cases: [DirectoryCase]
    let covers_cases: [CoversCase]
}

final class RadioLinksGridTests: XCTestCase {
    private var raw: Data!
    private var grid: RadioGrid!
    private var links: RadioLinks!

    override func setUpWithError() throws {
        raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/radio_links_grid.json"))
        grid = try JSONDecoder().decode(RadioGrid.self, from: raw)
        // The grid's "data" block has the links file's shape.
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
        let data = try JSONSerialization.data(withJSONObject: try XCTUnwrap(object["data"]))
        links = RadioLinks(data: data)
    }

    private func shown(_ options: [ListenOption]) -> [RadioGrid.Expected] {
        options.map { .init(label: $0.label, url: $0.url.absoluteString) }
    }

    func testGameOptions() {
        for item in grid.game_cases {
            let options = links.gameOptions(item.league, awayId: item.away_id, awayName: item.away_name,
                                            homeId: item.home_id, homeName: item.home_name)
            XCTAssertEqual(shown(options), item.expected, item.name)
        }
    }

    func testTeamListenOptions() {
        for item in grid.team_cases {
            let options = links.teamListenOptions(item.league, teamId: item.team_id, teamName: item.team_name)
            XCTAssertEqual(shown(options), item.expected, item.name)
        }
    }

    func testDirectory() {
        for item in grid.directory_cases {
            let rows = links.directory(item.league)
            XCTAssertEqual(rows.map(\.name), item.expected_names, item.league)
            XCTAssertEqual(rows.map { $0.links.count }, item.expected_link_counts, item.league)
        }
    }

    func testCovers() {
        for item in grid.covers_cases {
            XCTAssertEqual(links.covers(item.league), item.expected, item.league)
        }
    }

    func testUnreadableFileIsNoLinks() {
        let empty = RadioLinks(data: Data("{not json".utf8))
        XCTAssertTrue(empty.gameOptions("NFL", awayId: "9", awayName: "", homeId: "3", homeName: "").isEmpty)
        XCTAssertFalse(empty.covers("NFL"))
    }

    /// The copy the app ships reads, and covers the leagues The Bench lists.
    func testBundledFileCoversTheBenchLeagues() throws {
        let url = Fixtures.repoRoot.appendingPathComponent("iOS/SportsScoresApp/SportsScores/radio_links.json")
        let bundled = RadioLinks(data: try Data(contentsOf: url))
        for entry in RadioLinks.directoryLeagues {
            XCTAssertTrue(bundled.covers(entry.league), entry.league)
        }
        XCTAssertEqual(RadioLinks.directoryLeagues.first?.league, "MLB")
        XCTAssertEqual(bundled.directory("MLB").count, 30)
        let yankees = bundled.teamListenOptions("MLB", teamId: "10", teamName: "New York Yankees")
        XCTAssertTrue(yankees.first?.label.hasPrefix("New York Yankees: ") ?? false)
    }
}
