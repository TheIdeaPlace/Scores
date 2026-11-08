//
//  DriveResultsGridTests.swift
//  SportsScoresTests
//
//  DriveResults.swift against tests/fixtures/drive_results_grid.json, the grid
//  drive_results.py on Windows is held to, and on the real ESPN drives of the two
//  games where the NVDA bug bash found a return touchdown credited to the kicking team.
//

import XCTest
@testable import SportsScores

private struct DriveGrid: Decodable {
    struct Team: Decodable {
        let id: String
        let name: String
    }
    struct Drive: Decodable {
        let team_id: String?
        let plays: [[Int?]]
        let scoring_plays: [Int]
    }
    struct Expected: Decodable, Equatable {
        let kind: String?
        let points: Int
        let scorer: String?
        let by_opponent: Bool
        let other_points: Int
        let badge: String?
    }
    struct Case: Decodable {
        let name: String
        let away: Team
        let home: Team
        let drives: [Drive]
        let expected: [Expected]
    }
    struct FixtureCase: Decodable {
        let fixture: String
        let expected: [String: Expected]
    }
    let cases: [Case]
    let fixture_cases: [FixtureCase]
}

/// The header's two teams, which GameDetails.GameHeader doesn't need to carry.
private struct SummaryTeams: Decodable {
    struct Header: Decodable {
        struct Competition: Decodable {
            struct Competitor: Decodable {
                struct Team: Decodable {
                    let id: String
                    let displayName: String
                }
                let homeAway: String
                let team: Team
            }
            let competitors: [Competitor]
        }
        let competitions: [Competition]
    }
    let header: Header

    func team(_ side: String) throws -> Header.Competition.Competitor.Team {
        try XCTUnwrap(header.competitions.first?.competitors.first { $0.homeAway == side }?.team)
    }
}

final class DriveResultsGridTests: XCTestCase {
    private var grid: DriveGrid!

    override func setUpWithError() throws {
        let data = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/drive_results_grid.json"))
        grid = try JSONDecoder().decode(DriveGrid.self, from: data)
    }

    private func shown(_ result: DriveResult, away: String, home: String) -> DriveGrid.Expected {
        let scorerName = result.scorer == .home ? home : away
        let otherName = result.scorer == .home ? away : home
        return .init(kind: result.kind?.rawValue,
                     points: result.points,
                     scorer: result.scorer?.rawValue,
                     by_opponent: result.byOpponent,
                     other_points: result.otherPoints,
                     badge: DriveResults.badge(result, scorerName: scorerName, otherName: otherName))
    }

    func testGridCases() {
        XCTAssertFalse(grid.cases.isEmpty)
        for item in grid.cases {
            let inputs = item.drives.map { drive in
                DriveScoreInput(teamID: drive.team_id,
                                plays: drive.plays.enumerated().map { index, play in
                                    (away: play.first ?? nil,
                                     home: play.count > 1 ? play[1] : nil,
                                     scoring: drive.scoring_plays.contains(index))
                                })
            }
            let results = DriveResults.results(inputs, awayID: item.away.id, homeID: item.home.id)
            XCTAssertEqual(results.map { shown($0, away: item.away.name, home: item.home.name) },
                           item.expected, item.name)
        }
    }

    func testRealDrives() throws {
        XCTAssertFalse(grid.fixture_cases.isEmpty)
        for item in grid.fixture_cases {
            let data = try Fixtures.data(item.fixture)
            let teams = try JSONDecoder().decode(SummaryTeams.self, from: data)
            let away = try teams.team("away"), home = try teams.team("home")
            let drives = try XCTUnwrap(Fixtures.decodeDetails(data).drives?.all, item.fixture)
            let results = DriveResults.results(drives.map(\.scoreInput), awayID: away.id, homeID: home.id)
            var scored: [String: DriveGrid.Expected] = [:]
            for (drive, result) in zip(drives, results) where result.kind != nil {
                scored[drive.id] = shown(result, away: away.displayName, home: home.displayName)
            }
            XCTAssertEqual(scored, item.expected, item.fixture)
        }
    }

    /// Every play of the real drives decodes with its score: one odd play mustn't cost a drive.
    func testRealPlaysCarryTheirScores() throws {
        let data = try Fixtures.data("drives_NCAAF_401858286.json")
        let drives = try XCTUnwrap(Fixtures.decodeDetails(data).drives?.all)
        XCTAssertEqual(drives.count, 22)
        let plays = drives.flatMap { $0.plays ?? [] }
        XCTAssertFalse(plays.isEmpty)
        XCTAssertTrue(plays.allSatisfy { $0.awayScore != nil && $0.homeScore != nil })
        XCTAssertEqual(plays.filter { $0.scoringPlay == true }.count, 8)
    }
}
