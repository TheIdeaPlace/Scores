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
    let rankDisplay: String          // "2nd", "Tied-9th", or in college "118th of 302"
    let leagueSize: Int?             // how many teams the rank is out of, when it's from a list the team is on
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
    /// Which season the numbers are from, such as "2026-27 Regular Season", if it's known.
    let seasonLabel: String?

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

    init(name: String, displayName: String, leaders: [LeagueLeaderEntry], isTeamCategory: Bool = false,
         seasonLabel: String? = nil) {
        self.name = name
        self.displayName = displayName
        self.leaders = leaders
        self.isTeamCategory = isTeamCategory
        self.seasonLabel = seasonLabel
    }

    /// The same list, cut to its first `limit` rows.
    func keepingFirst(_ limit: Int) -> LeagueLeaderCategory {
        LeagueLeaderCategory(name: name, displayName: displayName, leaders: Array(leaders.prefix(limit)),
                             isTeamCategory: isTeamCategory, seasonLabel: seasonLabel)
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

/// A league's leaders from `site.web.api.espn.com/apis/site/v3/sports/{sport}/{league}/leaders`,
/// with names and teams inside the response.
struct SiteLeadersResponse: Decodable {
    let requestedSeason: Season?
    let leaders: Leaders?

    struct Season: Decodable {
        let displayName: String?
        let type: SeasonType?

        struct SeasonType: Decodable {
            let type: Int?
            let name: String?
        }
    }

    struct Leaders: Decodable {
        let categories: [Category]?

        enum CodingKeys: String, CodingKey {
            case categories
        }

        init(from decoder: Decoder) throws {
            categories = try decoder.container(keyedBy: CodingKeys.self).lossyArray(forKey: .categories)
        }
    }

    struct Category: Decodable {
        let name: String?
        let displayName: String?
        let leaders: [Leader]?

        enum CodingKeys: String, CodingKey {
            case name, displayName, leaders
        }

        /// One null row shouldn't lose the league's whole list.
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            name = try? container.decodeIfPresent(String.self, forKey: .name)
            displayName = try? container.decodeIfPresent(String.self, forKey: .displayName)
            leaders = container.lossyArray(forKey: .leaders)
        }
    }

    struct Leader: Decodable {
        let displayValue: String?
        let value: Double?
        let athlete: Athlete?
        let team: Team?

        enum CodingKeys: String, CodingKey {
            case displayValue, value, athlete, team
        }

        /// One odd field shouldn't lose the league's whole list.
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            displayValue = try? container.decodeIfPresent(String.self, forKey: .displayValue)
            value = try? container.decodeIfPresent(Double.self, forKey: .value)
            athlete = try? container.decodeIfPresent(Athlete.self, forKey: .athlete)
            team = try? container.decodeIfPresent(Team.self, forKey: .team)
        }
    }

    struct Athlete: Decodable {
        let displayName: String?
        let fullName: String?
        let shortName: String?
    }

    struct Team: Decodable {
        let abbreviation: String?
        let displayName: String?
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
    /// Only basketball has this. `count` can exceed the teams sent: ESPN sends 400 at most.
    let pagination: Pagination?
    /// Which season this really is, whatever was asked for. A past college football season is
    /// type 3 even when asked for type 2.
    let requestedSeason: RequestedSeason?
    /// Not ESPN's: the ids on its team list, for a college basketball list with schools outside
    /// Division I in it. See `LeagueTeamStats.divisionOneTeams`.
    var divisionOneTeamIDs: Set<String>? = nil

    /// "2026-27 Regular Season", the same words Windows uses. Asked for a past college football
    /// season's regular season, ESPN answers with type 3, the numbers running through the bowl
    /// games, so "Season" says what they are. Fewer teams than ESPN says it has, past the 800 that
    /// two sorted requests can reach, says so rather than the list looking whole.
    var seasonLabel: String? {
        guard let season = requestedSeason else { return nil }
        let type = season.type?.type == 3 ? "Season" : season.type?.name
        let label = [season.displayName, type].compactMap { $0 }.joined(separator: " ")
        guard !label.isEmpty else { return nil }
        if let count = pagination?.count, count > (teams ?? []).count {
            return "\(label), some teams missing"
        }
        return label
    }

    /// Whether the numbers are the regular season's, not the bowls as well.
    var isRegularSeason: Bool {
        requestedSeason?.type?.type == 2
    }

    struct Pagination: Codable {
        let count: Int?
    }

    struct RequestedSeason: Codable {
        let year: Int?
        let displayName: String?
        let type: SeasonType?

        struct SeasonType: Codable {
            let type: Int?
            let name: String?
        }
    }

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

/// ESPN's own idea of a league's season now, from the core API's `/season`. On Windows this is
/// espn_api.core_season, and the two follow the same rule.
struct CoreSeasonResponse: Decodable {
    let year: Int?
    let type: SeasonType?

    struct SeasonType: Decodable {
        let type: Int?
        /// "2026-10-20T07:00Z"
        let startDate: String?
    }

    /// The year whose regular season to show. A season's playoffs and off-season come after its
    /// regular season and are filed under its year, so only a preseason means the last one is the
    /// latest. Nil if ESPN didn't say.
    var latestRegularSeasonYear: Int? {
        guard let year else { return nil }
        return type?.type == 1 ? year - 1 : year
    }

    /// Whether a regular season began in the last few days. ESPN's type turns over before the
    /// first game (college basketball at 07:00 UTC on Nov 1, its first game at 14:30), and until
    /// there are games, some of its feeds answer 500 for the new season.
    func regularSeasonJustBegan(now: Date = Date()) -> Bool {
        guard type?.type == 2, let text = type?.startDate, let began = Self.startFormat.date(from: text) else { return false }
        let seconds = now.timeIntervalSince(began)
        return seconds >= 0 && seconds <= 3 * 24 * 60 * 60
    }

    private static let startFormat: DateFormatter = {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.timeZone = TimeZone(secondsFromGMT: 0)
        format.dateFormat = "yyyy-MM-dd'T'HH:mmX"
        return format
    }()
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

/// One event ESPN sent oddly costs that event, not the list. ESPN's own list for week 8
/// of college football in 2025 has a literal {} in it, which used to lose the whole week.
/// If most of the real entries can't be read, that's a change in the feed rather than a
/// stray entry, and a short list would look normal, so it's still an error. `judgingAbove`
/// is for a list short enough for that to mean nothing: a team schedule's postseason page
/// can be one bowl game, and losing it isn't a reason to lose the season.
enum LossyEvents {
    private struct AnyKey: CodingKey {
        var stringValue: String
        var intValue: Int? { nil }
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { nil }
    }

    /// An entry of `events`: its event if it can be read, and whether it was a blank {}.
    private struct Row<Event: Decodable>: Decodable {
        let event: Event?
        let isBlank: Bool

        init(from decoder: Decoder) throws {
            event = try? Event(from: decoder)
            isBlank = (try? decoder.container(keyedBy: AnyKey.self))?.allKeys.isEmpty ?? false
        }
    }

    static func decode<Event: Decodable, Key: CodingKey>(from container: KeyedDecodingContainer<Key>,
                                                         forKey key: Key,
                                                         judgingAbove minimum: Int = 0) throws -> [Event] {
        let rows = try container.decode([Row<Event>].self, forKey: key)
        let events = rows.compactMap { $0.event }
        let sent = rows.filter { !$0.isBlank }.count
        if sent > minimum && (sent - events.count) * 2 > sent {
            throw DecodingError.dataCorruptedError(forKey: key, in: container,
                                                   debugDescription: "Only \(events.count) of \(sent) events could be read")
        }
        return events
    }
}

extension ScoreboardResponse {
    private enum CodingKeys: String, CodingKey {
        case events, week, season, leagues
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        events = try LossyEvents.decode(from: container, forKey: .events)
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
    /// Any status but 400 or 404, where `invalidResponse` is ESPN answering that it has
    /// nothing there. Only team schedules tell them apart so far.
    case unexpectedStatus(Int)
    case decodingError
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .unexpectedStatus(let status):
            return "The server answered with an error (\(status))"
        case .decodingError:
            return "Failed to decode response"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}
