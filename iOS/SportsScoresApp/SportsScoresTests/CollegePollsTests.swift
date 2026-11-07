//
//  CollegePollsTests.swift
//  SportsScoresTests
//
//  College football's polls: every one ESPN has, in its order, the same as Windows shows them.
//  tests/unit/replay/test_scores_and_news.py and tests/unit/test_polls_dialog.py hold Windows to
//  the same fixture and the same list.
//

import XCTest
@testable import SportsScores

final class CollegePollsTests: XCTestCase {
    /// ESPN's order, the playoff committee's first. Windows' tabs read the same.
    private let footballPolls = [
        "CFP Rankings", "AP Poll", "AFCA Coaches Poll", "FCS Coaches Poll", "AFCA Div II", "AFCA Div III",
    ]

    private func polls(_ fixture: String) throws -> [RankingsPoll] {
        let response = try JSONDecoder().decode(RankingsAPIResponse.self, from: Fixtures.data(fixture))
        return response.rankings.map { RankingsPoll(from: $0) }
    }

    func testEveryFootballPollInESPNsOrder() throws {
        let football = try polls("rankings_NCAAF.json")
        XCTAssertEqual(football.map(\.shortName), footballPolls)
        XCTAssertEqual(football.map(\.name).first, "Playoff Committee Rankings")
        XCTAssertTrue(football.allSatisfy { !$0.ranks.isEmpty })
    }

    func testEachPollHasItsOwnTeams() throws {
        let football = try polls("rankings_NCAAF.json")
        let tops = football.map { $0.ranks.first?.teamDisplayName }
        XCTAssertEqual(tops[3], "Tarleton State Texans", "FCS")
        XCTAssertEqual(tops[4], "Ferris State Bulldogs", "Division II")
        XCTAssertEqual(tops[5], "Wheaton (IL) Thunder", "Division III")
    }

    /// The committee ranks with no votes: ESPN sends 0.0, which mustn't read as "0 points".
    /// In its first week every team has previous 0, which is new to the rankings.
    func testThePlayoffCommitteeHasNoPoints() throws {
        let cfp = try XCTUnwrap(try polls("rankings_NCAAF.json").first)
        XCTAssertTrue(cfp.ranks.allSatisfy { $0.points == nil })
        XCTAssertTrue(cfp.ranks.allSatisfy { $0.movementText == "NR" })
        XCTAssertEqual(cfp.ranks.map(\.recordSummary), ["8-0", "7-1", "8-0"])
    }

    func testTheVotedPollsKeepTheirPoints() throws {
        for poll in try polls("rankings_NCAAF.json").dropFirst() {
            XCTAssertTrue(poll.ranks.allSatisfy { ($0.points ?? 0) > 0 }, poll.shortName)
        }
    }

    /// Six segments would cut most of football's poll names short; basketball's two and
    /// hockey's one stay segments.
    func testFootballPicksItsPollFromAMenu() throws {
        XCTAssertTrue(PollsViewModel.usesMenu(pollCount: try polls("rankings_NCAAF.json").count))
        XCTAssertFalse(PollsViewModel.usesMenu(pollCount: 2))
        XCTAssertFalse(PollsViewModel.usesMenu(pollCount: try polls("rankings_NCAAH.json").count))
    }
}
