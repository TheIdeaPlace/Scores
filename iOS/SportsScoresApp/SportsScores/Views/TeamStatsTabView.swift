//
//  TeamStatsTabView.swift
//  SportsScores
//
//  Stats tab for the Team Hub. Two sub-tabs:
//    Players — leaders on this team in each stat category (no View All needed)
//    Team    — this team's rank in each league-wide stat category
//
//  Both sub-tabs honour the three view modes (Quick List / Table / Full List)
//  via a shared ViewModeMenuButton in the toolbar. Default is Quick List.
//

import SwiftUI

struct TeamStatsTabView: View {
    let teamId: String
    let teamAbbreviation: String
    let sport: Sport
    @Binding var viewMode: ViewMode

    @StateObject private var viewModel = TeamStatsViewModel()
    @State private var subTab: SubTab = .players

    private enum SubTab: String, CaseIterable {
        case players = "Players"
        case team    = "Team"
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("Stats Type", selection: $subTab) {
                ForEach(SubTab.allCases, id: \.self) { t in
                    Text(t.rawValue).tag(t)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 8)
            .padding(.bottom, 4)

            Group {
                switch subTab {
                case .players: playerContent
                case .team:    teamContent
                }
            }
        }
        .task { await viewModel.load(teamId: teamId, teamAbbreviation: teamAbbreviation, sport: sport) }
    }

    // MARK: - Player sub-tab

    @ViewBuilder
    private var playerContent: some View {
        if viewModel.isLoadingPlayers {
            ProgressView("Loading player stats…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.playerError {
            ErrorStateView(message: error) {
                Task { await viewModel.load(teamId: teamId, teamAbbreviation: teamAbbreviation, sport: sport) }
            }
        } else if viewModel.playerCategories.isEmpty {
            emptyState(icon: "chart.bar.xaxis", text: "No player statistics available")
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(viewModel.playerCategories) { category in
                        LeaderCategorySection(category: category, viewMode: viewMode, sport: sport)
                    }
                }
                .padding()
            }
        }
    }

    // MARK: - Team sub-tab

    @ViewBuilder
    private var teamContent: some View {
        if viewModel.isLoadingTeamRankings {
            ProgressView("Loading team stats…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.teamError {
            ErrorStateView(message: error) {
                Task { await viewModel.load(teamId: teamId, teamAbbreviation: teamAbbreviation, sport: sport) }
            }
        } else if viewModel.teamRankings.isEmpty {
            emptyState(icon: "building.2", text: "No team statistics available")
        } else {
            teamRankingsList
        }
    }

    private var teamRankingsList: some View {
        let sections = Dictionary(grouping: viewModel.teamRankings, by: \.sectionName)
        let sectionOrder = viewModel.teamRankings.map(\.sectionName).reduce(into: [String]()) {
            if !$0.contains($1) { $0.append($1) }
        }

        return ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ForEach(sectionOrder, id: \.self) { section in
                    let rankings = sections[section] ?? []
                    switch viewMode {
                    case .quickList: teamQuickList(section: section, rankings: rankings)
                    case .table:     teamTable(section: section, rankings: rankings)
                    case .fullList:  teamFullList(section: section, rankings: rankings)
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - Team view mode variants

    @ViewBuilder
    private func teamQuickList(section: String, rankings: [TeamStatRanking]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(section)
                .font(.headline).padding(.bottom, 6)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 0) {
                ForEach(Array(rankings.enumerated()), id: \.element.id) { idx, r in
                    HStack(spacing: 8) {
                        Text(r.categoryDisplayName)
                            .font(.subheadline)
                        Spacer()
                        Text(r.teamValue)
                            .font(.subheadline.bold()).monospacedDigit()
                        Text(r.rankDisplay)
                            .font(.caption)
                            .foregroundColor(rankColor(r))
                    }
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(r.categoryDisplayName): \(r.teamValue), \(r.rankDisplay)")
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
        }
    }

    @ViewBuilder
    private func teamTable(section: String, rankings: [TeamStatRanking]) -> some View {
        let rows = rankings.map { r in [r.categoryDisplayName, r.teamValue, r.rankDisplay] }

        VStack(alignment: .leading, spacing: 0) {
            Text(section)
                .font(.headline).padding(.bottom, 6)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    Text("Category")
                        .font(.caption.bold()).foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text("Value")
                        .font(.caption.bold()).foregroundColor(.secondary)
                        .frame(width: 70, alignment: .trailing)
                    Text("Rank")
                        .font(.caption.bold()).foregroundColor(.secondary)
                        .frame(width: 100, alignment: .trailing)
                }
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(Color.secondary.opacity(0.15))
                .accessibilityHidden(true)

                ForEach(Array(rankings.enumerated()), id: \.element.id) { idx, r in
                    HStack(spacing: 0) {
                        Text(r.categoryDisplayName)
                            .font(.subheadline)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text(r.teamValue)
                            .font(.subheadline.bold()).monospacedDigit()
                            .frame(width: 70, alignment: .trailing)
                        Text(r.rankDisplay)
                            .font(.subheadline)
                            .foregroundColor(rankColor(r))
                            .frame(width: 100, alignment: .trailing)
                    }
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(r.categoryDisplayName): \(r.teamValue), \(r.rankDisplay)")
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: ["Category", "Value", "Rank"], rows: rows)
                    .allowsHitTesting(false)
            )
        }
    }

    // Full List is visually identical to Quick List — same compact rows.
    // The only difference is the VoiceOver label includes label words.
    @ViewBuilder
    private func teamFullList(section: String, rankings: [TeamStatRanking]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(section)
                .font(.headline).padding(.bottom, 6)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 0) {
                ForEach(Array(rankings.enumerated()), id: \.element.id) { idx, r in
                    HStack(spacing: 8) {
                        Text(r.categoryDisplayName)
                            .font(.subheadline)
                        Spacer()
                        Text(r.teamValue)
                            .font(.subheadline.bold()).monospacedDigit()
                        Text(r.rankDisplay)
                            .font(.caption)
                            .foregroundColor(rankColor(r))
                    }
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Category: \(r.categoryDisplayName), Value: \(r.teamValue), Rank: \(r.rankDisplay)")
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
        }
    }

    // MARK: - Helpers

    /// Top quarter, middle, bottom, of the league's own size: 118th of 302 isn't red, and 8th of 15
    /// isn't green. With no list to say how many teams there are, the rank says nothing either way.
    private func rankColor(_ ranking: TeamStatRanking) -> Color {
        switch TeamStatRanks.band(rank: ranking.leagueRank, of: ranking.leagueSize) {
        case .top:              return .green
        case .middle, .unknown: return .primary
        case .bottom:           return Color(.systemRed)
        }
    }

    private func emptyState(icon: String, text: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: icon)
                .font(.system(size: 48)).foregroundColor(.secondary)
            Text(text)
                .font(.headline).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
