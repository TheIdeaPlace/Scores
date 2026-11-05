//
//  SettingsView.swift
//  SportsScores
//
//  Settings tab — accessible from the bottom tab bar.
//

import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        Form {
            teamNameSection
            tableDisplaySection
            collegeFootballSection
            sportsSection
            stadiumExplorationSection
            userGuideSection
            aboutSection
        }
        .navigationTitle("Settings")
    }

    // MARK: - Table Display Section

    private var tableDisplaySection: some View {
        Section {
            Picker("Default view", selection: $appSettings.defaultTableViewMode) {
                ForEach(ViewMode.allCases, id: \.self) { mode in
                    Text(mode.rawValue).tag(mode)
                }
            }
        } header: {
            Text("Table Default")
        } footer: {
            Text(appSettings.defaultTableViewMode.description)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - College Football Section

    private var collegeFootballSection: some View {
        Section {
            Picker("Coverage", selection: $appSettings.ncaafCoverage) {
                ForEach(NCAAFCoverage.allCases) { coverage in
                    Text(coverage.settingsLabel).tag(coverage)
                }
            }
            .accessibilityLabel("College football coverage")
            .accessibilityHint("Sets the games, standings and teams you see. All Division I shows FBS "
                               + "and FCS together, around 200 games a week, and is the only setting "
                               + "that shows opening weekend in full. FBS only shows about 100 games a week.")
        } header: {
            Text("College Football")
        } footer: {
            Text(appSettings.ncaafCoverage.settingsDescription)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Team Name Section

    private var teamNameSection: some View {
        Section {
            Picker("Announce teams as", selection: $appSettings.teamNamePreference) {
                ForEach(TeamNamePreference.allCases) { preference in
                    Text(preference.settingsLabel).tag(preference)
                }
            }
        } header: {
            Text("VoiceOver Team Names")
        } footer: {
            exampleFooter
        }
    }

    @ViewBuilder
    private var exampleFooter: some View {
        let pref = appSettings.teamNamePreference
        VStack(alignment: .leading, spacing: 4) {
            Text(pref.settingsDescription)
            Text("Example — Milwaukee Brewers: \"\(pref.exampleText)\"")
                .fontWeight(.semibold)
                .foregroundColor(.accentColor)
        }
        .font(.caption)
        .padding(.top, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(pref.settingsDescription). Example: VoiceOver would say \(pref.exampleText) for the Milwaukee Brewers")
    }

    // MARK: - Sports Section

    private var sportsSection: some View {
        Section {
            // Fixed "Live Scores" row — always first, not movable
            HStack(spacing: 12) {
                Image(systemName: "circle.fill")
                    .foregroundColor(.red)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Live Scores")
                        .font(.headline)
                    Text("All sports — always first")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: "lock.fill")
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("Live Scores, always first, locked")

            ForEach(appSettings.sportOrder) { sport in
                SportSettingsRow(sport: sport,
                                 isHidden: appSettings.hiddenSports.contains(sport),
                                 onToggle: { toggle(sport) },
                                 onMoveUp:     { move(sport, by: -1) },
                                 onMoveDown:   { move(sport, by: +1) },
                                 onMoveToTop:  { moveToTop(sport) },
                                 onMoveToBottom: { moveToBottom(sport) })
            }
            .onMove { source, destination in
                appSettings.sportOrder.move(fromOffsets: source, toOffset: destination)
            }

            // Hub sports — toggle only (no reordering; they appear below the main sports list)
            Toggle(isOn: $appSettings.soccerHubEnabled) {
                HStack(spacing: 12) {
                    Text("⚽")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Soccer")
                            .font(.headline)
                        Text("EPL, MLS, Champions League and more")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("Soccer hub")
            .accessibilityHint(appSettings.soccerHubEnabled ? "On. Tap to hide Soccer from the home page." : "Off. Tap to show Soccer on the home page.")

            Toggle(isOn: $appSettings.racingHubEnabled) {
                HStack(spacing: 12) {
                    Image(systemName: "flag.checkered")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Auto Racing")
                            .font(.headline)
                        Text("Formula 1, IndyCar, and NASCAR Cup")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("Auto Racing hub")
            .accessibilityHint(appSettings.racingHubEnabled ? "On. Tap to hide Auto Racing from the home page." : "Off. Tap to show Auto Racing on the home page.")

            Toggle(isOn: $appSettings.golfHubEnabled) {
                HStack(spacing: 12) {
                    Image(systemName: "figure.golf")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Golf")
                            .font(.headline)
                        Text("PGA Tour and LPGA Tour")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("Golf hub")
            .accessibilityHint(appSettings.golfHubEnabled ? "On. Tap to hide Golf from the home page." : "Off. Tap to show Golf on the home page.")

            Toggle(isOn: $appSettings.cflEnabled) {
                HStack(spacing: 12) {
                    Image(systemName: "figure.american.football")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("CFL")
                            .font(.headline)
                        Text("Canadian Football League · scores & standings")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("CFL")
            .accessibilityHint(appSettings.cflEnabled ? "On. Tap to hide CFL from the home page." : "Off. Tap to show CFL on the home page.")

            Toggle(isOn: $appSettings.worldCupHubEnabled) {
                HStack(spacing: 12) {
                    Image(systemName: "globe.americas.fill")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("2026 FIFA World Cup")
                            .font(.headline)
                        Text("Concluded · archived in The Bench")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("2026 FIFA World Cup hub")
            .accessibilityHint(appSettings.worldCupHubEnabled ? "On. Tap to hide from The Bench." : "Off. Tap to show in The Bench.")

            Toggle(isOn: $appSettings.worldCupWomensHubEnabled) {
                HStack(spacing: 12) {
                    Image(systemName: "globe.americas.fill")
                        .font(.title3)
                        .frame(width: 28)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("2027 FIFA Women's World Cup")
                            .font(.headline)
                        Text("2027 · Brazil")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .accessibilityLabel("2027 FIFA Women's World Cup hub")
            .accessibilityHint(appSettings.worldCupWomensHubEnabled ? "On. Tap to hide from the home page." : "Off. Tap to show on the home page.")
        } header: {
            Text("Home Page Sports")
        } footer: {
            Text("Drag to reorder. Toggle to show or hide a sport. Soccer, Golf, CFL, and World Cup are toggle-only and appear below the main list.")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Stadium Exploration Section

    private var stadiumExplorationSection: some View {
        Section {
            Toggle(isOn: $appSettings.useDirectTouchForTours) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Use Direct Touch")
                    Text("Double-tap the canvas to activate, then drag freely. VoiceOver is silenced during the drag. Turn off to use the double-tap-and-hold passthrough instead.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .accessibilityLabel("Use Direct Touch for stadium exploration")
            .accessibilityHint(appSettings.useDirectTouchForTours
                ? "On. Double-tap the canvas to start dragging. Turn off to use the double-tap-and-hold passthrough instead."
                : "Off. Turn on to double-tap the canvas to enter drag mode with VoiceOver silenced.")
        } header: {
            Text("Stadium Exploration")
        } footer: {
            Text(appSettings.useDirectTouchForTours
                ? "Direct Touch is on. Double-tap the canvas to activate, then drag freely. VoiceOver is silenced during the drag."
                : "Direct Touch is off. Swipe to focus the canvas, then use the VoiceOver double-tap-and-hold passthrough to drag.")
                .font(.caption)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
        }
    }

    // MARK: - User Guide Section

    private var userGuideSection: some View {
        Section {
            NavigationLink(destination: UserGuideView()) {
                HStack {
                    Image(systemName: "book.fill")
                        .foregroundColor(.blue)
                        .frame(width: 28)
                    Text("User Guide")
                }
            }
            .accessibilityLabel("User Guide")
            .accessibilityHint("Learn how to use all app features")
        }
    }

    // MARK: - About Section

    private var aboutSection: some View {
        Section("About") {
            HStack {
                Text("Version")
                Spacer()
                Text(appVersion)
                    .foregroundColor(.secondary)
            }
        }
    }

    private var appVersion: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "—"
        let build   = info?["CFBundleVersion"] as? String ?? "—"
        return "\(version) (\(build))"
    }

    // MARK: - Sport ordering helpers

    private func toggle(_ sport: Sport) {
        if appSettings.hiddenSports.contains(sport) {
            appSettings.hiddenSports.remove(sport)
        } else {
            appSettings.hiddenSports.insert(sport)
        }
    }

    private func move(_ sport: Sport, by delta: Int) {
        guard let idx = appSettings.sportOrder.firstIndex(of: sport) else { return }
        let dest = (idx + delta).clamped(to: 0...(appSettings.sportOrder.count - 1))
        guard dest != idx else { return }
        appSettings.sportOrder.move(fromOffsets: IndexSet(integer: idx),
                                    toOffset: dest > idx ? dest + 1 : dest)
    }

    private func moveToTop(_ sport: Sport) {
        guard let idx = appSettings.sportOrder.firstIndex(of: sport), idx != 0 else { return }
        appSettings.sportOrder.move(fromOffsets: IndexSet(integer: idx), toOffset: 0)
    }

    private func moveToBottom(_ sport: Sport) {
        guard let idx = appSettings.sportOrder.firstIndex(of: sport),
              idx != appSettings.sportOrder.count - 1 else { return }
        appSettings.sportOrder.move(fromOffsets: IndexSet(integer: idx),
                                    toOffset: appSettings.sportOrder.count)
    }
}

// MARK: - Sport settings row

private struct SportSettingsRow: View {
    let sport: Sport
    let isHidden: Bool
    let onToggle: () -> Void
    let onMoveUp: () -> Void
    let onMoveDown: () -> Void
    let onMoveToTop: () -> Void
    let onMoveToBottom: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Drag handle (visual affordance; actual drag handled by .onMove)
            Image(systemName: "line.3.horizontal")
                .foregroundColor(.secondary)
                .font(.body)
                .frame(width: 24)
                .accessibilityHidden(true)

            Text(sport.icon)
                .font(.title3)
                .frame(width: 28)
                .accessibilityHidden(true)

            Text(sport.displayName)
                .font(.headline)
                .foregroundColor(isHidden ? .secondary : .primary)

            Spacer()

            Button(action: onToggle) {
                Image(systemName: isHidden ? "eye.slash" : "eye")
                    .foregroundColor(isHidden ? .secondary : .accentColor)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(isHidden ? "Show \(sport.displayName)" : "Hide \(sport.displayName)")
            .accessibilityHint(isHidden ? "Adds this sport to the home page" : "Removes this sport from the home page")
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(sport.displayName), \(isHidden ? "hidden" : "visible")")
        .accessibilityHint("Double-tap to toggle visibility. Use actions to reorder.")
        .accessibilityAction(named: "Toggle visibility") { onToggle() }
        .accessibilityAction(named: "Move up") { onMoveUp() }
        .accessibilityAction(named: "Move down") { onMoveDown() }
        .accessibilityAction(named: "Move to top") { onMoveToTop() }
        .accessibilityAction(named: "Move to bottom") { onMoveToBottom() }
    }
}

// MARK: - Comparable clamping helper

private extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}

#Preview {
    NavigationStack {
        SettingsView()
            .environmentObject(AppSettings())
    }
}
