//
//  TeamHubModels.swift
//  SportsScores
//
//  Data models for the Team Hub feature.
//

import Foundation

// MARK: - Team Info (Info tab display model)

struct TeamHubTeamInfo {
    let teamId: String
    let displayName: String
    let abbreviation: String
    let location: String
    let color: String?           // hex without "#", e.g. "132448"
    let alternateColor: String?
    let primaryLogoURL: URL?
    let overallRecord: String?   // e.g. "25-11"
    let homeRecord: String?      // e.g. "13-5"
    let awayRecord: String?      // e.g. "12-6"
    let standingSummary: String? // e.g. "1st in AL East"
    let venueName: String?
    let venueCity: String?
    let coachName: String?
    let nextGame: TeamHubNextGame?
    /// A failure cost the page its record, which a league with no record to show doesn't.
    var recordUnavailable = false
    /// A college team's postseason counts in Standings but not here, from when it starts until
    /// the next regular season, so "overall" would be wrong: 31-3 here, 37-3 there.
    var recordIsRegularSeasonOnly = false
}

struct TeamHubNextGame {
    let gameId: String
    let date: Date
    let opponentDisplayName: String
    let opponentAbbreviation: String
    let isHome: Bool
    var timeIsKnown = true
    var isNeutralSite = false
}

// MARK: - Favorite Team (persisted team bookmark)

struct FavoriteTeam: Codable, Identifiable, Equatable {
    let id: String            // team.id — canonical ESPN team identifier
    let sport: Sport          // needed to call the correct API endpoints
    let displayName: String
    let abbreviation: String
    let color: String?        // hex without "#", e.g. "132448"
    let logoURLString: String?

    var logoURL: URL? { logoURLString.flatMap { URL(string: $0) } }

    /// Reconstructs a TransactionTeam so favorites can push into TeamHubDetailView.
    var asTransactionTeam: TransactionTeam {
        TransactionTeam(
            id: id, location: nil, name: nil,
            abbreviation: abbreviation, displayName: displayName,
            color: color, logos: nil
        )
    }
}

// MARK: - Conference Group (used by TeamHubConferencePickerView)

struct ConferenceGroup: Identifiable {
    let id: String          // conference id from ESPN standings
    let name: String
    let teams: [TransactionTeam]
}

// MARK: - Roster Player (Roster tab display model)

struct RosterPlayer: Identifiable {
    let id: String
    let jerseyNumber: String
    let displayName: String
    let positionAbbreviation: String
    let age: String
}

// MARK: - Decodable API Response: the current season (core /leagues/{league}/season)

/// The season ESPN calls current, and what part of it the league is in. From ESPN rather than
/// the calendar, so a preseason is known for what it is. Soccer's season types are numbers of
/// their own, and it doesn't ask.
struct CurrentSeasonResponse: Decodable {
    let year: Int
    /// "2026-27 English Premier League"
    let displayName: String?
    let type: SeasonType?

    struct SeasonType: Decodable {
        let type: Int?
    }

    var isRegularSeason: Bool { type?.type == 2 }

    /// A season's playoffs and off-season come after its regular season and are filed under
    /// its year, so only a preseason means that the last one is the latest.
    var regularSeasonYear: Int { type?.type == 1 ? year - 1 : year }
}

// MARK: - Decodable API Response: Team Info endpoint (/teams/{id})

struct TeamInfoAPIResponse: Decodable {
    let team: TeamInfoTeamData

    struct TeamInfoTeamData: Decodable {
        let id: String
        let location: String?
        let name: String?
        let abbreviation: String
        let displayName: String
        let color: String?
        let alternateColor: String?
        let logos: [TeamInfoLogo]?
        let record: TeamInfoRecord?
        let franchise: TeamInfoFranchise?
        let nextEvent: [TeamInfoNextEvent]?
        let standingSummary: String?
    }

    struct TeamInfoLogo: Decodable {
        let href: String
        let rel: [String]?
    }

    struct TeamInfoRecord: Decodable {
        let items: [TeamInfoRecordItem]?

        struct TeamInfoRecordItem: Decodable {
            let description: String?
            let type: String?
            let summary: String?
            let stats: [TeamInfoRecordStat]?

            struct TeamInfoRecordStat: Decodable {
                let name: String?
                let value: Double?
            }
        }
    }

    struct TeamInfoFranchise: Decodable {
        let venue: TeamInfoVenue?

        struct TeamInfoVenue: Decodable {
            let fullName: String?
            let address: TeamInfoAddress?

            struct TeamInfoAddress: Decodable {
                let city: String?
                let state: String?
            }
        }
    }

    struct TeamInfoNextEvent: Decodable {
        let id: String
        let date: String   // multi-format ISO8601 (may lack seconds)
        let timeValid: Bool?
        let competitions: [TeamInfoCompetition]?

        struct TeamInfoCompetition: Decodable {
            let timeValid: Bool?
            let neutralSite: Bool?
            let competitors: [TeamInfoCompetitor]?
            let status: TeamInfoStatus?

            struct TeamInfoStatus: Decodable {
                let type: TeamInfoStatusType?

                struct TeamInfoStatusType: Decodable {
                    let completed: Bool?
                    let state: String?
                }
            }

            /// Postponed or canceled, the same test as `ScheduleGame.isCalledOff`.
            var isCalledOff: Bool {
                status?.type?.completed == false && status?.type?.state == "post"
            }

            struct TeamInfoCompetitor: Decodable {
                let homeAway: String?
                let team: TeamInfoCompetitorTeam?

                struct TeamInfoCompetitorTeam: Decodable {
                    let id: String?
                    let displayName: String?
                    let abbreviation: String?
                }
            }
        }
    }
}

// MARK: - Decodable API Response: Roster endpoint (/teams/{id}/roster)
// ESPN returns two different shapes depending on sport:
//   Grouped (MLB, NFL, NHL, NBA): athletes = [{position: "Pitchers", items: [players]}]
//   Flat (college sports):        athletes = [players directly]

struct RosterAPIResponse: Decodable {
    let athletes: [RosterPositionGroup]?
    let coach: [RosterCoach]?

    struct RosterPositionGroup: Decodable {
        let position: String?
        let items: [RosterAthlete]?
    }

    struct RosterAthlete: Decodable {
        let id: String
        let displayName: String?
        let jersey: String?
        let age: Int?
        let position: RosterAthletePosition?
        let status: RosterAthleteStatus?

        struct RosterAthletePosition: Decodable {
            let abbreviation: String?
        }

        struct RosterAthleteStatus: Decodable {
            let name: String?
        }
    }

    struct RosterCoach: Decodable {
        let firstName: String?
        let lastName: String?
    }
}

/// Flat roster format used by college sports — athletes is a direct array of players.
struct FlatRosterAPIResponse: Decodable {
    let athletes: [FlatRosterAthlete]?
    let coach: [RosterAPIResponse.RosterCoach]?

    struct FlatRosterAthlete: Decodable {
        let id: String
        let displayName: String?
        let jersey: String?
        let age: Int?
        let position: Position?

        struct Position: Decodable {
            let abbreviation: String?
        }
    }
}
