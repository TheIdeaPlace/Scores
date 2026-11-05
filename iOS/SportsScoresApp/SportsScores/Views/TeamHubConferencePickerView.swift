//
//  TeamHubConferencePickerView.swift
//  SportsScores
//
//  Second level of Team Hub navigation for college sports — pick a conference.
//

import SwiftUI

struct TeamHubConferencePickerView: View {
    let sport: Sport
    @State private var conferences: [ConferenceGroup] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    var body: some View {
        Group {
            if isLoading {
                ProgressView("Loading conferences…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text(error)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { Task { await loadConferences() } }
                        .buttonStyle(.borderedProminent)
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(conferences) { conference in
                    NavigationLink(destination: TeamHubTeamPickerView(sport: sport, conferenceName: conference.name, preloadedTeams: conference.teams)) {
                        HStack(spacing: 12) {
                            Image(systemName: "building.columns")
                                .font(.title3)
                                .foregroundColor(.accentColor)
                                .frame(width: 30)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(conference.name)
                                    .font(.body)
                                Text("\(conference.teams.count) teams")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(conference.name), \(conference.teams.count) teams")
                }
            }
        }
        .navigationTitle(sport.displayName)
        .task { await loadConferences() }
    }

    private func loadConferences() async {
        isLoading = true
        errorMessage = nil
        do {
            let fetched = try await apiService.fetchConferencesWithTeams(for: sport)
            if fetched.isEmpty {
                // No conference structure — skip to team picker. A failure here shows the
                // error and Retry below, rather than a row reading "All Teams, 0 teams".
                let teams = try await apiService.fetchTeamsForSport(sport: sport)
                conferences = [ConferenceGroup(id: "all", name: "All Teams",
                                               teams: teams.sorted { $0.displayName < $1.displayName })]
            } else {
                conferences = fetched
            }
        } catch {
            errorMessage = APIError.unavailable("conferences")
        }
        isLoading = false
    }
}

#Preview {
    NavigationStack { TeamHubConferencePickerView(sport: .ncaaf) }
}
