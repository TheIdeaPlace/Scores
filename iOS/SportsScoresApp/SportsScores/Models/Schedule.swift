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
    /// ESPN's own `completed` and `state` for the status, which hold whatever the status is
    /// called. Nil for CFL games, whose feed has neither.
    var espnCompleted: Bool? = nil
    var espnState: String? = nil
    /// What sets this game apart, read with the row: "Super Bowl LX", "SEC Championship",
    /// "Preseason Week 1". Nil for an everyday game.
    var label: String? = nil

    /// Soccer says STATUS_FULL_TIME, or STATUS_FINAL_PEN after a shootout, for a finished game.
    private static let finishedStatuses: Set<String> = [
        "STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"
    ]

    var isCompleted: Bool { espnCompleted ?? Self.finishedStatuses.contains(statusType) }
    /// Includes halftime and a delay, which ESPN counts as under way and names differently.
    var isInProgress: Bool { espnState.map { $0 == "in" } ?? (statusType == "STATUS_IN_PROGRESS") }

    enum Outcome { case win, loss, tie }

    /// How the game went for one team. Nil without two scores. A draw is a tie, including one
    /// decided on penalties: the score is level, and `label` says who went through.
    func outcome(forTeamId teamId: String) -> Outcome? {
        guard let home = homeTeam.score, let away = awayTeam.score else { return nil }
        let (mine, theirs) = homeTeam.id == teamId ? (home, away) : (away, home)
        return mine > theirs ? .win : (mine < theirs ? .loss : .tie)
    }

    /// Whether this game is today (wall-clock comparison)
    var isToday: Bool { Calendar.current.isDateInToday(date) }

    /// True when the start is still ahead. With no set time, `date` is a placeholder,
    /// so a game later today still counts.
    func isAhead(of now: Date) -> Bool {
        timeIsKnown ? date > now : date >= Calendar.current.startOfDay(for: now)
    }

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

// MARK: - How a team's schedule is asked for

/// The requests behind a team's schedule, apart from the fetching so they can be tested.
/// Windows does the same in espn_api.get_team_schedule: change both together.
enum TeamScheduleQueries {
    /// Preseason, regular season, postseason.
    static let seasonTypes = [1, 2, 3]

    static func seasonType(_ seasonType: Int, season: Int) -> String {
        "season=\(season)&seasontype=\(seasonType)"
    }

    /// The games a soccer team played in a season. Soccer has no season type: 2 and 3 answer
    /// with nothing, which is why every team's schedule used to come up empty.
    static func soccerResults(season: Int) -> String {
        "season=\(season)"
    }

    /// The games a soccer team has to come, whatever season is asked for.
    static let soccerFixtures = "fixture=true"

    /// What to ask for once a season's results are in. Only the current season has fixtures.
    /// `espnSeason` is the `season.year` ESPN answers with, its own idea of the current season.
    /// A league's seasons cross the new year on their own calendar, so in February 2027 our
    /// year says 2027 while ESPN's Premier League is still in `season=2026`, 2026-27, and
    /// `season=2027` is empty. Those are the results to show then.
    static func afterSoccerResults(season: Int, currentSeason: Int,
                                   espnSeason: Int?) -> (fixtures: Bool, earlierResults: Int?) {
        guard season == currentSeason || season == espnSeason else { return (false, nil) }
        if let espnSeason, espnSeason < season { return (true, espnSeason) }
        return (true, nil)
    }

    /// One list in date order, with no game twice. The first list a game appears in wins, so
    /// results go first: a game just played that ESPN still lists as to come keeps its score.
    static func merged(_ lists: [[ScheduleGame]]) -> [ScheduleGame] {
        var seen = Set<String>()
        var games: [ScheduleGame] = []
        for list in lists {
            for game in list where seen.insert(game.id).inserted {
                games.append(game)
            }
        }
        return games.sorted { $0.date < $1.date }
    }
}

extension Sport {
    /// True where a team's schedule is asked for by results and fixtures, not by season type.
    /// The World Cups are soccer too, though `isSoccer` means the league hub.
    var usesSoccerSchedule: Bool { apiPath.hasPrefix("soccer/") }
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
        let week: APIWeek?
        let competitions: [APICompetition]

        struct APISeasonType: Codable {
            let type: Int
            let name: String?
        }

        struct APIWeek: Codable {
            let text: String?
        }

        struct APICompetition: Codable {
            let venue: APIVenue?
            let competitors: [APICompetitor]
            let status: APICompetitionStatus
            let timeValid: Bool?
            let neutralSite: Bool?
            let notes: [APINote]?

            struct APIVenue: Codable {
                let fullName: String?
            }

            /// `headline` is missing on soccer's bare ingest notes.
            struct APINote: Codable {
                let headline: String?
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
                    let completed: Bool?
                    let state: String?      // "pre" | "in" | "post"
                }
            }
        }

        /// What sets this game apart, the same way schedule_game_label does on Windows.
        /// ESPN's note says it best, and appears in any season type: FCS playoffs are filed
        /// under the regular season. "Week 5" isn't worth reading on every row, so the week
        /// and the season type's own name only count for preseason and postseason. Soccer's
        /// season types are long ids, so they never match.
        var gameLabel: String? {
            func text(_ value: String?) -> String? {
                guard let value, !value.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
                return value
            }
            for note in competitions.first?.notes ?? [] {
                if let headline = text(note.headline) { return headline }
            }
            guard seasonType.type == 1 || seasonType.type == 3 else { return nil }
            return text(week?.text) ?? text(seasonType.name)
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
                isNeutralSite: competition.neutralSite ?? false,
                espnCompleted: competition.status.type.completed,
                espnState: competition.status.type.state,
                label: gameLabel
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
