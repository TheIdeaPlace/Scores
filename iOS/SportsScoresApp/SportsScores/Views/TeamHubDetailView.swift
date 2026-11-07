//
//  TeamHubDetailView.swift
//  SportsScores
//
//  Team Hub detail screen — five-tab experience for a single team.
//

import SwiftUI

enum TeamHubTab: String, CaseIterable {
    case info         = "Info"
    case roster       = "Roster"
    case stats        = "Stats"
    case news         = "News"
    case schedule     = "Schedule"
    case transactions = "Transactions"

    var systemImage: String {
        switch self {
        case .info:         return "info.circle"
        case .roster:       return "person.3"
        case .stats:        return "chart.bar"
        case .news:         return "newspaper"
        case .schedule:     return "calendar"
        case .transactions: return "arrow.left.arrow.right"
        }
    }
}

struct TeamHubDetailView: View {
    let team: TransactionTeam
    let sport: Sport

    @StateObject private var viewModel: TeamHubViewModel
    @State private var selectedTab: TeamHubTab
    @State private var teamStatsViewMode: ViewMode = .quickList
    @EnvironmentObject private var appSettings: AppSettings

    init(team: TransactionTeam, sport: Sport, initialTab: TeamHubTab = .info) {
        self.team = team
        self.sport = sport
        _viewModel = StateObject(wrappedValue: TeamHubViewModel(teamId: team.id, sport: sport))
        _selectedTab = State(initialValue: initialTab)
    }

    private var isFavorite: Bool {
        appSettings.isFavorite(teamId: team.id, sport: sport)
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            TeamInfoTabView(viewModel: viewModel, team: team, sport: sport)
            .tabItem {
                Label(TeamHubTab.info.rawValue, systemImage: TeamHubTab.info.systemImage)
            }
            .tag(TeamHubTab.info)

            TeamRosterTabView(viewModel: viewModel)
            .tabItem {
                Label(TeamHubTab.roster.rawValue, systemImage: TeamHubTab.roster.systemImage)
            }
            .tag(TeamHubTab.roster)

            TeamStatsTabView(teamId: team.id, teamAbbreviation: team.abbreviation, sport: sport, viewMode: $teamStatsViewMode)
            .tabItem {
                Label(TeamHubTab.stats.rawValue, systemImage: TeamHubTab.stats.systemImage)
            }
            .tag(TeamHubTab.stats)

            TeamNewsTabView(viewModel: viewModel)
            .tabItem {
                Label(TeamHubTab.news.rawValue, systemImage: TeamHubTab.news.systemImage)
            }
            .tag(TeamHubTab.news)

            TeamScheduleTabView(viewModel: viewModel, team: team, sport: sport)
            .tabItem {
                Label(TeamHubTab.schedule.rawValue, systemImage: TeamHubTab.schedule.systemImage)
            }
            .tag(TeamHubTab.schedule)

            TeamTransactionsTabView(team: team, sport: sport)
            .tabItem {
                Label(TeamHubTab.transactions.rawValue, systemImage: TeamHubTab.transactions.systemImage)
            }
            .tag(TeamHubTab.transactions)
        }
        .navigationTitle(team.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 16) {
                    if selectedTab == .stats {
                        ViewModeMenuButton(currentMode: $teamStatsViewMode)
                    }
                    let listenOptions = RadioLinks.shared.teamListenOptions(
                        sport.rawValue, teamId: team.id, teamName: team.displayName)
                    if !listenOptions.isEmpty {
                        Menu {
                            ForEach(listenOptions) { option in
                                Link(option.label, destination: option.url)
                            }
                        } label: {
                            Image(systemName: "radio")
                                .foregroundColor(.accentColor)
                        }
                        .accessibilityLabel("Listen on the Radio")
                        .accessibilityHint("Places to hear \(team.displayName) games. Each opens outside the app.")
                    }
                    Button {
                        if isFavorite {
                            appSettings.removeFavorite(teamId: team.id, sport: sport)
                        } else {
                            appSettings.addFavorite(team, sport: sport)
                        }
                    } label: {
                        Image(systemName: isFavorite ? "star.fill" : "star")
                            .foregroundColor(.accentColor)
                    }
                    .accessibilityLabel(isFavorite ? "Remove from Favorites" : "Add to Favorites")
                }
            }
        }
        .onChange(of: selectedTab) { _, tab in
            Task { await loadTabIfNeeded(tab) }
        }
        .task { await viewModel.loadInfo() }
    }

    private func loadTabIfNeeded(_ tab: TeamHubTab) async {
        switch tab {
        case .info:         await viewModel.loadInfo()
        case .roster:       await viewModel.loadRoster()
        case .stats:        break  // TeamStatsTabView manages its own loading
        case .news:         await viewModel.loadNews()
        case .schedule:     await viewModel.loadSchedule()
        case .transactions: break  // TeamTransactionsTabView manages its own loading
        }
    }
}

#Preview {
    let mockTeam = TransactionTeam(
        id: "10", location: "New York", name: "Yankees",
        abbreviation: "NYY", displayName: "New York Yankees",
        color: "132448", logos: nil
    )
    return NavigationStack {
        TeamHubDetailView(team: mockTeam, sport: .mlb)
    }
}
