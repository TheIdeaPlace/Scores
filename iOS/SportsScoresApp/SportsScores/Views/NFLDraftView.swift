//
//  NFLDraftView.swift
//  SportsScores
//

import SwiftUI

struct NFLDraftView: View {
    @StateObject private var viewModel = NFLDraftViewModel()

    var body: some View {
        List {
            // MARK: Pickers
            Section {
                Picker("Year", selection: $viewModel.selectedYear) {
                    ForEach(viewModel.availableYears, id: \.self) { year in
                        Text(String(year)).tag(year)
                    }
                }
                .pickerStyle(.menu)

                if let response = viewModel.response, !viewModel.isLoading, !response.picks.isEmpty {
                    Picker("Round", selection: $viewModel.selectedRound) {
                        ForEach(1...viewModel.numberOfRounds, id: \.self) { round in
                            Text("Rd \(round)")
                                .accessibilityLabel("Round \(round)")
                                .tag(round)
                        }
                    }
                    .pickerStyle(.segmented)
                }
            }

            // MARK: Content
            if viewModel.isLoading {
                Section {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                    .accessibilityLabel("Loading draft data")
                }
            } else if let errorMsg = viewModel.errorMessage {
                Section {
                    Text(errorMsg)
                        .foregroundColor(.secondary)
                }
            } else if let response = viewModel.response {
                if response.picks.isEmpty {
                    Section {
                        Text("No pick data available for the \(String(viewModel.selectedYear)) NFL Draft.")
                            .foregroundColor(.secondary)
                    }
                } else {
                    // Picks for the selected round
                    let roundPicks = viewModel.picksForSelectedRound
                    Section("Round \(viewModel.selectedRound)") {
                        if roundPicks.isEmpty {
                            Text("No picks in round \(viewModel.selectedRound).")
                                .foregroundColor(.secondary)
                        } else {
                            ForEach(roundPicks) { pick in
                                pickRow(pick)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("NFL Draft")
        .task(id: viewModel.selectedYear) { await viewModel.fetchDraft() }
        .refreshable { await viewModel.fetchDraft() }
    }

    // MARK: - Pick row

    @ViewBuilder
    private func pickRow(_ pick: DraftPick) -> some View {
        let team = viewModel.team(for: pick)
        let teamAbbr = team.flatMap { $0.abbreviation.isEmpty ? nil : $0.abbreviation } ?? "?"
        let posAbbr: String? = pick.athlete.flatMap { viewModel.positionAbbr(for: $0.position) }

        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text("#\(pick.overall)")
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.secondary)
                    .frame(minWidth: 34, alignment: .trailing)
                Text(teamAbbr)
                    .font(.headline)
                Text("—")
                    .foregroundColor(.secondary)
                if pick.isCompleted, let athlete = pick.athlete {
                    Text(athlete.displayName)
                        .font(.headline)
                    if let pos = posAbbr {
                        Text(pos)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    if let college = athlete.team?.collegeName {
                        Text(college)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else {
                    Text("TBD")
                        .font(.headline)
                        .italic()
                        .foregroundColor(.secondary)
                }
            }
            if pick.hasTradeNote {
                Text(pick.tradeNote)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.leading, 40)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(pickAccessibilityLabel(pick, team: team, posAbbr: posAbbr))
    }

    private func pickAccessibilityLabel(_ pick: DraftPick, team: DraftTeam?, posAbbr: String?) -> String {
        let teamName = team?.shortDisplayName ?? team?.abbreviation ?? "Unknown team"
        var parts: [String] = ["Pick \(pick.overall)", teamName]
        if pick.isCompleted, let athlete = pick.athlete {
            parts.append(athlete.displayName)
            if let pos = posAbbr { parts.append(pos) }
            if let college = athlete.team?.collegeName { parts.append(college) }
        } else {
            parts.append("TBD")
        }
        if pick.hasTradeNote {
            parts.append("Via trade: \(pick.tradeNote)")
        }
        return parts.joined(separator: ". ")
    }
}
