//
//  Golf.swift
//  SportsScores
//
//  Domain models for golf tournaments, leaderboards, and schedules.
//  Constructed from GolfAPIModels (the raw Decodable layer).
//

import Foundation

// MARK: - Tournament Schedule Entry

struct GolfCalendarEntry: Identifiable, Equatable {
    let id: String
    let name: String
    let startDate: Date
    let endDate: Date

    var dateRangeText: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d"
        let start = fmt.string(from: startDate)
        // End date: show month only if different from start month
        let sameMonth = Calendar.current.component(.month, from: startDate) ==
                        Calendar.current.component(.month, from: endDate)
        let endFmt = DateFormatter()
        endFmt.dateFormat = sameMonth ? "d" : "MMM d"
        let end = endFmt.string(from: endDate)
        let yearFmt = DateFormatter()
        yearFmt.dateFormat = "yyyy"
        return "\(start) – \(end), \(yearFmt.string(from: endDate))"
    }
}

// MARK: - Hole Score

struct GolfHole: Identifiable {
    let number: Int           // 1–18
    let strokes: Int
    let relativeScore: String // "+1", "-1", "E", etc.

    var id: Int { number }
}

// MARK: - Round

struct GolfRound: Identifiable {
    let period: Int            // round number 1–4
    let displayScore: String   // par-relative: "-5", "+1", "E"
    let strokes: Int           // raw total e.g. 67
    let holes: [GolfHole]

    var id: Int { period }
    var label: String { "R\(period)" }

    /// Number of holes actually played (strokes > 0) in this round.
    var holesPlayed: Int { holes.filter { $0.strokes > 0 }.count }

    var isComplete: Bool { strokes > 0 }

    /// Stroke total for display in a compact table cell (e.g. "67").
    var tableCellText: String {
        guard isComplete else { return "--" }
        return String(strokes)
    }
}

// MARK: - Competitor (leaderboard row)

struct GolfCompetitor: Identifiable {
    let id: String
    let position: Int           // 1-based leaderboard rank
    let playerName: String
    let shortName: String
    let country: String
    let overallScore: String    // "-12", "E", "+5", "CUT", "WD", "DQ"
    let rounds: [GolfRound]
    /// First position of a group of golfers on the same score, shown as "T3".
    /// ESPN's `order` ranks tied golfers 3, 4, 5 arbitrarily.
    var tiedPosition: Int? = nil

    var isCut: Bool    { overallScore == "CUT" }
    var isWithdrawn: Bool { overallScore == "WD" || overallScore == "DQ" }
    var isActive: Bool { !isCut && !isWithdrawn }

    var positionDisplay: String {
        if isCut || isWithdrawn { return overallScore }
        if let tied = tiedPosition { return "T\(tied)" }
        return "\(position)"
    }

    // MARK: Table row helpers

    /// Values for each round column (R1–R4), "--" when not yet played.
    func roundScore(for round: Int) -> String {
        rounds.first(where: { $0.period == round })?.tableCellText ?? "--"
    }

    /// Holes completed in the player's current/latest round.
    /// Returns the hole count mid-round, "F" when the round is finished,
    /// or "--" when the player hasn't teed off yet.
    func thruDisplay(tournamentInProgress: Bool) -> String {
        if let progress = currentRoundProgress {
            return "\(progress.holesPlayed)"
        }
        if tournamentInProgress && isActive && !rounds.filter(\.isComplete).isEmpty {
            return "F"
        }
        return "--"
    }

    /// Current round's score to par (e.g. "-4"), or "--" if not started.
    var currentRoundDisplayScore: String {
        rounds.filter { $0.strokes > 0 }.sorted { $0.period > $1.period }.first?.displayScore ?? "--"
    }

    /// Sum of strokes across fully completed rounds (all 18 holes played).
    var totalStrokes: Int {
        rounds.filter { $0.holesPlayed == 18 }.reduce(0) { $0 + $1.strokes }
    }

    /// Formatted total for display; "--" if no rounds completed yet.
    var totalStrokesDisplay: String {
        let t = totalStrokes
        return t > 0 ? String(t) : "--"
    }

    /// When the tournament is live and this player is mid-round, returns
    /// the (round number, holes completed) pair; otherwise nil.
    var currentRoundProgress: (round: Int, holesPlayed: Int)? {
        guard isActive else { return nil }
        for round in rounds.sorted(by: { $0.period < $1.period }).reversed() {
            let played = round.holesPlayed
            if played > 0 && played < 18 {
                return (round: round.period, holesPlayed: played)
            }
        }
        return nil
    }

    // MARK: Accessible table helpers

    /// "thru 9" when mid-round, nil otherwise (doesn't need tournamentInProgress).
    var thruText: String? {
        guard let progress = currentRoundProgress else { return nil }
        return "thru \(progress.holesPlayed)"
    }

    /// Quick-list: "1. Justin Rose  -4 thru 10  -12  70 / 69 / 69 / 36  208"
    var quickListText: String {
        let scores = (1...4).map { roundScore(for: $0) }.joined(separator: " / ")
        let thru: String
        if let progress = currentRoundProgress {
            thru = "thru \(progress.holesPlayed)"
        } else if currentRoundDisplayScore != "--" {
            thru = "F"
        } else {
            thru = "--"
        }
        return "\(positionDisplay). \(playerName)  \(currentRoundDisplayScore) \(thru)  \(overallScore)  \(scores)  \(totalStrokesDisplay)"
    }

    /// Full-list (card) description for VoiceOver.
    var fullListText: String {
        var lines = ["Score: \(overallScore)"]
        if currentRoundDisplayScore != "--" { lines.append("Today: \(currentRoundDisplayScore)") }
        for r in rounds where r.isComplete {
            lines.append("Round \(r.period): \(r.displayScore) (\(r.strokes) strokes)")
        }
        if totalStrokesDisplay != "--" { lines.append("Total: \(totalStrokesDisplay)") }
        return lines.joined(separator: "; ")
    }
}

// MARK: - Tournament

struct GolfTournament: Identifiable {
    let id: String
    let name: String
    let startDate: Date
    let statusState: String    // "pre", "in", "post"
    let statusDescription: String  // "In Progress", "Scheduled", "Final"
    let isCompleted: Bool
    let broadcasts: [String]
    let competitors: [GolfCompetitor]

    var isInProgress: Bool { statusState == "in" }
    var isScheduled: Bool  { statusState == "pre" }

    /// Number of rounds completed or in progress, derived from competitors.
    var currentRound: Int {
        competitors.first?.rounds.filter(\.isComplete).count ?? 0
    }

    /// Human-readable status + round, e.g. "Round 4 · In Progress" or "Final".
    var roundStatusText: String {
        if isScheduled { return statusDescription }
        let r = currentRound
        if r == 0 { return statusDescription }
        let roundLabel = "Round \(r)"
        if isInProgress { return "\(roundLabel) · In Progress" }
        return isCompleted ? (r == 4 ? "Final" : "Complete") : roundLabel
    }

    /// Live broadcast networks, comma-joined.
    var broadcastText: String {
        broadcasts.joined(separator: " · ")
    }

    // MARK: Init from API response

    init(from api: GolfEventAPIResponse, parseDate: (String) -> Date?) {
        id = api.id
        name = api.name
        startDate = parseDate(api.date ?? "") ?? Date()
        let competition = api.competitions.first
        let type = api.status?.type ?? competition?.status?.type
        statusState = GolfRules.state(of: api)
        statusDescription = type?.description ?? ""
        isCompleted = type?.completed ?? false

        broadcasts = competition?.broadcasts.flatMap(\.names) ?? []

        var ranked = GolfRules.byOrder(competition?.competitors ?? [])
            .enumerated()
            .map { GolfCompetitor(from: $0.element, place: $0.offset + 1) }
        // Golfers on the same score share the first position among them ("T1").
        let active = ranked.filter(\.isActive)
        let counts = Dictionary(grouping: active, by: \.overallScore).mapValues(\.count)
        var firstPosition: [String: Int] = [:]
        for i in ranked.indices where ranked[i].isActive {
            let score = ranked[i].overallScore
            let first = firstPosition[score] ?? ranked[i].position
            firstPosition[score] = first
            if (counts[score] ?? 0) > 1 { ranked[i].tiedPosition = first }
        }
        competitors = ranked
    }
}

// MARK: - GolfCompetitor init from API

extension GolfCompetitor {
    /// `place` stands in for ESPN's `order` when it's left out: the row's place on the board.
    init(from api: GolfCompetitorAPIResponse, place: Int) {
        position = api.order ?? place
        id = api.id.isEmpty ? "row-\(place)" : api.id
        // A team event's competitor is a team ("Smalley/Springer"), with no athlete.
        playerName = GolfRules.competitorName(api)
        let short = api.athlete?.shortName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        shortName = short.isEmpty ? playerName : short
        country = api.athlete?.flag?.alt ?? ""
        overallScore = GolfCompetitor.totalToPar(
            score: api.score, roundScores: api.linescores.map(\.displayValue))

        rounds = api.linescores.map { ls in
            let strokes = ls.value.map { Int($0) } ?? 0
            let holes = ls.linescores.map { h -> GolfHole in
                GolfHole(
                    number: h.period,
                    strokes: h.value.map { Int($0) } ?? 0,
                    relativeScore: h.scoreType?.displayValue ?? "E"
                )
            }
            return GolfRound(
                period: ls.period,
                displayScore: ls.displayValue ?? "--",
                strokes: strokes,
                holes: holes
            )
        }
    }
}

extension GolfCompetitor {
    /// A golfer's total to par, including the round in progress.
    ///
    /// ESPN's `score` leaves out the round being played: a golfer at +1, -4
    /// and -8 through 12 holes of round 3 shows -3, not -11. Each round's
    /// displayValue is that round to par ("-8", "+1", "E", or "-" if not
    /// started), so the total is their sum. CUT, WD and DQ are kept as they
    /// are. Matches golf_total_to_par in the Windows app's espn_api.py.
    static func totalToPar(score: String?, roundScores: [String?]) -> String {
        let raw = (score ?? "").trimmingCharacters(in: .whitespaces)
        if !raw.isEmpty && raw.uppercased() != "E" && Int(raw) == nil {
            return raw  // CUT, WD, DQ
        }
        var total = 0
        var counted = false
        for case let value? in roundScores {
            let v = value.trimmingCharacters(in: .whitespaces)
            if v.uppercased() == "E" {
                counted = true
            } else if v.count > 1, let n = Int(v) {
                total += n
                counted = true
            }
        }
        guard counted else { return raw.isEmpty ? "E" : raw }
        if total == 0 { return "E" }
        return total > 0 ? "+\(total)" : "\(total)"
    }
}

// MARK: - Result bundle returned from API service

struct GolfTournamentResult {
    let tournament: GolfTournament?
    let calendar: [GolfCalendarEntry]
}

/// One event of the season, from `scoreboard?dates=YEAR` (the request Windows' schedule
/// makes): its state, and once it's finished, who won. Keyed to the calendar by `id`.
struct GolfSeasonEvent: Equatable {
    let id: String
    let state: String       // "pre", "in", "post", or "" when ESPN doesn't say
    let winner: GolfWinner?
    /// ESPN's word for the event's status ("Final", "Canceled"), as Windows shows a finished
    /// event with no winner.
    let statusDescription: String

    init(from api: GolfEventAPIResponse) {
        id = api.id
        state = GolfRules.state(of: api)
        winner = GolfRules.winner(of: api)
        let type = api.status?.type ?? api.competitions.first?.status?.type
        statusDescription = type?.description?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}
