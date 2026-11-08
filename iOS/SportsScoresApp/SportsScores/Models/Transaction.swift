//
//  Transaction.swift
//  SportsScores
//

import Foundation

// MARK: - Transactions list response

/// One /transactions answer. An empty one has no `transactions` at all, and a soccer team's is
/// `{"in": [...], "out": [...]}`; both read here, as transactions_paging.transaction_items does.
struct TransactionResponse: Decodable {
    let count: Int
    let pageCount: Int
    let transactions: [TransactionItem]

    enum CodingKeys: String, CodingKey { case count, pageCount, transactions }

    private struct InAndOut: Decodable {
        let items: [TransactionItem]
        enum CodingKeys: String, CodingKey { case incoming = "in", outgoing = "out" }
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            items = (container.lossyArray(forKey: .incoming) ?? []) + (container.lossyArray(forKey: .outgoing) ?? [])
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        count = (try? container.decodeIfPresent(Int.self, forKey: .count)) ?? 0
        pageCount = (try? container.decodeIfPresent(Int.self, forKey: .pageCount)) ?? 0
        if container.contains(.transactions), try container.decodeNil(forKey: .transactions) {
            // A null where the list belongs isn't an answer, as on Windows.
            throw DecodingError.valueNotFound([TransactionItem].self, .init(
                codingPath: [CodingKeys.transactions], debugDescription: "transactions is null"))
        }
        if let list: [TransactionItem] = container.lossyArray(forKey: .transactions) {
            transactions = list
        } else if let inAndOut = try? container.decodeIfPresent(InAndOut.self, forKey: .transactions) {
            transactions = inAndOut.items
        } else {
            transactions = []
        }
    }
}

struct TransactionItem: Decodable, Identifiable {
    /// Synthetic stable id — team id + date + first 40 chars of description
    var id: String { "\(team.id)-\(dateString)-\(description.prefix(40))" }

    let dateString: String
    /// ESPN's description, or for a soccer transfer, who moved where (TransactionPaging.describe).
    let description: String
    /// A team-filtered list leaves the team off; then it has an empty id and abbreviation.
    let team: TransactionTeam

    enum CodingKeys: String, CodingKey {
        case dateString = "date"
        case description, team, athlete, from, to, type, amount, currency
    }

    private struct Named: Decodable { let displayName: String? }
    private struct Currency: Decodable { let code: String?; let sign: String? }

    static let noTeam = TransactionTeam(id: "", location: nil, name: nil, abbreviation: "", displayName: "",
                                        color: nil, logos: nil)

    init(dateString: String, description: String, team: TransactionTeam) {
        self.dateString = dateString
        self.description = description
        self.team = team
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        dateString = (try? c.decodeIfPresent(String.self, forKey: .dateString)) ?? ""
        team = (try? c.decodeIfPresent(TransactionTeam.self, forKey: .team)) ?? Self.noTeam
        let currency = try? c.decodeIfPresent(Currency.self, forKey: .currency)
        description = TransactionPaging.describe(
            description: try? c.decodeIfPresent(String.self, forKey: .description),
            athlete: (try? c.decodeIfPresent(Named.self, forKey: .athlete))?.displayName,
            from: (try? c.decodeIfPresent(Named.self, forKey: .from))?.displayName,
            to: (try? c.decodeIfPresent(Named.self, forKey: .to))?.displayName,
            type: try? c.decodeIfPresent(String.self, forKey: .type),
            amount: c.lenientNumber(forKey: .amount),
            currencyCode: currency?.code,
            currencySign: currency?.sign)
    }

    /// The same transaction shown under a team that the list was filtered to.
    func withTeam(_ filterTeam: TransactionTeam?) -> TransactionItem {
        guard team.id.isEmpty, let filterTeam else { return self }
        return TransactionItem(dateString: dateString, description: description, team: filterTeam)
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
    let name: String?
    let children: [APIConference]?
    /// Women's college hockey has no conferences: its entries sit at the root.
    let standings: APIConference.APIStandings?

    /// One group per conference that has teams, in ESPN's order: FBS, then FCS. With no
    /// conferences, the teams at the root are one group named for the league, as on Windows.
    var conferenceGroups: [ConferenceGroup] {
        let groups: [ConferenceGroup] = (children ?? []).flatMap(\.conferences).compactMap { conference in
            let teams = conference.allTeams.sorted { $0.displayName < $1.displayName }
            guard !teams.isEmpty else { return nil }
            return ConferenceGroup(id: conference.id ?? conference.name, name: conference.name, teams: teams)
        }
        let rootTeams = (standings?.entries ?? []).map { $0.team.transactionTeam }
        guard groups.isEmpty, !rootTeams.isEmpty else { return groups }
        let rootName = name ?? "All Teams"
        return [ConferenceGroup(id: rootName, name: rootName,
                                teams: rootTeams.sorted { $0.displayName < $1.displayName })]
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
