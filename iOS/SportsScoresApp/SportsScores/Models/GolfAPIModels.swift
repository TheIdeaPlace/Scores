//
//  GolfAPIModels.swift
//  SportsScores
//
//  Decodable structs for the ESPN golf scoreboard endpoint.
//
//  Endpoint: GET /apis/site/v2/sports/golf/{pga|lpga}/scoreboard
//            Optionally ?dates=YYYYMMDD to fetch a specific tournament's data.
//
//  Response shape (confirmed against live API):
//    { leagues: [{ calendar: [...] }], events: [{ id, name, status, competitions: [{ broadcasts, competitors }] }] }
//

import Foundation

// MARK: - Top-level response

struct GolfScoreboardResponse: Decodable {
    /// Only the Golf hub's calendar comes from here, so a scoreboard without it still shows
    /// its tournament, as on Windows.
    let leagues: [GolfLeagueAPIResponse]?
    let events: [GolfEventAPIResponse]
}

// MARK: - League / Calendar

struct GolfLeagueAPIResponse: Decodable {
    let calendar: [GolfCalendarAPIEntry]
}

struct GolfCalendarAPIEntry: Decodable {
    let id: String
    let label: String
    let startDate: String
    let endDate: String
}

// MARK: - Event

struct GolfEventAPIResponse: Decodable {
    let id: String
    let name: String
    let date: String?
    let status: GolfEventStatusAPIResponse
    let competitions: [GolfCompetitionAPIResponse]
}

struct GolfEventStatusAPIResponse: Decodable {
    let type: GolfStatusTypeAPIResponse
}

struct GolfStatusTypeAPIResponse: Decodable {
    let id: String
    let name: String
    let state: String       // "pre", "in", "post"
    let completed: Bool
    let description: String // "In Progress", "Scheduled", "Final"
}

// MARK: - Competition

struct GolfCompetitionAPIResponse: Decodable {
    let broadcasts: [GolfBroadcastAPIResponse]?
    let competitors: [GolfCompetitorAPIResponse]?
}

struct GolfBroadcastAPIResponse: Decodable {
    let names: [String]
}

// MARK: - Competitor (leaderboard row)

struct GolfCompetitorAPIResponse: Decodable {
    let id: String
    let order: Int
    let score: String?              // "-12", "E", "+5", "CUT", "WD", "DQ"
    let athlete: GolfAthleteAPIResponse
    let linescores: [GolfRoundLinescoreAPIResponse]?
}

struct GolfAthleteAPIResponse: Decodable {
    let fullName: String
    let shortName: String?
    let flag: GolfFlagAPIResponse?
}

struct GolfFlagAPIResponse: Decodable {
    let alt: String?
}

// MARK: - Linescores (round-level)

struct GolfRoundLinescoreAPIResponse: Decodable {
    let value: Double?          // raw stroke total for the round (e.g. 71.0)
    let displayValue: String?   // par-relative score (e.g. "-5", "+1", "E")
    let period: Int             // round number: 1, 2, 3, 4
    let linescores: [GolfHoleLinescoreAPIResponse]?  // hole-by-hole breakdown
}

// MARK: - Linescores (hole-level)

struct GolfHoleLinescoreAPIResponse: Decodable {
    let value: Double?          // strokes taken on this hole
    let displayValue: String?   // stroke count as string ("4")
    let period: Int             // hole number: 1–18
    let scoreType: GolfScoreTypeAPIResponse?
}

struct GolfScoreTypeAPIResponse: Decodable {
    let displayValue: String?   // "+1" bogey, "-1" birdie, "-2" eagle, "E" par, "OTHER"
}
