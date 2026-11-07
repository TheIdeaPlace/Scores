//
//  BowlsView.swift
//  SportsScores
//
//  College football's bowls and playoff in one list, as the Windows app's Bowls & Playoffs
//  has them, from the same request. Reached from the NCAAF Scores tab. Each heading is a
//  VoiceOver heading and each game one element, which opens its details.
//

import SwiftUI
import UIKit

struct BowlsView: View {
    let sport: Sport
    @StateObject private var viewModel = BowlsViewModel()
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        // A view that stays put, so going from loading to an error isn't an appearance that
        // starts the task again.
        ZStack { content }
            .navigationTitle("Bowls & Playoffs")
            .navigationBarTitleDisplayMode(.inline)
            // The coverage setting picks the request, and Settings can change it.
            .task(id: appSettings.ncaafCoverage) {
                await viewModel.load(for: sport, coverage: appSettings.ncaafCoverage)
            }
            .onChange(of: viewModel.errorMessage) { _, message in
                if let message { UIAccessibility.post(notification: .announcement, argument: message) }
            }
            // Focus was on "Loading", which goes, so nothing else would say there are none.
            .onChange(of: viewModel.isLoading) { _, loading in
                if !loading, viewModel.errorMessage == nil, viewModel.sections.isEmpty {
                    UIAccessibility.post(notification: .announcement, argument: Self.emptyText)
                }
            }
            .onChange(of: viewModel.refreshFailed) { _, failed in
                if failed { UIAccessibility.post(notification: .announcement, argument: Self.refreshFailedText) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading {
            ProgressView("Loading bowl games…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage {
            ErrorStateView(message: error) {
                Task { await viewModel.retry(for: sport, coverage: appSettings.ncaafCoverage) }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if viewModel.sections.isEmpty {
            emptyState
        } else {
            list
        }
    }

    static let emptyText = "No bowl or playoff games are listed yet. ESPN adds them near the end of the regular season."
    private static let refreshFailedText = "Couldn't refresh the bowl games. These are the ones last loaded."

    private var emptyState: some View {
        ScrollView {
            VStack(spacing: 16) {
                Image(systemName: "trophy")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                    .accessibilityHidden(true)
                Text(Self.emptyText)
                    .font(.headline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
            .padding()
            .frame(maxWidth: .infinity)
            .padding(.top, 80)
        }
        // Pull to refresh works here too, for the day ESPN adds them.
        .refreshable { await viewModel.refresh(for: sport, coverage: appSettings.ncaafCoverage) }
    }

    private var list: some View {
        List {
            if viewModel.refreshFailed {
                Section {
                    HStack(spacing: 12) {
                        Text(Self.refreshFailedText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                        Button("Retry") {
                            Task { await viewModel.refresh(for: sport, coverage: appSettings.ncaafCoverage) }
                        }
                        .font(.caption)
                        .buttonStyle(.bordered)
                    }
                }
            }
            ForEach(viewModel.sections) { section in
                Section {
                    ForEach(section.games) { item in
                        if item.teamsUndecided {
                            // No teams, so no radio yet, and "Listen to TBD vs TBD" says nothing.
                            gameLink(item)
                        } else {
                            gameLink(item)
                                .listenToGame(item.game, sport: sport)
                        }
                    }
                } header: {
                    Text(section.heading)
                        .accessibilityAddTraits(.isHeader)
                }
            }
        }
        .listStyle(.plain)
        .refreshable { await viewModel.refresh(for: sport, coverage: appSettings.ncaafCoverage) }
    }

    private func gameLink(_ item: PostseasonGame) -> some View {
        NavigationLink(destination: GameDetailView(game: item.game, sport: sport)) {
            BowlGameRow(item: item)
        }
        .accessibilityHint("Opens game details")
    }
}

/// One game: its name, the teams, and when it is or how it stands. One VoiceOver element.
private struct BowlGameRow: View {
    let item: PostseasonGame
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        let game = item.game
        VStack(alignment: .leading, spacing: 4) {
            if let title = item.title {
                Text(title)
                    .font(.subheadline.bold())
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(PostseasonList.matchup(item) { $0.rankedAbbreviation })
                .font(.body)
            HStack {
                Text(PostseasonList.status(game, spoken: false))
                    .font(.caption)
                    .foregroundColor(game.status.isLive ? .red : .secondary)
                Spacer()
                if !game.status.isCompleted, let broadcast = game.broadcasts.first, !broadcast.isEmpty {
                    Text(broadcast)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.blue.opacity(0.2))
                        .cornerRadius(4)
                }
            }
            if let venue = game.venue, !venue.name.isEmpty {
                Text(venue.fullName)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PostseasonList.accessibilityLabel(item, teamNames: appSettings.teamNamePreference))
    }
}
