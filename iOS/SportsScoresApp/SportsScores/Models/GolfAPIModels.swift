//
//  GolfAPIModels.swift
//  SportsScores
//
//  Decodable structs for the ESPN golf scoreboard endpoint.
//
//  Endpoint: GET /apis/site/v2/sports/golf/{pga|lpga}/scoreboard
//            ?dates=YYYYMMDD for the tournament of that day (a past one this season),
//            ?dates=YYYY for the whole season with each finished event's winner.
//
//  Response shape (confirmed against live API):
//    { leagues: [{ calendar: [...] }], events: [{ id, name, status, competitions: [{ status, broadcasts, competitors }] }] }
//
//  Decoded leniently, as espn_api.py reads it on Windows: a field ESPN leaves out or sends
//  oddly costs that field, and an entry that can't be read at all (a calendar entry missing
//  its dates, a competitor that isn't an object) costs that entry, never the whole tour. A
//  team event's competitors are teams with no athlete (the Zurich Classic, the Presidents Cup).
//

import Foundation

private extension KeyedDecodingContainer {
    /// The value under `key`, or nil when it's absent, null or not of that type.
    func lenient<T: Decodable>(_ type: T.Type, forKey key: Key) -> T? {
        (try? decodeIfPresent(type, forKey: key)) ?? nil
    }
}

// MARK: - Top-level response

struct GolfScoreboardResponse: Decodable {
    /// Only the Golf hub's calendar comes from here, so a scoreboard without it still shows
    /// its tournament, as on Windows.
    let leagues: [GolfLeagueAPIResponse]?
    let events: [GolfEventAPIResponse]

    private enum CodingKeys: String, CodingKey { case leagues, events }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        leagues = container.lossyArray(forKey: .leagues)
        // No events is ESPN having none. A null where the list belongs isn't an answer, the
        // way _listed in espn_api.py treats it.
        if container.contains(.events), try container.decodeNil(forKey: .events) {
            throw DecodingError.valueNotFound([GolfEventAPIResponse].self, DecodingError.Context(
                codingPath: [CodingKeys.events], debugDescription: "events is null"))
        }
        events = container.lossyArray(forKey: .events) ?? []
    }
}

// MARK: - League / Calendar

struct GolfLeagueAPIResponse: Decodable {
    let calendar: [GolfCalendarAPIEntry]

    private enum CodingKeys: String, CodingKey { case calendar }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        calendar = container.lossyArray(forKey: .calendar) ?? []
    }
}

/// One tournament of the season. Strict: an entry without its id, name or dates is skipped.
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
    let status: GolfEventStatusAPIResponse?
    let competitions: [GolfCompetitionAPIResponse]

    private enum CodingKeys: String, CodingKey { case id, name, date, status, competitions }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.lenient(String.self, forKey: .id) ?? ""
        name = container.lenient(String.self, forKey: .name) ?? ""
        date = container.lenient(String.self, forKey: .date)
        status = container.lenient(GolfEventStatusAPIResponse.self, forKey: .status)
        competitions = container.lossyArray(forKey: .competitions) ?? []
    }
}

struct GolfEventStatusAPIResponse: Decodable {
    let type: GolfStatusTypeAPIResponse?

    private enum CodingKeys: String, CodingKey { case type }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = container.lenient(GolfStatusTypeAPIResponse.self, forKey: .type)
    }
}

struct GolfStatusTypeAPIResponse: Decodable {
    let state: String?          // "pre", "in", "post"
    let completed: Bool?
    let description: String?    // "In Progress", "Scheduled", "Final", "Canceled"
    let detail: String?         // "Round 3 - Play Complete"

    private enum CodingKeys: String, CodingKey { case state, completed, description, detail }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        state = container.lenient(String.self, forKey: .state)
        completed = container.lenient(Bool.self, forKey: .completed)
        description = container.lenient(String.self, forKey: .description)
        detail = container.lenient(String.self, forKey: .detail)
    }
}

// MARK: - Competition

struct GolfCompetitionAPIResponse: Decodable {
    let status: GolfEventStatusAPIResponse?
    let broadcasts: [GolfBroadcastAPIResponse]
    let competitors: [GolfCompetitorAPIResponse]

    private enum CodingKeys: String, CodingKey { case status, broadcasts, competitors }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = container.lenient(GolfEventStatusAPIResponse.self, forKey: .status)
        broadcasts = container.lossyArray(forKey: .broadcasts) ?? []
        competitors = container.lossyArray(forKey: .competitors) ?? []
    }
}

struct GolfBroadcastAPIResponse: Decodable {
    let names: [String]

    private enum CodingKeys: String, CodingKey { case names }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        names = container.lossyArray(forKey: .names) ?? []
    }
}

// MARK: - Competitor (leaderboard row)

struct GolfCompetitorAPIResponse: Decodable {
    let id: String
    let order: Int?                 // leaderboard order; nil when ESPN leaves it out
    let score: String?              // "-12", "E", "+5", "CUT", "WD", "DQ"; a cup's points, "17"
    let winner: Bool?               // set on the team cups
    let athlete: GolfAthleteAPIResponse?
    let team: GolfTeamAPIResponse?  // a team event's competitor, in place of an athlete
    let linescores: [GolfRoundLinescoreAPIResponse]

    private enum CodingKeys: String, CodingKey { case id, order, score, winner, athlete, team, linescores }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = container.lenient(String.self, forKey: .id) ?? ""
        order = container.lenient(Int.self, forKey: .order)
        score = container.lenient(String.self, forKey: .score)
        winner = container.lenient(Bool.self, forKey: .winner)
        athlete = container.lenient(GolfAthleteAPIResponse.self, forKey: .athlete)
        team = container.lenient(GolfTeamAPIResponse.self, forKey: .team)
        linescores = container.lossyArray(forKey: .linescores) ?? []
    }
}

struct GolfAthleteAPIResponse: Decodable {
    let displayName: String?
    let fullName: String?
    let shortName: String?
    let flag: GolfFlagAPIResponse?

    private enum CodingKeys: String, CodingKey { case displayName, fullName, shortName, flag }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        displayName = container.lenient(String.self, forKey: .displayName)
        fullName = container.lenient(String.self, forKey: .fullName)
        shortName = container.lenient(String.self, forKey: .shortName)
        flag = container.lenient(GolfFlagAPIResponse.self, forKey: .flag)
    }
}

struct GolfTeamAPIResponse: Decodable {
    let displayName: String?
    let name: String?

    private enum CodingKeys: String, CodingKey { case displayName, name }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        displayName = container.lenient(String.self, forKey: .displayName)
        name = container.lenient(String.self, forKey: .name)
    }
}

struct GolfFlagAPIResponse: Decodable {
    let alt: String?

    private enum CodingKeys: String, CodingKey { case alt }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        alt = container.lenient(String.self, forKey: .alt)
    }
}

// MARK: - Linescores (round-level)

struct GolfRoundLinescoreAPIResponse: Decodable {
    let value: Double?          // raw stroke total for the round (e.g. 71.0)
    let displayValue: String?   // par-relative score (e.g. "-5", "+1", "E")
    let period: Int             // round number: 1, 2, 3, 4; 0 when ESPN leaves it out
    let linescores: [GolfHoleLinescoreAPIResponse]  // hole-by-hole breakdown

    private enum CodingKeys: String, CodingKey { case value, displayValue, period, linescores }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        value = container.lenient(Double.self, forKey: .value)
        displayValue = container.lenient(String.self, forKey: .displayValue)
        period = container.lenient(Int.self, forKey: .period) ?? 0
        linescores = container.lossyArray(forKey: .linescores) ?? []
    }
}

// MARK: - Linescores (hole-level)

struct GolfHoleLinescoreAPIResponse: Decodable {
    let value: Double?          // strokes taken on this hole
    let displayValue: String?   // stroke count as string ("4")
    let period: Int             // hole number: 1–18; 0 when ESPN leaves it out
    let scoreType: GolfScoreTypeAPIResponse?

    private enum CodingKeys: String, CodingKey { case value, displayValue, period, scoreType }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        value = container.lenient(Double.self, forKey: .value)
        displayValue = container.lenient(String.self, forKey: .displayValue)
        period = container.lenient(Int.self, forKey: .period) ?? 0
        scoreType = container.lenient(GolfScoreTypeAPIResponse.self, forKey: .scoreType)
    }
}

struct GolfScoreTypeAPIResponse: Decodable {
    let displayValue: String?   // "+1" bogey, "-1" birdie, "-2" eagle, "E" par, "OTHER"

    private enum CodingKeys: String, CodingKey { case displayValue }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        displayValue = container.lenient(String.self, forKey: .displayValue)
    }
}
