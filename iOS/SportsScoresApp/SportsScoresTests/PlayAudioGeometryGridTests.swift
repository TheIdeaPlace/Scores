//
//  PlayAudioGeometryGridTests.swift
//  SportsScoresTests
//
//  PlayAudioGeometry.swift and play_geometry.py are the same mapping written twice.
//  tests/fixtures/play_geometry_grid.json is the reference, and
//  tests/unit/test_play_geometry_parity.py holds the Python side to it. This holds the
//  Swift side, so a change to one that misses the other fails CI (#106). The numeric cases
//  are NBA and NHL. The `located` rows reach all seven leagues, so those also have to have
//  a sound, which is what would go missing if a league fell out of the family list.
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
            // The grid holds whole milliseconds. Python's round() takes exactly .5 to the even
            // number, and Swift works in seconds, so 350.5 can be 350.50000000000006 here.
            XCTAssertEqual(result.duration * 1000, Double(item.duration_ms), accuracy: 0.5 + 1e-6, label)
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
            if item.located {
                XCTAssertNotNil(PlayAudioGeometry.audioParameters(for: sport, x: item.x, y: item.y), label)
            }
        }
    }

    func testEveryLeagueWithLocationsIsInTheGrid() throws {
        let leagues = Set(try grid().located.map(\.league))
        XCTAssertEqual(leagues, ["NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "NCAAH", "NCAAWH"])
    }

    func testEachLeagueSoundsLikeItsSport() {
        for sport in [Sport.nba, .wnba, .ncaam, .ncaawb] {
            XCTAssertEqual(PlayAudioGeometry.family(for: sport), .basketball, sport.rawValue)
        }
        for sport in [Sport.nhl, .ncaah, .ncaawh] {
            XCTAssertEqual(PlayAudioGeometry.family(for: sport), .hockey, sport.rawValue)
        }
        for sport in [Sport.nfl, .ncaaf, .mlb] {
            XCTAssertNil(PlayAudioGeometry.family(for: sport), sport.rawValue)
        }
    }
}
