//
//  GameDetails.swift
//  SportsScores
//
//  Full game-detail model decoded from the ESPN summary + boxscore APIs.
//  Used by GameDetailView, BoxScoreView, PlaysView, NFLDrivesView, etc.
//

import Foundation

struct GameDetails: Codable {
    let boxscore: Boxscore?
    let plays: [Play]?
    let leaders: [Leader]?
    /// NFL/NCAAF only — drive-by-drive breakdown.
    let drives: DrivesContainer?
    /// Venue, officials, odds, injuries from the summary API.
    let gameInfo: GameInfo?
    let odds: [OddsEntry]?
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

            struct HeaderStatus: Codable {
                let type: HeaderStatusType?

                struct HeaderStatusType: Codable {
                    /// Human-readable detail, e.g. "Top 9th", "Q3 5:42", "End of 2nd".
                    let detail: String?
                    /// Low-level state: "pre", "in", "post".
                    let state: String?
                }
            }

            struct HeaderCompetitor: Codable {
                let homeAway: String
                let team: HeaderTeam
                let score: Int?

                struct HeaderTeam: Codable {
                    let id: String?
                    let abbreviation: String?
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

    struct WinProbEntry: Codable {
        let homeWinPercentage: Double
        let tiePercentage: Double
        let playId: String
    }

    // MARK: - Season Series

    struct SeasonSeriesEntry: Codable {
        let type: String?
        let title: String?
        let summary: String?
        let completed: Bool?
        let totalCompetitions: Int?
        let seriesScore: String?

        // Prefer "Regular Season Series" and "Current Series" for display
        var displayOrder: Int {
            switch type {
            case "current":  return 0
            case "season":   return 1
            case "preseason": return 2
            default:         return 3
            }
        }
    }

    // MARK: - Game News

    struct GameNewsContainer: Codable {
        let articles: [GameArticle]?

        struct GameArticle: Codable, Identifiable {
            let id: Int?
            let headline: String?
            let description: String?
            let type: String?
            let links: ArticleLinks?

            struct ArticleLinks: Codable {
                let web: WebLink?
                struct WebLink: Codable {
                    let href: String?
                }
            }

            var webURL: URL? {
                links?.web?.href.flatMap { URL(string: $0) }
            }
        }
    }

    // ── Game-info sub-models ──────────────────────────────────────────────

    struct GameInfo: Codable {
        let officials: [Official]?

        struct Official: Codable {
            let fullName: String?
            let position: OfficialPosition?

            struct OfficialPosition: Codable {
                let displayName: String?
            }
        }
    }

    struct OddsEntry: Codable {
        let details: String?         // spread text e.g. "KC -6.5"
        let overUnder: Double?
        let provider: OddsProvider?

        struct OddsProvider: Codable {
            let name: String?
        }
    }

    struct InjuryTeam: Codable {
        let team: InjuryTeamInfo?
        let injuries: [PlayerInjury]?

        struct InjuryTeamInfo: Codable {
            let displayName: String?
            let abbreviation: String?
        }

        struct PlayerInjury: Codable {
            let athlete: InjuryAthlete?
            let type: InjuryType?
            let status: String?

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

        /// All drives in chronological order (current drive appended at end if present).
        var all: [Drive] {
            var list = previous ?? []
            if let cur = current { list.append(cur) }
            return list
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
        
        struct TeamStats: Codable {
            let team: TeamInfo
            // ESPN returns statistics in two different shapes depending on sport:
            //   MLB  → [{name, displayName, stats:[{name,displayName,...}]}]  (nested categories)
            //   NFL/NBA/NHL → [{name, label, abbreviation?, displayValue}]     (flat rows)
            let statistics: [StatEntry]
            
            struct TeamInfo: Codable {
                let displayName: String
                let abbreviation: String
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
            
            struct TeamInfo: Codable {
                let displayName: String
                let abbreviation: String
            }
            
            struct PlayerStatGroup: Codable {
                /// ESPN uses "type" for MLB/NFL/NBA, "name" for NHL/NCAAH.
                /// Both serve as the group identifier (e.g. "forwards", "goalies", "passing").
                let type: String?
                let name: String?
                let names: [String]?
                let labels: [String]?
                let keys: [String]?
                let athletes: [AthleteStats]
                
                var groupTitle: String { (type ?? name ?? "unknown").capitalized }
                
                /// Column headers for player stats. MLB uses 'names', NFL/NBA/NHL use 'labels'.
                var columnHeaders: [String] { names ?? labels ?? [] }
                
                struct AthleteStats: Codable {
                    let athlete: AthleteInfo
                    let stats: [String]
                    let active: Bool?
                    
                    var isActive: Bool { active ?? true }
                    
                    struct AthleteInfo: Codable {
                        let displayName: String
                        let position: Position?
                        let headshot: Headshot?
                        
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
        // Default init values let callers (e.g. previews) omit optional fields
        init(id: String, text: String?, type: PlayType, scoreValue: Int?,
             period: Period?, awayScore: Int? = nil, homeScore: Int? = nil,
             clock: PlayClock? = nil, summaryType: String? = nil,
             pitchCoordinate: PitchCoordinate? = nil,
             pitchType: PitchTypeInfo? = nil, pitchVelocity: Int? = nil,
             bats: BatterHand? = nil, atBatId: String? = nil,
             atBatPitchNumber: Int? = nil, resultCount: PitchCount? = nil,
             outs: Int? = nil, coordinate: PlayCoordinate? = nil) {
            self.coordinate = coordinate
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

        /// True when this play has a location worth sonifying.
        var hasPlayLocation: Bool { coordinate?.isUsable == true }
        
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
