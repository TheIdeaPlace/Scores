//
//  StatGlossaryGridTests.swift
//  SportsScoresTests
//
//  StatGlossary.swift against tests/fixtures/stat_glossary_grid.json, the grid
//  stat_glossary.py on Windows is held to, on the real byteam payloads it names (#193).
//

import XCTest
@testable import SportsScores

private struct GlossaryGrid: Decodable {
    struct Case: Decodable {
        let name: String
        let fixture: String
        let sport: String
        let kind: String
        let key: String
        let definition: String?
    }
    let leader_stats: [String: [String: [String]]]
    let glossaries: [String: [String: String]]
    let cases: [Case]
}

final class StatGlossaryGridTests: XCTestCase {
    private var grid: GlossaryGrid!

    override func setUpWithError() throws {
        let raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/stat_glossary_grid.json"))
        grid = try JSONDecoder().decode(GlossaryGrid.self, from: raw)
    }

    private func glossary(_ fixture: String) throws -> [String: String] {
        let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data(fixture))
        return StatGlossary.glossary(from: response.categories ?? [])
    }

    func testTheLeaderTableIsTheGrids() {
        let table = StatGlossary.leaderStats.mapValues { $0.mapValues { [$0.category, $0.name] } }
        XCTAssertEqual(table, grid.leader_stats)
    }

    func testTheGlossaryOfEachRealPayloadIsTheGrids() throws {
        for (fixture, expected) in grid.glossaries {
            XCTAssertEqual(try glossary(fixture), expected, fixture)
        }
    }

    func testEachLookupGivesTheGridsAnswer() throws {
        for item in grid.cases {
            let found = StatGlossary.definition(in: try glossary(item.fixture), sport: item.sport,
                                                key: item.key, team: item.kind == "team")
            XCTAssertEqual(found, item.definition, item.name)
        }
    }

    /// The bug in #193: the glossary was keyed by name, and batting came first.
    func testPitchersStrikeoutLeadersGetThePitchersDefinition() throws {
        let found = try glossary("byteam_MLB.json")
        let leaders = try XCTUnwrap(StatGlossary.definition(in: found, sport: "baseball", key: "strikeouts", team: false))
        XCTAssertTrue(leaders.contains("pitcher"), leaders)
        XCTAssertNotEqual(leaders, StatGlossary.definition(in: found, sport: "baseball", key: "batting.strikeouts", team: true))
    }

    func testAnOpponentsListTakesTheStatsDefinition() throws {
        let found = try glossary("byteam_NFL.json")
        XCTAssertEqual(StatGlossary.definition(in: found, sport: "football", key: "opponent.passing.passingYards", team: true),
                       StatGlossary.definition(in: found, sport: "football", key: "passing.passingYards", team: true))
    }
}
