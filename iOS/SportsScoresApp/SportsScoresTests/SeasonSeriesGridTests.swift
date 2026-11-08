//
//  SeasonSeriesGridTests.swift
//  SportsScoresTests
//
//  SeasonSeries.swift against tests/fixtures/season_series_grid.json, the grid
//  season_series.py on Windows is held to, read through GameDetails as the app
//  reads a summary.
//

import XCTest
@testable import SportsScores

private struct SeasonSeriesGrid: Decodable {
    struct Shown: Decodable {
        let label: String
        let text: String
        let games: Int
    }
    struct Case: Decodable {
        let name: String
        let fixture: String?
        let names: [String: String]
        let expected: [Shown]
        let expected_line: String
    }
    let cases: [Case]
}

final class SeasonSeriesGridTests: XCTestCase {
    func testGrid() throws {
        let raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/season_series_grid.json"))
        let grid = try JSONDecoder().decode(SeasonSeriesGrid.self, from: raw)
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
            let entries = details.seasonseries ?? []
            let shown = SeasonSeries.shown(entries, names: item.names)
            XCTAssertEqual(shown.map(\.label), item.expected.map(\.label), item.name)
            XCTAssertEqual(shown.map(\.text), item.expected.map(\.text), item.name)
            XCTAssertEqual(shown.map(\.games), item.expected.map(\.games), item.name)
            XCTAssertEqual(SeasonSeries.summaryLine(entries, names: item.names), item.expected_line, item.name)
            if item.fixture != nil {
                XCTAssertEqual(details.teamNamesByID, item.names, item.name)
            }
        }
    }
}
