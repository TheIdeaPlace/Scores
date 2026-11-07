//
//  RacingLeagueView.swift
//  SportsScores
//
//  Tabbed view for a single racing series: Results · Standings · News.
//  Mirrors GolfLeagueView. One StateObject ViewModel per presented series.
//
//  ViewModeMenuButton appears in the toolbar for Results and Standings tabs.
//  News has no list to mode-switch.
//

import SwiftUI

private enum RacingTab: Int {
    case results = 0, standings, news
}

struct RacingLeagueView: View {
    let series: Sport
    @StateObject private var viewModel = RacingViewModel()
    @State private var selectedTab: RacingTab = .results
    @State private var viewMode: ViewMode = .savedDefault()

    var body: some View {
        VStack(spacing: 0) {
            tabContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider()
            Picker("View", selection: $selectedTab) {
                Text("Results").tag(RacingTab.results)
                Text("Standings").tag(RacingTab.standings)
                Text("News").tag(RacingTab.news)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 4)
            .padding(.bottom, 8)
        }
        .navigationTitle(series.displayName)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if selectedTab != .news {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
        .task { await viewModel.load(series: series) }
        .refreshable { await viewModel.refresh(series: series) }
    }

    @ViewBuilder
    private var tabContent: some View {
        switch selectedTab {
        case .results:
            if let error = viewModel.errorMessage, viewModel.raceEvent == nil {
                ErrorStateView(message: error) {
                    Task { await viewModel.refresh(series: series) }
                }
            } else {
                RacingResultsView(
                    series: series,
                    raceEvent: viewModel.raceEvent,
                    isLoading: viewModel.isLoadingEvent,
                    viewMode: viewMode
                )
            }

        case .standings:
            RacingStandingsView(
                standings: viewModel.standings,
                isLoading: viewModel.isLoadingStandings,
                viewMode: viewMode
            )

        case .news:
            NewsView(sport: series)
        }
    }
}

#Preview {
    NavigationStack {
        RacingLeagueView(series: .formulaOne)
    }
}
