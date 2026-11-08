//
//  SportsScoresApp.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI

@main
struct SportsScoresApp: App {
    @StateObject private var appSettings = AppSettings()
    /// Live Scores' Monitoring section, for this run of the app only.
    @StateObject private var monitoring = MonitoringStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appSettings)
                .environmentObject(monitoring)
        }
        .onChange(of: scenePhase) { _, newPhase in
            AppLifecycle.handlePhaseChange(newPhase)
        }
    }
}
