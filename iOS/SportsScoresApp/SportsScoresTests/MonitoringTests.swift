//
//  MonitoringTests.swift
//  SportsScoresTests
//
//  Live Scores' Monitoring section (#185): the store, and which games are on today's
//  scoreboard, held to tests/fixtures/scoreboard_date_grid.json as game_labels.py is.
//

import XCTest
@testable import SportsScores

private struct ScoreboardDateGrid: Decodable {
    struct Case: Decodable {
        let name: String
        let date: String
        let time_valid: Bool
        let now: String
        let zone: String
        let today: Bool
    }
    let cases: [Case]
}

final class ScoreboardDateGridTests: XCTestCase {
    private func utcStart(_ text: String) throws -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm'Z'"
        return try XCTUnwrap(formatter.date(from: text), text)
    }

    private func wallClock(_ text: String, in zone: TimeZone) throws -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = zone
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return try XCTUnwrap(formatter.date(from: text), text)
    }

    func testTheSharedGrid() throws {
        let raw = try Data(contentsOf: Fixtures.repoRoot
            .appendingPathComponent("tests/fixtures/scoreboard_date_grid.json"))
        let grid = try JSONDecoder().decode(ScoreboardDateGrid.self, from: raw)
        XCTAssertEqual(Set(grid.cases.map(\.today)), [true, false])
        for item in grid.cases {
            let zone = try XCTUnwrap(TimeZone(identifier: item.zone), item.zone)
            let start = try utcStart(item.date)
            // As Game(from:) stores it: a game with no time set sits at noon local on its UTC date.
            let stored = item.time_valid ? start : ScoreboardDay.localNoon(onUTCDayOf: start, in: zone)
            let now = try wallClock(item.now, in: zone)
            XCTAssertEqual(ScoreboardDay.isOnTodaysScoreboard(stored, timeValid: item.time_valid, now: now,
                                                              localTimeZone: zone),
                           item.today, item.name)
        }
    }
}

@MainActor
final class MonitoringStoreTests: XCTestCase {
    private func game(_ id: String, name: String = "Chicago Bears at Seattle Seahawks",
                      date: Date = Date(), timeValid: Bool? = nil) -> Game {
        var game = Game(id: id, name: name, shortName: "CHI @ SEA", date: date,
                        status: Game.GameStatus(state: "pre", detail: "Scheduled", period: nil, clock: nil, name: nil),
                        homeTeam: Game.Team(id: "26", name: "Seahawks", abbreviation: "SEA",
                                            displayName: "Seattle Seahawks", score: nil, record: nil, logo: nil),
                        awayTeam: Game.Team(id: "3", name: "Bears", abbreviation: "CHI",
                                            displayName: "Chicago Bears", score: nil, record: nil, logo: nil),
                        venue: nil, broadcasts: [], situation: nil, seasonType: 2)
        game.timeValid = timeValid
        return game
    }

    private let chicago = TimeZone(identifier: "America/Chicago")!

    /// Noon on Saturday, November 7, 2026, in Chicago.
    private var saturdayNoon: Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = chicago
        return calendar.date(from: DateComponents(year: 2026, month: 11, day: 7, hour: 12))!
    }

    func testTheWordsMatchWindows() {
        XCTAssertEqual(MonitoringStore.Said.added, "Added to monitoring")
        XCTAssertEqual(MonitoringStore.Said.removed, "Removed from monitoring")
        XCTAssertEqual(MonitoringStore.Said.addedFromSportPage, "Added to monitoring, at the top of Live Scores")
        XCTAssertEqual(MonitoringStore.Said.onlyToday, "Only today's games can be monitored")
        XCTAssertEqual(MonitoringStore.Said.removedFromSection("Bears at Seahawks"),
                       "Bears at Seahawks removed from monitoring")
        XCTAssertEqual(MonitoringStore.ActionName.monitor, "Monitor")
        XCTAssertEqual(MonitoringStore.ActionName.stop, "Stop Monitoring")
    }

    /// A sport page offers Monitor only for leagues Live Scores lists: a CFL game would never show.
    func testOnlyLiveScoresLeaguesCanBeMonitored() {
        XCTAssertTrue(Sport.liveScoresLeagues.contains(.nfl))
        XCTAssertTrue(Sport.liveScoresLeagues.contains(.soccerEPL))
        XCTAssertFalse(Sport.liveScoresLeagues.contains(.cfl))
        XCTAssertFalse(Sport.liveScoresLeagues.contains(.pga))
    }

    func testLiveScoresTogglesAndKeepsTheOrderAdded() {
        let store = MonitoringStore()
        XCTAssertEqual(store.actionName(for: "1"), "Monitor")
        XCTAssertEqual(store.toggleFromLiveScores(game("2")), "Added to monitoring")
        XCTAssertEqual(store.toggleFromLiveScores(game("1")), "Added to monitoring")
        XCTAssertEqual(store.toggleFromLiveScores(game("3")), "Added to monitoring")
        XCTAssertEqual(store.gameIDs, ["2", "1", "3"])
        XCTAssertEqual(store.actionName(for: "1"), "Stop Monitoring")
        XCTAssertEqual(store.toggleFromLiveScores(game("1")), "Removed from monitoring")
        XCTAssertEqual(store.gameIDs, ["2", "3"])
        XCTAssertFalse(store.isMonitored("1"))
    }

    func testASportPageAddsOnlyTodaysGames() {
        let store = MonitoringStore()
        let tonight = game("tonight", date: saturdayNoon.addingTimeInterval(7 * 3600))   // 7 PM Chicago
        let tomorrow = game("tomorrow", date: saturdayNoon.addingTimeInterval(24 * 3600))
        XCTAssertEqual(store.toggleFromSportPage(tomorrow, now: saturdayNoon, localTimeZone: chicago),
                       "Only today's games can be monitored")
        XCTAssertFalse(store.isMonitored("tomorrow"))
        XCTAssertEqual(store.toggleFromSportPage(tonight, now: saturdayNoon, localTimeZone: chicago),
                       "Added to monitoring, at the top of Live Scores")
        XCTAssertEqual(store.gameIDs, ["tonight"])
        XCTAssertEqual(store.toggleFromSportPage(tonight, now: saturdayNoon, localTimeZone: chicago),
                       "Removed from monitoring")
        XCTAssertTrue(store.gameIDs.isEmpty)
    }

    func testAGameAlreadyMonitoredComesOffFromASportPageWhateverTheDay() {
        let store = MonitoringStore()
        let tonight = game("tonight", date: saturdayNoon.addingTimeInterval(7 * 3600))
        _ = store.toggleFromLiveScores(tonight)
        let nextDay = saturdayNoon.addingTimeInterval(24 * 3600)
        XCTAssertEqual(store.toggleFromSportPage(tonight, now: nextDay, localTimeZone: chicago),
                       "Removed from monitoring")
    }

    func testAGameWithNoTimeSetGoesByItsDate() {
        let store = MonitoringStore()
        let noon = ScoreboardDay.localNoon(onUTCDayOf: saturdayNoon, in: chicago)
        XCTAssertEqual(store.toggleFromSportPage(game("tbd", date: noon, timeValid: false),
                                                 now: saturdayNoon, localTimeZone: chicago),
                       "Added to monitoring, at the top of Live Scores")
    }

    func testStopMonitoringMovesToTheNextRowOrTheHeader() {
        let store = MonitoringStore()
        for id in ["a", "b", "c"] { _ = store.toggleFromLiveScores(game(id)) }
        let shown = ["a", "b", "c"]

        let middle = store.stopFromMonitoringRow(game("b"), shown: shown)
        XCTAssertEqual(middle.said, "Chicago Bears at Seattle Seahawks removed from monitoring")
        XCTAssertEqual(middle.next, "c")

        let last = store.stopFromMonitoringRow(game("c"), shown: ["a", "c"])
        XCTAssertNil(last.next, "none after it: the section's header")

        let unnamed = store.stopFromMonitoringRow(game("a", name: "  "), shown: ["a"])
        XCTAssertEqual(unnamed.said, "Game removed from monitoring")
        XCTAssertNil(unnamed.next)
        XCTAssertTrue(store.gameIDs.isEmpty)
    }

    func testShownIsInTheOrderAddedAndOnlyWhatsOnToday() {
        let store = MonitoringStore()
        for id in ["late", "early", "gone"] { _ = store.toggleFromLiveScores(game(id)) }
        let sections: [(sport: Sport, games: [Game])] = [
            (sport: .nfl, games: [game("early"), game("other")]),
            (sport: .ncaaf, games: [game("late")]),
            // The same game listed again further down keeps the first sport it was found under.
            (sport: .nba, games: [game("early")])
        ]
        let shown = store.shown(in: sections)
        XCTAssertEqual(shown.map(\.id), ["late", "early"])
        XCTAssertEqual(shown.map(\.sport), [.ncaaf, .nfl])
        // Not on the list today, so not shown, but still monitored for when it is.
        XCTAssertTrue(store.isMonitored("gone"))
    }
}
