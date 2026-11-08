//
//  ContentView.swift
//  SportsScores
//
//  Root three-tab experience:
//    Tab 1 — Scores  (home page: sports list, live scores, soccer hub)
//    Tab 2 — The Bench (venue tours, spatial exploration tools)
//    Tab 3 — Settings
//

import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            SportSelectionView()
                .tabItem {
                    Label("Scores", systemImage: "sportscourt")
                }

            NavigationStack {
                TheBenchView()
            }
            .tabItem {
                Label("The Bench", systemImage: "waveform.and.mic")
            }

            NavigationStack {
                SettingsView()
            }
            .tabItem {
                Label("Settings", systemImage: "gearshape")
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppSettings())
        .environmentObject(MonitoringStore())
}
