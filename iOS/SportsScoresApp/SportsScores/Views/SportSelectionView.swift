//
//  SportSelectionView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI

// MARK: - View

struct SportSelectionView: View {
    @StateObject private var homeVM = HomeViewModel()
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Date navigation bar
                dateNavigationBar
                    .padding()
                    .background(Color.secondary.opacity(0.05))
                    .overlay(alignment: .bottom) {
                        Divider()
                    }

                List {
                    // Live Scores - All Sports
                    Section {
                        NavigationLink(destination: LiveScoresView()) {
                            HStack {
                                Image(systemName: "circle.fill")
                                    .foregroundColor(.red)
                                    .font(.title2)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Live Scores")
                                        .font(.headline)
                                    Text("All sports - Live, completed & upcoming")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                        .accessibilityLabel("Live Scores - View all games from all sports")
                    } header: {
                        Text(headerText)
                    }
                    
                    // Individual Sports
                    Section {
                        ForEach(appSettings.visibleSports) { sport in
                            NavigationLink(destination: ScoresView(sport: sport, initialDate: homeVM.selectedDate)) {
                                SportRowView(sport: sport,
                                             count: homeVM.gameCounts[sport],
                                             isLoading: homeVM.isLoading)
                            }
                            .accessibilityLabel(accessibilityLabel(for: sport))
                        }

                        // Soccer hub — single entry for all soccer leagues
                        if appSettings.soccerHubEnabled {
                            NavigationLink(destination: SoccerHubView(initialDate: homeVM.selectedDate)) {
                                HStack(spacing: 12) {
                                    Image(systemName: "figure.soccer")
                                        .font(.title2)
                                        .foregroundColor(.accentColor)
                                        .frame(width: 36)
                                    Text("Soccer")
                                        .font(.headline)
                                    Spacer()
                                    soccerBadge
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityLabel(soccerAccessibilityLabel)
                        }

                        // Auto Racing hub — F1, IndyCar, NASCAR Cup
                        if appSettings.racingHubEnabled {
                            NavigationLink(destination: RacingHubView()) {
                                HStack(spacing: 12) {
                                    Image(systemName: "flag.checkered")
                                        .font(.title2)
                                        .foregroundColor(.accentColor)
                                        .frame(width: 36)
                                    Text("Auto Racing")
                                        .font(.headline)
                                    Spacer()
                                    Text("F1 · IndyCar · NASCAR")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityLabel("Auto Racing — Formula 1, IndyCar, and NASCAR Cup Series")
                        }

                        // Golf hub — PGA Tour and LPGA Tour
                        if appSettings.golfHubEnabled {
                            NavigationLink(destination: GolfHubView()) {
                                HStack(spacing: 12) {
                                    Image(systemName: "figure.golf")
                                        .font(.title2)
                                        .foregroundColor(.accentColor)
                                        .frame(width: 36)
                                    Text("Golf")
                                        .font(.headline)
                                    Spacer()
                                    Text("PGA · LPGA")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityLabel("Golf — PGA Tour and LPGA Tour")
                        }

                        // Canadian Football League (separate data source)
                        if appSettings.cflEnabled {
                            NavigationLink(destination: ScoresView(sport: .cfl, initialDate: homeVM.selectedDate)) {
                                HStack(spacing: 12) {
                                    Image(systemName: Sport.cfl.systemImage)
                                        .font(.title2)
                                        .foregroundColor(.accentColor)
                                        .frame(width: 36)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("CFL")
                                            .font(.headline)
                                        Text("Canadian Football League")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    cflBadge
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityLabel(cflAccessibilityLabel)
                        }

                        // 2026 FIFA World Cup has concluded — its hub now lives at
                        // the bottom of The Bench (see TheBenchView) as an archive.

                        // 2027 FIFA Women's World Cup hub
                        if appSettings.worldCupWomensHubEnabled {
                            NavigationLink(destination: WorldCupHubView(sport: .worldCupWomens)) {
                                HStack(spacing: 12) {
                                    Image(systemName: Sport.worldCupWomens.systemImage)
                                        .font(.title2)
                                        .foregroundColor(.accentColor)
                                        .frame(width: 36)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("2027 FIFA Women's World Cup")
                                            .font(.headline)
                                        Text("2027 · Brazil")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                            }
                            .accessibilityLabel("2027 FIFA Women's World Cup hub — Scores, Groups, Bracket, and News")
                        }
                    } header: {
                        Text("Browse by Sport")
                    }


                }
            }
            .navigationTitle("Sports Scores")
            .task { await homeVM.load() }
        }
    }

    private var dateNavigationBar: some View {
        HStack(spacing: 8) {
            Button {
                Task { await homeVM.goBack() }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(homeVM.isLoading || !homeVM.canNavigateBackward)
            .accessibilityLabel("Previous Day")

            Spacer()

            VStack(spacing: 2) {
                Text(homeVM.selectedDate.formatted(date: .abbreviated, time: .omitted))
                    .font(.subheadline.bold())
                Text( dayOfWeek(homeVM.selectedDate))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(accessibilityDate(homeVM.selectedDate))

            Spacer()

            Button {
                Task { await homeVM.goForward() }
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(homeVM.isLoading || !homeVM.canNavigateForward)
            .accessibilityLabel("Next Day")

            // Today button (if not on today)
            if !ScoreboardDay.isToday(homeVM.selectedDate) {
                Button("Today") {
                    Task { await homeVM.goToToday() }
                }
                .font(.caption)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .transition(.opacity)
            }
        }
    }

    private var headerText: String {
        if ScoreboardDay.isToday(homeVM.selectedDate) {
            return "Today's Games"
        }
        return "\(dayOfWeek(homeVM.selectedDate))'s Games"
    }

    private func dayOfWeek(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE"
        return formatter.string(from: date)
    }

    private func accessibilityDate(_ date: Date) -> String {
        if ScoreboardDay.isToday(date) { return "Today" }
        if ScoreboardDay.isYesterday(date) { return "Yesterday" }
        if ScoreboardDay.isTomorrow(date) { return "Tomorrow" }
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d"
        return formatter.string(from: date)
    }

    private func accessibilityLabel(for sport: Sport) -> String {
        guard !homeVM.isLoading else { return sport.displayName }
        let count = homeVM.gameCounts[sport] ?? 0
        if count == 0 { return "\(sport.displayName), no games today" }
        return "\(sport.displayName), \(count) \(count == 1 ? "game" : "games") today"
    }

    @ViewBuilder
    private var soccerBadge: some View {
        if homeVM.isLoading {
            ProgressView()
                .scaleEffect(0.75)
                .frame(width: 36, height: 20)
        } else if homeVM.soccerGameCount > 0 {
            let n = homeVM.soccerGameCount
            Text("\(n)")
                .font(.system(.caption, design: .rounded).bold())
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(n > 10 ? Color.red : n > 5 ? Color.orange : Color.blue, in: Capsule())
                .accessibilityHidden(true)
        } else {
            Text("—")
                .font(.caption)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
        }
    }

    private var soccerAccessibilityLabel: String {
        guard !homeVM.isLoading else { return "Soccer" }
        let n = homeVM.soccerGameCount
        if n == 0 { return "Soccer, no games today" }
        return "Soccer, \(n) \(n == 1 ? "game" : "games") today across all leagues"
    }

    @ViewBuilder
    private var cflBadge: some View {
        if homeVM.isLoading {
            ProgressView()
                .scaleEffect(0.75)
                .frame(width: 36, height: 20)
        } else if homeVM.cflGameCount > 0 {
            Text("\(homeVM.cflGameCount)")
                .font(.system(.caption, design: .rounded).bold())
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.blue, in: Capsule())
                .accessibilityHidden(true)
        } else {
            Text("—")
                .font(.caption)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
        }
    }

    private var cflAccessibilityLabel: String {
        guard !homeVM.isLoading else { return "CFL, Canadian Football League" }
        let n = homeVM.cflGameCount
        if n == 0 { return "CFL, Canadian Football League, no games today" }
        return "CFL, Canadian Football League, \(n) \(n == 1 ? "game" : "games") today"
    }
}

// MARK: - Sport row with game count badge

private struct SportRowView: View {
    let sport: Sport
    let count: Int?       // nil while loading
    let isLoading: Bool

    var body: some View {
        HStack(spacing: 12) {
            Text(sport.icon)
                .font(.title2)
                .frame(width: 36)

            Text(sport.displayName)
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
                .accessibilityHidden(true)   // spoken via accessibilityLabel on the row
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
    SportSelectionView()
        .environmentObject(AppSettings())
        .environmentObject(MonitoringStore())
}
