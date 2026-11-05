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
    /// A pull to refresh failed. The list stays, and this says it's the one last loaded.
    @Published private(set) var refreshFailed = false

    /// What was last asked for, whatever came of it. The view's task runs again on coming
    /// back from a venue's details, and reloading then would take VoiceOver off the row it
    /// was on. It doesn't ask again after a failure either, which is for Retry.
    private var attemptedQuery: String?
    /// Which load is the current one, so that one it has replaced changes nothing.
    private var latestLoad = 0
    private let apiService: ESPNAPIService

    init(apiService: ESPNAPIService = .shared) {
        self.apiService = apiService
    }

    func fetchVenues(for sport: Sport) async {
        guard apiService.venueQuery(for: sport) != attemptedQuery else { return }
        await retry(for: sport)
    }

    func retry(for sport: Sport) async {
        attemptedQuery = apiService.venueQuery(for: sport)
        isLoading = true
        errorMessage = nil
        refreshFailed = false
        latestLoad += 1
        let load = latestLoad
        do {
            let list = try await apiService.fetchVenues(for: sport)
            guard load == latestLoad else { return }
            venues = list
            isLoading = false
        } catch is CancellationError {
            // Gone from the screen, so it's asked for again on coming back.
            guard load == latestLoad else { return }
            attemptedQuery = nil
        } catch {
            guard load == latestLoad else { return }
            venues = []
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    /// Pull to refresh asks ESPN again, and the list stays on screen while it does and if it fails.
    func refresh(for sport: Sport) async {
        refreshFailed = false
        latestLoad += 1
        let load = latestLoad
        do {
            let list = try await apiService.fetchVenues(for: sport, ignoringCache: true)
            guard load == latestLoad else { return }
            venues = list
        } catch is CancellationError {
            return
        } catch {
            guard load == latestLoad else { return }
            refreshFailed = true
        }
    }
}
