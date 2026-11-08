//
//  GameDetails.swift
//  SportsScores
//
//  Full game-detail model decoded from the ESPN summary + boxscore APIs.
//  Used by GameDetailView, BoxScoreView, PlaysView, NFLDrivesView, etc.
//

import Foundation

/// One element of an ESPN array, nil when it can't be read, so a bad row costs
/// that row rather than everything around it.
struct Lossy<Element: Decodable>: Decodable {
    let value: Element?

    init(from decoder: Decoder) throws {
        value = try? Element(from: decoder)
    }
}

extension KeyedDecodingContainer {
    /// The array under `key` without the elements that can't be read; nil when
    /// the key is absent or isn't an array.
    func lossyArray<Element: Decodable>(forKey key: Key) -> [Element]? {
        guard let rows = try? decodeIfPresent([Lossy<Element>].self, forKey: key) else { return nil }
        return rows.compactMap { $0.value }
    }

    /// An id ESPN may send as text or as a whole number: "11" either way; nil for anything else.
    func lenientString(forKey key: Key) -> String? {
        if let text = try? decodeIfPresent(String.self, forKey: key) { return text }
        if let number = try? decodeIfPresent(Int.self, forKey: key) { return String(number) }
        return nil
    }

    /// A number ESPN may send as an int, a float or text such as "64,195"; nil for
    /// anything else, so an odd value costs that value and not what's around it.
    func lenientNumber(forKey key: Key) -> Double? {
        if let number = try? decodeIfPresent(Double.self, forKey: key) {
            return number.isFinite ? number : nil
        }
        guard let text = try? decodeIfPresent(String.self, forKey: key),
              let number = Double(text.replacingOccurrences(of: ",", with: "")) else { return nil }
        return number.isFinite ? number : nil
    }
}

private extension String {
    /// Nil when there's nothing here but whitespace. ESPN sends empty strings as well as nulls.
    var nonBlank: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// ESPN's own way of saying it has nothing, as a value in an injury's details.
    var saysSomething: String? {
        guard let text = nonBlank, text.lowercased() != "not specified" else { return nil }
        return text
    }
}

struct GameDetails: Codable {
    let boxscore: Boxscore?
    let plays: [Play]?
    let leaders: [Leader]?
    /// NFL/NCAAF only — drive-by-drive breakdown.
    let drives: DrivesContainer?
    /// Officials, attendance and weather from the summary API.
    let gameInfo: GameInfo?
    /// Betting lines. Usually empty outside soccer, where `pickcenter` has them.
    let odds: [OddsEntry]?
    let pickcenter: [OddsEntry]?
    let injuries: [InjuryTeam]?
    /// Win probability timeline (MLB, per play).
    let winprobability: [WinProbEntry]?
    /// Season series breakdown (MLB — current series, regular season, preseason).
    let seasonseries: [SeasonSeriesEntry]?
    /// Game-specific news articles embedded in summary response.
    let news: GameNewsContainer?
    /// Live header from the summary endpoint — contains current scores and status.
    /// Used when the Game object was built from schedule data (which has stale/nil scores).
    let header: GameHeader?
    /// Live situation from the root of the summary endpoint — balls, strikes, outs,
    /// base occupancy, and pitcher/batter player IDs. Combine with `playerLookup`
    /// to resolve player IDs to short names.
    let situation: SummarySituation?
    /// Full rosters from the summary endpoint, used to resolve player IDs to names.
    let rosters: [GameRoster]?
    /// ESPN's own article on this game: a preview until it's played, then a recap.
    let article: GameNewsContainer.GameArticle?
    /// Football only: every score, in order.
    let scoringPlays: [ScoringPlay]?
    /// The division or conference tables the two teams are in.
    let standings: GameStandings?
    /// NHL, while the game is being played: who is on the ice, away team first.
    /// Read from `onIce`, the box score and the header together; empty otherwise.
    let onIceTeams: [OnIceTeam]

    /// Each section decodes on its own: ESPN's summary varies by sport, league
    /// and game state, and something unreadable in one section must never take
    /// the rest of the game's details down with it.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        boxscore = try? container.decodeIfPresent(Boxscore.self, forKey: .boxscore)
        plays = container.lossyArray(forKey: .plays)
        leaders = container.lossyArray(forKey: .leaders)
        drives = try? container.decodeIfPresent(DrivesContainer.self, forKey: .drives)
        gameInfo = try? container.decodeIfPresent(GameInfo.self, forKey: .gameInfo)
        odds = container.lossyArray(forKey: .odds)
        pickcenter = container.lossyArray(forKey: .pickcenter)
        injuries = container.lossyArray(forKey: .injuries)
        winprobability = container.lossyArray(forKey: .winprobability)
        seasonseries = container.lossyArray(forKey: .seasonseries)
        news = try? container.decodeIfPresent(GameNewsContainer.self, forKey: .news)
        header = try? container.decodeIfPresent(GameHeader.self, forKey: .header)
        situation = try? container.decodeIfPresent(SummarySituation.self, forKey: .situation)
        rosters = container.lossyArray(forKey: .rosters)
        article = try? container.decodeIfPresent(GameNewsContainer.GameArticle.self, forKey: .article)
        scoringPlays = container.lossyArray(forKey: .scoringPlays)
        standings = try? container.decodeIfPresent(GameStandings.self, forKey: .standings)
        onIceTeams = (try? OnIceLineup(from: decoder))?.teams ?? []
    }

    /// The betting line to show: the first with something in it, `odds` before
    /// `pickcenter`. game_labels.best_odds on Windows.
    var bettingLine: OddsEntry? {
        ((odds ?? []) + (pickcenter ?? [])).first { line in
            line.details?.nonBlank != nil || (line.overUnder ?? 0) != 0
        }
    }

    // MARK: - Game story

    /// The article to read in full, once the game's over. Windows offers its Game Wrap Up
    /// for the same games, whichever kind of article ESPN has by then, except that a game
    /// called off is "post" too and has only a preview: that stays in the news here.
    var gameStory: GameNewsContainer.GameArticle? {
        guard let competition = header?.competitions.first, !competition.hasNotBeenPlayed else { return nil }
        let state = competition.status?.type?.state?.lowercased()
        guard state == "post" || state == "final", article?.headline?.nonBlank != nil else { return nil }
        return article
    }

    /// The news list. Windows puts ESPN's article on this game first, so a preview
    /// goes here until the game has a story of its own. It's never listed twice.
    var relatedArticles: [GameNewsContainer.GameArticle] {
        let others = news?.articles ?? []
        guard let article, article.headline?.nonBlank != nil else { return others }
        let rest = others.filter { article.id == nil || $0.id != article.id }
        return gameStory == nil ? [article] + rest : rest
    }

    /// The scoring plays by period, in the order they happened. Rows with no words are left out.
    func scoringSummary(isFootball: Bool) -> [ScoringPeriod] {
        var periods: [ScoringPeriod] = []
        for play in scoringPlays ?? [] where play.text?.nonBlank != nil {
            let number = play.period?.number ?? 1
            if periods.last?.number == number {
                periods[periods.count - 1].plays.append(play)
            } else {
                let title = play.period?.displayName?.nonBlank
                    ?? ScoringPeriod.title(number: number, isFootball: isFootball)
                periods.append(ScoringPeriod(number: number, title: title, plays: [play]))
            }
        }
        return periods
    }

    struct ScoringPeriod {
        let number: Int
        let title: String
        var plays: [ScoringPlay]

        /// ESPN gives scoring plays only a period's number. Football reads the way it
        /// does on Windows, game_labels.football_period_label.
        static func title(number: Int, isFootball: Bool) -> String {
            guard isFootball else { return "Period \(number)" }
            if number <= 4 { return "Quarter \(number)" }
            return number == 5 ? "OT" : "\(number - 4)OT"
        }
    }

    // MARK: - Scoring plays

    struct ScoringPlay: Codable {
        let text: String?
        let period: Period?
        let clock: Clock?
        let team: Team?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            text = try? container.decodeIfPresent(String.self, forKey: .text)
            period = try? container.decodeIfPresent(Period.self, forKey: .period)
            clock = try? container.decodeIfPresent(Clock.self, forKey: .clock)
            team = try? container.decodeIfPresent(Team.self, forKey: .team)
        }

        struct Period: Codable {
            let number: Int?
            let displayName: String?
        }

        struct Clock: Codable {
            let displayValue: String?
        }

        struct Team: Codable {
            let displayName: String?
        }

        /// "Chicago Bears - 5:25", the line above the play as Windows has it.
        var teamAndClock: String {
            [team?.displayName?.nonBlank, clock?.displayValue?.nonBlank]
                .compactMap { $0 }
                .joined(separator: " - ")
        }

        /// What VoiceOver reads for the row.
        var spokenText: String {
            let lead = [team?.displayName?.nonBlank, clock?.displayValue?.nonBlank]
                .compactMap { $0 }
                .joined(separator: ", ")
            let body = text?.nonBlank ?? ""
            return lead.isEmpty ? body : "\(lead): \(body)"
        }
    }

    // MARK: - Standings in a game

    /// Root `standings`: `groups[].standings.entries[]`, where `team` is a plain name.
    /// The Windows side is game_labels.game_standings_tables.
    struct GameStandings: Codable {
        let groups: [Group]?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            groups = container.lossyArray(forKey: .groups)
        }

        struct Group: Codable {
            let header: String?
            let standings: Entries?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                header = try? container.decodeIfPresent(String.self, forKey: .header)
                standings = try? container.decodeIfPresent(Entries.self, forKey: .standings)
            }

            struct Entries: Codable {
                let entries: [Entry]?

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    entries = container.lossyArray(forKey: .entries)
                }
            }
        }

        struct Entry: Codable {
            let team: String?
            let stats: [Stat]?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                team = try? container.decodeIfPresent(String.self, forKey: .team)
                stats = container.lossyArray(forKey: .stats)
            }
        }

        struct Stat: Codable {
            let name: String?
            let shortDisplayName: String?
            let abbreviation: String?
            let displayValue: String?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                name = try? container.decodeIfPresent(String.self, forKey: .name)
                shortDisplayName = try? container.decodeIfPresent(String.self, forKey: .shortDisplayName)
                abbreviation = try? container.decodeIfPresent(String.self, forKey: .abbreviation)
                if let text = try? container.decodeIfPresent(String.self, forKey: .displayValue) {
                    displayValue = text
                } else if let number = container.lenientNumber(forKey: .displayValue) {
                    // A bare number, as Windows would show it.
                    displayValue = Int(exactly: number).map { String($0) } ?? String(number)
                } else {
                    displayValue = nil
                }
            }
        }

        /// One table, with the team in the first column of `headers` and of each row.
        struct Table {
            let title: String
            let headers: [String]
            let rows: [[String]]

            /// "L: 1, PA: 93", leaving out anything blank.
            func statsText(row: [String]) -> String {
                zip(headers.dropFirst(), row.dropFirst())
                    .filter { !$0.1.isEmpty }
                    .map { "\($0): \($1)" }
                    .joined(separator: ", ")
            }

            /// What VoiceOver reads for the row, as in a box score's Quick List.
            func spokenText(row: [String]) -> String {
                let stats = statsText(row: row)
                let team = row.first ?? ""
                return stats.isEmpty ? team : "\(team), \(stats)"
            }
        }

        /// One table per group that has any teams. A column is every stat any team has, in
        /// the order ESPN first gives them.
        var tables: [Table] {
            (groups ?? []).compactMap { group -> Table? in
                // A row with no team would read as numbers about nobody.
                let entries = (group.standings?.entries ?? []).filter { $0.team?.nonBlank != nil }
                guard !entries.isEmpty else { return nil }

                var keys: [String] = []
                var labels: [String: String] = [:]
                for entry in entries {
                    for stat in entry.stats ?? [] {
                        guard let key = stat.name?.nonBlank, labels[key] == nil else { continue }
                        keys.append(key)
                        labels[key] = stat.shortDisplayName?.nonBlank ?? stat.abbreviation?.nonBlank ?? key
                    }
                }

                let rows = entries.map { entry -> [String] in
                    var values: [String: String] = [:]
                    for stat in entry.stats ?? [] {
                        if let key = stat.name?.nonBlank { values[key] = stat.displayValue ?? "" }
                    }
                    return [entry.team ?? ""] + keys.map { values[$0] ?? "" }
                }

                return Table(title: group.header?.nonBlank ?? "Standings",
                             headers: ["Team"] + keys.map { labels[$0] ?? $0 },
                             rows: rows)
            }
        }
    }

    // MARK: - Player lookup (situation → names)

    /// Maps player ID → short name across both team rosters.
    var playerLookup: [Int: String] {
        var dict: [Int: String] = [:]
        for teamRoster in rosters ?? [] {
            for entry in teamRoster.roster ?? [] {
                if let idStr = entry.athlete?.id, let id = Int(idStr) {
                    dict[id] = entry.athlete?.shortName ?? entry.athlete?.displayName
                }
            }
        }
        return dict
    }

    // MARK: - Live Situation (from summary root)

    struct SummarySituation: Codable {
        let balls: Int?
        let strikes: Int?
        let outs: Int?
        /// Non-nil when a runner occupies this base; the object carries the player ID.
        struct SituationPlayer: Codable { let playerId: Int? }
        let onFirst: SituationPlayer?
        let onSecond: SituationPlayer?
        let onThird: SituationPlayer?
        let pitcher: SituationPlayer?
        let batter: SituationPlayer?

        /// Human-readable baseball situation line for VoiceOver.
        /// Pass `playerLookup` from `GameDetails.playerLookup` to resolve pitcher/batter names.
        func situationText(playerLookup: [Int: String]) -> String? {
            guard balls != nil || outs != nil else { return nil }
            var parts: [String] = []
            if let pid = pitcher?.playerId, let name = playerLookup[pid] {
                parts.append("P: \(name)")
            }
            if let pid = batter?.playerId, let name = playerLookup[pid] {
                parts.append("AB: \(name)")
            }
            let hasFirst  = onFirst  != nil
            let hasSecond = onSecond != nil
            let hasThird  = onThird  != nil
            if hasFirst || hasSecond || hasThird {
                var bases: [String] = []
                if hasFirst  { bases.append("1st") }
                if hasSecond { bases.append("2nd") }
                if hasThird  { bases.append("3rd") }
                parts.append(bases.joined(separator: " & "))
            } else {
                parts.append("Bases empty")
            }
            if let b = balls, let s = strikes { parts.append("\(b)-\(s)") }
            if let o = outs { parts.append("\(o) \(o == 1 ? "out" : "outs")") }
            return parts.isEmpty ? nil : parts.joined(separator: " · ")
        }
    }

    // MARK: - Rosters (for player name lookup)

    struct GameRoster: Codable {
        let homeAway: String?
        let roster: [RosterEntry]?

        struct RosterEntry: Codable {
            let athlete: RosterAthlete?

            struct RosterAthlete: Codable {
                let id: String?
                let shortName: String?
                let displayName: String?
            }
        }
    }

    // MARK: - Live Header (scores & status)

    struct GameHeader: Codable {
        let competitions: [HeaderCompetition]

        struct HeaderCompetition: Codable {
            let competitors: [HeaderCompetitor]
            /// Status of the competition — carries the current period/inning/clock.
            let status: HeaderStatus?
            /// National and local TV, which the summary's own list can leave out.
            let broadcasts: [HeaderBroadcast]?

            struct HeaderBroadcast: Codable {
                let media: Media?

                struct Media: Codable {
                    let shortName: String?
                }
            }

            /// TV names, each once.
            var broadcastNames: [String] {
                var seen = Set<String>()
                return (broadcasts ?? []).compactMap { $0.media?.shortName }
                    .filter { !$0.isEmpty && seen.insert($0).inserted }
            }

            /// True when this game hasn't been played and may never be: ESPN
            /// sends a postponed game as state "post" with a score of 0 to 0, a
            /// delayed one as "in" at period 0, and season averages in place of
            /// team statistics until it starts.
            var hasNotBeenPlayed: Bool {
                switch status?.type?.name {
                case "STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED": return true
                default:
                    return status?.type?.state == "pre"
                        || (status?.type?.state == "in" && status?.period == 0)
                }
            }

            struct HeaderStatus: Codable {
                let type: HeaderStatusType?
                let period: Int?

                struct HeaderStatusType: Codable {
                    /// Human-readable detail, e.g. "Top 9th", "Q3 5:42", "End of 2nd".
                    let detail: String?
                    /// Low-level state: "pre", "in", "post".
                    let state: String?
                    /// ESPN's status name, e.g. "STATUS_POSTPONED".
                    let name: String?
                }
            }

            struct HeaderCompetitor: Codable {
                let homeAway: String
                let team: HeaderTeam
                let score: Int?

                struct HeaderTeam: Codable {
                    let id: String?
                    let abbreviation: String?
                    /// "Mets": the short name win probability and the season series say.
                    var name: String? = nil
                    var shortDisplayName: String? = nil
                    var displayName: String? = nil
                }

                // ESPN summary returns score as a plain integer; handle int/double/string.
                enum CodingKeys: String, CodingKey { case homeAway, team, score }

                init(from decoder: Decoder) throws {
                    let c = try decoder.container(keyedBy: CodingKeys.self)
                    homeAway = try c.decode(String.self, forKey: .homeAway)
                    team = try c.decode(HeaderTeam.self, forKey: .team)
                    if let i = try? c.decode(Int.self, forKey: .score) {
                        score = i
                    } else if let d = try? c.decode(Double.self, forKey: .score) {
                        score = Int(d)
                    } else if let s = try? c.decode(String.self, forKey: .score),
                              let i = Int(s) {
                        score = i
                    } else {
                        score = nil
                    }
                }

                func encode(to encoder: Encoder) throws {
                    var c = encoder.container(keyedBy: CodingKeys.self)
                    try c.encode(homeAway, forKey: .homeAway)
                    try c.encode(team, forKey: .team)
                    try c.encodeIfPresent(score, forKey: .score)
                }
            }
        }
    }

    // MARK: - Win Probability

    /// One point on the line, after one play. Only the home team's chance is
    /// needed: an entry without it is dropped, as win_probability.py drops it.
    struct WinProbEntry: Codable {
        let homeWinPercentage: Double
        let tiePercentage: Double?
        let playId: String?

        enum CodingKeys: String, CodingKey { case homeWinPercentage, tiePercentage, playId }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            homeWinPercentage = try c.decode(Double.self, forKey: .homeWinPercentage)
            tiePercentage = try? c.decodeIfPresent(Double.self, forKey: .tiePercentage)
            playId = c.lenientString(forKey: .playId)
        }
    }

    // MARK: - Season Series

    /// One series between the two teams. ESPN's `summary` sentence is kept but not
    /// shown: it can be wrong, so SeasonSeries counts the record from `events`.
    struct SeasonSeriesEntry: Codable {
        let type: String?
        let title: String?
        let summary: String?
        let completed: Bool?
        let totalCompetitions: Int?
        let seriesScore: String?
        /// "World Series", on a playoff series.
        let round: String?
        /// The games in the series, oldest first.
        let events: [SeriesEvent]

        enum CodingKeys: String, CodingKey {
            case type, title, summary, completed, totalCompetitions, seriesScore, round, events
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            type = try? c.decodeIfPresent(String.self, forKey: .type)
            title = try? c.decodeIfPresent(String.self, forKey: .title)
            summary = try? c.decodeIfPresent(String.self, forKey: .summary)
            completed = try? c.decodeIfPresent(Bool.self, forKey: .completed)
            totalCompetitions = try? c.decodeIfPresent(Int.self, forKey: .totalCompetitions)
            seriesScore = try? c.decodeIfPresent(String.self, forKey: .seriesScore)
            round = try? c.decodeIfPresent(String.self, forKey: .round)
            events = c.lossyArray(forKey: .events) ?? []
        }

        struct SeriesEvent: Codable {
            let id: String?
            let status: String?
            let statusType: StatusType?
            let competitors: [Competitor]

            enum CodingKeys: String, CodingKey { case id, status, statusType, competitors }

            init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                id = c.lenientString(forKey: .id)
                status = try? c.decodeIfPresent(String.self, forKey: .status)
                statusType = try? c.decodeIfPresent(StatusType.self, forKey: .statusType)
                competitors = c.lossyArray(forKey: .competitors) ?? []
            }

            /// Only a finished game counts toward the record. `status` is read only
            /// without a `statusType`: a postponed game can say "post" too.
            var isFinished: Bool {
                if let statusType = statusType { return statusType.completed == true }
                return status?.trimmingCharacters(in: .whitespacesAndNewlines) == "post"
            }

            struct StatusType: Codable {
                let completed: Bool?
            }

            struct Competitor: Codable {
                let winner: Bool?
                let team: Team?

                struct Team: Codable {
                    let id: String?
                    let displayName: String?
                    let abbreviation: String?

                    enum CodingKeys: String, CodingKey { case id, displayName, abbreviation }

                    init(from decoder: Decoder) throws {
                        let c = try decoder.container(keyedBy: CodingKeys.self)
                        id = c.lenientString(forKey: .id)
                        displayName = try? c.decodeIfPresent(String.self, forKey: .displayName)
                        abbreviation = try? c.decodeIfPresent(String.self, forKey: .abbreviation)
                    }
                }
            }
        }

        /// Playoff, regular season, this set of games, spring training, then the rest.
        var displayOrder: Int {
            switch type {
            case "playoff":   return 0
            case "season":    return 1
            case "current":   return 2
            case "preseason": return 3
            default:          return 4
            }
        }
    }

    // MARK: - Game News

    struct GameNewsContainer: Codable {
        let articles: [GameArticle]?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            articles = container.lossyArray(forKey: .articles)
        }

        struct GameArticle: Codable, Identifiable {
            let id: Int?
            let headline: String?
            let description: String?
            let type: String?
            let links: ArticleLinks?
            /// The full text, in ESPN's markup. Only the root `article` has one.
            let story: String?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                id = try? container.decodeIfPresent(Int.self, forKey: .id)
                headline = try? container.decodeIfPresent(String.self, forKey: .headline)
                description = try? container.decodeIfPresent(String.self, forKey: .description)
                type = try? container.decodeIfPresent(String.self, forKey: .type)
                links = try? container.decodeIfPresent(ArticleLinks.self, forKey: .links)
                story = try? container.decodeIfPresent(String.self, forKey: .story)
            }

            struct ArticleLinks: Codable {
                let web: WebLink?
                struct WebLink: Codable {
                    let href: String?
                }
            }

            var webURL: URL? {
                links?.web?.href.flatMap { URL(string: $0) }
            }

            /// The story as headings and paragraphs, to read.
            var storyBlocks: [GameStoryBlock] { GameStoryBlock.blocks(from: story ?? "") }

            /// The description as plain words. AP's start with the dash that follows
            /// the dateline in the story, which is cut off here: "— Jeffery Simmons ran".
            var plainDescription: String? {
                guard let description else { return nil }
                let text = GameStoryBlock.plainText(description)
                    .replacingOccurrences(of: "^[—–\\-\\s]+", with: "", options: .regularExpression)
                return text.nonBlank
            }

            /// The description, if it adds anything to the story. ESPN's is nearly always the
            /// story's own opening, cut short, and that's not worth hearing twice.
            var descriptionNotInStory: String? {
                guard let description = plainDescription else { return nil }
                let blocks = storyBlocks
                guard !blocks.isEmpty else { return description }
                let storyText = blocks.map(\.text).joined(separator: " ")
                let opening = String(description.prefix(60))
                return storyText.contains(opening) ? nil : description
            }
        }
    }

    // ── Game-info sub-models ──────────────────────────────────────────────

    struct GameInfo: Codable {
        let officials: [Official]?
        let attendance: Int?
        let weather: Weather?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            officials = container.lossyArray(forKey: .officials)
            attendance = container.lenientNumber(forKey: .attendance).flatMap { Int(exactly: $0.rounded()) }
            weather = try? container.decodeIfPresent(Weather.self, forKey: .weather)
        }

        private static let groupedNumber: NumberFormatter = {
            let formatter = NumberFormatter()
            formatter.locale = Locale(identifier: "en_US")
            formatter.numberStyle = .decimal
            return formatter
        }()

        /// "Attendance: 68,739". ESPN sends 0 for a game with no count, and that's no row.
        var attendanceText: String? {
            guard let attendance, attendance > 0,
                  let shown = Self.groupedNumber.string(from: NSNumber(value: attendance)) else { return nil }
            return "Attendance: \(shown)"
        }

        /// "Weather: 67°F". Nil for a game with none, which is most: ESPN sends it
        /// for outdoor football before kickoff.
        var weatherText: String? {
            weather?.text.map { "Weather: \($0)" }
        }

        struct Official: Codable {
            let fullName: String?
            let position: OfficialPosition?

            struct OfficialPosition: Codable {
                let displayName: String?
            }
        }

        struct Weather: Codable {
            /// Windows reads this first, though ESPN's forecasts come without it.
            let displayValue: String?
            let temperature: Double?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                displayValue = try? container.decodeIfPresent(String.self, forKey: .displayValue)
                temperature = container.lenientNumber(forKey: .temperature)
            }

            /// 0 is a temperature, not a lack of one.
            private var temperatureText: String? {
                guard let temperature else { return nil }
                if let whole = Int(exactly: temperature) { return "\(whole)°F" }
                return "\(temperature)°F"
            }

            /// The words and the temperature, whichever ESPN has, and the temperature
            /// only once if the words already say it.
            var text: String? {
                guard let words = displayValue?.nonBlank else { return temperatureText }
                guard let temperatureText, !words.contains(temperatureText) else { return words }
                return "\(words), \(temperatureText)"
            }
        }
    }

    struct OddsEntry: Codable {
        let details: String?         // spread text e.g. "KC -6.5"
        let overUnder: Double?
        let provider: OddsProvider?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            details = try? container.decodeIfPresent(String.self, forKey: .details)
            overUnder = container.lenientNumber(forKey: .overUnder)
            provider = try? container.decodeIfPresent(OddsProvider.self, forKey: .provider)
        }

        struct OddsProvider: Codable {
            let name: String?
        }

        /// The line, when there's one to read. Nil rather than empty, as with the total.
        var spreadText: String? { details?.nonBlank }

        /// "39.5". A total of 0 is ESPN having none, not a line anyone would bet.
        var overUnderText: String? {
            guard let overUnder, overUnder != 0 else { return nil }
            return String(format: "%.1f", overUnder)
        }

        /// "Line: JAX -10", "O/U: 39.5": the row's text and the share sheet's.
        var shownParts: [String] {
            var parts: [String] = []
            if let spread = spreadText { parts.append("Line: \(spread)") }
            if let total = overUnderText { parts.append("O/U: \(total)") }
            return parts
        }

        /// What VoiceOver reads for the row.
        var spokenText: String {
            var parts: [String] = []
            if let spread = spreadText { parts.append("Line: \(spread)") }
            if let total = overUnderText { parts.append("Over/under: \(total)") }
            return parts.joined(separator: ". ")
        }
    }

    struct InjuryTeam: Codable {
        let team: InjuryTeamInfo?
        let injuries: [PlayerInjury]?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            team = try? container.decodeIfPresent(InjuryTeamInfo.self, forKey: .team)
            injuries = container.lossyArray(forKey: .injuries)
        }

        /// The injuries with something to say, so VoiceOver has no silent stops.
        var listedInjuries: [PlayerInjury] {
            (injuries ?? []).filter { !$0.spokenText.isEmpty }
        }

        struct InjuryTeamInfo: Codable {
            let displayName: String?
            let abbreviation: String?
        }

        struct PlayerInjury: Codable {
            let athlete: InjuryAthlete?
            let type: InjuryType?
            let status: String?
            /// Type, detail and return date. An odd one costs these and not the player.
            let details: InjuryDetails?

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                athlete = try? container.decodeIfPresent(InjuryAthlete.self, forKey: .athlete)
                type = try? container.decodeIfPresent(InjuryType.self, forKey: .type)
                status = try? container.decodeIfPresent(String.self, forKey: .status)
                details = try? container.decodeIfPresent(InjuryDetails.self, forKey: .details)
            }

            /// The columns Windows has after the status, each only when ESPN says
            /// something: "Type: Knee", "Details: Sprain", "Return Date: Nov 8, 2026".
            var detailLines: [String] {
                var lines: [String] = []
                if let type = details?.type?.saysSomething { lines.append("Type: \(type)") }
                if let detail = details?.detail?.saysSomething { lines.append("Details: \(detail)") }
                if let date = details?.returnDateText { lines.append("Return Date: \(date)") }
                return lines
            }

            /// What VoiceOver reads for the row.
            var spokenText: String {
                var parts: [String] = []
                if let name = athlete?.displayName?.nonBlank { parts.append(name) }
                if let position = athlete?.position?.abbreviation?.nonBlank { parts.append(position) }
                if let status = status?.nonBlank { parts.append("Status: \(status)") }
                return (parts + detailLines).joined(separator: ", ")
            }

            struct InjuryDetails: Codable {
                let type: String?
                let detail: String?
                /// A plain date, "2026-11-08".
                let returnDate: String?

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    type = try? container.decodeIfPresent(String.self, forKey: .type)
                    detail = try? container.decodeIfPresent(String.self, forKey: .detail)
                    returnDate = try? container.decodeIfPresent(String.self, forKey: .returnDate)
                }

                private static func formatter(_ format: String) -> DateFormatter {
                    let formatter = DateFormatter()
                    formatter.locale = Locale(identifier: "en_US_POSIX")
                    formatter.timeZone = TimeZone(identifier: "UTC")
                    formatter.dateFormat = format
                    return formatter
                }

                private static let espnDate = formatter("yyyy-MM-dd")
                private static let spokenDate = formatter("MMM d, yyyy")

                /// "Nov 8, 2026", since VoiceOver reads "2026-11-08" a digit group at a time.
                /// Anything that isn't a plain date is shown as ESPN sent it.
                var returnDateText: String? {
                    guard let returnDate = returnDate?.nonBlank else { return nil }
                    guard let date = Self.espnDate.date(from: returnDate) else { return returnDate }
                    return Self.spokenDate.string(from: date)
                }
            }

            struct InjuryAthlete: Codable {
                let displayName: String?
                let position: AthletePosition?

                struct AthletePosition: Codable {
                    let abbreviation: String?
                }
            }

            struct InjuryType: Codable {
                let description: String?
            }
        }
    }

    // ── Drives container (NFL / NCAAF) ────────────────────────────────────

    struct DrivesContainer: Codable {
        let current: Drive?
        let previous: [Drive]?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            current = try? container.decodeIfPresent(Drive.self, forKey: .current)
            previous = container.lossyArray(forKey: .previous)
        }

        /// All drives in chronological order, each once. During a live game
        /// `previous` already holds the drive in progress, so `current` only adds
        /// to the list when it isn't there.
        var all: [Drive] {
            var seen = Set<String>()
            return ((previous ?? []) + (current.map { [$0] } ?? [])).filter {
                seen.insert($0.id).inserted
            }
        }
    }

    struct Drive: Codable, Identifiable {
        let id: String
        let description: String?
        let yards: Int?
        let offensivePlays: Int?
        /// Short abbreviation ("FG", "PUNT", "TD"). Use `displayResult` for the
        /// human-readable version that drives the emoji mapping.
        let result: String?
        /// Human-readable result e.g. "Field Goal", "Punt", "Touchdown".
        let displayResult: String?
        let isScore: Bool?
        let team: DriveTeam?
        let start: DrivePosition?
        let end: DrivePosition?
        let plays: [DrivePlay]?

        /// Drive result mapped to an emoji. Uses `displayResult` (e.g. "Field Goal")
        /// because `result` contains abbreviations ("FG") which don't match a simple switch.
        var resultEmoji: String {
            switch displayResult?.lowercased() {
            case "touchdown":                               return "🏈"
            case "field goal":                             return "🥅"
            case "punt":                                   return "⚡"
            case "fumble", "interception",
                 "turnover on downs":                      return "🔄"
            case "missed field goal", "missed fg":        return "❌"
            case "end of half", "end of game",
                 "end of quarter":                         return "🕒"
            default:
                // Fallback: use the short abbreviation
                switch result?.uppercased() {
                case "TD":   return "🏈"
                case "FG":   return "🥅"
                case "PUNT": return "⚡"
                default:     return "•"
                }
            }
        }

        /// ESPN period number for the drive start (1-4, plus 5+ for OT).
        var quarterNumber: Int { start?.period?.number ?? 1 }

        struct DriveTeam: Codable {
            let id: String?
            let abbreviation: String?
            let displayName: String?
        }

        struct DrivePosition: Codable {
            let period: DrivePeriod?
            let yardLine: Int?
            let text: String?

            struct DrivePeriod: Codable {
                let number: Int?
            }
        }

        struct DrivePlay: Codable, Identifiable {
            let id: String
            let text: String?
            let statYardage: Int?
            let type: PlayType?
            let clock: PlayClock?
            let period: DrivePeriod?
            /// The score after the play, which says who scored on the drive (DriveResults).
            let awayScore: Int?
            let homeScore: Int?
            /// ESPN's mark on a play that scored.
            let scoringPlay: Bool?

            enum CodingKeys: String, CodingKey {
                case id, text, statYardage, type, clock, period, awayScore, homeScore, scoringPlay
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                id = try container.decode(String.self, forKey: .id)
                text = try? container.decodeIfPresent(String.self, forKey: .text)
                statYardage = try? container.decodeIfPresent(Int.self, forKey: .statYardage)
                type = try? container.decodeIfPresent(PlayType.self, forKey: .type)
                clock = try? container.decodeIfPresent(PlayClock.self, forKey: .clock)
                period = try? container.decodeIfPresent(DrivePeriod.self, forKey: .period)
                // An odd score costs the score, not the play.
                awayScore = container.lenientNumber(forKey: .awayScore).map { Int($0) }
                homeScore = container.lenientNumber(forKey: .homeScore).map { Int($0) }
                scoringPlay = try? container.decodeIfPresent(Bool.self, forKey: .scoringPlay)
            }

            struct PlayType: Codable {
                let text: String?
                let type: String?
            }

            struct PlayClock: Codable {
                let displayValue: String?
            }

            struct DrivePeriod: Codable {
                let number: Int?
            }
        }
    }
    
    struct Boxscore: Codable {
        let teams: [TeamStats]
        let players: [TeamPlayers]?

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            teams = container.lossyArray(forKey: .teams) ?? []
            players = container.lossyArray(forKey: .players)
        }

        /// A team as ESPN's box score names it. Falls back rather than fails, so
        /// one odd team block can't cost the box score.
        struct TeamInfo: Codable {
            let displayName: String
            let abbreviation: String

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                let name = try? container.decodeIfPresent(String.self, forKey: .displayName)
                let abbreviation = try? container.decodeIfPresent(String.self, forKey: .abbreviation)
                displayName = name ?? abbreviation ?? "Team"
                self.abbreviation = abbreviation ?? name ?? "Team"
            }
        }

        struct TeamStats: Codable {
            let team: TeamInfo
            // ESPN returns statistics in two different shapes depending on sport:
            //   MLB  → [{name, displayName, stats:[{name,displayName,...}]}]  (nested categories)
            //   NFL/NBA/NHL → [{name, label, abbreviation?, displayValue}]     (flat rows)
            let statistics: [StatEntry]

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                team = try container.decode(TeamInfo.self, forKey: .team)
                statistics = container.lossyArray(forKey: .statistics) ?? []
            }

            /// One element of the statistics array.
            /// Use `isNested` to distinguish MLB category format from NFL/NBA/NHL flat format.
            struct StatEntry: Codable {
                // Present in every format
                let name: String
                // MLB nested: category label (e.g. "Batting")
                let displayName: String?
                // NFL/NBA/NHL flat: row label (e.g. "1st Downs")
                let label: String?
                // NHL flat rows include an abbreviation
                let abbreviation: String?
                // Flat formats carry the displayValue directly
                let displayValue: String?
                // MLB only: nested stat rows under this category
                let stats: [StatItem]?

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    name = try container.decode(String.self, forKey: .name)
                    displayName = try? container.decodeIfPresent(String.self, forKey: .displayName)
                    label = try? container.decodeIfPresent(String.self, forKey: .label)
                    abbreviation = try? container.decodeIfPresent(String.self, forKey: .abbreviation)
                    displayValue = try? container.decodeIfPresent(String.self, forKey: .displayValue)
                    stats = container.lossyArray(forKey: .stats)
                }

                /// Human-readable title for this entry (works for all formats).
                var groupTitle: String { displayName ?? label ?? name }

                /// True when this entry is an MLB-style category wrapping nested stats.
                var isNested: Bool { stats != nil }

                struct StatItem: Codable {
                    let name: String
                    let displayName: String
                    let shortDisplayName: String?
                    let description: String?
                    let abbreviation: String?
                    let displayValue: String
                }
            }
        }

        struct TeamPlayers: Codable {
            let team: TeamInfo
            let statistics: [PlayerStatGroup]

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                team = try container.decode(TeamInfo.self, forKey: .team)
                statistics = container.lossyArray(forKey: .statistics) ?? []
            }

            struct PlayerStatGroup: Codable {
                /// ESPN uses "type" for MLB, "name" for football and hockey, and
                /// neither for basketball, whose one group holds everybody.
                let type: String?
                let name: String?
                let names: [String]?
                let labels: [String]?
                let keys: [String]?
                /// The team's line for this group. Empty strings for columns that
                /// don't add up, such as minutes; absent in hockey.
                let totals: [String]?
                let athletes: [AthleteStats]

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    type = try? container.decodeIfPresent(String.self, forKey: .type)
                    name = try? container.decodeIfPresent(String.self, forKey: .name)
                    names = try? container.decodeIfPresent([String].self, forKey: .names)
                    labels = try? container.decodeIfPresent([String].self, forKey: .labels)
                    keys = try? container.decodeIfPresent([String].self, forKey: .keys)
                    totals = try? container.decodeIfPresent([String].self, forKey: .totals)
                    athletes = container.lossyArray(forKey: .athletes) ?? []
                }

                /// Column headers for player stats. MLB and basketball use 'names',
                /// football and hockey only 'labels'.
                var columnHeaders: [String] {
                    if let names, !names.isEmpty { return names }
                    return labels ?? []
                }

                struct AthleteStats: Codable {
                    let athlete: AthleteInfo
                    let stats: [String]
                    let active: Bool?
                    let didNotPlay: Bool?

                    init(from decoder: Decoder) throws {
                        let container = try decoder.container(keyedBy: CodingKeys.self)
                        athlete = (try? container.decode(AthleteInfo.self, forKey: .athlete))
                            ?? AthleteInfo(displayName: AthleteInfo.unknownName, position: nil, headshot: nil)
                        stats = (try? container.decodeIfPresent([String].self, forKey: .stats)) ?? []
                        active = try? container.decodeIfPresent(Bool.self, forKey: .active)
                        didNotPlay = try? container.decodeIfPresent(Bool.self, forKey: .didNotPlay)
                    }

                    var isActive: Bool { active ?? true }

                    struct AthleteInfo: Codable {
                        /// Always something to read. Some players who sat out carry
                        /// only `shortName`, and college football has a "Team" row
                        /// spelled " Team".
                        let displayName: String
                        let position: Position?
                        let headshot: Headshot?

                        static let unknownName = "Unknown player"

                        private enum CodingKeys: String, CodingKey {
                            case displayName, shortName, position, headshot
                        }

                        init(displayName: String, position: Position?, headshot: Headshot?) {
                            self.displayName = displayName
                            self.position = position
                            self.headshot = headshot
                        }

                        init(from decoder: Decoder) throws {
                            let container = try decoder.container(keyedBy: CodingKeys.self)
                            let names = [CodingKeys.displayName, .shortName].compactMap {
                                (try? container.decodeIfPresent(String.self, forKey: $0))?
                                    .trimmingCharacters(in: .whitespacesAndNewlines)
                            }
                            displayName = names.first { !$0.isEmpty } ?? Self.unknownName
                            position = try? container.decodeIfPresent(Position.self, forKey: .position)
                            headshot = try? container.decodeIfPresent(Headshot.self, forKey: .headshot)
                        }

                        func encode(to encoder: Encoder) throws {
                            var container = encoder.container(keyedBy: CodingKeys.self)
                            try container.encode(displayName, forKey: .displayName)
                            try container.encodeIfPresent(position, forKey: .position)
                            try container.encodeIfPresent(headshot, forKey: .headshot)
                        }

                        struct Position: Codable {
                            let name: String?
                            let abbreviation: String?
                        }

                        struct Headshot: Codable {
                            let href: String?
                            let alt: String?
                        }
                    }
                }
            }
        }
    }

    struct Play: Codable {
        let id: String
        // text is absent on some play types (e.g. inning-start markers in MLB)
        let text: String?
        let type: PlayType
        let scoreValue: Int?
        // ESPN uses "period" (with a displayValue) rather than a "clock" key for most sports
        let period: Period?
        // Cumulative score after this play (present in NBA/NCAAB, absent in MLB/NFL/NHL)
        let awayScore: Int?
        let homeScore: Int?
        // Game-clock time remaining at time of play (NBA, NFL)
        let clock: PlayClock?
        /// MLB play classification: I=inning-header, A=at-bat-header, P=pitch, N=result-note
        let summaryType: String?
        /// ESPN's own flag. `scoreValue` isn't enough: college basketball sets it
        /// on misses too.
        let scoringPlay: Bool?
        // Default init values let callers (e.g. previews) omit optional fields
        init(id: String, text: String?, type: PlayType, scoreValue: Int?,
             period: Period?, awayScore: Int? = nil, homeScore: Int? = nil,
             clock: PlayClock? = nil, summaryType: String? = nil,
             pitchCoordinate: PitchCoordinate? = nil,
             pitchType: PitchTypeInfo? = nil, pitchVelocity: Int? = nil,
             bats: BatterHand? = nil, atBatId: String? = nil,
             atBatPitchNumber: Int? = nil, resultCount: PitchCount? = nil,
             outs: Int? = nil, coordinate: PlayCoordinate? = nil, scoringPlay: Bool? = nil) {
            self.coordinate = coordinate
            self.scoringPlay = scoringPlay
            self.id = id; self.text = text; self.type = type
            self.scoreValue = scoreValue; self.period = period
            self.awayScore = awayScore; self.homeScore = homeScore
            self.clock = clock; self.summaryType = summaryType
            self.pitchCoordinate = pitchCoordinate; self.pitchType = pitchType
            self.pitchVelocity = pitchVelocity; self.bats = bats
            self.atBatId = atBatId; self.atBatPitchNumber = atBatPitchNumber
            self.resultCount = resultCount; self.outs = outs
        }
        
        // ── Pitch-specific fields (MLB / baseball only) ──────────────────────
        /// Pixel coordinates in ESPN's 256×256 strike-zone space.
        let pitchCoordinate: PitchCoordinate?
        /// Pitch classification (Four-seam FB, Curveball, etc.).
        let pitchType: PitchTypeInfo?
        /// Pitch speed in mph.
        let pitchVelocity: Int?
        /// Batter handedness ("L" / "R").
        let bats: BatterHand?
        /// The at-bat this pitch belongs to.
        let atBatId: String?
        /// Pitch number within the at-bat.
        let atBatPitchNumber: Int?
        /// Balls/strikes count *after* this pitch.
        let resultCount: PitchCount?
        /// Outs at time of pitch.
        let outs: Int?

        // ── Court / rink location (basketball and hockey) ────────────────────
        /// Where on the court or ice the play happened, when ESPN says.
        let coordinate: PlayCoordinate?

        var isPitch: Bool { pitchCoordinate != nil }

        var isScoring: Bool { scoringPlay ?? ((scoreValue ?? 0) > 0) }

        /// The score after this play. Nil in a shootout, where ESPN repeats the
        /// tied score plus one on every attempt rather than anything meaningful.
        var runningScore: (away: Int, home: Int)? {
            guard period?.displayValue != "SO", let awayScore, let homeScore else { return nil }
            return (awayScore, homeScore)
        }

        /// True when this play has a location worth sonifying in `sport`.
        func hasPlayLocation(for sport: Sport) -> Bool {
            guard let coordinate else { return false }
            return PlayAudioGeometry.hasLocation(coordinate, for: sport)
        }
        
        struct PlayType: Codable {
            let text: String
            /// ESPN play-type slug: "ball", "called-strike", "foul", "in-play-out", etc.
            let type: String?
        }
        
        struct Period: Codable {
            let displayValue: String
            /// "Top" or "Bottom" (MLB half-inning), quarter/period name for other sports
            let type: String?
            /// Inning or period number
            let number: Int?
        }
        
        struct PlayClock: Codable {
            let displayValue: String
        }
        
        struct PitchCoordinate: Codable {
            let x: Int
            let y: Int
        }

        /// Court or rink location, in the sport's own units. ESPN puts this on
        /// basketball and hockey plays under `coordinate`; baseball uses
        /// `pitchCoordinate` above, and football has no spatial coordinates at
        /// all. See `PlayAudioGeometry` for what the numbers mean.
        struct PlayCoordinate: Codable {
            let x: Double
            let y: Double

            /// ESPN sends a scaled int32 minimum rather than null for a play
            /// with no location — a substitution, a timeout, a free throw, most
            /// face-offs — so this has to be checked by magnitude.
            var isUsable: Bool {
                abs(x) < 1_000_000 && abs(y) < 1_000_000
            }

            /// Decoded leniently: one play with `{}` or a null x must not throw
            /// and take the whole game's details down with it. A missing or
            /// unreadable value decodes as the no-location sentinel instead.
            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                x = (try? container.decodeIfPresent(Double.self, forKey: .x)) ?? Self.noLocation
                y = (try? container.decodeIfPresent(Double.self, forKey: .y)) ?? Self.noLocation
            }

            init(x: Double, y: Double) {
                self.x = x
                self.y = y
            }

            private static let noLocation = -214_748_340.0
            private enum CodingKeys: String, CodingKey { case x, y }
        }
        
        struct PitchTypeInfo: Codable {
            let text: String
            let abbreviation: String
        }
        
        struct BatterHand: Codable {
            let abbreviation: String  // "L" or "R"
        }
        
        struct PitchCount: Codable {
            let balls: Int
            let strikes: Int
        }
        
        // ── Derived helpers ──────────────────────────────────────────────────
        
        /// Single-character result label for display (B / K / F / O / H / R / •)
        var pitchResultLabel: String {
            switch type.type {
            case "ball":           return "B"
            case "called-strike":  return "K"
            case "swinging-strike": return "K"
            case "foul":           return "F"
            case "in-play-out":    return "O"
            case "in-play-score":  return "R"
            case "in-play-no-out": return "H"
            default:               return "•"
            }
        }
        
        /// Color name for the pitch result dot.
        var pitchResultColorName: String {
            switch type.type {
            case "ball":                       return "blue"
            case "called-strike", "swinging-strike": return "red"
            case "foul":                       return "orange"
            case "in-play-out":                return "gray"
            case "in-play-score":              return "green"
            case "in-play-no-out":             return "green"
            default:                           return "secondary"
            }
        }
        
        /// Human-readable zone description matching the Python app's logic.
        func locationDescription(batterHand: String?) -> String {
            guard let coord = pitchCoordinate else { return "Unknown" }
            let xNorm = Double(coord.x) / 255.0
            let isLeft = (batterHand ?? bats?.abbreviation) == "L"
            
            let horizontal: String
            if isLeft {
                horizontal = xNorm < 0.2 ? "way outside" : xNorm < 0.4 ? "outside" :
                             xNorm < 0.6 ? "over plate"  : xNorm < 0.8 ? "inside"  : "way inside"
            } else {
                horizontal = xNorm < 0.2 ? "way inside" : xNorm < 0.4 ? "inside" :
                             xNorm < 0.6 ? "over plate"  : xNorm < 0.8 ? "outside" : "way outside"
            }
            let yNorm = Double(coord.y) / 255.0
            let vertical = yNorm < 0.33 ? "high" : yNorm < 0.66 ? "middle" : "low"
            return "\(vertical) \(horizontal)"
        }
    }
    
    struct Leader: Codable {
        // NBA wraps categories under a {team, leaders} envelope;
        // MLB/NFL/NHL put {name, displayName} at the top level.
        // Make everything optional so a mismatch in one sport doesn't
        // blow up decoding for another.
        let name: String?
        let displayName: String?
        let leaders: [PlayerLeader]?

        // NBA adds a team reference; ignore it for display purposes.
        // let team: …  (not decoded)

        struct PlayerLeader: Codable {
            // For MLF/NFL/NHL: flat player entry
            let displayValue: String?
            let athlete: Athlete?
            // For NBA: this struct doubles as a category container with its own leaders
            let name: String?
            let displayName: String?
            let leaders: [PlayerLeader]?

            struct Athlete: Codable {
                let displayName: String
            }
        }
    }
}

/// One piece of a game story: ESPN's `<hl2>` headings and everything between them.
enum GameStoryBlock: Equatable {
    case heading(String)
    case paragraph(String)

    var text: String {
        switch self {
        case .heading(let text), .paragraph(let text): return text
        }
    }

    /// Story markup as headings and paragraphs of plain words, Windows's
    /// _format_article_story for a screen rather than a browser. Links keep their words,
    /// photos and the like go, and AP's closing "------" is dropped, alone on its line or not.
    /// ESPN's AP stories have the dateline run into a stray dash, "SEATTLE -- — Jeffery",
    /// which would be read out.
    static func blocks(from story: String) -> [GameStoryBlock] {
        let headingMark = "\u{E000}"
        let blockBreak = "\u{E001}"
        var text = story.replacingOccurrences(of: "(?is)<hl2\\b[^>]*>(.*?)</hl2>",
                                              with: "\(blockBreak)\(headingMark)$1\(blockBreak)",
                                              options: .regularExpression)
        text = text.replacingOccurrences(of: "(?i)</?(p|br)\\b[^>]*>", with: blockBreak, options: .regularExpression)
        text = text.replacingOccurrences(of: "\\n\\s*\\n", with: blockBreak, options: .regularExpression)

        var blocks: [GameStoryBlock] = []
        for piece in text.components(separatedBy: blockBreak) {
            let isHeading = piece.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix(headingMark)
            let words = plainText(piece.replacingOccurrences(of: headingMark, with: ""))
                .replacingOccurrences(of: "-- —", with: "--")
                .replacingOccurrences(of: "\\s*-{3,}$", with: "", options: .regularExpression)
            guard words.rangeOfCharacter(from: .alphanumerics) != nil else { continue }
            blocks.append(isHeading ? .heading(words) : .paragraph(words))
        }
        return blocks
    }

    /// Markup and entities out, and whitespace down to single spaces.
    static func plainText(_ markup: String) -> String {
        var text = markup.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
        // Ampersand last, so "&amp;lt;" comes out as "&lt;" rather than "<".
        for (entity, character) in [("&nbsp;", " "), ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
                                    ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")] {
            text = text.replacingOccurrences(of: entity, with: character)
        }
        return text.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
