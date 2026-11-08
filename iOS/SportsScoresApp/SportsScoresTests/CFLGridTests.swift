//
//  CFLGridTests.swift
//  SportsScoresTests
//
//  tests/fixtures/cfl_grid.json holds both apps to the same reading of the CFL's own feed: each
//  game's status and score, which week is current, the East and West standings, the teams, a
//  team's season and its next game. tests/unit/test_cfl.py holds cfl.py on Windows to the same
//  file. The feed is the real capture in tests/fixtures/espn/cfl_*, read by `CFLFeed`, the part
//  of CFLAPIService that does no fetching.
//

import XCTest
@testable import SportsScores

final class CFLGridTests: XCTestCase {
    private var grid: [String: Any] = [:]
    private var feed: CFLFeed!

    override func setUpWithError() throws {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/cfl_grid.json")
        grid = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let rounds = try Fixtures.data(try XCTUnwrap(grid["rounds"] as? String))
        let squads = try Fixtures.data(try XCTUnwrap(grid["squads"] as? String))
        feed = try CFLFeed.decode(rounds: rounds, squads: squads)
    }

    private func cases(_ key: String) throws -> [[String: Any]] {
        try XCTUnwrap(grid[key] as? [[String: Any]], key)
    }

    private func json(_ object: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: object)
    }

    private func date(_ text: Any?) throws -> Date {
        try XCTUnwrap(ISO8601DateFormatter().date(from: try XCTUnwrap(text as? String)))
    }

    /// A JSON null comes out of JSONSerialization as NSNull.
    private func optionalInt(_ value: Any?) -> Int? { value as? Int }
    private func optionalString(_ value: Any?) -> String? { value as? String }

    private func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    func testEachStatusReadsAsTheGridSays() throws {
        for item in try cases("statuses") {
            let name = item["case"] as? String ?? "?"
            let raw = try JSONDecoder().decode(CFLTournament.self, from: try json(try XCTUnwrap(item["game"])))
            let game = feed.makeGame(from: raw, seasonType: 2)
            XCTAssertEqual(game.status.state, item["state"] as? String, name)
            XCTAssertEqual(game.status.detail, item["detail"] as? String, name)
            XCTAssertEqual(game.awayTeam.score, optionalInt(item["away_score"]), name)
            XCTAssertEqual(game.homeTeam.score, optionalInt(item["home_score"]), name)
        }
    }

    func testEachWeekReadsAsTheGridSays() throws {
        for item in try cases("weeks") {
            let name = item["case"] as? String ?? "?"
            let rounds = try Fixtures.data(try XCTUnwrap(item["rounds"] as? String, name))
            let weekFeed = CFLFeed(rounds: try JSONDecoder().decode([CFLRound].self, from: rounds), squads: feed.squads)
            let week = weekFeed.round(index: optionalInt(item["index"]), now: try date(item["now"]))
            XCTAssertEqual(week.roundIndex, item["expect_index"] as? Int, name)
            XCTAssertEqual(week.label, item["label"] as? String, name)
            XCTAssertEqual(week.roundCount, item["count"] as? Int, name)
            XCTAssertEqual(week.isCurrentRound, item["is_current"] as? Bool, name)
            let expected = try XCTUnwrap(item["games"] as? [[String: Any]], name)
            XCTAssertEqual(week.games.count, expected.count, name)
            for (game, want) in zip(week.games, expected) {
                XCTAssertEqual(game.id, want["id"] as? String, name)
                XCTAssertEqual(iso(game.date), want["date"] as? String, name)
                XCTAssertEqual(game.name, want["name"] as? String, name)
                XCTAssertEqual(game.status.state, want["state"] as? String, name)
                XCTAssertEqual(game.status.detail, want["detail"] as? String, name)
                XCTAssertEqual(game.seasonType, want["season_type"] as? Int, name)
                for (team, side) in [(game.awayTeam, "away"), (game.homeTeam, "home")] {
                    let row = try XCTUnwrap(want[side] as? [Any], name)
                    XCTAssertEqual(team.id, row[0] as? String, "\(name) \(side)")
                    XCTAssertEqual(team.abbreviation, row[1] as? String, "\(name) \(side)")
                    XCTAssertEqual(team.score, optionalInt(row[2]), "\(name) \(side)")
                    XCTAssertEqual(team.record, optionalString(row[3]), "\(name) \(side)")
                }
            }
        }
    }

    private func check(_ groups: [StandingsGroup], against expected: [[String: Any]], _ name: String) {
        XCTAssertEqual(groups.map(\.name), expected.map { $0["name"] as? String ?? "" }, name)
        for (group, want) in zip(groups, expected) {
            let rows = want["entries"] as? [[Any]] ?? []
            XCTAssertEqual(group.entries.count, rows.count, "\(name) \(group.name)")
            for (entry, row) in zip(group.entries, rows) {
                XCTAssertEqual(entry.rank, row[0] as? Int, "\(name) \(group.name)")
                XCTAssertEqual(entry.team.id, row[1] as? String, "\(name) \(group.name)")
                XCTAssertEqual(entry.team.abbreviation, row[2] as? String, "\(name) \(group.name)")
                XCTAssertEqual(entry.stats.record, row[3] as? String, "\(name) \(group.name)")
            }
        }
    }

    func testTheStandingsReadAsTheGridSays() throws {
        check(feed.standings(), against: try cases("standings"), "standings")
    }

    func testDrawsAndLevelTeamsReadAsTheGridSays() throws {
        let item = try XCTUnwrap(grid["standings_with_draws"] as? [String: Any])
        let squads = try JSONDecoder().decode([CFLSquad].self, from: try json(try XCTUnwrap(item["squads"])))
        let groups = CFLFeed(rounds: [], squads: squads).standings()
        check(groups, against: try XCTUnwrap(item["groups"] as? [[String: Any]]), "draws")
    }

    func testTheTeamsReadAsTheGridSays() throws {
        let expected = try XCTUnwrap(grid["teams"] as? [[String]])
        XCTAssertEqual(feed.teams().map { [$0.id, $0.displayName, $0.abbreviation] }, expected)
    }

    func testEachScheduleReadsAsTheGridSays() throws {
        for item in try cases("schedules") {
            let teamId = try XCTUnwrap(item["team_id"] as? String)
            let games = feed.schedule(teamId: teamId)
            let expected = try XCTUnwrap(item["games"] as? [[Any]])
            XCTAssertEqual(games.count, expected.count, teamId)
            for (game, row) in zip(games, expected) {
                XCTAssertEqual(game.id, row[0] as? String, teamId)
                let state = game.isCompleted ? "post" : game.isInProgress ? "in" : "pre"
                XCTAssertEqual(state, row[1] as? String, "\(teamId) \(game.id)")
                XCTAssertEqual(game.statusText, row[2] as? String, "\(teamId) \(game.id)")
                XCTAssertEqual(game.awayTeam.score, optionalInt(row[3]), "\(teamId) \(game.id)")
                XCTAssertEqual(game.homeTeam.score, optionalInt(row[4]), "\(teamId) \(game.id)")
            }
        }
    }

    func testEachTeamReadsAsTheGridSays() throws {
        for item in try cases("team_info") {
            let teamId = try XCTUnwrap(item["team_id"] as? String)
            let info = try feed.teamInfo(teamId: teamId, now: try date(item["now"]))
            XCTAssertEqual(info.displayName, item["name"] as? String, teamId)
            XCTAssertEqual(info.overallRecord, item["record"] as? String, teamId)
            XCTAssertEqual(info.standingSummary, item["standing"] as? String, teamId)
            XCTAssertEqual(info.nextGame?.gameId, optionalString(item["next_game"]), teamId)
        }
    }

    func testAFailedRequestSaysWhatWindowsSays() throws {
        let failed = try XCTUnwrap(grid["failed"] as? [String: String])
        XCTAssertFalse(failed.isEmpty)
        for (what, sentence) in failed {
            XCTAssertEqual(APIError.unavailable(what, source: "The CFL"), sentence)
        }
    }

    func testTheTBDTeamHasNoRecord() throws {
        let greyCup = feed.round(index: 26)
        XCTAssertEqual(greyCup.games.first?.homeTeam.id, "0")
        XCTAssertNil(greyCup.games.first?.homeTeam.record)
        XCTAssertThrowsError(try feed.teamInfo(teamId: "0"))
    }
}
