//
//  PlayAudioGeometryGridTests.swift
//  SportsScoresTests
//
//  PlayAudioGeometry.swift and play_geometry.py are the same mapping written twice.
//  tests/fixtures/play_geometry_grid.json is the reference, and
//  tests/unit/test_play_geometry_parity.py holds the Python side to it. This holds the
//  Swift side, so a change to one that misses the other fails CI (#106).
//

import XCTest
@testable import SportsScores

final class PlayAudioGeometryGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Case: Decodable {
            let league: String
            let x: Double
            let y: Double
            let frequency: Double
            let duration_ms: Int
            let balance: Double
            let description: String
        }
        struct Located: Decodable {
            let league: String
            let x: Double
            let y: Double
            let located: Bool
        }
        let cases: [Case]
        let located: [Located]
    }

    private func grid() throws -> Grid {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/play_geometry_grid.json")
        return try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
    }

    func testEveryCaseMatchesTheSharedGrid() throws {
        let grid = try grid()
        XCTAssertGreaterThan(grid.cases.count, 400)
        for item in grid.cases {
            let label = "\(item.league) (\(item.x), \(item.y))"
            let sport = try XCTUnwrap(Sport(rawValue: item.league), label)
            let result = try XCTUnwrap(PlayAudioGeometry.audioParameters(for: sport, x: item.x, y: item.y), label)
            XCTAssertEqual(result.frequency, item.frequency, accuracy: 0.001, label)
            // Python's round() goes to the even number at exactly .5, so 224.5 is 224.
            XCTAssertEqual(Int((result.duration * 1000).rounded(.toNearestOrEven)), item.duration_ms, label)
            // Windows' balance runs 0 to 1, iOS's pan -1 to 1.
            XCTAssertEqual((Double(result.pan) + 1) / 2, item.balance, accuracy: 0.0001, label)
            XCTAssertEqual(result.description, item.description, label)
        }
    }

    func testBothPlatformsAgreeOnWhichPlaysHaveALocation() throws {
        let grid = try grid()
        XCTAssertFalse(grid.located.isEmpty)
        for item in grid.located {
            let label = "\(item.league) (\(item.x), \(item.y))"
            let sport = try XCTUnwrap(Sport(rawValue: item.league), label)
            let json = #"{"x": \#(item.x), "y": \#(item.y)}"#
            let coordinate = try JSONDecoder().decode(GameDetails.Play.PlayCoordinate.self, from: Data(json.utf8))
            XCTAssertEqual(PlayAudioGeometry.hasLocation(coordinate, for: sport), item.located, label)
        }
    }
}
