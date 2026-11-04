//
//  Transaction.swift
//  SportsScores
//

import Foundation

// MARK: - Transactions list response

struct TransactionResponse: Codable {
    let season: TransactionSeason?
    let count: Int
    let pageIndex: Int
    let pageSize: Int
    let pageCount: Int
    let transactions: [TransactionItem]
}

struct TransactionSeason: Codable {
    let year: Int
    let type: Int?
    let displayName: String
}

struct TransactionItem: Codable, Identifiable {
    /// Synthetic stable id — team id + date + first 40 chars of description
    var id: String { "\(team.id)-\(dateString)-\(description.prefix(40))" }

    let dateString: String
    let description: String
    let team: TransactionTeam

    enum CodingKeys: String, CodingKey {
        case dateString = "date"
        case description
        case team
    }
}

struct TransactionTeam: Codable, Identifiable {
    let id: String
    let location: String?
    let name: String?
    let abbreviation: String
    let displayName: String
    let color: String?
    let logos: [TransactionTeamLogo]?

    /// URL of the default (light) team logo.
    var primaryLogoURL: URL? {
        let defaultLogo = logos?.first(where: { $0.rel?.contains("default") == true })
        return (defaultLogo ?? logos?.first)?.href.flatMap { URL(string: $0) }
    }
}

struct TransactionTeamLogo: Codable {
    let href: String?
    let width: Int?
    let height: Int?
    let rel: [String]?
}

// MARK: - Teams endpoint response (used by the team picker)

struct TeamsAPIResponse: Codable {
    let sports: [TeamsSport]
}

struct TeamsSport: Codable {
    let leagues: [TeamsLeague]
}

struct TeamsLeague: Codable {
    let teams: [TeamsTeamWrapper]
}

struct TeamsTeamWrapper: Codable {
    let team: TransactionTeam
}

// MARK: - Conferences (standings) API response — used by fetchConferencesWithTeams

struct ConferencesAPIResponse: Codable {
    let children: [APIConference]?

    /// One group per conference that has teams, in ESPN's order: FBS, then FCS.
    var conferenceGroups: [ConferenceGroup] {
        (children ?? []).flatMap(\.conferences).compactMap { conference in
            let teams = conference.allTeams.sorted { $0.displayName < $1.displayName }
            guard !teams.isEmpty else { return nil }
            return ConferenceGroup(id: conference.id ?? conference.name, name: conference.name, teams: teams)
        }
    }

    struct APIConference: Codable {
        let id: String?
        let name: String
        /// False on what sits above a conference (FBS, FCS) and below one (Sun Belt - East).
        /// Only some sports send it: college basketball's women and hockey leave it out.
        let isConference: Bool?
        let children: [APIConference]?
        // standings is absent for some conferences (e.g. Sun Belt which only has
        // East/West sub-division children). Must be optional to avoid a decode error
        // crashing the entire response.
        let standings: APIStandings?

        /// The conferences at or below this node. A conference keeps its sub-divisions in
        /// with it, and anything else with nothing of its own is only a level to walk down.
        /// With no flag from ESPN, this splits a conference rather than naming one "FBS".
        var conferences: [APIConference] {
            let hasOwnTeams = !(standings?.entries.isEmpty ?? true)
            guard isConference != true, !hasOwnTeams, let children, !children.isEmpty else {
                return [self]
            }
            return children.flatMap(\.conferences)
        }

        /// Every team at or below this node.
        var allTeams: [TransactionTeam] {
            (standings?.entries.map { $0.team.transactionTeam } ?? [])
                + (children ?? []).flatMap(\.allTeams)
        }

        struct APIStandings: Codable {
            let entries: [APIEntry]

            // One bad team shouldn't cost every conference in the list.
            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                entries = container.lossyArray(forKey: .entries) ?? []
            }

            struct APIEntry: Codable {
                let team: APITeam

                struct APITeam: Codable {
                    let id: String
                    let displayName: String
                    let abbreviation: String
                    let location: String?
                    let name: String?
                    let color: String?
                    let logos: [APILogo]?

                    struct APILogo: Codable {
                        let href: String
                        let rel: [String]?
                    }

                    var transactionTeam: TransactionTeam {
                        TransactionTeam(
                            id: id,
                            location: location,
                            name: name,
                            abbreviation: abbreviation,
                            displayName: displayName,
                            color: color,
                            logos: logos?.map { TransactionTeamLogo(href: $0.href, width: nil, height: nil, rel: $0.rel) }
                        )
                    }
                }
            }
        }
    }
}
