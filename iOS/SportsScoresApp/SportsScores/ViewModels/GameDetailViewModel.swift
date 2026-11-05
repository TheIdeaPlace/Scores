//
//  GameDetailViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
final class GameDetailViewModel: ObservableObject {
    @Published var gameDetails: GameDetails?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let game: Game
    private let sport: Sport
    private let apiService: ESPNAPIService

    init(game: Game, sport: Sport, apiService: ESPNAPIService = .shared) {
        self.game = game
        self.sport = sport
        self.apiService = apiService
    }

    /// The first load shows the spinner, or the error if it fails. Coming back from a
    /// screen opened from here runs this again, and that refresh has to happen quietly: the
    /// spinner would replace the tabs, and VoiceOver would lose its place on the row it came
    /// back to. If it fails, what's already showing stays.
    func loadDetails() async {
        // CFL has no box score / play-by-play feed. Leave details nil so the
        // view shows the game header alone rather than an error.
        guard !sport.usesCFLSource else {
            isLoading = false
            return
        }
        if gameDetails == nil {
            isLoading = true
            errorMessage = nil
        }
        do {
            gameDetails = try await apiService.fetchGameDetails(for: game.id, sport: sport)
        } catch let error where error.isCancellation {
            // Left the screen. It asks again if it comes back.
        } catch {
            if gameDetails == nil {
                errorMessage = "Failed to load details: \(error.localizedDescription)"
            }
        }
        isLoading = false
    }
}
