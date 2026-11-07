//
//  DriveResults.swift
//  SportsScores
//
//  Who scored on a football drive, and how many points. Pure, so the tests run it on
//  the shared grid and the real ESPN drives.
//
//  ESPN's drive `result` names how the drive ended, not who scored: a missed field goal
//  run back for a touchdown, a kickoff returned for one, a pick six and a safety are all
//  marked on the drive of the team that gave the points up. And it gives no points, so
//  a touchdown with no extra point, or with a two-point conversion, reads like any other.
//  Every play carries the score after it, so this reads the score instead: the side whose
//  score went up first in the drive scored, with every point that side added in it.
//
//  The Windows twin is drive_results.py. The two must agree:
//  tests/fixtures/drive_results_grid.json holds both, with DriveResultsGridTests.swift
//  here and tests/unit/test_drive_results.py there.
//

import Foundation

enum DriveSide: String, Equatable {
    case away, home

    var other: DriveSide { self == .away ? .home : .away }
}

/// How a drive's scoring reads. Raw values are the grid's.
enum DriveScoreKind: String, Equatable {
    case touchdown = "TD"
    case fieldGoal = "FG"
    case score = "SCORE"
    case returnTouchdown = "RETURN TD"
    case safety = "SAFETY"
    case opponentScore = "OPPONENT SCORE"
}

struct DriveResult: Equatable {
    /// Nil when nobody scored.
    var kind: DriveScoreKind? = nil
    var points: Int = 0
    var scorer: DriveSide? = nil
    /// True when the side that scored isn't the side with the ball.
    var byOpponent: Bool = false
    /// Points the other side scored later in the same drive, such as a blocked extra
    /// point run back for two.
    var otherPoints: Int = 0
}

/// What the rule needs of a drive: who had the ball, and the score after each play
/// (nil for a play without one).
struct DriveScoreInput {
    let teamID: String?
    let plays: [(away: Int?, home: Int?)]
}

enum DriveResults {
    private static func kind(points: Int, byOpponent: Bool) -> DriveScoreKind {
        if byOpponent {
            if (6...8).contains(points) { return .returnTouchdown }
            if points == 2 { return .safety }
            return .opponentScore
        }
        if (6...8).contains(points) { return .touchdown }
        if points == 3 { return .fieldGoal }
        return .score
    }

    /// One result per drive, for drives in the order they were played from the start of
    /// the game: the score before a drive is the last score seen before it. A play
    /// without a score is skipped; a score that goes down is taken as the new score
    /// without counting anything.
    static func results(_ drives: [DriveScoreInput], awayID: String?, homeID: String?) -> [DriveResult] {
        var running = (away: 0, home: 0)
        return drives.map { drive in
            var added = (away: 0, home: 0)
            var first: DriveSide?
            for play in drive.plays {
                guard let away = play.away, let home = play.home else { continue }
                if away > running.away {
                    added.away += away - running.away
                    first = first ?? .away
                }
                if home > running.home {
                    added.home += home - running.home
                    first = first ?? .home
                }
                running = (away, home)
            }
            guard let scorer = first else { return DriveResult() }
            var offense: DriveSide?
            if let team = drive.teamID, !team.isEmpty {
                if team == awayID { offense = .away } else if team == homeID { offense = .home }
            }
            let byOpponent = offense != nil && offense != scorer
            let points = scorer == .away ? added.away : added.home
            return DriveResult(kind: kind(points: points, byOpponent: byOpponent),
                               points: points,
                               scorer: scorer,
                               byOpponent: byOpponent,
                               otherPoints: scorer == .away ? added.home : added.away)
        }
    }

    private static func pts(_ points: Int) -> String { points == 1 ? "1pt" : "\(points)pts" }

    /// "TD 6pts", or "Duke Blue Devils return TD 7pts" for a score by the team without
    /// the ball. Nil for a drive with no score.
    static func badge(_ result: DriveResult, scorerName: String, otherName: String) -> String? {
        guard let kind = result.kind else { return nil }
        let points = pts(result.points)
        let scorer = scorerName.isEmpty ? "Other team" : scorerName
        var badge: String
        switch kind {
        case .touchdown:       badge = "TD \(points)"
        case .fieldGoal:       badge = "FG \(points)"
        case .score:           badge = points
        case .returnTouchdown: badge = "\(scorer) return TD \(points)"
        case .safety:          badge = "\(scorer) safety \(points)"
        case .opponentScore:   badge = "\(scorer) \(points)"
        }
        if result.otherPoints > 0 {
            badge += ", \(otherName.isEmpty ? "other team" : otherName) \(pts(result.otherPoints))"
        }
        return badge
    }
}

extension GameDetails.Drive {
    var scoreInput: DriveScoreInput {
        DriveScoreInput(teamID: team?.id,
                        plays: (plays ?? []).map { (away: $0.awayScore, home: $0.homeScore) })
    }
}
