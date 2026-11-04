//
//  StatLeaderDetailView.swift
//  SportsScores
//
//  Full leader list for a single stat category, opened via "View All".
//  Immediately shows the 10 summary entries already in memory, then fetches
//  the full list in the background: 50 players, or every team, so a college
//  team's rank on its Team Hub can be found here too.
//

import SwiftUI

struct StatLeaderDetailView: View {
    let summary: LeagueLeaderCategory   // 10 entries already in hand
    let sport: Sport
    let initialViewMode: ViewMode

    @State private var viewMode: ViewMode
    @State private var fullCategory: LeagueLeaderCategory?
    @State private var isLoadingMore = false
    @State private var loadError: String?

    private var displayCategory: LeagueLeaderCategory { fullCategory ?? summary }

    init(category: LeagueLeaderCategory, sport: Sport, initialViewMode: ViewMode) {
        self.summary = category
        self.sport = sport
        self.initialViewMode = initialViewMode
        self._viewMode = State(initialValue: initialViewMode)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let season = displayCategory.seasonLabel {
                    SeasonLabel(text: season)
                        .padding([.horizontal, .top])
                }
                LeaderCategorySection(category: displayCategory, viewMode: viewMode, sport: sport)
                    .padding()

                if isLoadingMore {
                    ProgressView("Loading more…")
                        .frame(maxWidth: .infinity)
                        .padding(.bottom)
                } else if let err = loadError {
                    Text(err)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding()
                }
            }
        }
        .navigationTitle(summary.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
        .task { await loadFull() }
    }

    private func loadFull() async {
        isLoadingMore = true
        loadError = nil
        do {
            let allCategories = summary.isTeamCategory
                ? try await ESPNAPIService.shared.fetchTeamLeaders(for: sport, limit: .max)
                : try await ESPNAPIService.shared.fetchLeagueLeaders(for: sport, limit: 50)
            fullCategory = allCategories.first { $0.name == summary.name }
        } catch {
            loadError = "Couldn't load full list."
        }
        isLoadingMore = false
    }
}
