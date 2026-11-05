//
//  StandingsViewModel.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

/// Which grouping the standings screen is showing. MLB is the only sport with a
/// wild card race, so the picker only appears there.
enum StandingsMode: String, CaseIterable, Identifiable {
    case divisions
    case wildCard

    var id: String { rawValue }

    var label: String {
        switch self {
        case .divisions: return "Divisions"
        case .wildCard:  return "Wild Card"
        }
    }
}

@MainActor
class StandingsViewModel: ObservableObject {
    @Published var standingsGroups: [StandingsGroup] = []
    @Published var wildCardGroups: [StandingsGroup] = []
    @Published var mode: StandingsMode = .divisions
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    /// Whether the wild card fetch has been tried. Distinct from
    /// `wildCardGroups.isEmpty`, which stays true after a legitimate empty
    /// result (the offseason) and would otherwise refetch on every toggle.
    private var hasAttemptedWildCard = false

    /// The groups the view should render for the current mode.
    var visibleGroups: [StandingsGroup] {
        mode == .wildCard ? wildCardGroups : standingsGroups
    }

    func fetchStandings(for sport: Sport) async {
        isLoading = standingsGroups.isEmpty
        errorMessage = nil
        
        do {
            if sport.usesCFLSource {
                standingsGroups = try await CFLAPIService.shared.fetchStandings()
            } else {
                standingsGroups = try await apiService.fetchStandings(for: sport)
            }
        } catch {
            errorMessage = APIError.unavailable("standings", source: sport.usesCFLSource ? "The CFL" : "ESPN")
        }
        
        isLoading = false
    }

    /// Loads the wild card race the first time the user switches to it. Kept
    /// separate from `fetchStandings` so the divisions view, which is what most
    /// people want, is never held up by a second network call.
    func loadWildCardIfNeeded(for sport: Sport) async {
        // The mode check matters: onChange fires on both transitions, and in the
        // offseason ESPN legitimately returns no records — so without it,
        // every switch *back* to Divisions would re-enter here, blank the loaded
        // divisions table with a spinner, and then show a wild card error over
        // perfectly good division data.
        guard mode == .wildCard, sport.hasWildCardStandings, wildCardGroups.isEmpty,
              !hasAttemptedWildCard else { return }
        hasAttemptedWildCard = true
        isLoading = true
        errorMessage = nil
        do {
            wildCardGroups = try await apiService.fetchMLBWildCardStandings()
        } catch {
            errorMessage = APIError.unavailable("wild card standings")
            hasAttemptedWildCard = false  // so Retry can ask again
        }
        isLoading = false
    }

    /// Clears state that belongs to the mode being left, so an error raised in
    /// one mode never renders over the other's data.
    func modeChanged() {
        errorMessage = nil
        isLoading = false
    }

    func refresh(for sport: Sport) async {
        if mode == .wildCard && sport.hasWildCardStandings {
            wildCardGroups = []
            hasAttemptedWildCard = false
            await loadWildCardIfNeeded(for: sport)
        } else {
            await fetchStandings(for: sport)
        }
    }
}
