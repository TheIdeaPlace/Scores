//
//  DivisionMapper.swift
//  SportsScores
//
//  Created on 2/26/26.
//
//  Maps team abbreviations to division names and provides ordered division
//  lists for standings view. Mirrors the Python app's _get_team_division() logic.

import Foundation

enum DivisionMapper {

    // MARK: - MLB

    static let mlb: [String: String] = [
        // American League East
        "BAL": "AL East", "BOS": "AL East", "NYY": "AL East", "TB": "AL East", "TOR": "AL East",
        // American League Central
        "CHW": "AL Central", "CWS": "AL Central",
        "CLE": "AL Central", "DET": "AL Central", "KC": "AL Central", "MIN": "AL Central",
        // American League West
        "HOU": "AL West", "LAA": "AL West",
        "OAK": "AL West", "ATH": "AL West",   // Oakland / Athletics
        "SEA": "AL West", "TEX": "AL West",
        // National League East
        "ATL": "NL East", "MIA": "NL East", "NYM": "NL East", "PHI": "NL East", "WSH": "NL East",
        // National League Central
        "CHC": "NL Central", "CIN": "NL Central",
        "MIL": "NL Central", "PIT": "NL Central", "STL": "NL Central",
        // National League West
        "ARI": "NL West", "COL": "NL West", "LAD": "NL West", "SD": "NL West", "SF": "NL West"
    ]

    static let mlbOrder = ["AL East", "AL Central", "AL West",
                            "NL East", "NL Central", "NL West"]

    // MARK: - NFL

    static let nfl: [String: String] = [
        // AFC East
        "BUF": "AFC East", "MIA": "AFC East", "NE": "AFC East", "NYJ": "AFC East",
        // AFC North
        "BAL": "AFC North", "CIN": "AFC North", "CLE": "AFC North", "PIT": "AFC North",
        // AFC South
        "HOU": "AFC South", "IND": "AFC South", "JAX": "AFC South", "TEN": "AFC South",
        // AFC West
        "DEN": "AFC West", "KC": "AFC West", "LV": "AFC West", "LAC": "AFC West",
        // NFC East
        "DAL": "NFC East", "NYG": "NFC East", "PHI": "NFC East", "WSH": "NFC East",
        // NFC North
        "CHI": "NFC North", "DET": "NFC North", "GB": "NFC North", "MIN": "NFC North",
        // NFC South
        "ATL": "NFC South", "CAR": "NFC South", "NO": "NFC South", "TB": "NFC South",
        // NFC West
        "ARI": "NFC West", "LAR": "NFC West", "SF": "NFC West", "SEA": "NFC West"
    ]

    static let nflOrder = ["AFC East", "AFC North", "AFC South", "AFC West",
                            "NFC East", "NFC North", "NFC South", "NFC West"]

    // MARK: - NBA

    static let nba: [String: String] = [
        // Atlantic
        "BOS": "Atlantic", "BKN": "Atlantic", "NY": "Atlantic", "NYK": "Atlantic",
        "PHI": "Atlantic", "TOR": "Atlantic",
        // Central
        "CHI": "Central", "CLE": "Central", "DET": "Central", "IND": "Central", "MIL": "Central",
        // Southeast
        "ATL": "Southeast", "CHA": "Southeast", "MIA": "Southeast", "ORL": "Southeast", "WSH": "Southeast",
        // Northwest
        "DEN": "Northwest", "MIN": "Northwest", "OKC": "Northwest",
        "POR": "Northwest", "UTA": "Northwest", "UTAH": "Northwest",
        // Pacific
        "GS": "Pacific", "GSW": "Pacific",
        "LAC": "Pacific", "LAL": "Pacific", "PHX": "Pacific", "SAC": "Pacific",
        // Southwest
        "DAL": "Southwest", "HOU": "Southwest", "MEM": "Southwest", "NO": "Southwest", "SA": "Southwest"
    ]

    static let nbaOrder = ["Atlantic", "Central", "Southeast",
                            "Northwest", "Pacific", "Southwest"]

    // MARK: - NHL

    static let nhl: [String: String] = [
        // Atlantic
        "BOS": "Atlantic", "BUF": "Atlantic", "DET": "Atlantic", "FLA": "Atlantic",
        "MTL": "Atlantic", "OTT": "Atlantic", "TB": "Atlantic", "TOR": "Atlantic",
        // Metropolitan
        "CAR": "Metropolitan", "CBJ": "Metropolitan",
        "NJ": "Metropolitan", "NYI": "Metropolitan",
        "NYR": "Metropolitan", "PHI": "Metropolitan", "PIT": "Metropolitan", "WSH": "Metropolitan",
        // Central
        "CHI": "Central", "COL": "Central", "DAL": "Central", "UTA": "Central", "UTAH": "Central",
        "MIN": "Central", "NSH": "Central", "STL": "Central", "WPG": "Central",
        // Pacific
        "ANA": "Pacific", "CGY": "Pacific", "EDM": "Pacific", "LA": "Pacific",
        "SJ": "Pacific", "SEA": "Pacific", "VAN": "Pacific", "VGK": "Pacific"
    ]

    static let nhlOrder = ["Atlantic", "Metropolitan", "Central", "Pacific"]

    // MARK: - Public API

    /// Returns the division name for a team abbreviation within the given sport.
    /// Returns `nil` if the sport has no division mapping or the team is unknown.
    static func division(for sport: Sport, abbreviation abbr: String) -> String? {
        switch sport {
        case .mlb:  return mlb[abbr]
        case .nfl:  return nfl[abbr]
        case .nba:  return nba[abbr]
        case .nhl:  return nhl[abbr]
        default:    return nil
        }
    }

    /// Preferred display order for divisions in the given sport.
    static func divisionOrder(for sport: Sport) -> [String] {
        switch sport {
        case .mlb:  return mlbOrder
        case .nfl:  return nflOrder
        case .nba:  return nbaOrder
        case .nhl:  return nhlOrder
        default:    return []
        }
    }

    /// Whether the given sport uses division grouping.
    static func hasDivisions(_ sport: Sport) -> Bool {
        switch sport {
        case .mlb, .nfl, .nba, .nhl: return true
        default: return false
        }
    }
}
