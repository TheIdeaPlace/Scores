//
//  Racing.swift
//  SportsScores
//
//  Domain models for auto racing: race events, competitors, and championship standings.
//  Covers Formula 1 (racing/f1), IndyCar (racing/irl), and NASCAR Cup (racing/nascar-premier).
//

import Foundation

// MARK: - Race Competitor

struct RaceCompetitor: Identifiable {
    let id: String
    let position: Int?         // finishing or running order; nil before the race, in an entry list
    let driverName: String
    let shortName: String      // e.g. "K. Antonelli"
    let nationality: String    // country name from flag.alt, may be empty
}

// MARK: - Race Event

/// The date, status and field are the race's own competition, never the event's or the first
/// session's: Formula 1's event said Final with the race the next day. racing.py on Windows reads
/// the same way, and tests/fixtures/racing_grid.json holds the two together.
struct RaceEvent: Identifiable {
    let id: String
    let name: String
    let date: Date
    let statusState: String        // "pre", "in", "post"
    let statusDescription: String  // "Scheduled", "In Progress", "Final", "Canceled"
    let completed: Bool            // false on a canceled race, which is also "post"
    let broadcasts: [String]
    let competitors: [RaceCompetitor]

    var isScheduled: Bool  { statusState == "pre" }
    var isInProgress: Bool { statusState == "in" }
    var isCompleted: Bool  { statusState == "post" && completed }
    var isCanceled: Bool   { statusState == "post" && !completed }

    var broadcastText: String {
        broadcasts.isEmpty ? "" : broadcasts.joined(separator: " · ")
    }

    /// Whoever finished first, once the race is over. ESPN's own `winner` flag isn't always set.
    var winner: RaceCompetitor? {
        isCompleted ? competitors.first { $0.position == 1 } : nil
    }

    /// What the field is: "Entry List" before the race, "Running Order" during it, "Results"
    /// after, and empty with no field. The same words as racing.py.
    var kind: String {
        if competitors.isEmpty || isCanceled { return "" }
        if isScheduled { return "Entry List" }
        if isInProgress { return "Running Order" }
        return "Results"
    }
}

// MARK: - Standings Entry

struct RacingStandingsEntry: Identifiable {
    let id: String
    let rank: Int
    let name: String          // driver display name or constructor name
    let shortName: String     // abbreviated; e.g. "K. Antonelli", "MER"
    let nationality: String   // driver nationality; empty for constructor entries
    let points: String        // formatted championship points, e.g. "156"
}

// MARK: - Standings Group

struct RacingStandingsGroup: Identifiable {
    let id: String            // "drivers" or "constructors"
    let name: String          // "Driver Standings", "Constructor Standings", "Standings"
    let entries: [RacingStandingsEntry]
}
