//
//  ViewMode.swift
//  SportsScores
//
//  Created on 1/4/26.
//
//  This implements the revolutionary three-view-mode system from the desktop app

import Foundation
import SwiftUI
import UIKit

enum ViewMode: String, CaseIterable {
    case table = "Table View"
    case quickList = "Quick List"
    case fullList = "Full List"
    
    var icon: String {
        switch self {
        case .table: return "tablecells"
        case .quickList: return "list.bullet"
        case .fullList: return "list.bullet.rectangle"
        }
    }
    
    var description: String {
        switch self {
        case .table:
            return "Grid with column headers — best for visual scanning"
        case .quickList:
            return "Compact rows, terse VoiceOver labels"
        case .fullList:
            return "Compact rows, VoiceOver labels include field names"
        }
    }

    var accessibilityLabel: String {
        switch self {
        case .table:
            return "Table View: grid with column headers"
        case .quickList:
            return "Quick List: compact rows, terse labels"
        case .fullList:
            return "Full List: compact rows, labeled for VoiceOver"
        }
    }
    
    func next() -> ViewMode {
        let all = ViewMode.allCases
        let currentIndex = all.firstIndex(of: self) ?? 0
        let nextIndex = (currentIndex + 1) % all.count
        return all[nextIndex]
    }

    /// Where AppSettings keeps the "Default view" setting.
    static let defaultsKey = "defaultTableViewMode"

    /// The mode every table screen starts in: the "Default view" setting, else Quick List.
    /// A screen declares `@State private var viewMode: ViewMode = .savedDefault()`, so it is
    /// in that mode from its first frame and VoiceOver never lands on a Quick List that is
    /// about to become a table.
    static func savedDefault(in defaults: UserDefaults = .standard) -> ViewMode {
        ViewMode(rawValue: defaults.string(forKey: defaultsKey) ?? "") ?? .quickList
    }
}

// MARK: - View Mode Menu Button
struct ViewModeMenuButton: View {
    @Binding var currentMode: ViewMode

    var body: some View {
        Menu {
            Picker("View Mode", selection: $currentMode) {
                ForEach(ViewMode.allCases, id: \.self) { mode in
                    Label(mode.rawValue, systemImage: mode.icon).tag(mode)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Image(systemName: currentMode.icon)
        }
        .accessibilityLabel("View mode: \(currentMode.rawValue)")
        .accessibilityHint("Tap to change table view mode")
    }
}

// MARK: - Conditional Direct Touch

extension View {
    /// Applies `.accessibilityDirectTouch(options: .silentOnTouch)` only when `enabled` is true.
    /// When disabled, VoiceOver treats the view as a standard element; users can still pass
    /// touches through via the VoiceOver double-tap-and-hold gesture.
    @ViewBuilder
    func conditionalDirectTouch(_ enabled: Bool) -> some View {
        if enabled {
            // .requiresActivation: canvas only intercepts touches after the user double-taps it,
            // so VoiceOver's "double-tap anywhere to activate" gesture for OTHER elements works
            // normally even when their double-tap physically lands inside the canvas region.
            // .silentOnTouch: silences VoiceOver announcements while dragging.
            self.accessibilityDirectTouch(options: [.silentOnTouch, .requiresActivation])
        } else {
            self
        }
    }

    /// Adds a named VoiceOver custom action only when `action` is non-nil.
    /// Use this to suppress unavailable actions (e.g. "Move Up" for the first item)
    /// so VoiceOver does not announce actions that have no effect.
    @ViewBuilder
    func accessibilityActionIfPresent(named name: String, action: (() -> Void)?) -> some View {
        if let action = action {
            self.accessibilityAction(named: name) { action() }
        } else {
            self
        }
    }
}
