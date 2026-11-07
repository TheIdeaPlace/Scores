//
//  PostseasonGridTests.swift
//  SportsScoresTests
//
//  PostseasonRound against tests/fixtures/postseason_grid.json, the grid postseason.py
//  on Windows is held to, so the two Bowls & Playoffs lists group games the same way.
//

import XCTest
@testable import SportsScores

private struct PostseasonGrid: Decodable {
    struct RoundCase: Decodable {
        let headline: String?
        let type_id: Int?
        let expected: String
    }
    let headings: [String]
    let round_cases: [RoundCase]
}

final class PostseasonGridTests: XCTestCase {
    private func grid() throws -> PostseasonGrid {
        let data = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/postseason_grid.json"))
        return try JSONDecoder().decode(PostseasonGrid.self, from: data)
    }

    func testHeadingsAreInTheGridsOrder() throws {
        XCTAssertEqual(PostseasonRound.allCases.map(\.heading), try grid().headings)
    }

    func testRounds() throws {
        let cases = try grid().round_cases
        XCTAssertFalse(cases.isEmpty)
        for item in cases {
            XCTAssertEqual(PostseasonRound.from(headline: item.headline, typeID: item.type_id).heading,
                           item.expected, "\(item.headline ?? "nil") / \(item.type_id.map(String.init) ?? "nil")")
        }
    }
}
