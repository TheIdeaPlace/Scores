//
//  LeagueVenues.swift
//  SportsScores
//
//  A league's venues and their home teams, built from its scoreboard. The twin of
//  services/venue_service.py on Windows. tests/fixtures/venues_grid.json holds the two apps
//  to the same months, the same venues and the same words, so change both together.
//
//  ESPN has no list of a league's venues. /teams carries no venue at all, and a team's
//  franchise.venue is years out of date for some teams. A scoreboard names the venue of
//  every game and which team is at home there, so one month of it gives both.
//
//  Being listed as home isn't enough to make a venue a team's home. A game at a neutral
//  site, a preseason game, and a one-off that ESPN doesn't mark neutral all list a home team.
//

import Foundation

// MARK: - Which months

/// The rules for each league, with the reasons for them in venue_service.py, where they
/// were measured against ESPN's scoreboards in November 2026.
enum VenueRules {
    /// In-season months to try before giving up, the latest first. Off-season, the first of
    /// them is already last season's. The others are for a month ESPN won't answer or has
    /// nothing for.
    static let monthsToTry = 3

    /// The regular season months with the most teams at home. Nil for a league with no Venues.
    static func inSeasonMonths(for sport: Sport) -> Set<Int>? {
        switch sport {
        case .mlb:    return [4, 5, 6, 7, 8, 9]
        case .nfl:    return [9, 11, 12]
        case .nba:    return [11, 1, 3]
        case .nhl:    return [11, 12, 1, 3]
        case .wnba:   return [6]
        case .ncaaf:  return [10, 11]
        case .ncaam, .ncaawb, .ncaah: return [2]
        case .ncaawh: return [1]
        default:      return nil
        }
    }

    /// College basketball and hockey can look ahead, because ESPN has the conference
    /// schedule long before it's played, and it's the only time every team is at home.
    static func monthsAhead(for sport: Sport) -> Int {
        switch sport {
        case .ncaam, .ncaawb, .ncaah, .ncaawh: return 3
        default: return 0
        }
    }

    /// ESPN has marked American Airlines Center as not indoors for a WNBA game. Football,
    /// baseball and hockey really do play outdoors, so only these leagues ignore that.
    static func isAlwaysIndoors(_ sport: Sport) -> Bool {
        switch sport {
        case .nba, .wnba, .ncaam, .ncaawb: return true
        default: return false
        }
    }

    /// groups=50 keeps any game with a Division I team in it, so a visit to a Division III
    /// host stays on the board. ESPN gives Division I teams a conferenceId and those hosts
    /// none. It gives no team a conferenceId in the other leagues, so this can't apply there.
    static func hostsNeedAConference(_ sport: Sport) -> Bool {
        sport == .ncaam || sport == .ncaawb
    }

    /// What the details say about the league, past what its name says.
    static func leagueFact(for sport: Sport) -> String? {
        switch sport {
        case .mlb:    return "Major League Baseball venue"
        case .nfl:    return "National Football League venue"
        case .nba:    return "National Basketball Association venue"
        case .nhl:    return "National Hockey League venue"
        case .wnba:   return "Women's National Basketball Association venue"
        case .ncaaf:  return "College football venue"
        case .ncaam:  return "Men's college basketball venue"
        case .ncaawb: return "Women's college basketball venue"
        case .ncaah:  return "Men's college hockey venue"
        case .ncaawh: return "Women's college hockey venue"
        default:      return nil
        }
    }

    /// The months to ask for as YYYYMM, the first of them the latest in-season month at or
    /// before `monthsAhead` from the given one.
    static func months(for sport: Sport, year: Int, month: Int) -> [String] {
        guard let inSeason = inSeasonMonths(for: sport), !inSeason.isEmpty else { return [] }
        var count = year * 12 + month - 1 + monthsAhead(for: sport)
        var found: [String] = []
        while found.count < monthsToTry {
            let thisMonth = count % 12 + 1
            if inSeason.contains(thisMonth) {
                found.append(String(format: "%04d%02d", count / 12, thisMonth))
            }
            count -= 1
        }
        return found
    }
}

/// Nothing came back, and at least one month that could have had it didn't answer. A plain
/// sentence, since "no venues" would be untrue and raw network text shouldn't be read aloud.
enum VenuesError: LocalizedError {
    case espnDidNotAnswer

    var errorDescription: String? { "ESPN did not answer. Try again in a minute." }
}

// MARK: - The venue

struct VenueHomeTeam: Hashable {
    let id: String
    let name: String
    let abbreviation: String

    /// A team's line in the details: Brooklyn Nets (BKN).
    var detailLine: String {
        abbreviation.isEmpty ? name : "\(name) (\(abbreviation))"
    }
}

struct LeagueVenue: Identifiable, Hashable {
    let id: String
    let name: String
    let city: String
    let state: String
    /// Nil when ESPN doesn't say: no answer isn't the same as outdoors.
    var indoor: Bool?
    var homeTeams: [VenueHomeTeam] = []

    var location: String {
        [city, state].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    private var teamNames: String {
        homeTeams.map(\.name).joined(separator: ", ")
    }

    /// Indoor or Outdoor, and empty when it isn't known.
    var typeText: String {
        guard let indoor else { return "" }
        return indoor ? "Indoor" : "Outdoor"
    }

    /// A venue's row in the list: Name (City, State) [Indoor] - Home Team.
    var summary: String {
        var text = name
        if !location.isEmpty { text += " (\(location))" }
        if !typeText.isEmpty { text += " [\(typeText)]" }
        if !homeTeams.isEmpty { text += " - \(teamNames)" }
        return text
    }

    /// The same row for VoiceOver in Quick List, which would otherwise read the punctuation.
    var quickAccessibilityLabel: String {
        [name, location, typeText, teamNames].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    /// The same row in Full List, with what each part is.
    var fullAccessibilityLabel: String {
        var parts = ["Venue: \(name)"]
        if !location.isEmpty { parts.append("Location: \(location)") }
        if !typeText.isEmpty { parts.append("Type: \(typeText)") }
        if !homeTeams.isEmpty { parts.append("\(homeTeams.count == 1 ? "Home team" : "Home teams"): \(teamNames)") }
        return parts.joined(separator: ". ")
    }

    /// A row of Table View: Venue, Location, Type and Home Teams. "Not listed" stands in for
    /// a blank, which VoiceOver would pass over and leave the row short a column.
    var tableRow: [String] {
        [name,
         location.isEmpty ? "Not listed" : location,
         typeText.isEmpty ? "Not listed" : typeText,
         teamNames]
    }

    /// "Type: Indoor stadium" in the details, or nil when it isn't known.
    var typeDetailLine: String? {
        guard let indoor else { return nil }
        return "Type: \(indoor ? "Indoor" : "Outdoor") stadium"
    }

    /// The league lines of the details. Only what the scoreboard says: capacity and playing
    /// surface aren't in it.
    func facts(in sport: Sport) -> [String] {
        var facts: [String] = []
        if indoor == true {
            facts.append("Indoor venue")
        } else if indoor == false {
            facts.append("Open-air stadium exposed to weather")
        }
        if let league = VenueRules.leagueFact(for: sport) {
            facts.append(league)
        }
        if sport == .mlb {
            if name.contains("Field") {
                facts.append("Classic baseball 'Field' naming")
            } else if name.contains("Park") {
                facts.append("Traditional baseball 'Park' naming")
            }
        } else if sport == .nfl && indoor == true {
            facts.append("Weather never affects games here")
        }
        if !location.isEmpty {
            facts.append("Located in \(location)")
        }
        if homeTeams.count == 1 {
            facts.append("Home of the \(homeTeams[0].name)")
        } else if homeTeams.count > 1 {
            facts.append("Shared by \(homeTeams.count) teams")
        }
        return facts
    }

    /// Every venue that is some team's home in these scoreboard events, by name as both
    /// apps list them.
    ///
    /// A team's home is a venue it uses at least half as often as the one it uses most, which
    /// keeps the Athletics' 9 games in Sacramento and 6 in Las Vegas, and loses the Mammoth's
    /// one game at a football stadium. A month is few games, so one of two has to stay: the
    /// UConn men split theirs between two arenas.
    static func venues(from events: [VenueScoreboard.Event], in sport: Sport) -> [LeagueVenue] {
        var venues: [String: LeagueVenue] = [:]
        var venueOrder: [String] = []
        var teams: [String: VenueHomeTeam] = [:]
        var teamOrder: [String] = []
        var uses: [String: [String: Int]] = [:]
        let alwaysIndoors = VenueRules.isAlwaysIndoors(sport)
        let needsConference = VenueRules.hostsNeedAConference(sport)

        for event in events {
            guard let competition = event.competition,
                  competition.neutralSite != true,
                  event.seasonType != VenueScoreboard.preseason,
                  let raw = competition.venue,
                  let venueId = raw.id,
                  let venueName = raw.name,
                  let team = competition.homeTeam(needsConference: needsConference) else { continue }

            if venues[venueId] == nil {
                venues[venueId] = LeagueVenue(id: venueId, name: venueName, city: raw.city, state: raw.state)
                venueOrder.append(venueId)
            }
            if raw.indoor == true || (raw.indoor == false && !alwaysIndoors) {
                venues[venueId]?.indoor = raw.indoor
            }
            if teams[team.id] == nil {
                teamOrder.append(team.id)
            }
            teams[team.id] = team
            uses[team.id, default: [:]][venueId, default: 0] += 1
        }

        for teamId in teamOrder {
            guard let team = teams[teamId], let teamUses = uses[teamId] else { continue }
            let mostUsed = teamUses.values.max() ?? 0
            for (venueId, count) in teamUses where count * 2 >= mostUsed {
                venues[venueId]?.homeTeams.append(team)
            }
        }

        var result: [LeagueVenue] = []
        for venueId in venueOrder {
            guard var venue = venues[venueId], !venue.homeTeams.isEmpty else { continue }
            venue.homeTeams.sort { $0.name < $1.name }
            result.append(venue)
        }
        result.sort { $0.name < $1.name }
        return result
    }
}

// MARK: - What's read from a scoreboard

/// Only what the rule needs from a month of games, which is up to 19 MB in college
/// basketball. A game with a hole in it costs only that game, and what isn't an object has
/// no games in it, which isn't the same as not being JSON at all: that one still throws.
struct VenueScoreboard: Decodable {
    /// `season.type` of a preseason game.
    static let preseason = 1

    let events: [Event]

    private enum CodingKeys: String, CodingKey { case events }

    init(from decoder: Decoder) throws {
        let container = try? decoder.container(keyedBy: CodingKeys.self)
        events = container?.lossyArray(forKey: .events) ?? []
    }

    /// ESPN's ids come as text or as a number. Nothing, "" and 0 all mean there isn't one.
    private struct Identifier: Decodable {
        let text: String?

        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let string = try? container.decode(String.self) {
                text = string.isEmpty ? nil : string
            } else if let number = try? container.decode(Int.self) {
                text = number == 0 ? nil : String(number)
            } else {
                text = nil
            }
        }
    }

    struct Event: Decodable {
        let seasonType: Int?
        let competition: Competition?

        private enum CodingKeys: String, CodingKey { case season, competitions }
        private struct Season: Decodable { let type: Int? }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            let season = try? container.decodeIfPresent(Season.self, forKey: .season)
            seasonType = season?.type
            let competitions: [Competition]? = container.lossyArray(forKey: .competitions)
            competition = competitions?.first
        }
    }

    struct Competition: Decodable {
        let neutralSite: Bool?
        let venue: Venue?
        let competitors: [Competitor]

        private enum CodingKeys: String, CodingKey { case neutralSite, venue, competitors }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            neutralSite = try? container.decodeIfPresent(Bool.self, forKey: .neutralSite)
            venue = try? container.decodeIfPresent(Venue.self, forKey: .venue)
            competitors = container.lossyArray(forKey: .competitors) ?? []
        }

        /// The team at home in this game, or nil if ESPN doesn't name one or it doesn't count.
        func homeTeam(needsConference: Bool) -> VenueHomeTeam? {
            guard let team = competitors.first(where: { $0.homeAway == "home" })?.team,
                  let id = team.id,
                  let name = team.name,
                  !needsConference || team.hasConference else { return nil }
            return VenueHomeTeam(id: id, name: name, abbreviation: team.abbreviation)
        }
    }

    struct Venue: Decodable {
        let id: String?
        let name: String?
        let city: String
        let state: String
        let indoor: Bool?

        private enum CodingKeys: String, CodingKey { case id, fullName, displayName, address, indoor }
        private enum AddressKeys: String, CodingKey { case city, state }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            let identifier = try? container.decodeIfPresent(Identifier.self, forKey: .id)
            id = identifier?.text
            let fullName = try? container.decodeIfPresent(String.self, forKey: .fullName)
            let displayName = try? container.decodeIfPresent(String.self, forKey: .displayName)
            name = [fullName, displayName].compactMap { $0 }.first { !$0.isEmpty }
            indoor = try? container.decodeIfPresent(Bool.self, forKey: .indoor)
            let address = try? container.nestedContainer(keyedBy: AddressKeys.self, forKey: .address)
            let cityText = try? address?.decodeIfPresent(String.self, forKey: .city)
            let stateText = try? address?.decodeIfPresent(String.self, forKey: .state)
            city = cityText ?? ""
            state = stateText ?? ""
        }
    }

    struct Competitor: Decodable {
        let homeAway: String?
        let team: Team?

        private enum CodingKeys: String, CodingKey { case homeAway, team }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            homeAway = try? container.decodeIfPresent(String.self, forKey: .homeAway)
            team = try? container.decodeIfPresent(Team.self, forKey: .team)
        }
    }

    struct Team: Decodable {
        let id: String?
        let name: String?
        let abbreviation: String
        let hasConference: Bool

        private enum CodingKeys: String, CodingKey { case id, displayName, name, abbreviation, conferenceId }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            let identifier = try? container.decodeIfPresent(Identifier.self, forKey: .id)
            id = identifier?.text
            let displayName = try? container.decodeIfPresent(String.self, forKey: .displayName)
            let shortName = try? container.decodeIfPresent(String.self, forKey: .name)
            name = [displayName, shortName].compactMap { $0 }.first { !$0.isEmpty }
            let abbreviationText = try? container.decodeIfPresent(String.self, forKey: .abbreviation)
            abbreviation = abbreviationText ?? ""
            let conference = try? container.decodeIfPresent(Identifier.self, forKey: .conferenceId)
            hasConference = conference?.text != nil
        }
    }
}
