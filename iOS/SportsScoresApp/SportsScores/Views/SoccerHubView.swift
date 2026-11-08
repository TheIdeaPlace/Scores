//
//  SoccerHubView.swift
//  SportsScores
//
//  Soccer entry point — mirrors SportSelectionView but scoped to soccer.
//  Shows a "Live Soccer" row (all leagues) and one row per soccer league,
//  each navigating into the standard ScoresView.
//

import SwiftUI

struct SoccerHubView: View {
    @StateObject private var hubVM: SoccerHubViewModel

    init(initialDate: Date? = nil) {
        _hubVM = StateObject(wrappedValue: SoccerHubViewModel(initialDate: initialDate))
    }

    var body: some View {
        VStack(spacing: 0) {
            dateNavigationBar
                .padding()
                .background(Color.secondary.opacity(0.05))
                .overlay(alignment: .bottom) { Divider() }

            List {
                // Live Soccer — all leagues combined
                Section {
                    NavigationLink(destination: SoccerLiveView()) {
                        HStack {
                            Image(systemName: "circle.fill")
                                .foregroundColor(.red)
                                .font(.title2)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Live Soccer")
                                    .font(.headline)
                                Text("All leagues — Live, completed & upcoming")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .accessibilityLabel("Live Soccer — view all games across all soccer leagues")
                } header: {
                    Text(hubVM.headerText)
                }

                // Individual leagues
                Section {
                    ForEach(Sport.soccerLeagues) { league in
                        NavigationLink(destination: ScoresView(sport: league,
                                                               initialDate: hubVM.selectedDate)) {
                            LeagueRowView(league: league,
                                         count: hubVM.gameCounts[league],
                                         isLoading: hubVM.isLoading)
                        }
                        .accessibilityLabel(hubVM.accessibilityLabel(for: league))
                    }
                } header: {
                    Text("Browse by League")
                }
            }
        }
        .navigationTitle("Soccer")
        .task { await hubVM.load() }
    }

    // MARK: - Date navigation bar (same pattern as SportSelectionView)

    private var dateNavigationBar: some View {
        HStack(spacing: 8) {
            Button {
                Task { await hubVM.goBack() }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(hubVM.isLoading || !hubVM.canNavigateBackward)
            .accessibilityLabel("Previous Day")

            Spacer()

            VStack(spacing: 2) {
                Text(hubVM.selectedDate.formatted(date: .abbreviated, time: .omitted))
                    .font(.subheadline.bold())
                Text(dayOfWeek(hubVM.selectedDate))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(accessibilityDate(hubVM.selectedDate))

            Spacer()

            Button {
                Task { await hubVM.goForward() }
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(hubVM.isLoading || !hubVM.canNavigateForward)
            .accessibilityLabel("Next Day")

            if !hubVM.isOnToday {
                Button("Today") {
                    Task { await hubVM.goToToday() }
                }
                .font(.caption)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .transition(.opacity)
            }
        }
    }

    private func dayOfWeek(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE"
        return fmt.string(from: date)
    }

    private func accessibilityDate(_ date: Date) -> String {
        if ScoreboardDay.isToday(date)     { return "Today" }
        if ScoreboardDay.isYesterday(date) { return "Yesterday" }
        if ScoreboardDay.isTomorrow(date)  { return "Tomorrow" }
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE, MMMM d"
        return fmt.string(from: date)
    }
}

// MARK: - League row with game count badge

private struct LeagueRowView: View {
    let league: Sport
    let count: Int?
    let isLoading: Bool

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: league.systemImage)
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 36)
            Text(league.displayName)
                .font(.headline)
            Spacer()
            gameBadge
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var gameBadge: some View {
        if isLoading {
            ProgressView()
                .scaleEffect(0.75)
                .frame(width: 36, height: 20)
        } else if let n = count, n > 0 {
            Text("\(n)")
                .font(.system(.caption, design: .rounded).bold())
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(badgeColor(n), in: Capsule())
                .accessibilityHidden(true)
        } else {
            Text("—")
                .font(.caption)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
        }
    }

    private func badgeColor(_ n: Int) -> Color {
        switch n {
        case 1...5:  return .blue
        case 6...10: return .orange
        default:     return .red
        }
    }
}

#Preview {
    NavigationStack {
        SoccerHubView()
            .environmentObject(AppSettings())
            .environmentObject(MonitoringStore())
    }
}
