//
//  Schedule.swift
//  SportsScores
//
//  Created on 2/26/26.
//
//  Team schedule models (for TeamScheduleView and TeamScheduleViewModel).

import Foundation

// MARK: - Display model

struct ScheduleGame: Identifiable {
    let id: String
    let date: Date
    let name: String            // "Yankees at Orioles"
    let awayTeam: ScheduleTeam
    let homeTeam: ScheduleTeam
    let statusText: String      // "Final" / "7:05 PM ET" / "In Progress"
    let statusType: String      // "STATUS_FINAL" / "STATUS_SCHEDULED" etc.
    let seasonType: Int         // 1=spring/pre, 2=regular, 3=postseason
    let venueName: String?
    /// False when ESPN's time is a placeholder; `date` is then noon local on the game's date.
    var timeIsKnown: Bool = true
    var isNeutralSite: Bool = false

    var isCompleted: Bool { statusType == "STATUS_FINAL" }
    var isInProgress: Bool { statusType == "STATUS_IN_PROGRESS" }

    /// Whether this game is today (wall-clock comparison)
    var isToday: Bool { Calendar.current.isDateInToday(date) }

    /// Convert to the Game model so GameDetailView can be reused.
    func toGame() -> Game {
        Game(
            id: id,
            name: name,
            shortName: "\(awayTeam.abbreviation) @ \(homeTeam.abbreviation)",
            date: date,
            status: Game.GameStatus(
                state: isCompleted ? "post" : isInProgress ? "in" : "pre",
                detail: statusText,
                period: nil,
                clock: nil,
                name: nil
            ),
            homeTeam: Game.Team(
                id: homeTeam.id,
                name: homeTeam.displayName,
                abbreviation: homeTeam.abbreviation,
                displayName: homeTeam.displayName,
                score: homeTeam.score,
                record: nil,
                logo: nil
            ),
            awayTeam: Game.Team(
                id: awayTeam.id,
                name: awayTeam.displayName,
                abbreviation: awayTeam.abbreviation,
                displayName: awayTeam.displayName,
                score: awayTeam.score,
                record: nil,
                logo: nil
            ),
            venue: venueName.map { Game.Venue(name: $0, city: nil, state: nil) },
            broadcasts: [],
            situation: nil,
            seasonType: seasonType,
            timeValid: timeIsKnown,
            isNeutralSite: isNeutralSite
        )
    }

    struct ScheduleTeam {
        let id: String
        let abbreviation: String
        let displayName: String
        let score: Int?         // nil if game not yet played
    }
}

// MARK: - API response types (Codable)

struct TeamScheduleAPIResponse: Codable {
    let season: APISeason?
    let events: [APIScheduleEvent]

    struct APISeason: Codable {
        let year: Int
    }

    struct APIScheduleEvent: Codable {
        let id: String
        let date: String            // ISO-8601 string
        let timeValid: Bool?
        let name: String
        let seasonType: APISeasonType
        let competitions: [APICompetition]

        struct APISeasonType: Codable {
            let type: Int
        }

        struct APICompetition: Codable {
            let venue: APIVenue?
            let competitors: [APICompetitor]
            let status: APICompetitionStatus
            let timeValid: Bool?
            let neutralSite: Bool?

            struct APIVenue: Codable {
                let fullName: String?
            }

            struct APICompetitor: Codable {
                let homeAway: String    // "home" | "away"
                let team: APITeam
                let score: APIScore?

                struct APITeam: Codable {
                    let id: String
                    let abbreviation: String
                    let displayName: String
                }

                struct APIScore: Codable {
                    let value: Double?
                }
            }

            struct APICompetitionStatus: Codable {
                let type: APIStatusType

                struct APIStatusType: Codable {
                    let name: String        // "STATUS_FINAL" etc.
                    let description: String // "Final" / "7:05 PM ET"
                }
            }
        }

        /// Convert to display model. Returns nil if competitors cannot be found.
        func toScheduleGame() -> ScheduleGame? {
            guard let competition = competitions.first else { return nil }
            let comps = competition.competitors

            guard
                let homeComp = comps.first(where: { $0.homeAway == "home" }),
                let awayComp = comps.first(where: { $0.homeAway == "away" })
            else { return nil }

            // ESPN returns dates without seconds ("2025-03-27T19:00Z") which the default
            // ISO8601DateFormatter fails to parse, returning nil → Date.distantPast → Dec 31.
            // Try multiple formats, same approach as Game.swift.
            let parsedDate = Self.parseDate(date)
            let timeIsKnown = (timeValid ?? competition.timeValid) != false

            return ScheduleGame(
                id: id,
                date: timeIsKnown ? parsedDate : ScoreboardDay.localNoon(onUTCDayOf: parsedDate),
                name: name,
                awayTeam: ScheduleGame.ScheduleTeam(
                    id: awayComp.team.id,
                    abbreviation: awayComp.team.abbreviation,
                    displayName: awayComp.team.displayName,
                    score: awayComp.score?.value.map { Int($0) } ?? nil
                ),
                homeTeam: ScheduleGame.ScheduleTeam(
                    id: homeComp.team.id,
                    abbreviation: homeComp.team.abbreviation,
                    displayName: homeComp.team.displayName,
                    score: homeComp.score?.value.map { Int($0) } ?? nil
                ),
                statusText: competition.status.type.description,
                statusType: competition.status.type.name,
                seasonType: seasonType.type,
                venueName: competition.venue?.fullName,
                timeIsKnown: timeIsKnown,
                isNeutralSite: competition.neutralSite ?? false
            )
        }

        /// Robustly parse an ESPN date string, which can appear with or without seconds.
        /// Falls back to today's date rather than Date.distantPast so failures are visible.
        static func parseDate(_ string: String) -> Date {
            let fmt = DateFormatter()
            fmt.locale = Locale(identifier: "en_US_POSIX")
            fmt.timeZone = TimeZone(secondsFromGMT: 0)
            let formats = [
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                "yyyy-MM-dd'T'HH:mm'Z'",
                "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
            ]
            for f in formats {
                fmt.dateFormat = f
                if let d = fmt.date(from: string) { return d }
            }
            // If all formats fail, log the bad string and return today so it
            // appears near the current date rather than December 31, year 0000.
            print("[Schedule] WARNING: failed to parse date '\(string)'")
            return Date()
        }
    }
}
