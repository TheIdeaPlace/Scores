//
//  VenuesViewModel.swift
//  SportsScores
//
//  A league's venues, for the Venues tab.
//

import Foundation

@MainActor
final class VenuesViewModel: ObservableObject {
    @Published private(set) var venues: [LeagueVenue] = []
    /// True from the start, so nothing can read as "no venues" before the first answer.
    @Published private(set) var isLoading = true
    @Published private(set) var errorMessage: String?

    /// What the list on screen was asked for with. Coming back from a venue's details runs
    /// the view's task again, and reloading then would take VoiceOver off the row it was on.
    private var loadedQuery: String?
    private let apiService: ESPNAPIService

    init(apiService: ESPNAPIService = .shared) {
        self.apiService = apiService
    }

    func fetchVenues(for sport: Sport) async {
        guard apiService.venueQuery(for: sport) != loadedQuery else { return }
        isLoading = true
        errorMessage = nil
        await load(for: sport, ignoringCache: false)
    }

    /// Pull to refresh asks ESPN again, and the list stays on screen while it does.
    func refresh(for sport: Sport) async {
        errorMessage = nil
        await load(for: sport, ignoringCache: true)
    }

    private func load(for sport: Sport, ignoringCache: Bool) async {
        let query = apiService.venueQuery(for: sport)
        do {
            let list = try await apiService.fetchVenues(for: sport, ignoringCache: ignoringCache)
            // Gone from the screen, or the coverage setting changed and a newer load has it.
            guard !Task.isCancelled else { return }
            venues = list
            loadedQuery = query
        } catch is CancellationError {
            return
        } catch {
            guard !Task.isCancelled else { return }
            venues = []
            loadedQuery = nil
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
