//
//  ViewModeDefaultTests.swift
//  SportsScoresTests
//
//  Issue 90. Every table screen starts in the "Default view" setting, through
//  ViewMode.savedDefault() (tests/unit/test_ios_default_view.py checks that every screen
//  uses it), and a standings Full List row is spoken with every field it shows.
//

import XCTest
@testable import SportsScores

final class ViewModeDefaultTests: XCTestCase {
    private var defaults: UserDefaults!
    private let suite = "ViewModeDefaultTests"

    override func setUp() {
        super.setUp()
        defaults = UserDefaults(suiteName: suite)
        defaults.removePersistentDomain(forName: suite)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
        super.tearDown()
    }

    func testNothingSavedIsQuickList() {
        XCTAssertEqual(ViewMode.savedDefault(in: defaults), .quickList)
    }

    func testEachSavedModeComesBack() {
        for mode in ViewMode.allCases {
            defaults.set(mode.rawValue, forKey: ViewMode.defaultsKey)
            XCTAssertEqual(ViewMode.savedDefault(in: defaults), mode)
        }
    }

    func testSomethingUnreadableIsQuickList() {
        defaults.set("Grid", forKey: ViewMode.defaultsKey)
        XCTAssertEqual(ViewMode.savedDefault(in: defaults), .quickList)
    }

    /// The setting the Settings screen changes is the one a new screen starts from.
    @MainActor
    func testTheSettingIsWhatANewScreenStartsIn() {
        let saved = UserDefaults.standard.string(forKey: ViewMode.defaultsKey)
        defer {
            if let saved { UserDefaults.standard.set(saved, forKey: ViewMode.defaultsKey) }
            else { UserDefaults.standard.removeObject(forKey: ViewMode.defaultsKey) }
        }
        let settings = AppSettings()
        settings.defaultTableViewMode = .table
        XCTAssertEqual(ViewMode.savedDefault(), .table)
        settings.defaultTableViewMode = .fullList
        XCTAssertEqual(ViewMode.savedDefault(), .fullList)
        XCTAssertEqual(AppSettings().defaultTableViewMode, .fullList)
    }
}

final class StandingsFullListSpeechTests: XCTestCase {
    private func stats(otLosses: Int? = nil, points: Int? = nil, lastTen: String? = nil) -> StandingsEntry.StandingsStats {
        StandingsEntry.StandingsStats(
            wins: 93, losses: 68, winPercent: 0.578, gamesBack: "-", streak: "W1", record: "93-68",
            pointsFor: nil, pointsAgainst: nil, ties: nil, otLosses: otLosses, nhlPoints: points,
            avgPointsFor: nil, avgPointsAgainst: nil, homeRecord: nil, roadRecord: nil,
            lastTenRecord: lastTen, divisionRecord: nil, playoffSeed: nil, differential: nil)
    }

    private let yankees = StandingsEntry.TeamInfo(
        id: "10", name: "Yankees", abbreviation: "NYY", displayName: "New York Yankees", logo: nil)

    func testAWildCardRowSaysItsRecord() {
        let entry = StandingsEntry(
            rank: 0, team: yankees, stats: stats(),
            wildCard: WildCardStanding(position: "1", status: "Wild card 1", gamesBack: "+2.0"))
        let spoken = entry.fullListText(team: "NYY")
        XCTAssertTrue(spoken.contains("Record: 93-68"), spoken)
        XCTAssertEqual(spoken, entry.fullListText.replacingOccurrences(of: "New York Yankees", with: "NYY"))
        XCTAssertEqual(spoken,
            "Position: 1; Team: NYY; Wins: 93; Losses: 68; Win%: .578; Wild card games back: +2.0; "
            + "Streak: W1; Record: 93-68; Status: Wild card 1")
    }

    func testAnNhlRowSaysItsLastTen() {
        let entry = StandingsEntry(rank: 0, team: yankees, stats: stats(otLosses: 1, points: 21, lastTen: "7-2-1"))
        let spoken = entry.nhlFullListText(team: "Yankees")
        XCTAssertEqual(spoken, entry.nhlFullListText.replacingOccurrences(of: "New York Yankees", with: "Yankees"))
        XCTAssertTrue(spoken.contains("Overtime losses: 1; Points: 21"), spoken)
        XCTAssertTrue(spoken.hasSuffix("; Last 10: 7-2-1"), spoken)
    }

    func testNoRankIsNotSpokenAsZero() {
        let entry = StandingsEntry(rank: 0, team: yankees, stats: stats())
        XCTAssertFalse(entry.fullListText(team: "NYY").contains("Rank"))
        XCTAssertTrue(StandingsEntry(rank: 2, team: yankees, stats: stats())
            .fullListText(team: "NYY").hasPrefix("Rank: 2; Team: NYY"))
    }
}
