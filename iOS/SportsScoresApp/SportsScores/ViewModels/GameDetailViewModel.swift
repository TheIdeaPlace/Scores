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

    init(game: Game, sport: Sport) {
        self.game = game
        self.sport = sport
    }

    func loadDetails() async {
        // CFL has no box score / play-by-play feed. Leave details nil so the
        // view shows the game header alone rather than an error.
        guard !sport.usesCFLSource else {
            isLoading = false
            return
        }
        isLoading = true
        errorMessage = nil
        do {
            gameDetails = try await ESPNAPIService.shared.fetchGameDetails(for: game.id, sport: sport)
        } catch {
            errorMessage = APIError.unavailable("this game")
        }
        isLoading = false
    }
}
