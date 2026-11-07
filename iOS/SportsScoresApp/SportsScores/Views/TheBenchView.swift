//
//  TheBenchView.swift
//  SportsScores
//
//  Hub for all venue audio touch tours. Accessible from the The Bench tab.
//  Each sport plays continuous terrain-based audio as you drag across the field.
//

import SwiftUI

struct TheBenchView: View {
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        List {
            Section {
                rowLink(
                    title: "Team Hub",
                    subtitle: "Explore any team — info, roster, news & more",
                    icon: "person.3.fill",
                    destination: TeamHubSportPickerView()
                )
            }

            Section {
                rowLink(
                    title: "NFL Draft",
                    subtitle: "Pick-by-pick results & history",
                    icon: "person.3.sequence.fill",
                    destination: NFLDraftView()
                )
                rowLink(
                    title: "Fantasy Cheatsheet",
                    subtitle: "Draft board · sortable · custom scoring",
                    icon: "list.clipboard",
                    destination: FantasyCheatsheetView()
                )
            }

            Section {
                rowLink(
                    title: "Game Radio",
                    subtitle: "Where to listen · every team's radio, SiriusXM & more",
                    icon: "radio",
                    destination: GameRadioView()
                )
            }

            Section {
                rowLink(
                    title: "Transaction Hub",
                    subtitle: "Player moves, signings & releases",
                    icon: "arrow.left.arrow.right",
                    destination: TransactionHubView()
                )
            }

            Section {
                rowLink(
                    title: "MLB Stadiums",
                    subtitle: "All 30 parks — real wall distances",
                    icon: "figure.baseball",
                    destination: BaseballTourInfoView()
                )
                rowLink(
                    title: "Strike Zone",
                    subtitle: "17\" wide · 24\" tall · audio touch exploration",
                    icon: "square.grid.3x3",
                    destination: StrikeZoneInfoView()
                )
            } header: {
                Text("Baseball")
            }

            Section {
                rowLink(
                    title: "NFL Football Field",
                    subtitle: "120 yds · yard lines · hash marks · goal posts",
                    icon: "figure.american.football",
                    destination: FootballTourInfoView(variant: .nfl)
                )
                rowLink(
                    title: "CFL Football Field",
                    subtitle: "150 yds × 65 yds · 20-yd end zones · goal posts on goal line",
                    icon: "figure.american.football",
                    destination: FootballTourInfoView(variant: .cfl)
                )
            } header: {
                Text("Football")
            }

            Section {
                rowLink(
                    title: "NHL Hockey Rink",
                    subtitle: "200 ft · zones · blue lines · creases",
                    icon: "figure.ice.hockey",
                    destination: HockeyTourInfoView()
                )
            } header: {
                Text("Hockey")
            }

            Section {
                rowLink(
                    title: "NBA Basketball Court",
                    subtitle: "94 ft · paint · 3-point arc · free throw line",
                    icon: "figure.basketball",
                    destination: BasketballTourInfoView()
                )
            } header: {
                Text("Basketball")
            }

            Section {
                rowLink(
                    title: "Soccer Pitch",
                    subtitle: "105m × 68m · center circle · penalty areas · goals",
                    icon: "figure.soccer",
                    destination: SoccerTourInfoView()
                )
            } header: {
                Text("Soccer")
            }

            Section {
                rowLink(
                    title: "Race Tracks",
                    subtitle: "Daytona · Talladega · Indianapolis · Bristol · Charlotte",
                    icon: "flag.checkered",
                    destination: RaceTrackHubView()
                )
            } header: {
                Text("Auto Racing")
            }

            // The 2026 World Cup has concluded; its hub lives here as an archive
            // rather than on the Scores home page. The existing Settings toggle
            // still hides/shows it.
            if appSettings.worldCupHubEnabled {
                Section {
                    rowLink(
                        title: "2026 FIFA World Cup",
                        subtitle: "Final bracket, results & standings · Jun 11 – Jul 19",
                        icon: Sport.worldCup.systemImage,
                        destination: WorldCupHubView(sport: .worldCup)
                    )
                } header: {
                    Text("Archive")
                }
            }
        }
        .navigationTitle("The Bench")
    }

    @ViewBuilder
    private func rowLink<Dest: View>(title: String, subtitle: String, icon: String, destination: Dest) -> some View {
        NavigationLink(destination: destination) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(.accentColor)
                    .frame(width: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.headline)
                    Text(subtitle).font(.caption).foregroundColor(.secondary)
                }
            }
            .padding(.vertical, 4)
        }
        .accessibilityLabel("\(title). \(subtitle)")
    }
}

#Preview {
    NavigationStack { TheBenchView() }
}
