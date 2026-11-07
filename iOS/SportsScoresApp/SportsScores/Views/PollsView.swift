//
//  PollsView.swift
//  SportsScores
//
//  Phase 6 — College rankings: AP Top 25, Coaches Poll, etc.
//  Shows for: the college sports, as Windows does.
//

import SwiftUI
import UIKit

struct PollsView: View {
    let sport: Sport
    @StateObject private var viewModel = PollsViewModel()
    @State private var viewMode: ViewMode = .quickList

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading rankings…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorMessage, viewModel.polls.isEmpty {
                // A refresh that fails keeps what's showing, as the scores list does.
                errorState(message: error)
            } else if viewModel.polls.isEmpty {
                emptyState
            } else {
                pollsContent
            }
        }
        .task { await viewModel.fetchRankings(for: sport) }
        .refreshable {
            await viewModel.refresh(for: sport)
            // With a list showing, nothing else would say so.
            if let error = viewModel.errorMessage, !viewModel.polls.isEmpty {
                UIAccessibility.post(notification: .announcement, argument: error)
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }

    // MARK: - Main Content

    private var pollsContent: some View {
        VStack(spacing: 0) {
            if let poll = viewModel.selectedPoll {
                switch viewMode {
                case .table:
                    rankingTableView(poll: poll)
                case .quickList:
                    rankingQuickListView(poll: poll)
                case .fullList:
                    rankingList(poll: poll)
                }
            }
            if viewModel.polls.count > 1 {
                Divider()
                pollPicker
                    .padding(.horizontal)
                    .padding(.vertical, 8)
            }
        }
    }

    // MARK: - Poll picker

    /// Every poll ESPN has, in its order. College football has six, the playoff committee's first,
    /// and six segments would cut most of their names short, so past a few it's a menu.
    @ViewBuilder
    private var pollPicker: some View {
        let picker = Picker("Poll", selection: $viewModel.selectedPollIndex) {
            ForEach(viewModel.polls.indices, id: \.self) { idx in
                Text(viewModel.polls[idx].shortName).tag(idx)
            }
        }
        .accessibilityLabel("Select poll")
        // The menu shows "Poll" beside it; Voice Control should answer to either.
        .accessibilityInputLabels(["Poll", "Select poll"])
        if PollsViewModel.usesMenu(pollCount: viewModel.polls.count) {
            HStack {
                Text("Poll")
                    .accessibilityHidden(true)
                Spacer()
                picker.pickerStyle(.menu)
            }
        } else {
            picker.pickerStyle(.segmented)
        }
    }

    // MARK: - Table view mode

    private func rankingTableView(poll: RankingsPoll) -> some View {
        let showsPoints = hasPoints(poll)
        let headers = showsPoints ? ["Rank", "Team", "Record", "Pts"] : ["Rank", "Team", "Record"]
        let rows = poll.ranks.map { rankTableRow($0, showsPoints: showsPoints) }
        return ScrollView {
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    ForEach(headers, id: \.self) { h in
                        Text(h)
                            .font(.caption.bold())
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background(Color.secondary.opacity(0.12))
                    }
                }
                .accessibilityHidden(true)
                ForEach(Array(poll.ranks.enumerated()), id: \.element.id) { idx, entry in
                    HStack(spacing: 0) {
                        ForEach(Array(rankTableRow(entry, showsPoints: showsPoints).enumerated()), id: \.offset) { _, val in
                            Text(val)
                                .font(.subheadline)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 8)
                        }
                    }
                    .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    .accessibilityHidden(true)
                    if idx < poll.ranks.count - 1 { Divider() }
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: headers, rows: rows)
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    /// College hockey's polls have no points, so a column of them would be nothing but dashes.
    private func hasPoints(_ poll: RankingsPoll) -> Bool {
        poll.ranks.contains { $0.points != nil }
    }

    private func rankTableRow(_ entry: RankingsPoll.RankEntry, showsPoints: Bool) -> [String] {
        var row = ["\(entry.current)", entry.teamDisplayName, entry.recordSummary ?? "-"]
        if showsPoints {
            row.append(entry.points.map { String(format: $0 >= 100 ? "%.0f" : "%.1f", $0) } ?? "-")
        }
        return row
    }

    // MARK: - Quick List view mode

    private func rankingQuickListView(poll: RankingsPoll) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 2) {
                ForEach(Array(poll.ranks.enumerated()), id: \.element.id) { idx, entry in
                    Text(rankQuickText(entry))
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                        .accessibilityLabel(rankQuickText(entry))
                }
            }
            .padding(.vertical, 8)
        }
    }

    private func rankQuickText(_ entry: RankingsPoll.RankEntry) -> String {
        let pts = entry.points.map { String(format: $0 >= 100 ? "%.0f" : "%.1f", $0) } ?? ""
        let record = entry.recordSummary.map { " \($0)" } ?? ""
        let ptsStr = pts.isEmpty ? "" : " \u{2014} \(pts) pts"
        return "#\(entry.current) \(entry.teamDisplayName)\(record)\(ptsStr)"
    }

    // MARK: - Ranking list

    private func rankingList(poll: RankingsPoll) -> some View {
        List {
            if let lastUpdated = poll.lastUpdated, !lastUpdated.isEmpty {
                Section {
                    Text("Updated \(lastUpdated)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Section {
                ForEach(poll.ranks) { entry in
                    RankingRow(entry: entry)
                }
            } header: {
                HStack {
                    Text("Rank").frame(width: 36, alignment: .leading)
                    Text("Team")
                    Spacer()
                    Text("Record").frame(width: 52, alignment: .trailing)
                    if hasPoints(poll) {
                        Text("Pts").frame(width: 44, alignment: .trailing)
                    }
                }
                .font(.caption.bold())
                .foregroundColor(.secondary)
            }
        }
        .listStyle(.insetGrouped)
    }

    // MARK: - States

    private func errorState(message: String) -> some View {
        ErrorStateView(message: message) { Task { await viewModel.fetchRankings(for: sport) } }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "list.number")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No rankings available")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("Rankings are published weekly during the season.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
    }
}

// MARK: - Ranking Row

private struct RankingRow: View {
    let entry: RankingsPoll.RankEntry

    var body: some View {
        HStack(spacing: 10) {
            // Current rank
            Text("\(entry.current)")
                .font(.title3.bold())
                .monospacedDigit()
                .frame(width: 28, alignment: .trailing)

            // Movement indicator
            Text(entry.movementText)
                .font(.caption.bold())
                .foregroundColor(movementColor)
                .frame(width: 28, alignment: .leading)

            // Team name
            VStack(alignment: .leading, spacing: 1) {
                Text(entry.teamDisplayName)
                    .font(.subheadline)
                if let record = entry.recordSummary {
                    Text(record)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            // Points
            if let pts = entry.points {
                Text(String(format: pts >= 100 ? "%.0f" : "%.1f", pts))
                    .font(.caption.bold())
                    .monospacedDigit()
                    .foregroundColor(.secondary)
                    .frame(width: 44, alignment: .trailing)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    private var movementColor: Color {
        if entry.movementDirection > 0 { return .green }
        if entry.movementDirection < 0 { return .red }
        return .secondary
    }

    private var accessibilityLabel: String {
        var parts: [String] = []
        parts.append("Ranked \(entry.current)")
        parts.append(entry.teamDisplayName)
        if let record = entry.recordSummary { parts.append(record) }

        let mov = entry.movementDirection
        if mov > 0 { parts.append("Up \(mov)") }
        else if mov < 0 { parts.append("Down \(abs(mov))") }
        else if entry.previous == nil || entry.previous == 0 { parts.append("New to rankings") }
        else { parts.append("No change") }

        if let pts = entry.points {
            parts.append("\(Int(pts)) points")
        }
        return parts.joined(separator: ", ")
    }
}

#Preview {
    NavigationStack {
        PollsView(sport: .ncaaf)
            .navigationTitle("NCAAF Rankings")
    }
}
