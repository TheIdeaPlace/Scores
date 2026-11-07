//
//  GameRadioView.swift
//  SportsScores
//
//  The Bench's Game Radio: where to hear each league's games. The Windows app has
//  the same list as a league's Game Radio row. Both read radio_links.json.
//

import SwiftUI

struct GameRadioView: View {
    private let links = RadioLinks.shared

    var body: some View {
        List {
            ForEach(RadioLinks.directoryLeagues, id: \.league) { entry in
                if links.covers(entry.league) {
                    NavigationLink(destination: GameRadioLeagueView(league: entry.league, title: entry.title)) {
                        Label(entry.title, systemImage: "radio")
                    }
                }
            }
        }
        .navigationTitle("Game Radio")
    }
}

struct GameRadioLeagueView: View {
    let league: String
    let title: String
    private let links = RadioLinks.shared

    var body: some View {
        List {
            ListenSection(header: "Every game", options: links.leagueOptions(league))
            Section {
                ForEach(links.directory(league)) { team in
                    NavigationLink(destination: GameRadioTeamView(league: league, team: team)) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(team.name).font(.headline)
                            if !team.station.isEmpty {
                                Text(team.station).font(.caption).foregroundColor(.secondary)
                            }
                        }
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityValue(team.links.isEmpty ? "No link yet" : "")
                }
            } header: {
                Text("Teams")
            } footer: {
                if league == "NCAAF" {
                    Text("A school's radio network carries its football and basketball.")
                }
            }
        }
        .navigationTitle("\(title) Radio")
    }
}

struct GameRadioTeamView: View {
    let league: String
    let team: RadioDirectoryTeam
    private let links = RadioLinks.shared

    var body: some View {
        List {
            if !team.station.isEmpty {
                Section {
                    Text(team.station)
                } header: {
                    Text("Station")
                }
            }
            ListenSection(header: "Listen",
                          options: links.teamListenOptions(league, teamId: team.id, teamName: team.name))
        }
        .navigationTitle(team.name)
    }
}

#Preview {
    NavigationStack { GameRadioView() }
}
