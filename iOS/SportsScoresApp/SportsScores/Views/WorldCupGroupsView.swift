//
//  WorldCupGroupsView.swift
//  SportsScores
//
//  Displays all World Cup group standings (Groups A–L) in three view modes:
//  Table · Quick List · Full List.  Each group is a section; within each
//  section the four teams are sorted by rank as returned by the API.
//
//  Advancement status is spoken inline by VoiceOver so screen readers never
//  have to rely on the colour-coded dot alone.
//

import SwiftUI

struct WorldCupGroupsView: View {

    let groups: [WorldCupGroup]
    let sport: Sport
    let phases: [WorldCupPhase]
    let isLoading: Bool
    let error: String?
    let onRetry: () -> Void

    @State private var viewMode: ViewMode = .savedDefault()

    private let headers = ["Team", "GP", "W", "D", "L", "GD", "Pts"]

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading group standings…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityLabel("Loading World Cup group standings")
            } else if let err = error {
                ErrorStateView(message: err, retryAction: onRetry)
            } else if groups.isEmpty {
                emptyState
            } else {
                groupsContent
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }

    // MARK: - Main content

    private var groupsContent: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                ForEach(groups) { group in
                    Section {
                        switch viewMode {
                        case .table:
                            tableSection(for: group)
                        case .quickList:
                            quickListSection(for: group)
                        case .fullList:
                            fullListSection(for: group)
                        }

                    } header: {
                        Text(group.name)
                            .font(.headline)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal)
                            .padding(.vertical, 8)
                            .background(Color(uiColor: .systemBackground))
                            .accessibilityAddTraits(.isHeader)
                    }
                }
            }
        }
    }

    // MARK: - Table mode

    private func tableSection(for group: WorldCupGroup) -> some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                Text(headers[0])
                    .font(.caption.bold())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 8)
                ForEach(headers.dropFirst(), id: \.self) { col in
                    Text(col)
                        .font(.caption.bold())
                        .frame(width: 38)
                }
            }
            .padding(.vertical, 6)
            .background(Color.secondary.opacity(0.15))

            Divider()

            ForEach(Array(group.entries.enumerated()), id: \.element.id) { idx, entry in
                HStack(spacing: 0) {
                    // Team abbreviation + advancement dot
                    HStack(spacing: 4) {
                        if entry.advancementNote != nil {
                            Circle()
                                .fill(Color.green)
                                .frame(width: 7, height: 7)
                                .accessibilityHidden(true)
                        }
                        Text(entry.teamAbbreviation)
                            .font(.subheadline.bold())
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 8)

                    ForEach(Array(entry.tableRow.dropFirst().enumerated()), id: \.offset) { _, value in
                        Text(value)
                            .font(.caption.monospacedDigit())
                            .frame(width: 38)
                    }
                }
                .padding(.vertical, 7)
                .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                .accessibilityHidden(true)

                if idx < group.entries.count - 1 {
                    Divider().padding(.leading, 8)
                }
            }
        }
        // UIKit accessible table overlay handles VoiceOver navigation in table mode.
        .accessibilityHidden(true)
        .overlay(
            AccessibleDataTable(
                headers: headers,
                rows: group.entries.map { $0.tableRow }
            )
            .allowsHitTesting(false)
        )
        .padding(.bottom, 16)
    }

    // MARK: - Quick List mode

    private func quickListSection(for group: WorldCupGroup) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(group.entries) { entry in
                NavigationLink(destination: WorldCupTeamView(
                    entry: entry, group: group, sport: sport, phases: phases)) {
                    Text(entry.quickListText)
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(entry.accessibilityLabel())
                .accessibilityHint("Opens \(entry.teamDisplayName) tournament path")
            }
        }
        .padding(.bottom, 16)
    }

    // MARK: - Full List mode

    private func fullListSection(for group: WorldCupGroup) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(group.entries) { entry in
                NavigationLink(destination: WorldCupTeamView(
                    entry: entry, group: group, sport: sport, phases: phases)) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            if entry.advancementNote != nil {
                                Circle()
                                    .fill(Color.green)
                                    .frame(width: 8, height: 8)
                                    .accessibilityHidden(true)
                            }
                            Text(entry.teamDisplayName)
                                .font(.headline)
                        }
                        Text(entry.fullListText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.05))
                    .cornerRadius(8)
                    .padding(.horizontal, 12)
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(entry.accessibilityLabel())
                .accessibilityHint("Opens \(entry.teamDisplayName) tournament path")
            }
        }
        .padding(.bottom, 16)
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "list.bullet.clipboard")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text("Group standings not available yet.")
                .font(.headline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    NavigationStack {
        WorldCupGroupsView(
            groups: [
                WorldCupGroup(id: "1", name: "Group A", entries: [

                    WorldCupGroupEntry(id: "203", teamAbbreviation: "MEX", teamDisplayName: "Mexico",
                                       rank: 1, gamesPlayed: 2, wins: 1, draws: 1, losses: 0,
                                       goalsFor: 3, goalsAgainst: 1, goalDifference: 2, points: 4,
                                       advancementNote: "Advance to Round of 32"),
                    WorldCupGroupEntry(id: "100", teamAbbreviation: "CZE", teamDisplayName: "Czech Republic",
                                       rank: 2, gamesPlayed: 2, wins: 1, draws: 0, losses: 1,
                                       goalsFor: 2, goalsAgainst: 2, goalDifference: 0, points: 3,
                                       advancementNote: "Advance to Round of 32"),
                    WorldCupGroupEntry(id: "101", teamAbbreviation: "KOR", teamDisplayName: "South Korea",
                                       rank: 3, gamesPlayed: 2, wins: 0, draws: 1, losses: 1,
                                       goalsFor: 1, goalsAgainst: 2, goalDifference: -1, points: 1,
                                       advancementNote: nil),
                    WorldCupGroupEntry(id: "102", teamAbbreviation: "RSA", teamDisplayName: "South Africa",
                                       rank: 4, gamesPlayed: 2, wins: 0, draws: 0, losses: 2,
                                       goalsFor: 0, goalsAgainst: 1, goalDifference: -1, points: 0,
                                       advancementNote: nil),
                ])
            ],
            sport: .worldCup,
            phases: WorldCupPhase.wc2026,
            isLoading: false,
            error: nil,
            onRetry: {}
        )
        .navigationTitle("Groups")
        .environmentObject(AppSettings())
    }
}
