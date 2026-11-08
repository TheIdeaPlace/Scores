//
//  ListenToGame.swift
//  SportsScores
//
//  "Listen to the Game": a VoiceOver action and a context menu item on a game, and a
//  list of places for a game or team screen. Each place opens in Safari, or in its
//  own app when that app claims the link; the person signs in there if asked.
//  Monitor and Stop Monitoring (#185) share the row's actions and context menu.
//

import SwiftUI
import UIKit

/// Says a Monitor action's confirmation. `queued` waits for VoiceOver to finish what it's
/// saying, such as the row focus has just moved to.
@MainActor
func announceMonitoring(_ text: String, queued: Bool = false) {
    let said = NSAttributedString(string: text,
                                  attributes: [.accessibilitySpeechQueueAnnouncement: queued])
    UIAccessibility.post(notification: .announcement, argument: said)
}

/// Monitor or Stop Monitoring on a game row (#185): its name, which is both the VoiceOver
/// custom action's and the context menu item's, and what it does.
struct MonitorAction {
    let name: String
    let perform: () -> Void
}

/// Adds "Listen to the Game" to a row: a VoiceOver custom action that offers the places
/// to listen, and the same places in the row's context menu. With `monitor`, adds that
/// action and menu item too. Both share the one context menu, since a row has only one.
/// Adds nothing when there is nowhere to listen and nothing to monitor.
struct ListenToGameModifier: ViewModifier {
    let title: String
    let options: [ListenOption]
    var monitor: MonitorAction? = nil
    @State private var choosing = false
    @Environment(\.openURL) private var openURL

    func body(content: Content) -> some View {
        if options.isEmpty && monitor == nil {
            content
        } else {
            content
                .accessibilityActions {
                    if !options.isEmpty {
                        Button("Listen to the Game") { listen() }
                    }
                    if let monitor {
                        Button(monitor.name) { monitor.perform() }
                    }
                }
                .contextMenu {
                    if !options.isEmpty {
                        Menu {
                            ForEach(options) { option in
                                Button(option.label) { openURL(option.url) }
                            }
                        } label: {
                            Label("Listen to the Game", systemImage: "radio")
                        }
                    }
                    if let monitor {
                        Button(action: monitor.perform) {
                            Label(monitor.name, systemImage: monitor.name == MonitoringStore.ActionName.monitor
                                  ? "eye" : "eye.slash")
                        }
                    }
                }
                .confirmationDialog(title, isPresented: $choosing, titleVisibility: .visible) {
                    ForEach(options) { option in
                        Button(option.label) { openURL(option.url) }
                    }
                    Button("Cancel", role: .cancel) {}
                }
        }
    }

    private func listen() {
        if options.count == 1, let only = options.first {
            openURL(only.url)
        } else {
            choosing = true
        }
    }
}

extension View {
    /// Listen to the Game, and Monitor or Stop Monitoring when `monitor` is given.
    func listenToGame(_ game: Game, sport: Sport, monitor: MonitorAction? = nil) -> some View {
        modifier(ListenToGameModifier(
            title: "Listen to \(game.awayTeam.displayName) \(game.matchupWord) \(game.homeTeam.displayName)",
            options: game.listenOptions(league: sport.rawValue),
            monitor: monitor))
    }
}

/// The places to listen, as a list section of links, for a game or team screen.
struct ListenSection: View {
    let header: String
    let options: [ListenOption]
    var footer: String = "Opens in Safari or the service's app. Sign in there if it asks."

    var body: some View {
        if !options.isEmpty {
            Section {
                ForEach(options) { option in
                    Link(destination: option.url) {
                        Label(option.label, systemImage: "radio")
                    }
                    .accessibilityHint("Opens outside the app")
                }
            } header: {
                Text(header)
            } footer: {
                Text(footer)
            }
        }
    }
}
