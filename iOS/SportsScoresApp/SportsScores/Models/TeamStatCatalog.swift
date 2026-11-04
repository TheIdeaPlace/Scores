//
//  TeamStatCatalog.swift
//  SportsScores
//
//  Curated list of league-wide team statistics per sport.
//
//  ESPN's `statistics/byteam` endpoint returns every team's full stat line
//  (100+ values for football). Showing all of them would bury the interesting
//  numbers, so each sport gets a hand-picked list in a sensible reading order
//  (offense → defense → special teams), together with the sort direction that
//  makes "#1" mean "best" rather than merely "largest".
//

import Foundation

/// One team-stat category to build from the `byteam` payload.
struct TeamStatSpec {
    /// Which half of the payload the value comes from. ESPN reports each
    /// category twice: the team's own production (`splitId` 0) and what its
    /// opponents did against it (`splitId` 900) — the latter is how "yards
    /// allowed" and "opponent points" are expressed.
    enum Split {
        case own
        case opponent
    }

    let split: Split
    /// ESPN category name, e.g. "batting", "passing", "offensive".
    let section: String
    /// ESPN stat name within that category, e.g. "homeRuns", "avgPoints".
    let stat: String
    /// Heading shown to the user. ESPN's own display names collide across
    /// categories (batting and pitching both have "Strikeouts"), so titles
    /// are spelled out here rather than taken from the feed.
    let title: String
    /// True when a larger value ranks first (points scored); false when a
    /// smaller value does (ERA, turnovers, points allowed).
    let higherIsBetter: Bool

    init(_ split: Split, _ section: String, _ stat: String, _ title: String, higherIsBetter: Bool = true) {
        self.split = split
        self.section = section
        self.stat = stat
        self.title = title
        self.higherIsBetter = higherIsBetter
    }

    /// The team's own production — the common case.
    init(_ section: String, _ stat: String, _ title: String, higherIsBetter: Bool = true) {
        self.init(.own, section, stat, title, higherIsBetter: higherIsBetter)
    }

    /// Stable identifier used as the category name so "View All" can re-find
    /// this category after a second fetch.
    var key: String {
        "\(split == .opponent ? "opponent." : "")\(section).\(stat)"
    }
}

enum TeamStatCatalog {

    /// Specs for a sport, or an empty array when ESPN publishes no team
    /// statistics for it (soccer, golf, racing, college hockey, CFL).
    static func specs(for sport: Sport) -> [TeamStatSpec] {
        switch sport {
        case .mlb:
            return baseball
        case .nfl, .ncaaf:
            return football
        case .nba, .wnba, .ncaam, .ncaawb:
            return basketball
        case .nhl:
            return hockey
        default:
            return []
        }
    }

    // MARK: - Baseball

    private static let baseball: [TeamStatSpec] = [
        // Batting
        TeamStatSpec("batting", "runs", "Runs"),
        TeamStatSpec("batting", "homeRuns", "Home Runs"),
        TeamStatSpec("batting", "avg", "Batting Average"),
        TeamStatSpec("batting", "onBasePct", "On Base Percentage"),
        TeamStatSpec("batting", "slugAvg", "Slugging Percentage"),
        TeamStatSpec("batting", "OPS", "OPS"),
        TeamStatSpec("batting", "hits", "Hits"),
        TeamStatSpec("batting", "doubles", "Doubles"),
        TeamStatSpec("batting", "triples", "Triples"),
        TeamStatSpec("batting", "walks", "Walks Drawn"),
        TeamStatSpec("batting", "stolenBases", "Stolen Bases"),
        TeamStatSpec("batting", "strikeouts", "Fewest Batter Strikeouts", higherIsBetter: false),
        // Pitching
        TeamStatSpec("pitching", "ERA", "Earned Run Average", higherIsBetter: false),
        TeamStatSpec("pitching", "WHIP", "WHIP", higherIsBetter: false),
        TeamStatSpec("pitching", "opponentAvg", "Opponent Batting Average", higherIsBetter: false),
        TeamStatSpec("pitching", "strikeouts", "Pitching Strikeouts"),
        TeamStatSpec("pitching", "qualityStarts", "Quality Starts"),
        TeamStatSpec("pitching", "saves", "Saves"),
        TeamStatSpec("pitching", "shutouts", "Shutouts"),
        TeamStatSpec("pitching", "homeRuns", "Fewest Home Runs Allowed", higherIsBetter: false),
        TeamStatSpec("pitching", "walks", "Fewest Walks Allowed", higherIsBetter: false),
        // Fielding
        TeamStatSpec("fielding", "fieldingPct", "Fielding Percentage"),
        TeamStatSpec("fielding", "errors", "Fewest Errors", higherIsBetter: false),
    ]

    // MARK: - Football
    //
    // NFL publishes a superset of the college feed; specs missing from the
    // college payload (turnover differential, takeaways) are skipped silently.

    private static let football: [TeamStatSpec] = [
        // Scoring and total offense
        TeamStatSpec("passing", "totalPointsPerGame", "Points Per Game"),
        TeamStatSpec(.opponent, "passing", "totalPointsPerGame", "Fewest Points Allowed Per Game", higherIsBetter: false),
        TeamStatSpec("passing", "yardsPerGame", "Total Yards Per Game"),
        TeamStatSpec(.opponent, "passing", "yardsPerGame", "Fewest Total Yards Allowed Per Game", higherIsBetter: false),
        // Passing
        TeamStatSpec("passing", "passingYardsPerGame", "Passing Yards Per Game"),
        TeamStatSpec(.opponent, "passing", "passingYardsPerGame", "Fewest Passing Yards Allowed Per Game", higherIsBetter: false),
        TeamStatSpec("passing", "passingTouchdowns", "Passing Touchdowns"),
        TeamStatSpec("passing", "completionPct", "Completion Percentage"),
        TeamStatSpec("passing", "QBRating", "Passer Rating"),
        // Rushing
        TeamStatSpec("rushing", "rushingYardsPerGame", "Rushing Yards Per Game"),
        TeamStatSpec(.opponent, "rushing", "rushingYardsPerGame", "Fewest Rushing Yards Allowed Per Game", higherIsBetter: false),
        TeamStatSpec("rushing", "rushingTouchdowns", "Rushing Touchdowns"),
        TeamStatSpec("rushing", "yardsPerRushAttempt", "Yards Per Rush"),
        // Situational
        TeamStatSpec("miscellaneous", "firstDowns", "First Downs"),
        TeamStatSpec("miscellaneous", "thirdDownConvPct", "Third Down Percentage"),
        TeamStatSpec("miscellaneous", "fourthDownConvPct", "Fourth Down Percentage"),
        TeamStatSpec("miscellaneous", "turnOverDifferential", "Turnover Differential"),
        TeamStatSpec("miscellaneous", "totalTakeaways", "Takeaways"),
        TeamStatSpec("miscellaneous", "totalGiveaways", "Fewest Giveaways", higherIsBetter: false),
        TeamStatSpec("miscellaneous", "totalPenaltyYards", "Fewest Penalty Yards", higherIsBetter: false),
        // Defense (the defense's production shows up in the opponent split)
        TeamStatSpec(.opponent, "passing", "sacks", "Sacks"),
        TeamStatSpec(.opponent, "passing", "interceptions", "Interceptions"),
        // Special teams
        TeamStatSpec("kicking", "fieldGoalPct", "Field Goal Percentage"),
        TeamStatSpec("punting", "netAvgPuntYards", "Net Punting Average"),
    ]

    // MARK: - Basketball

    private static let basketball: [TeamStatSpec] = [
        TeamStatSpec("offensive", "avgPoints", "Points Per Game"),
        TeamStatSpec(.opponent, "offensive", "avgPoints", "Fewest Points Allowed Per Game", higherIsBetter: false),
        TeamStatSpec("differential", "avgPointsDifferential", "Scoring Margin"),
        TeamStatSpec("offensive", "fieldGoalPct", "Field Goal Percentage"),
        TeamStatSpec(.opponent, "offensive", "fieldGoalPct", "Opponent Field Goal Percentage", higherIsBetter: false),
        TeamStatSpec("offensive", "threePointFieldGoalPct", "3-Point Percentage"),
        TeamStatSpec("offensive", "avgThreePointFieldGoalsMade", "3-Pointers Made Per Game"),
        TeamStatSpec("offensive", "freeThrowPct", "Free Throw Percentage"),
        TeamStatSpec("offensive", "avgAssists", "Assists Per Game"),
        TeamStatSpec("general", "avgRebounds", "Rebounds Per Game"),
        TeamStatSpec("offensive", "avgOffensiveRebounds", "Offensive Rebounds Per Game"),
        TeamStatSpec("defensive", "avgDefensiveRebounds", "Defensive Rebounds Per Game"),
        TeamStatSpec("defensive", "avgSteals", "Steals Per Game"),
        TeamStatSpec("defensive", "avgBlocks", "Blocks Per Game"),
        TeamStatSpec("general", "assistTurnoverRatio", "Assist To Turnover Ratio"),
        TeamStatSpec("offensive", "avgTurnovers", "Fewest Turnovers Per Game", higherIsBetter: false),
        TeamStatSpec("general", "avgFouls", "Fewest Fouls Per Game", higherIsBetter: false),
    ]

    // MARK: - Hockey

    private static let hockey: [TeamStatSpec] = [
        TeamStatSpec("offensive", "avgGoals", "Goals For Per Game"),
        TeamStatSpec("defensive", "avgGoalsAgainst", "Goals Against Average", higherIsBetter: false),
        TeamStatSpec("offensive", "goals", "Goals"),
        TeamStatSpec("offensive", "assists", "Assists"),
        TeamStatSpec("offensive", "powerPlayPct", "Power Play Percentage"),
        TeamStatSpec("defensive", "penaltyKillPct", "Penalty Kill Percentage"),
        TeamStatSpec("offensive", "powerPlayGoals", "Power Play Goals"),
        TeamStatSpec("offensive", "shortHandedGoals", "Short Handed Goals"),
        TeamStatSpec("offensive", "shotsTotal", "Shots"),
        TeamStatSpec("offensive", "shootingPct", "Shooting Percentage"),
        TeamStatSpec("defensive", "savePct", "Save Percentage"),
        TeamStatSpec("defensive", "saves", "Saves"),
        TeamStatSpec("defensive", "shutouts", "Shutouts"),
        TeamStatSpec("defensive", "shotsAgainst", "Fewest Shots Against", higherIsBetter: false),
        TeamStatSpec("penalties", "penaltyMinutes", "Fewest Penalty Minutes", higherIsBetter: false),
        TeamStatSpec("general", "wins", "Wins"),
    ]

    // MARK: - Which way a stat ranks

    /// The team's own stats where less is better, by the first part of the sport's ESPN path.
    /// The opponent's version of a stat goes the other way: a team wants its opponents to score
    /// less, and to turn it over more. On Windows this is team_stats.LOW_IS_GOOD, and
    /// tests/fixtures/team_stat_directions.json holds both. The specs above are a subset. A stat
    /// nobody has listed reads highest first, and the validator warns about a stat it doesn't know.
    static let lowIsGood: [String: Set<String>] = [
        "baseball": [
            "batting.strikeouts",
            "pitching.losses", "pitching.ERA", "pitching.hits", "pitching.earnedRuns", "pitching.homeRuns",
            "pitching.walks", "pitching.opponentAvg", "pitching.WHIP",
            "fielding.errors",
        ],
        "football": [
            "general.fumblesLost",
            "passing.interceptions", "passing.sacks", "passing.sackYardsLost",
            "rushing.rushingFumbles", "rushing.rushingFumblesLost",
            "receiving.receivingFumbles", "receiving.receivingFumblesLost",
            "miscellaneous.totalPenalties", "miscellaneous.totalPenaltyYards", "miscellaneous.totalGiveaways",
            "punting.puntsBlocked", "punting.touchbacks", "punting.puntReturns", "punting.puntReturnYards",
            "punting.avgPuntReturnYards",
        ],
        "basketball": [
            "general.fouls", "general.avgFouls", "general.technicalFouls",
            "offensive.turnovers", "offensive.avgTurnovers",
            "differential.turnoversDifferential", "differential.avgTurnoversDifferential",
            "differential.avgFoulsDifferential",
        ],
        "hockey": [
            "general.losses",
            "defensive.avgGoalsAgainst", "defensive.goalsAgainst", "defensive.shotsAgainst",
            "defensive.overtimeLosses", "defensive.shootoutShotsAgainst",
            "penalties.penaltyMinutes",
        ],
    ]

    /// Counts of tries, which aren't good or bad in themselves, so they read highest first for the
    /// team and its opponents alike: a defense wants to force punts, and an attempt isn't a miss.
    static let countsOfTries: [String: Set<String>] = [
        "baseball": ["batting.atBats", "pitching.innings", "fielding.totalChances"],
        "football": [
            "passing.passingAttempts", "rushing.rushingAttempts",
            "miscellaneous.thirdDownAttempts", "miscellaneous.fourthDownAttempts",
            "kicking.fieldGoalAttempts", "kicking.fieldGoalAttempts1_19", "kicking.fieldGoalAttempts20_29",
            "kicking.fieldGoalAttempts30_39", "kicking.fieldGoalAttempts40_49", "kicking.fieldGoalAttempts50",
            "kicking.extraPointAttempts",
            "punting.punts", "returning.kickReturns", "returning.puntReturns",
        ],
        "basketball": [
            "offensive.fieldGoalsAttempted", "offensive.avgFieldGoalsAttempted",
            "offensive.threePointFieldGoalsAttempted", "offensive.avgThreePointFieldGoalsAttempted",
            "offensive.freeThrowsAttempted", "offensive.avgFreeThrowsAttempted",
        ],
        "hockey": ["offensive.powerPlayOpportunities", "offensive.shootoutAttempts"],
    ]

    static func sportKey(for sport: Sport) -> String {
        sport.apiPath.components(separatedBy: "/").first ?? ""
    }

    static func higherIsBetter(sportKey: String, section: String, stat: String, opponent: Bool = false) -> Bool {
        let key = "\(section).\(stat)"
        if stat == "gamesPlayed" || stat == "games" || countsOfTries[sportKey]?.contains(key) == true { return true }
        let low = lowIsGood[sportKey]?.contains(key) ?? false
        return opponent ? low : !low
    }

    /// Whether a sport's list has schools outside Division I in it. College football's is only FBS.
    static func listHasOtherDivisions(_ sport: Sport) -> Bool {
        sport.isCollegeSport && sportKey(for: sport) == "basketball"
    }

    /// A column every team has, to ask for the list sorted each way when ESPN can't send it all
    /// at once. Only basketball says how many it has, and the rest fit.
    static func sortColumn(for sport: Sport) -> String? {
        sportKey(for: sport) == "basketball" ? "offensive.avgTurnovers" : nil
    }
}

// MARK: - Ranks

enum TeamStatRanks {
    /// One plus how many teams are better. Teams level share a rank, and the next rank counts
    /// them. tests/fixtures/team_stat_directions.json holds this and Windows to the same answers.
    static func rank(of value: Double, among values: [Double], higherIsBetter: Bool) -> Int {
        1 + values.filter { higherIsBetter ? $0 > value : $0 < value }.count
    }

    static func ordinal(_ number: Int) -> String {
        let lastTwo = number % 100
        if (11...13).contains(lastTwo) { return "\(number)th" }
        switch number % 10 {
        case 1: return "\(number)st"
        case 2: return "\(number)nd"
        case 3: return "\(number)rd"
        default: return "\(number)th"
        }
    }

    enum Band {
        case top, middle, bottom, unknown
    }

    /// Top quarter, a bit over a third, the rest, which in a league of 32 is 8, 12 and 12.
    static func band(rank: Int, of leagueSize: Int?) -> Band {
        guard let leagueSize, leagueSize > 0 else { return .unknown }
        let place = Double(rank) / Double(leagueSize)
        if place <= 0.25 { return .top }
        return place <= 0.625 ? .middle : .bottom
    }

    /// "9th", "Tied-9th", as ESPN writes them. A college list gets what it's out of: "118th" is
    /// a good team among 300 and a bad one among 32, and a pro fan knows how many teams there are.
    static func display(rank: Int, tied: Bool, outOf leagueSize: Int?) -> String {
        let place = (tied ? "Tied-" : "") + ordinal(rank)
        return leagueSize.map { "\(place) of \($0)" } ?? place
    }
}

// MARK: - A league's team stats, ranked

/// A season's `byteam` payload, ready to rank. The league list and Team Hub both rank through this,
/// so they can't disagree. ESPN's own ranks aren't used where this has the stat: this feed's are
/// blank for NBA points per game and its totalGiveaways rank 1 is the team with the most giveaways,
/// and the core API has no rank for NBA per-game stats and ranks its totals per game, so a team
/// with the 11th most assists reads 5th.
struct LeagueTeamStats {
    typealias Team = TeamStatsByTeamResponse.TeamStats

    struct Row {
        let value: Double
        let display: String
        let team: Team.TeamInfo
    }

    let sport: Sport
    let teams: [Team]
    /// Lower-case section name to stat name to column. The core API writes
    /// "defensiveInterceptions" where this feed writes "defensiveinterceptions".
    private let columns: [String: [String: Int]]

    private static let opponentSplit = "900"

    init(_ response: TeamStatsByTeamResponse, sport: Sport) {
        self.sport = sport
        self.teams = response.divisionOneTeamIDs.map { Self.divisionOneTeams(in: response, teamList: $0) }
            ?? (response.teams ?? [])
        var columns: [String: [String: Int]] = [:]
        // Each section comes once per split, and only the first copy has the names.
        for meta in response.categories ?? [] {
            guard let section = meta.name?.lowercased(), let names = meta.names, !names.isEmpty,
                  columns[section] == nil else { continue }
            var index: [String: Int] = [:]
            // ESPN repeats a few stat keys within a category (NFL rushing lists
            // rushingYards twice, with the same number); the first is the one to use.
            for (i, name) in names.enumerated() where index[name] == nil {
                index[name] = i
            }
            columns[section] = index
        }
        self.columns = columns
    }

    /// A college basketball list has every school that played a Division I team, so a Division II
    /// school with one game can top a per-game stat: 722 teams in 2025-26's men's basketball, 362 of
    /// them Division I. ESPN only has opponents' numbers for Division I teams, which tells them
    /// apart when everyone has played once. A few schools moving up to Division I have none (East
    /// Texas A&M, Southern Indiana, Queens and Lindenwood in the women's game in 2026-27), and those
    /// are on ESPN's team list, which has no other schools. On Windows this is
    /// team_stats.qualified_teams.
    static func divisionOneTeams(in response: TeamStatsByTeamResponse, teamList: Set<String>) -> [Team] {
        (response.teams ?? []).filter { team in
            hasOpponents(team) || team.team.id.map { teamList.contains($0) } == true
        }
    }

    static func hasOpponents(_ team: Team) -> Bool {
        (team.categories ?? []).contains { $0.splitId == opponentSplit }
    }

    func rows(section: String, stat: String, opponent: Bool = false) -> [Row] {
        guard let index = columns[section.lowercased()]?[stat] else { return [] }
        return teams.compactMap { team -> Row? in
            guard let category = (team.categories ?? []).first(where: {
                $0.name?.lowercased() == section.lowercased()
                    && (opponent ? $0.splitId == Self.opponentSplit : $0.splitId != Self.opponentSplit)
            }),
            let display = category.totals?[safe: index] ?? nil,
            !display.isEmpty, display != "-",
            // An NHL team yet to go to a shootout has "0" with a null.
            let value = (category.values?[safe: index] ?? nil) ?? (display == "0" ? 0 : nil)
            else { return nil }
            return Row(value: value, display: display, team: team.team)
        }
    }

    /// The rows best first, each with its rank. A tie reads in name order so the list doesn't reshuffle.
    func ranked(section: String, stat: String, opponent: Bool, higherIsBetter: Bool) -> [(rank: Int, row: Row)] {
        let sorted = rows(section: section, stat: stat, opponent: opponent).sorted { first, second in
            if first.value != second.value {
                return higherIsBetter ? first.value > second.value : first.value < second.value
            }
            return (first.team.displayName ?? "") < (second.team.displayName ?? "")
        }
        var ranked: [(rank: Int, row: Row)] = []
        for (position, row) in sorted.enumerated() {
            let shared = ranked.last.flatMap { $0.row.value == row.value ? $0.rank : nil }
            ranked.append((shared ?? position + 1, row))
        }
        return ranked
    }

    /// Where a team stands in one of its own stats, or nil if this feed doesn't have it. Team Hub's
    /// answer to "where does this team rank", the same as reading it off the league list.
    func standing(ofTeam teamId: String, section: String, stat: String) -> (rank: Int, tied: Bool)? {
        let league = rows(section: section, stat: stat)
        guard let own = league.first(where: { $0.team.id == teamId }) else { return nil }
        let values = league.map(\.value)
        let higher = TeamStatCatalog.higherIsBetter(
            sportKey: TeamStatCatalog.sportKey(for: sport),
            section: section.lowercased(),
            stat: stat
        )
        return (TeamStatRanks.rank(of: own.value, among: values, higherIsBetter: higher),
                values.filter { $0 == own.value }.count > 1)
    }
}
