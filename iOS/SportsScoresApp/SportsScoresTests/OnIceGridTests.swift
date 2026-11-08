//
//  OnIceGridTests.swift
//  SportsScoresTests
//
//  OnIce.swift against tests/fixtures/on_ice_grid.json, the grid on_ice.py on
//  Windows is held to, read through GameDetails as the app reads a summary.
//

import XCTest
@testable import SportsScores

private struct OnIceGrid: Decodable {
    struct Player: Decodable, Equatable {
        let id: String
        let name: String
        let last_name: String
        let jersey: String
        let position: String
        let group: String
    }
    struct Team: Decodable, Equatable {
        let id: String
        let name: String
        let short_name: String
        let home_away: String
        let players: [Player]
    }
    struct Case: Decodable {
        let name: String
        let fixture: String?
        let expected_teams: [Team]
        let expected_line: String
        let expected_headings: [String]
        let expected_player_texts: [[String]]
    }
    let cases: [Case]
}

final class OnIceGridTests: XCTestCase {
    private func shown(_ teams: [OnIceTeam]) -> [OnIceGrid.Team] {
        teams.map { team in
            OnIceGrid.Team(id: team.id, name: team.name, short_name: team.shortName, home_away: team.homeAway,
                           players: team.players.map {
                               OnIceGrid.Player(id: $0.id, name: $0.name, last_name: $0.lastName,
                                                jersey: $0.jersey, position: $0.position, group: $0.group)
                           })
        }
    }

    func testGrid() throws {
        let raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/on_ice_grid.json"))
        let grid = try JSONDecoder().decode(OnIceGrid.self, from: raw)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
        let rawCases = try XCTUnwrap(object["cases"] as? [[String: Any]])
        XCTAssertEqual(grid.cases.count, rawCases.count)
        XCTAssertGreaterThan(grid.cases.count, 5)

        for (item, rawCase) in zip(grid.cases, rawCases) {
            let summary: Data
            if let fixture = item.fixture {
                summary = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/" + fixture))
            } else {
                summary = try JSONSerialization.data(withJSONObject: try XCTUnwrap(rawCase["summary"], item.name))
            }
            let details = try JSONDecoder().decode(GameDetails.self, from: summary)
            let teams = details.onIceTeams
            XCTAssertEqual(shown(teams), item.expected_teams, item.name)
            XCTAssertEqual(OnIce.summaryLine(teams), item.expected_line, item.name)
            XCTAssertEqual(teams.map(\.heading), item.expected_headings, item.name)
            XCTAssertEqual(teams.map { $0.players.map(\.spokenText) }, item.expected_player_texts, item.name)
        }
    }

    /// The real live summary keeps the rest of the game's details, too.
    func testLiveFixtureStillDecodesTheBoxScore() throws {
        let details = try JSONDecoder().decode(GameDetails.self, from: try Fixtures.data("summary_live_NHL_401892664.json"))
        XCTAssertEqual(details.boxscore?.players?.count, 2)
        XCTAssertEqual(details.onIceTeams.map(\.shortName), ["Rangers", "Kraken"])
    }
}
