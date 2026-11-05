//
//  WorldCupTeamViewModel.swift
//  SportsScores
//
//  Loads all of a single team's matches across the full tournament, grouped
//  by phase so the view can show the team's path from Group Stage to Final.
//

import Foundation

@MainActor
final class WorldCupTeamViewModel: ObservableObject {

    @Published var phaseGames: [(phase: WorldCupPhase, games: [Game])] = []
    @Published var isLoading = false
    @Published var error: String? = nil

    let entry: WorldCupGroupEntry
    let group: WorldCupGroup
    let sport: Sport
    let phases: [WorldCupPhase]

    private let api = ESPNAPIService.shared

    init(entry: WorldCupGroupEntry, group: WorldCupGroup, sport: Sport, phases: [WorldCupPhase]) {
        self.entry  = entry
        self.group  = group
        self.sport  = sport
        self.phases = phases
    }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil

        guard let firstPhase = phases.first, let lastPhase = phases.last else {
            isLoading = false
            return
        }

        do {
            let all = try await api.fetchGamesRange(
                for: sport,
                startDate: firstPhase.startDate,
                endDate: lastPhase.endDate
            )

            // Filter to this team's games only.
            let teamGames = all.filter {
                $0.homeTeam.id == entry.id || $0.awayTeam.id == entry.id
            }
            .sorted { $0.date < $1.date }

            // Group by phase using each game's date.
            var result: [(phase: WorldCupPhase, games: [Game])] = []
            for phase in phases {
                let inPhase = teamGames.filter { game in
                    game.date >= phase.startDate &&
                    game.date <= Calendar.current.date(byAdding: .day, value: 1, to: phase.endDate)!
                }
                if !inPhase.isEmpty {
                    result.append((phase: phase, games: inPhase))
                }
            }
            phaseGames = result
        } catch {
            self.error = APIError.unavailable("\(entry.teamDisplayName)'s matches")
        }

        isLoading = false
    }

    func refresh() async {
        isLoading = false   // reset so load() runs again
        await load()
    }
}
