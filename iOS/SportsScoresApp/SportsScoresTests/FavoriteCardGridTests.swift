//
//  FavoriteCardGridTests.swift
//  SportsScoresTests
//
//  FavoriteCardGames.swift against tests/fixtures/favorite_card_grid.json, the grid
//  favorite_card.py on Windows is held to (tests/unit/test_favorite_card_grid.py).
//

import XCTest
@testable import SportsScores

final class FavoriteCardGridTests: XCTestCase {

    private struct Expected: Decodable {
        let live: String?
        let last: String?
        let next: String?
        let last_line: String?
    }

    private struct Case: Decodable {
        let name: String
        let team_id: String
        let now: String
        let fixture: String?
        let expected: Expected
    }

    private struct Grid: Decodable {
        let cases: [Case]
    }

    private func gridData() throws -> Data {
        try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/favorite_card_grid.json"))
    }

    /// A grid game in short form as a minimal ESPN schedule event, the same one
    /// test_favorite_card_grid.py builds.
    private func espnEvent(_ game: [String: Any]) -> [String: Any] {
        var statusType: [String: Any] = ["name": game["status"]!, "description": game["status"]!]
        for key in ["state", "completed"] where game[key] != nil {
            statusType[key] = game[key]
        }
        func competitor(_ side: String) -> [String: Any] {
            let team = game[side] as! [Any]
            let abbreviation = team[1] as! String
            var entry: [String: Any] = [
                "homeAway": side,
                "team": ["id": team[0] as! String, "abbreviation": abbreviation, "displayName": abbreviation],
            ]
            if let score = team[2] as? NSNumber {
                entry["score"] = ["value": score.doubleValue, "displayValue": score.stringValue]
            }
            return entry
        }
        var competition: [String: Any] = [
            "competitors": [competitor("home"), competitor("away")],
            "status": ["type": statusType],
            "neutralSite": (game["neutral"] as? Bool) ?? false,
        ]
        if let label = game["label"] as? String, !label.isEmpty {
            competition["notes"] = [["headline": label]]
        }
        let away = (game["away"] as! [Any])[1] as! String
        let home = (game["home"] as! [Any])[1] as! String
        return [
            "id": game["id"]!,
            "date": game["date"]!,
            "name": "\(away) at \(home)",
            "timeValid": (game["time_valid"] as? Bool) ?? true,
            "seasonType": ["type": 2],
            "competitions": [competition],
        ]
    }

    /// The case's games as ESPNAPIService gives them: parsed, each once, in date order.
    private func schedule(for item: Case, raw: [String: Any]) throws -> [ScheduleGame] {
        let body: Data
        if let fixture = item.fixture {
            body = try Fixtures.data(fixture)
        } else {
            let games = try XCTUnwrap(raw["games"] as? [[String: Any]], item.name)
            body = try JSONSerialization.data(withJSONObject: ["events": games.map(espnEvent)])
        }
        let events = try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: body).events
        // Every event read, so a case can't pass on a game that silently dropped out.
        XCTAssertEqual(events.count, try Fixtures.rawCount("events", of: body), item.name)
        return TeamScheduleQueries.merged([events.compactMap { $0.toScheduleGame() }])
    }

    func testGrid() throws {
        let data = try gridData()
        let grid = try JSONDecoder().decode(Grid.self, from: data)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let rawCases = try XCTUnwrap(object["cases"] as? [[String: Any]])
        XCTAssertEqual(grid.cases.count, rawCases.count)

        let isoFormatter = ISO8601DateFormatter()
        for (item, raw) in zip(grid.cases, rawCases) {
            let now = try XCTUnwrap(isoFormatter.date(from: item.now), item.name)
            let picked = FavoriteCardGames(schedule: try schedule(for: item, raw: raw), now: now)
            XCTAssertEqual(picked.live?.id, item.expected.live, "\(item.name): live")
            XCTAssertEqual(picked.last?.id, item.expected.last, "\(item.name): last")
            XCTAssertEqual(picked.next?.id, item.expected.next, "\(item.name): next")
            let line = picked.last.map { FavoriteCardGames.resultLine(for: $0, teamId: item.team_id) }
            XCTAssertEqual(line, item.expected.last_line, "\(item.name): last line")
        }
    }
}
