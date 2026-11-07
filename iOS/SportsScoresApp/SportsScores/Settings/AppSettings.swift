//
//  AppSettings.swift
//  SportsScores
//
//  Root-level ObservableObject injected into the SwiftUI environment via
//  `.environmentObject()` at the app entry point. All views read
//  preferences through `@EnvironmentObject var appSettings: AppSettings`.
//
//  Preferences are persisted in UserDefaults so they survive restarts.
//

import Foundation
import Combine

private enum StorageKeys {
    static let teamNamePreference = "teamNamePreference"
    static let autoRefreshInterval = "autoRefreshInterval"
    static let useDirectTouchForTours = "useDirectTouchForTours"
    static let sportOrder = "sportOrder"
    static let hiddenSports = "hiddenSports"
    static let soccerHubEnabled = "soccerHubEnabled"
    static let golfHubEnabled = "golfHubEnabled"
    static let cflEnabled = "cflEnabled"
    static let racingHubEnabled = "racingHubEnabled"
    static let worldCupHubEnabled = "worldCupHubEnabled"
    static let worldCupWomensHubEnabled = "worldCupWomensHubEnabled"
    static let defaultTableViewMode = ViewMode.defaultsKey
    static let favoriteTeams = "favoriteTeams"
    static let ncaafCoverage = "ncaafCoverage"
}

@MainActor
final class AppSettings: ObservableObject {

    // MARK: - Team Name Announcement

    /// Controls how team names are spoken by VoiceOver in accessible labels.
    /// Visual abbreviations are unaffected by this setting.
    @Published var teamNamePreference: TeamNamePreference {
        didSet {
            UserDefaults.standard.set(
                teamNamePreference.rawValue,
                forKey: StorageKeys.teamNamePreference
            )
        }
    }

    // MARK: - Home Page Sport Customization

    /// Ordered list of main sports shown on the home page.
    /// Always contains every Sport.allCases entry; users change the order but cannot remove entries.
    /// Soccer is a separate hardcoded row and is not included here.
    @Published var sportOrder: [Sport] {
        didSet {
            UserDefaults.standard.set(sportOrder.map(\.rawValue), forKey: StorageKeys.sportOrder)
        }
    }

    /// Raw values of sports the user has hidden from the home page.
    @Published var hiddenSports: Set<Sport> {
        didSet {
            UserDefaults.standard.set(Array(hiddenSports.map(\.rawValue)), forKey: StorageKeys.hiddenSports)
        }
    }

    /// Whether the Soccer hub row is shown on the home page.
    @Published var soccerHubEnabled: Bool {
        didSet { UserDefaults.standard.set(soccerHubEnabled, forKey: StorageKeys.soccerHubEnabled) }
    }

    /// Whether the Golf hub row is shown on the home page.
    @Published var golfHubEnabled: Bool {
        didSet { UserDefaults.standard.set(golfHubEnabled, forKey: StorageKeys.golfHubEnabled) }
    }

    /// Whether the Auto Racing hub row is shown on the home page.
    @Published var racingHubEnabled: Bool {
        didSet { UserDefaults.standard.set(racingHubEnabled, forKey: StorageKeys.racingHubEnabled) }
    }

    /// Whether the CFL row is shown on the home page.
    @Published var cflEnabled: Bool {
        didSet { UserDefaults.standard.set(cflEnabled, forKey: StorageKeys.cflEnabled) }
    }

    /// Whether the 2026 FIFA World Cup hub row is shown on the home page.
    @Published var worldCupHubEnabled: Bool {
        didSet { UserDefaults.standard.set(worldCupHubEnabled, forKey: StorageKeys.worldCupHubEnabled) }
    }

    /// Whether the 2027 FIFA Women's World Cup hub row is shown on the home page.
    @Published var worldCupWomensHubEnabled: Bool {
        didSet { UserDefaults.standard.set(worldCupWomensHubEnabled, forKey: StorageKeys.worldCupWomensHubEnabled) }
    }

    /// Sports in user-defined order, filtering out hidden ones — ready for the home page ForEach.
    var visibleSports: [Sport] {
        sportOrder.filter { !hiddenSports.contains($0) }
    }

    // MARK: - Stadium Tour Accessibility

    /// When true the drag canvases in stadium tours use .accessibilityDirectTouch(options: .silentOnTouch)
    /// so VoiceOver silences itself and passes touches straight to the drag gesture.
    /// When false VoiceOver behaves normally; users can still drag via the double-tap-and-hold passthrough.
    @Published var useDirectTouchForTours: Bool {
        didSet {
            UserDefaults.standard.set(useDirectTouchForTours, forKey: StorageKeys.useDirectTouchForTours)
        }
    }

    // MARK: - Default Table View Mode

    /// Controls which view mode (Table, Quick List, Full List) tables open in by default.
    @Published var defaultTableViewMode: ViewMode {
        didSet {
            UserDefaults.standard.set(
                defaultTableViewMode.rawValue,
                forKey: StorageKeys.defaultTableViewMode
            )
        }
    }

    // MARK: - Favorite Teams

    /// Teams the user has bookmarked in Team Hub.
    @Published var favoriteTeams: [FavoriteTeam] {
        didSet {
            if let data = try? JSONEncoder().encode(favoriteTeams) {
                UserDefaults.standard.set(data, forKey: StorageKeys.favoriteTeams)
            }
        }
    }

    func isFavorite(teamId: String, sport: Sport) -> Bool {
        favoriteTeams.contains { $0.id == teamId && $0.sport == sport }
    }

    func addFavorite(_ team: TransactionTeam, sport: Sport) {
        guard !isFavorite(teamId: team.id, sport: sport) else { return }
        let fav = FavoriteTeam(
            id: team.id,
            sport: sport,
            displayName: team.displayName,
            abbreviation: team.abbreviation,
            color: team.color,
            logoURLString: team.primaryLogoURL?.absoluteString
        )
        favoriteTeams.append(fav)
    }

    func removeFavorite(teamId: String, sport: Sport) {
        favoriteTeams.removeAll { $0.id == teamId && $0.sport == sport }
    }

    /// Moves a favorite to a new position. `to` is the desired final index in the
    /// original array (before the item is removed). The move is clamped to valid bounds.
    func moveFavorite(teamId: String, sport: Sport, to newIndex: Int) {
        guard let current = favoriteTeams.firstIndex(where: { $0.id == teamId && $0.sport == sport }) else { return }
        var updated = favoriteTeams
        let item = updated.remove(at: current)
        let clamped = max(0, min(newIndex, updated.count))
        updated.insert(item, at: clamped)
        favoriteTeams = updated
    }

    // MARK: - College Football Coverage

    /// How much of college football the NCAAF scoreboard requests from ESPN.
    /// Defaults to all of Division I, because the narrower FBS view hides most
    /// of the games actually played on opening weekend. See `NCAAFCoverage`.
    @Published var ncaafCoverage: NCAAFCoverage {
        didSet {
            UserDefaults.standard.set(
                ncaafCoverage.rawValue,
                forKey: StorageKeys.ncaafCoverage
            )
        }
    }

    // MARK: - Auto-Refresh Interval

    /// Shared refresh cadence used by both ScoresView and LiveScoresView.
    /// Persisted in UserDefaults so it survives app restarts.
    @Published var autoRefreshInterval: AutoRefreshInterval {
        didSet {
            UserDefaults.standard.set(
                autoRefreshInterval.rawValue,
                forKey: StorageKeys.autoRefreshInterval
            )
        }
    }

    // MARK: - Init

    init() {
        let raw = UserDefaults.standard.string(forKey: StorageKeys.teamNamePreference) ?? ""
        teamNamePreference = TeamNamePreference(rawValue: raw) ?? .full

        defaultTableViewMode = ViewMode.savedDefault()

        let rawCoverage = UserDefaults.standard.string(forKey: StorageKeys.ncaafCoverage) ?? ""
        ncaafCoverage = NCAAFCoverage(rawValue: rawCoverage) ?? .allDivisionI

        let storedInterval = UserDefaults.standard.object(forKey: StorageKeys.autoRefreshInterval) as? Int
        autoRefreshInterval = storedInterval.flatMap { AutoRefreshInterval(rawValue: $0) } ?? .manual

        // Default to true (direct touch on) — only false if user has explicitly disabled it
        if UserDefaults.standard.object(forKey: StorageKeys.useDirectTouchForTours) == nil {
            useDirectTouchForTours = true
        } else {
            useDirectTouchForTours = UserDefaults.standard.bool(forKey: StorageKeys.useDirectTouchForTours)
        }

        // Sport order: restore from defaults, filling in any missing sports at the end
        let defaultOrder = Sport.allCases
        if let saved = UserDefaults.standard.stringArray(forKey: StorageKeys.sportOrder) {
            let savedSports = saved.compactMap { Sport(rawValue: $0) }
            let knownSet = Set(savedSports)
            let extras = defaultOrder.filter { !knownSet.contains($0) }
            sportOrder = savedSports + extras
        } else {
            sportOrder = defaultOrder
        }

        // Hidden sports
        if let savedHidden = UserDefaults.standard.stringArray(forKey: StorageKeys.hiddenSports) {
            hiddenSports = Set(savedHidden.compactMap { Sport(rawValue: $0) })
        } else {
            hiddenSports = []
        }

        // Hub toggles — default on if never set
        if UserDefaults.standard.object(forKey: StorageKeys.soccerHubEnabled) == nil {
            soccerHubEnabled = true
        } else {
            soccerHubEnabled = UserDefaults.standard.bool(forKey: StorageKeys.soccerHubEnabled)
        }

        if UserDefaults.standard.object(forKey: StorageKeys.golfHubEnabled) == nil {
            golfHubEnabled = true
        } else {
            golfHubEnabled = UserDefaults.standard.bool(forKey: StorageKeys.golfHubEnabled)
        }

        if UserDefaults.standard.object(forKey: StorageKeys.racingHubEnabled) == nil {
            racingHubEnabled = true
        } else {
            racingHubEnabled = UserDefaults.standard.bool(forKey: StorageKeys.racingHubEnabled)
        }

        // CFL — default on until the user explicitly turns it off.
        if UserDefaults.standard.object(forKey: StorageKeys.cflEnabled) == nil {
            cflEnabled = true
        } else {
            cflEnabled = UserDefaults.standard.bool(forKey: StorageKeys.cflEnabled)
        }

        // World Cup hubs — default to true (always on until the user explicitly turns them off)
        if UserDefaults.standard.object(forKey: StorageKeys.worldCupHubEnabled) == nil {
            worldCupHubEnabled = true
        } else {
            worldCupHubEnabled = UserDefaults.standard.bool(forKey: StorageKeys.worldCupHubEnabled)
        }

        if UserDefaults.standard.object(forKey: StorageKeys.worldCupWomensHubEnabled) == nil {
            worldCupWomensHubEnabled = true
        } else {
            worldCupWomensHubEnabled = UserDefaults.standard.bool(forKey: StorageKeys.worldCupWomensHubEnabled)
        }

        // Favorite teams
        if let data = UserDefaults.standard.data(forKey: StorageKeys.favoriteTeams),
           let decoded = try? JSONDecoder().decode([FavoriteTeam].self, from: data) {
            favoriteTeams = decoded
        } else {
            favoriteTeams = []
        }
    }
}
