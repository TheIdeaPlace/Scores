//
//  Draft.swift
//  SportsScores
//

import Foundation

struct DraftPosition: Codable {
    let id: String
    let abbreviation: String
}

struct DraftAthletePosition: Codable {
    let id: String
}

struct DraftAthleteTeam: Codable {
    let location: String?
    let shortDisplayName: String?

    /// Not the short name first: that reads OSU, FSU and Miss St. Windows reads it the same way.
    var collegeName: String { location ?? shortDisplayName ?? "" }
}

struct DraftAthlete: Codable, Identifiable {
    let id: String
    let displayName: String
    let position: DraftAthletePosition
    let displayWeight: String?
    let displayHeight: String?
    let team: DraftAthleteTeam?
}

struct DraftPick: Codable, Identifiable {
    var id: Int { overall }
    let status: String
    let pick: Int
    let overall: Int
    let round: Int
    let traded: Bool
    let tradeNote: String
    let athlete: DraftAthlete?
    let teamId: String

    var isCompleted: Bool { status == "SELECTION_MADE" }
    /// True for trades AND compensatory picks — both carry a non-empty tradeNote.
    var hasTradeNote: Bool { !tradeNote.isEmpty }

    // ESPN omits `tradeNote` entirely from picks where there is no note (rather
    // than sending an empty string). Provide a custom decoder so that missing
    // key decodes as "" instead of throwing keyNotFound.
    private enum CodingKeys: String, CodingKey {
        case status, pick, overall, round, traded, tradeNote, athlete, teamId
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status    = try c.decode(String.self,  forKey: .status)
        pick      = try c.decode(Int.self,     forKey: .pick)
        overall   = try c.decode(Int.self,     forKey: .overall)
        round     = try c.decode(Int.self,     forKey: .round)
        traded    = try c.decode(Bool.self,    forKey: .traded)
        tradeNote = try c.decodeIfPresent(String.self, forKey: .tradeNote) ?? ""
        athlete   = try c.decodeIfPresent(DraftAthlete.self, forKey: .athlete)
        teamId    = try c.decode(String.self,  forKey: .teamId)
    }
}

struct DraftTeam: Codable {
    let id: String
    let abbreviation: String
    let displayName: String
    let shortDisplayName: String
    let logo: String
    let darkLogo: String
    let nextPick: Int?
}

struct DraftStatus: Codable {
    let round: Int
    let state: String
    let name: String
    let description: String?
}

struct DraftCurrentInfo: Codable {
    let pickId: Int?
    let bestAvailablePicks: [DraftAthlete]?
    let bestAvailable: DraftAthlete?
    let bestFit: DraftAthlete?
    let next: Int?
}

struct DraftResponse: Codable {
    let year: Int
    let displayName: String
    let rounds: Int?
    let positions: [DraftPosition]
    let picks: [DraftPick]
    let teams: [DraftTeam]
    let status: DraftStatus?
    let current: DraftCurrentInfo?

    // ESPN omits `positions` entirely for very early drafts (pre-1967) where
    // no pick data exists. Default to [] so those years still decode cleanly
    // and show the "no pick data" empty state instead of an error.
    private enum CodingKeys: String, CodingKey {
        case year, displayName, rounds, positions, picks, teams, status, current
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        year        = try c.decode(Int.self,          forKey: .year)
        displayName = try c.decode(String.self,       forKey: .displayName)
        rounds      = try c.decodeIfPresent(Int.self, forKey: .rounds)
        positions   = try c.decodeIfPresent([DraftPosition].self, forKey: .positions) ?? []
        picks       = try c.decodeIfPresent([DraftPick].self,     forKey: .picks)     ?? []
        teams       = try c.decodeIfPresent([DraftTeam].self,     forKey: .teams)     ?? []
        status      = try c.decodeIfPresent(DraftStatus.self,     forKey: .status)
        current     = try c.decodeIfPresent(DraftCurrentInfo.self, forKey: .current)
    }
}
