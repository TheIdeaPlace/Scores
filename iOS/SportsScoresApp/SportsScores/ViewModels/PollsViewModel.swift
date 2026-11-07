//
//  PollsViewModel.swift
//  SportsScores
//
//  Phase 6 — College rankings / polls.
//

import Foundation

@MainActor
class PollsViewModel: ObservableObject {
    @Published var polls: [RankingsPoll] = []
    @Published var selectedPollIndex = 0
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    /// Segments for up to this many polls, a menu past it. Basketball's two and hockey's one stay
    /// segments; college football's six would cut their names short.
    nonisolated static let maxSegmentedPolls = 3

    nonisolated static func usesMenu(pollCount: Int) -> Bool {
        pollCount > maxSegmentedPolls
    }

    var selectedPoll: RankingsPoll? {
        guard selectedPollIndex < polls.count else { return nil }
        return polls[selectedPollIndex]
    }

    func fetchRankings(for sport: Sport) async {
        isLoading = polls.isEmpty
        errorMessage = nil

        do {
            polls = try await apiService.fetchRankings(for: sport)
            // Reset to first poll if out of bounds
            if selectedPollIndex >= polls.count { selectedPollIndex = 0 }
        } catch {
            errorMessage = APIError.unavailable("polls")
        }

        isLoading = false
    }

    func refresh(for sport: Sport) async {
        await fetchRankings(for: sport)
    }
}
