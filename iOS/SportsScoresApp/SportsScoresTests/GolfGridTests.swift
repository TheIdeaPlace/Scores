//
//  GolfGridTests.swift
//  SportsScoresTests
//
//  GolfRules.swift, through the lenient GolfAPIModels decoding, against
//  tests/fixtures/golf_grid.json, the grid golf.py on Windows is held to by
//  test_golf_grid.py. Then the golf requests themselves: the event in progress rather than
//  events.first (#206), a past week's event by id, and the season's winners (#189).
//

import XCTest
@testable import SportsScores

final class GolfGridTests: XCTestCase {
    private var grid: [String: Any]!

    override func setUpWithError() throws {
        let raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/golf_grid.json"))
        grid = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
    }

    private func cases(_ key: String) throws -> [[String: Any]] {
        let found = try XCTUnwrap(grid[key] as? [[String: Any]], "no \(key)")
        XCTAssertFalse(found.isEmpty, "\(key) tests nothing")
        return found
    }

    /// The events as the app reads a scoreboard: an entry it can't read is skipped.
    private func decodeEvents(_ events: Any) throws -> [GolfEventAPIResponse] {
        let data = try JSONSerialization.data(withJSONObject: ["events": events])
        return try JSONDecoder().decode(GolfScoreboardResponse.self, from: data).events
    }

    private func decodeEvent(_ event: Any) throws -> GolfEventAPIResponse {
        try XCTUnwrap(try decodeEvents([event]).first)
    }

    private func optionalString(_ value: Any?) -> String? {
        value as? String   // NSNull and absent are both nil
    }

    func testState() throws {
        for c in try cases("state_cases") {
            let event = try decodeEvent(try XCTUnwrap(c["event"]))
            XCTAssertEqual(GolfRules.state(of: event), c["expected"] as? String, c["name"] as? String ?? "")
        }
    }

    func testPick() throws {
        for c in try cases("pick_cases") {
            let events = try decodeEvents(try XCTUnwrap(c["events"]))
            let picked = GolfRules.pickEvent(events, id: optionalString(c["event_id"]))
            XCTAssertEqual(picked?.id, optionalString(c["expected_id"]), c["name"] as? String ?? "")
        }
    }

    func testWinner() throws {
        for c in try cases("winner_cases") {
            let event = try decodeEvent(try XCTUnwrap(c["event"]))
            XCTAssertEqual(GolfRules.winner(of: event)?.text ?? "", c["expected"] as? String, c["name"] as? String ?? "")
        }
    }

    func testRealFixtures() throws {
        for c in try cases("fixture_cases") {
            let file = try XCTUnwrap(c["file"] as? String)
            let data = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/\(file)"))
            let events = try JSONDecoder().decode(GolfScoreboardResponse.self, from: data).events
            XCTAssertEqual(events.count, c["event_count"] as? Int, file)
            XCTAssertEqual(GolfRules.pickEvent(events, id: optionalString(c["event_id"]))?.id,
                           c["expected_pick"] as? String, file)
            var winners: [String: String] = [:]
            for event in events { winners[event.id] = GolfRules.winner(of: event)?.text ?? "" }
            XCTAssertEqual(winners.values.filter { !$0.isEmpty }.count, c["winner_count"] as? Int, file)
            for (id, expected) in try XCTUnwrap(c["winners"] as? [String: String]) {
                XCTAssertEqual(winners[id], expected, "\(file) \(id)")
            }
        }
    }

    // MARK: - Lenient decoding (#206)

    func testAMalformedCalendarEntryOrGolferCostsOnlyThat() throws {
        let json = #"""
        {"leagues": [{"calendar": [
            {"id": "1", "label": "Good", "startDate": "2026-01-15T08:00Z", "endDate": "2026-01-18T08:00Z"},
            {"id": "2", "label": "No dates"},
            "junk"]}],
         "events": [{"id": "1", "name": "Good", "status": {"type": {"state": "in"}},
            "competitions": [{"competitors": [
                {"id": "a", "order": 1, "score": "-5", "athlete": {"displayName": "Has A Name"}},
                {"id": "b", "order": 2, "score": "-4"},
                7,
                {"id": "c", "order": 3, "score": "-3", "athlete": {"fullName": 12}, "linescores": [{"period": "x"}]}]}]}]}
        """#
        let response = try JSONDecoder().decode(GolfScoreboardResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.leagues?.first?.calendar.map(\.id), ["1"])
        let tournament = GolfTournament(from: try XCTUnwrap(response.events.first), parseDate: { _ in nil })
        XCTAssertEqual(tournament.competitors.map(\.id), ["a", "b", "c"])
        XCTAssertEqual(tournament.competitors.map(\.playerName), ["Has A Name", "", ""])
        XCTAssertTrue(tournament.isInProgress)
    }

    func testANullEventsListIsNotAnAnswer() {
        XCTAssertThrowsError(try JSONDecoder().decode(GolfScoreboardResponse.self, from: Data(#"{"events": null}"#.utf8)))
        XCTAssertEqual(try JSONDecoder().decode(GolfScoreboardResponse.self, from: Data("{}".utf8)).events.count, 0)
    }

    func testATeamEventsLeaderboardNamesTheTeams() throws {
        let response = try JSONDecoder().decode(GolfScoreboardResponse.self,
                                                from: try Fixtures.data("golf_scoreboard_PGA_20260423.json"))
        let tournament = GolfTournament(from: try XCTUnwrap(response.events.first), parseDate: { _ in nil })
        XCTAssertEqual(tournament.competitors.prefix(2).map(\.playerName), ["Smalley/Springer", "Reitan/Ventura"])
        XCTAssertEqual(tournament.competitors.first?.overallScore, "-30")
    }

    // MARK: - The requests

    private let service = ESPNAPIService(session: StubESPN.session())

    func testTheTournamentIsTheOneInProgressNotTheFirst() async throws {
        var text = String(decoding: try Fixtures.data("golf_scoreboard_PGA_20260305.json"), as: UTF8.self)
        // The second event, the opposite-field Puerto Rico Open, is the one being played.
        let marker = #""name": "Puerto Rico Open""#
        let range = try XCTUnwrap(text.range(of: marker))
        let after = text[range.upperBound...]
        let state = try XCTUnwrap(after.range(of: #""state": "post""#))
        text.replaceSubrange(state, with: #""state": "in""#)
        let body = Data(text.utf8)
        StubESPN.answer { _ in .body(body) }
        let result = try await service.fetchGolfTournament(for: .pga)
        XCTAssertEqual(result.tournament?.name, "Puerto Rico Open")
    }

    func testAPastWeekIsAskedByDateAndPickedById() async throws {
        let body = try Fixtures.data("golf_scoreboard_PGA_20260305.json")
        StubESPN.answer { _ in .body(body) }
        var parts = DateComponents()
        parts.year = 2026; parts.month = 3; parts.day = 5; parts.hour = 12
        let day = try XCTUnwrap(Calendar.current.date(from: parts))
        let result = try await service.fetchGolfTournament(for: .pga, startDate: day, eventID: "401811936")
        XCTAssertEqual(result.tournament?.name, "Puerto Rico Open")
        XCTAssertEqual(StubESPN.requests.first?.query, "dates=20260305")
    }

    func testTheSeasonHasEachFinishedEventsWinner() async throws {
        let body = try Fixtures.data("golf_schedule_PGA_2026.json")
        StubESPN.answer { _ in .body(body) }
        let season = try await service.fetchGolfSeason(for: .pga, year: 2026)
        XCTAssertEqual(StubESPN.requests.first?.query, "dates=2026")
        XCTAssertEqual(season.count, 49)
        let byID = Dictionary(uniqueKeysWithValues: season.map { ($0.id, $0) })
        XCTAssertEqual(byID["401811928"]?.winner?.text, "Chris Gotterup (-16)")
        XCTAssertEqual(byID["401824815"]?.winner?.text, "USA (17)")
        XCTAssertNil(byID["401811927"]?.winner)  // cancelled
        XCTAssertEqual(byID["401850979"]?.state, "in")
    }

    func testTheSeasonFailingThrowsAndNothingThereIsEmpty() async throws {
        StubESPN.answer { _ in .status(503) }
        do {
            _ = try await service.fetchGolfSeason(for: .pga, year: 2026)
            XCTFail("a 503 should throw")
        } catch {}
        StubESPN.answer { _ in .status(404) }
        let none = try await service.fetchGolfSeason(for: .pga, year: 2026)
        XCTAssertTrue(none.isEmpty)
    }

    @MainActor
    func testTheViewModelKeepsWinnersAndSaysWhenTheyFail() async throws {
        let body = try Fixtures.data("golf_schedule_PGA_2026.json")
        StubESPN.answer { _ in .body(body) }
        var parts = DateComponents()
        parts.year = 2026; parts.month = 11; parts.day = 7; parts.hour = 12
        let now = try XCTUnwrap(Calendar(identifier: .gregorian).date(from: parts))
        let model = GolfViewModel(apiService: service, clock: { now })
        await model.fetchSeason(for: .pga)
        XCTAssertFalse(model.seasonFailed)
        XCTAssertEqual(model.seasonEvents["401811941"]?.winner?.text, "Rory McIlroy (-12)")
        XCTAssertEqual(StubESPN.requests.first?.query, "dates=2026")

        StubESPN.answer { _ in .failure(URLError(.timedOut)) }
        await model.fetchSeason(for: .pga)
        XCTAssertTrue(model.seasonFailed)
        XCTAssertEqual(model.seasonEvents.count, 49, "what was shown stays")
    }
}
