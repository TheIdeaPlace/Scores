//
//  StandingsView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI

struct StandingsView: View {
    let sport: Sport
    @StateObject private var viewModel = StandingsViewModel()
    
    var body: some View {
        VStack(spacing: 0) {
            if sport.hasWildCardStandings {
                modePicker
            }
            content
        }
        .task {
            await viewModel.fetchStandings(for: sport)
        }
        // Fetch the wild card race the first time it is asked for, not on load.
        .onChange(of: viewModel.mode) {
            viewModel.modeChanged()
            Task { await viewModel.loadWildCardIfNeeded(for: sport) }
        }
        .refreshable {
            await viewModel.refresh(for: sport)
        }
    }

    private var modePicker: some View {
        Picker("Standings view", selection: $viewModel.mode) {
            ForEach(StandingsMode.allCases) { mode in
                Text(mode.label).tag(mode)
            }
        }
        .pickerStyle(.segmented)
        .padding(.horizontal)
        .padding(.vertical, 8)
        .accessibilityLabel("Standings view")
        .accessibilityHint("Divisions shows each division separately. "
                           + "Wild Card shows the division leaders and the wild card race for each league.")
    }

    private var emptyText: String {
        if viewModel.mode == .wildCard { return "No wild card standings available" }
        return sport.isSoccer
            ? "ESPN has no league table for \(sport.displayName) right now. A knockout competition doesn't have one."
            : "No standings available"
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading {
            ProgressView(viewModel.mode == .wildCard
                         ? "Loading wild card standings..."
                         : "Loading standings...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage {
            ErrorStateView(message: error) {
                Task {
                    if viewModel.mode == .wildCard {
                        await viewModel.loadWildCardIfNeeded(for: sport)
                    } else {
                        await viewModel.fetchStandings(for: sport)
                    }
                }
            }
        } else if viewModel.visibleGroups.isEmpty {
            VStack(spacing: 16) {
                Image(systemName: "list.bullet.clipboard")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                    .accessibilityHidden(true)
                Text(emptyText)
                    .font(.headline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onAppear {
                // It replaces the spinner with nothing else to land on, and it's the answer.
                if sport.isSoccer {
                    UIAccessibility.post(notification: .announcement, argument: emptyText)
                }
            }
        } else {
            StandingsTableView(standingsGroups: viewModel.visibleGroups,
                               sport: sport,
                               isWildCard: viewModel.mode == .wildCard)
        }
    }
}

#Preview {
    NavigationStack {
        StandingsView(sport: .mlb)
            .navigationTitle("MLB Standings")
    }
}
