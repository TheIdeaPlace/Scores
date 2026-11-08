//
//  WinProbabilityGridTests.swift
//  SportsScoresTests
//
//  WinProbability.swift against tests/fixtures/win_probability_grid.json, the grid
//  win_probability.py on Windows is held to, read through GameDetails as the app
//  reads a summary.
//

import XCTest
@testable import SportsScores

private struct WinProbabilityGrid: Decodable {
    struct PercentCase: Decodable {
        let fraction: Double
        let percent: Int
    }
    struct LeaderCase: Decodable {
        let home_fraction: Double
        let home: String
        let away: String
        let text: String
    }
    struct SummaryCase: Decodable {
        let name: String
        let fixture: String?
        let home: String
        let away: String
        let expected_count: Int
        let expected_first_home_percent: Int?
        let expected_leader: String?
    }
    let percent_cases: [PercentCase]
    let leader_cases: [LeaderCase]
    let summary_cases: [SummaryCase]
}

final class WinProbabilityGridTests: XCTestCase {
    private func load() throws -> (WinProbabilityGrid, [[String: Any]]) {
        let raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/win_probability_grid.json"))
        let grid = try JSONDecoder().decode(WinProbabilityGrid.self, from: raw)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
        return (grid, try XCTUnwrap(object["summary_cases"] as? [[String: Any]]))
    }

    func testPercent() throws {
        let (grid, _) = try load()
        XCTAssertGreaterThan(grid.percent_cases.count, 5)
        for item in grid.percent_cases {
            XCTAssertEqual(WinProbability.percent(item.fraction), item.percent, "\(item.fraction)")
        }
    }

    func testLeaderText() throws {
        let (grid, _) = try load()
        for item in grid.leader_cases {
            XCTAssertEqual(WinProbability.leaderText(homeFraction: item.home_fraction, home: item.home, away: item.away),
                           item.text, "\(item.home_fraction)")
        }
    }

    func testSummaries() throws {
        let (grid, rawCases) = try load()
        XCTAssertEqual(grid.summary_cases.count, rawCases.count)
        for (item, rawCase) in zip(grid.summary_cases, rawCases) {
            let summary: Data
            if let fixture = item.fixture {
                summary = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/" + fixture))
            } else {
                summary = try JSONSerialization.data(withJSONObject: try XCTUnwrap(rawCase["summary"], item.name))
            }
            let details = try JSONDecoder().decode(GameDetails.self, from: summary)
            let entries = details.winprobability ?? []
            XCTAssertEqual(entries.count, item.expected_count, item.name)
            if item.fixture != nil {
                XCTAssertEqual(details.sideNames.home, item.home, item.name)
                XCTAssertEqual(details.sideNames.away, item.away, item.name)
            }
            guard let leader = item.expected_leader else {
                XCTAssertTrue(entries.isEmpty, item.name)
                continue
            }
            XCTAssertEqual(entries.first.map { WinProbability.percent($0.homeWinPercentage) },
                           item.expected_first_home_percent, item.name)
            let last = try XCTUnwrap(entries.last, item.name)
            XCTAssertEqual(WinProbability.leaderText(homeFraction: last.homeWinPercentage, home: item.home, away: item.away),
                           leader, item.name)
        }
    }
}
