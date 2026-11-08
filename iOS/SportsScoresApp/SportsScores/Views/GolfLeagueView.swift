//
//  GolfLeagueView.swift
//  SportsScores
//
//  Main content view for a single golf tour (PGA or LPGA).
//  Provides:
//   - Tournament navigation bar (prev/next tournament, season year picker)
//   - Four tabs: Leaderboard · Schedule · Stats · News
//

import SwiftUI

private enum GolfTab: Int {
    case leaderboard = 0, schedule, stats, news
}

struct GolfLeagueView: View {

    let sport: Sport
    @StateObject private var viewModel = GolfViewModel()
    @State private var selectedTab: GolfTab = .leaderboard

    var body: some View {
        VStack(spacing: 0) {

            // Tournament navigation bar (only shown on Leaderboard tab)
            if selectedTab == .leaderboard {
                tournamentNavBar
                    .padding(.horizontal)
                    .padding(.top, 8)
                    .padding(.bottom, 6)
            }

            // Tab content
            tabContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            // Tab picker
            Divider()
            Picker("View", selection: $selectedTab) {
                Text("Leaderboard").tag(GolfTab.leaderboard)
                Text("Schedule").tag(GolfTab.schedule)
                Text("Stats").tag(GolfTab.stats)
                Text("News").tag(GolfTab.news)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 4)
            .padding(.bottom, 8)
        }
        .navigationTitle(sport.displayName)
        .task {
            async let season: Void = viewModel.fetchSeason(for: sport)
            await viewModel.fetchCurrentTournament(for: sport)
            await season
        }
        .refreshable {
            if selectedTab == .leaderboard {
                await viewModel.refresh(for: sport)
            } else if selectedTab == .schedule {
                await viewModel.fetchSeason(for: sport)
            }
        }
    }

    // MARK: - Tab content

    @ViewBuilder
    private var tabContent: some View {
        switch selectedTab {
        case .leaderboard:
            leaderboardContent

        case .schedule:
            GolfScheduleView(
                calendar: viewModel.calendar,
                seasonEvents: viewModel.seasonEvents,
                seasonFailed: viewModel.seasonFailed,
                selectedIndex: viewModel.selectedCalendarIndex,
                onSelect: { idx in
                    selectedTab = .leaderboard
                    Task { await viewModel.navigate(to: idx, for: sport) }
                }
            )

        case .stats:
            StatisticsView(sport: sport)

        case .news:
            NewsView(sport: sport)
        }
    }

    // MARK: - Leaderboard content

    @ViewBuilder
    private var leaderboardContent: some View {
        if viewModel.isLoading && viewModel.tournament == nil {
            ProgressView("Loading tournament…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage, viewModel.tournament == nil {
            ErrorStateView(message: error) {
                Task { await viewModel.fetchCurrentTournament(for: sport) }
            }
        } else if let tournament = viewModel.tournament {
            GolfLeaderboardView(tournament: tournament)
        } else {
            // Calendar loaded but no active event (off-season)
            VStack(spacing: 16) {
                Image(systemName: "figure.golf")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("No Active Tournament")
                    .font(.headline)
                    .foregroundColor(.secondary)
                Text("Browse the Schedule tab to view past or upcoming events.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Tournament navigation bar

    private var tournamentNavBar: some View {
        HStack(spacing: 8) {

            // ← Previous tournament
            Button {
                Task { await viewModel.goBack(for: sport) }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoading || !viewModel.canGoBack)
            .accessibilityLabel("Previous Tournament")

            Spacer()

            // Centre: tournament name + round status
            VStack(spacing: 2) {
                Text(viewModel.tournamentNavLabel)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                    .accessibilityLabel(viewModel.tournamentNavLabel)

                if let tournament = viewModel.tournament {
                    Text(tournament.roundStatusText)
                        .font(.caption)
                        .foregroundColor(tournament.isInProgress ? .red : .secondary)
                }
            }
            .accessibilityElement(children: .combine)

            Spacer()

            // Next tournament →
            Button {
                Task { await viewModel.goForward(for: sport) }
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoading || !viewModel.canGoForward)
            .accessibilityLabel("Next Tournament")
        }
    }
}
