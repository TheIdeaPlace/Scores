//
//  ESPNAPIResponseModels.swift
//  SportsScores
//
//  Raw API response types decoded in ESPNAPIService, plus the display models
//  for league leaders and polls that are consumed by view models.
//

import Foundation

// MARK: - Team Stats Ranking

/// One row in the Team Stats tab: where this team ranks in a given stat category.
struct TeamStatRanking: Identifiable {
    let id = UUID()
    let sectionName: String          // "Batting", "Pitching", etc.
    let categoryDisplayName: String  // "ERA", "Home Runs"
    let teamValue: String            // "3.58"
    let leagueRank: Int             // numeric rank, used for color coding
    let rankDisplay: String          // ESPN display string: "2nd", "Tied-9th"
}

// MARK: - Core API Team Statistics Response
// Used by ESPNAPIService.fetchTeamStatRankings.
// URL: sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/seasons/{year}/types/{type}/teams/{id}/statistics

struct CoreTeamStatisticsResponse: Codable {
    let splits: Splits?

    struct Splits: Codable {
        let categories: [StatCategory]?

        struct StatCategory: Codable {
            let name: String?
            let displayName: String?
            let stats: [Stat]?

            struct Stat: Codable {
                let name: String?
                let displayName: String?
                let value: Double?
                let displayValue: String?
                let rank: Int?
                let rankDisplayValue: String?
            }
        }
    }
}

// MARK: - League Leaders Models

struct LeagueLeaderCategory: Identifiable {
    let id = UUID()
    let name: String
    let displayName: String
    let leaders: [LeagueLeaderEntry]
    /// True when every entry represents a team rather than an individual player.
    let isTeamCategory: Bool

    struct LeagueLeaderEntry: Identifiable {
        let id = UUID()
        let rank: Int
        let displayValue: String
        /// Player name for player categories; team abbreviation for team categories.
        let athleteName: String
        /// Team abbreviation for player categories; empty for team categories.
        let teamAbbreviation: String
        /// Full name set for team categories, so VoiceOver can speak the team
        /// per the user's TeamNamePreference instead of reading the
        /// abbreviation shown on screen. Nil for player categories.
        let teamNames: TeamNameSet?

        init(rank: Int,
             displayValue: String,
             athleteName: String,
             teamAbbreviation: String,
             teamNames: TeamNameSet? = nil) {
            self.rank = rank
            self.displayValue = displayValue
            self.athleteName = athleteName
            self.teamAbbreviation = teamAbbreviation
            self.teamNames = teamNames
        }
    }

    /// The name variants ESPN publishes for a team, so a view can honor the
    /// user's `TeamNamePreference` without another lookup.
    struct TeamNameSet {
        /// "Baltimore Orioles"
        let displayName: String
        /// "Orioles"
        let name: String
        /// "BAL"
        let abbreviation: String

        /// "Baltimore" — `displayName` with the mascot stripped off the end.
        var cityName: String {
            guard displayName.hasSuffix(name) else { return displayName }
            let city = String(displayName.dropLast(name.count))
                .trimmingCharacters(in: .whitespaces)
            return city.isEmpty ? displayName : city
        }

        func voiceOverName(for preference: TeamNamePreference) -> String {
            switch preference {
            case .full:         return displayName
            case .mascot:       return name
            case .city:         return cityName
            case .abbreviation: return abbreviation
            }
        }
    }

    init(name: String, displayName: String, leaders: [LeagueLeaderEntry], isTeamCategory: Bool = false) {
        self.name = name
        self.displayName = displayName
        self.leaders = leaders
        self.isTeamCategory = isTeamCategory
    }

    /// The bare ESPN stat key, used to look up this category's definition.
    /// Team categories are named "section.stat" (or "opponent.section.stat");
    /// player categories are already a bare key like "homeRuns".
    var statKey: String {
        name.components(separatedBy: ".").last ?? name
    }

    /// True when the category ranks teams by what their opponents did to them
    /// (yards allowed, opponent shooting percentage).
    var isOpponentCategory: Bool {
        name.hasPrefix("opponent.")
    }
}

// MARK: - Core API Response Models

struct CoreLeadersAPIResponse: Codable {
    let categories: [CoreCategory]?
    
    struct CoreCategory: Codable {
        let name: String?
        let displayName: String?
        let leaders: [CoreLeader]?
        
        struct CoreLeader: Codable {
            let displayValue: String?
            /// The raw numeric stat value (e.g. 0.331 for BA, 4.0 for HR count).
            /// Use this instead of displayValue for MLB, whose displayValue is a
            /// full stats-line string like "9-17, 4 HR, 2B, 6 RBI, 7 R, 3 BB, 4 K".
            let value: Double?
            let athlete: Reference?
            let team: Reference?
            
            struct Reference: Codable {
                let ref: String?

                enum CodingKeys: String, CodingKey {
                    case ref = "$ref"
                }
            }
        }
    }
}

/// League-wide team statistics — every team's full stat line for the season.
/// From `site.web.api.espn.com/apis/common/v3/sports/{sport}/{league}/statistics/byteam`.
///
/// The payload is column-oriented: the top-level `categories` carry the stat
/// names/labels, and each team's matching category carries `totals` (display
/// strings), `values` (numbers) and `ranks` in the same order. Look a stat's
/// index up once in the top-level metadata, then read that index out of every
/// team's arrays.
struct TeamStatsByTeamResponse: Codable {
    let teams: [TeamStats]?
    /// Column metadata. ESPN repeats a category name once per split, and only
    /// the first copy is guaranteed to carry the `names` array.
    let categories: [CategoryMetadata]?

    struct CategoryMetadata: Codable {
        let name: String?
        /// Stat keys, e.g. ["gamesPlayed", "atBats", "runs", …]
        let names: [String]?
        let displayNames: [String]?
        /// Plain-English definitions, parallel to `names` — ESPN's own glossary
        /// text, e.g. "The number representing walks plus hits divided by
        /// innings pitched." Surfaced by the stat-definition sheet.
        let descriptions: [String]?
    }

    struct TeamStats: Codable {
        let team: TeamInfo
        let categories: [TeamCategory]?

        struct TeamInfo: Codable {
            let id: String?
            let abbreviation: String?
            let displayName: String?
            let name: String?
        }

        struct TeamCategory: Codable {
            let name: String?
            /// "0" for the team's own production, "900" for what opponents did
            /// against it. Absent on categories that have no split (e.g. NBA
            /// "differential"), which are treated as the team's own.
            let splitId: String?
            /// Display strings, e.g. ["115", "3,939", ".250", …]
            let totals: [String]?
            /// The same values as numbers, for sorting.
            let values: [Double?]?
        }
    }
}

struct CoreAthleteResponse: Codable {
    let displayName: String?
}

struct CoreTeamResponse: Codable {
    let displayName: String?
    let abbreviation: String?
}

// MARK: - Rankings / Polls Models

struct RankingsPoll: Identifiable {
    let id = UUID()
    let name: String
    let shortName: String
    let lastUpdated: String?
    let ranks: [RankEntry]

    struct RankEntry: Identifiable {
        let id = UUID()
        let current: Int
        let previous: Int?
        let trend: String?
        let points: Double?
        let firstPlaceVotes: Int?
        let teamDisplayName: String
        let teamAbbreviation: String
        let recordSummary: String?

        var movementText: String {
            guard let prev = previous, prev > 0 else { return "NR" }
            let diff = prev - current
            if diff > 0 { return "↑\(diff)" }
            if diff < 0 { return "↓\(abs(diff))" }
            return "—"
        }

        var movementDirection: Int {
            guard let prev = previous, prev > 0 else { return 0 }
            return prev - current
        }
    }

    init(from api: RankingsAPIResponse.APIPoll) {
        self.name = api.name ?? api.shortName ?? "Poll"
        self.shortName = api.shortName ?? api.name ?? "Poll"
        self.lastUpdated = api.lastUpdated
        self.ranks = (api.ranks ?? []).map { r in
            RankEntry(
                current: r.current ?? 0,
                previous: r.previous,
                trend: r.trend,
                points: r.points,
                firstPlaceVotes: r.firstPlaceVotes,
                teamDisplayName: r.team?.resolvedDisplayName ?? "Unknown",
                teamAbbreviation: r.team?.abbreviation ?? "—",
                recordSummary: r.recordSummary ?? r.record?.summary ?? r.team?.record?.summary
            )
        }
    }
}

struct RankingsAPIResponse: Codable {
    let rankings: [APIPoll]

    struct APIPoll: Codable {
        let name: String?
        let shortName: String?
        let headline: String?
        let lastUpdated: String?
        let ranks: [APIRank]?

        struct APIRank: Codable {
            let current: Int?
            let previous: Int?
            let trend: String?
            let points: Double?
            let firstPlaceVotes: Int?
            /// ESPN sends the team's record here, at the top level of the rank
            /// entry — not nested under `record` or `team.record`, both of which
            /// it leaves null. Reading only those showed an empty record column.
            let recordSummary: String?
            let record: APIRecord?
            let team: APITeam?

            struct APIRecord: Codable {
                let summary: String?
            }
            struct APITeam: Codable {
                /// Absent on the rankings endpoint for every polled sport — see
                /// `resolvedDisplayName`. Kept for any feed that does send it.
                let displayName: String?
                /// The school, e.g. "Ohio State".
                let location: String?
                /// The mascot, e.g. "Buckeyes".
                let name: String?
                /// Usually the school again, e.g. "Ohio State".
                let nickname: String?
                let abbreviation: String?
                let record: APIRecord?

                /// ESPN's rankings feed carries no `displayName` — only the
                /// school, mascot and nickname separately — so reading it
                /// directly made every team in every poll read "Unknown".
                /// Assembled the same way the Windows app does it.
                var resolvedDisplayName: String {
                    if let location, let name, !location.isEmpty, !name.isEmpty {
                        return "\(location) \(name)"
                    }
                    for candidate in [location, name, nickname, displayName] {
                        if let candidate, !candidate.isEmpty { return candidate }
                    }
                    return "Unknown"
                }
            }
        }
    }
}

// MARK: - Scoreboard Response

/// One event ESPN sent oddly costs that event, not the board. ESPN's own list for week 8
/// of college football in 2025 has a literal {} in it, which used to lose the whole week.
/// If nothing at all can be read, that's a change in the feed, and it's still an error.
extension ScoreboardResponse {
    private enum CodingKeys: String, CodingKey {
        case events, week, season, leagues
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let rows = try container.decode([Lossy<APIGame>].self, forKey: .events)
        events = rows.compactMap { $0.value }
        if events.isEmpty && !rows.isEmpty {
            throw DecodingError.dataCorruptedError(forKey: .events, in: container,
                                                   debugDescription: "None of the \(rows.count) events could be read")
        }
        week = try container.decodeIfPresent(APIWeek.self, forKey: .week)
        season = try container.decodeIfPresent(APISeason.self, forKey: .season)
        leagues = try container.decodeIfPresent([APILeague].self, forKey: .leagues)
    }
}

struct ScoreboardResponse: Decodable {
    let events: [APIGame]
    /// Present for football sports — describes the current week.
    let week: APIWeek?
    /// Describes the current season being served.
    let season: APISeason?
    /// Football scoreboards embed the whole season calendar here — season types
    /// and every navigable week with its label and date range.
    let leagues: [APILeague]?

    struct APIWeek: Decodable {
        let number: Int?
        let text: String?
    }

    struct APISeason: Decodable {
        let year: Int?
        let type: Int?
    }

    struct APILeague: Decodable {
        let calendar: [APICalendarSection]?

        private enum CodingKeys: String, CodingKey { case calendar }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            // Non-football scoreboards return `calendar` as a flat array of date
            // strings rather than season-type objects — ignore those rather than
            // failing the whole decode.
            calendar = try? container.decodeIfPresent([APICalendarSection].self, forKey: .calendar)
        }
    }

    /// One season type ("Preseason", "Regular Season", …) and its weeks.
    struct APICalendarSection: Decodable {
        let label: String?
        /// ESPN season type code as a string ("1" / "2" / "3").
        let value: String?
        let entries: [APICalendarEntry]?
    }

    /// One navigable week within a season type.
    struct APICalendarEntry: Decodable {
        let label: String?
        let alternateLabel: String?
        /// Week number within its season type, as a string.
        let value: String?
        let startDate: String?
        let endDate: String?
    }
}

// MARK: - Error Types

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case decodingError
    case networkError(Error)
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .decodingError:
            return "Failed to decode response"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}
