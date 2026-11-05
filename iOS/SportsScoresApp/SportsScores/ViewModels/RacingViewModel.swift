//
//  RacingViewModel.swift
//  SportsScores
//
//  Loads and holds race event + championship standings for a single racing series.
//  Event and standings fetches run concurrently on initial load.
//

import Foundation

@MainActor
class RacingViewModel: ObservableObject {

    @Published var raceEvent: RaceEvent?
    @Published var standings: [RacingStandingsGroup] = []
    @Published var isLoadingEvent = false
    @Published var isLoadingStandings = false
    @Published var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    var isLoading: Bool { isLoadingEvent || isLoadingStandings }

    // MARK: - Load

    func load(series: Sport) async {
        errorMessage = nil
        isLoadingEvent = true
        isLoadingStandings = true

        async let eventFetch: Void = fetchEvent(series: series)
        async let standingsFetch: Void = fetchStandings(series: series)
        _ = await (eventFetch, standingsFetch)
    }

    func refresh(series: Sport) async {
        await load(series: series)
    }

    // MARK: - Private

    private func fetchEvent(series: Sport) async {
        defer { isLoadingEvent = false }
        do {
            raceEvent = try await apiService.fetchRaceEvent(for: series)
        } catch {
            errorMessage = APIError.unavailable("this race")
        }
    }

    private func fetchStandings(series: Sport) async {
        defer { isLoadingStandings = false }
        do {
            standings = try await apiService.fetchRacingStandings(for: series)
        } catch {
            // Standings failure is non-fatal — results may still be shown
        }
    }
}
