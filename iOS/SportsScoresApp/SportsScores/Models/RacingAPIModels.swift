//
//  RacingAPIModels.swift
//  SportsScores
//
//  Raw Decodable structs for the ESPN racing scoreboard and standings endpoints.
//  These are converted into domain models (Racing.swift) by ESPNAPIService.
//

import Foundation

// MARK: - Scoreboard Response

struct RacingScoreboardResponse: Decodable {
    let events: [RacingEventAPI]
}

struct RacingEventAPI: Decodable {
    let id: String
    let name: String
    let date: String
    let status: RacingEventStatusWrapper
    let competitions: [RacingCompetitionAPI]
}

struct RacingEventStatusWrapper: Decodable {
    let type: RacingStatusTypeAPI
}

struct RacingStatusTypeAPI: Decodable {
    let state: String           // "pre", "in", "post"
    let completed: Bool
    let description: String     // "Scheduled", "In Progress", "Final"
}

/// One session of a race weekend. Formula 1 lists each (FP1, FP2, FP3, Qual, or SS and SR on a
/// sprint weekend, then Race); IndyCar and NASCAR list one, untyped, which is the race.
struct RacingCompetitionAPI: Decodable {
    let date: String?
    let type: RacingCompetitionTypeAPI?
    let status: RacingEventStatusWrapper?
    let broadcasts: [RacingBroadcastAPI]?
    let competitors: [RacingCompetitorAPI]?
}

struct RacingCompetitionTypeAPI: Decodable {
    let abbreviation: String?
}

struct RacingBroadcastAPI: Decodable {
    let names: [String]
}

struct RacingCompetitorAPI: Decodable {
    let id: String
    /// Finishing or running order. A race not yet run lists its field with none at all.
    let order: Int?
    let athlete: RacingAthleteAPI?
}

struct RacingAthleteAPI: Decodable {
    let displayName: String?
    let fullName: String?
    let shortName: String?
    let flag: RacingFlagAPI?
}

struct RacingFlagAPI: Decodable {
    let alt: String?
}

// MARK: - Standings Response

struct RacingStandingsResponse: Decodable {
    let children: [RacingStandingsGroupAPI]
}

struct RacingStandingsGroupAPI: Decodable {
    let name: String
    let standings: RacingStandingsDataAPI?
}

struct RacingStandingsDataAPI: Decodable {
    let entries: [RacingStandingsEntryAPI]
}

struct RacingStandingsEntryAPI: Decodable {
    // Driver standings: has athlete; Constructor standings: has team
    let athlete: RacingStandingsAthleteAPI?
    let team: RacingStandingsTeamAPI?
    let stats: [RacingStatAPI]
}

struct RacingStandingsAthleteAPI: Decodable {
    let id: String?
    let displayName: String?
    let shortName: String?
    let flag: RacingFlagAPI?
}

struct RacingStandingsTeamAPI: Decodable {
    let id: String?
    let displayName: String?
    let abbreviation: String?
}

struct RacingStatAPI: Decodable {
    // Only named stats (rank, championshipPts, points) have a `name` field.
    // Per-race columns have no `name` — they decode to nil.
    let name: String?
    let displayValue: String?
}
