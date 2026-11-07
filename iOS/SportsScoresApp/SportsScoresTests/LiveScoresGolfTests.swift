//
//  LiveScoresGolfTests.swift
//  SportsScoresTests
//
//  Golf on Live Scores when a tour doesn't answer, the same rules as Windows: the tournament
//  last shown stays, on the same scoreboard day, and the tour is named in the note under the
//  list. A tour that answers with nothing in progress comes off, which isn't a failure.
//

import XCTest
@testable import SportsScores

@MainActor
final class LiveScoresGolfTests: XCTestCase {
    private let noGames = Data(#"{"events":[]}"#.utf8)

    /// The time the view model sees: noon today, unless a test moves it.
    private var now = Calendar.current.date(bySettingHour: 12, minute: 0, second: 0, of: Date()) ?? Date()

    private func makeModel() -> LiveScoresViewModel {
        LiveScoresViewModel(apiService: ESPNAPIService(session: StubESPN.session()),
                            clock: { [unowned self] in self.now })
    }

    /// The PGA fixture (a tournament not started yet), with its state set to `state`.
    private func pgaScoreboard(_ state: String) throws -> Data {
        let text = String(decoding: try Fixtures.data("golf_scoreboard_PGA.json"), as: UTF8.self)
        return Data(text.replacingOccurrences(of: #""state": "pre""#, with: "\"state\": \"\(state)\"").utf8)
    }

    /// Every team league with no games; the PGA answering `pga`, the LPGA with nothing on,
    /// and `nba` for the NBA when given.
    private func answer(pga: StubESPN.Reply, nba: StubESPN.Reply? = nil) throws {
        let notStarted = try pgaScoreboard("pre")
        let empty = noGames
        StubESPN.answer { url in
            let path = url.path
            if path.contains("/golf/pga/") { return pga }
            if path.contains("/golf/lpga/") { return .body(notStarted) }
            if let nba, path.contains("/basketball/nba/") { return nba }
            return .body(empty)
        }
    }

    private func failure(_ names: [String], showing: Bool) -> String {
        APIError.liveScoresFailure(names, showing: showing)
    }

    func testATournamentInProgressIsShown() async throws {
        try answer(pga: .body(pgaScoreboard("in")))
        let model = makeModel()
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.activeTournaments.map(\.sport), [.pga])
        XCTAssertEqual(model.activeTournaments.first?.tournament.name, "World Wide Technology Championship")
        XCTAssertNil(model.failureNote)
        // A tournament is something to show, so there's no "no games" screen over it.
        XCTAssertNil(model.errorMessage)
    }

    func testATourThatFailsKeepsItsTournamentAndIsNamed() async throws {
        let model = makeModel()
        try answer(pga: .body(pgaScoreboard("in")))
        await model.fetchAllGames(golf: true)

        try answer(pga: .failure(URLError(.timedOut)))
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.activeTournaments.map(\.sport), [.pga])
        XCTAssertEqual(model.activeTournaments.first?.tournament.name, "World Wide Technology Championship")
        XCTAssertEqual(model.failureNote, failure([Sport.pga.displayName], showing: true))
        XCTAssertNil(model.errorMessage)

        // And a server error the same.
        try answer(pga: .status(503))
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.activeTournaments.map(\.sport), [.pga])
        XCTAssertEqual(model.failureNote, failure([Sport.pga.displayName], showing: true))

        // Answering again clears the note.
        try answer(pga: .body(pgaScoreboard("in")))
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.activeTournaments.map(\.sport), [.pga])
        XCTAssertNil(model.failureNote)
    }

    func testAKeptTournamentGoesWhenTheScoreboardDayIsOver() async throws {
        let model = makeModel()
        try answer(pga: .body(pgaScoreboard("in")))
        await model.fetchAllGames(golf: true)

        // Still last night's scoreboard at 4 AM: kept. (Set by the clock, not by adding hours,
        // which a daylight saving change would throw off.)
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: now)!
        now = Calendar.current.date(bySettingHour: 4, minute: 0, second: 0, of: tomorrow)!
        try answer(pga: .failure(URLError(.timedOut)))
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.activeTournaments.map(\.sport), [.pga])

        // Past 5 AM it's a new day, and what was kept is too old to show.
        now = Calendar.current.date(bySettingHour: 6, minute: 0, second: 0, of: tomorrow)!
        await model.fetchAllGames(golf: true)
        XCTAssertTrue(model.activeTournaments.isEmpty)
        XCTAssertNil(model.failureNote)
        XCTAssertEqual(model.errorMessage, failure([Sport.pga.displayName], showing: false))
    }

    func testAFailedTourIsNamedWithTheFailedLeagues() async throws {
        let model = makeModel()
        try answer(pga: .body(pgaScoreboard("in")))
        await model.fetchAllGames(golf: true)

        try answer(pga: .failure(URLError(.timedOut)), nba: .status(500))
        await model.fetchAllGames(golf: true)
        XCTAssertEqual(model.failureNote, failure([Sport.nba.displayName, Sport.pga.displayName], showing: true))
    }

    func testATourFailingWithNothingToKeepSaysSo() async throws {
        try answer(pga: .failure(URLError(.timedOut)))
        let model = makeModel()
        await model.fetchAllGames(golf: true)
        XCTAssertTrue(model.activeTournaments.isEmpty)
        XCTAssertNil(model.failureNote)
        XCTAssertEqual(model.errorMessage, failure([Sport.pga.displayName], showing: false))
    }

    func testATournamentThatsOverComesOff() async throws {
        let model = makeModel()
        try answer(pga: .body(pgaScoreboard("in")))
        await model.fetchAllGames(golf: true)

        try answer(pga: .body(pgaScoreboard("post")))
        await model.fetchAllGames(golf: true)
        XCTAssertTrue(model.activeTournaments.isEmpty)
        XCTAssertNil(model.failureNote)
        XCTAssertEqual(model.errorMessage, "No games scheduled today")
    }

    /// ESPN's 400 and 404 mean nothing there, as on Windows, not a failure.
    func testNothingThereIsntAFailure() async throws {
        for code in [400, 404] {
            try answer(pga: .status(code))
            let model = makeModel()
            await model.fetchAllGames(golf: true)
            XCTAssertTrue(model.activeTournaments.isEmpty, "\(code)")
            XCTAssertNil(model.failureNote, "\(code)")
            XCTAssertEqual(model.errorMessage, "No games scheduled today", "\(code)")
        }
    }

    func testGolfTurnedOffAsksForNoGolf() async throws {
        try answer(pga: .failure(URLError(.timedOut)))
        let model = makeModel()
        await model.fetchAllGames(golf: false)
        XCTAssertTrue(model.activeTournaments.isEmpty)
        XCTAssertNil(model.failureNote)
        XCTAssertEqual(model.errorMessage, "No games scheduled today")
        XCTAssertFalse(StubESPN.requests.contains { $0.path.contains("/golf/") })
    }
}
