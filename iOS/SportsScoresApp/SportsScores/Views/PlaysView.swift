//
//  PlaysView.swift
//  SportsScores
//
//  Four-level collapsible plays hierarchy for MLB:
//    Inning  →  Half (Top/Bottom)  →  At-bat  →  Pitches
//
//  VoiceOver model on at-bat rows:
//    • accessibilityValue reflects the "current" pitch as you step through
//    • swipe up   (increment) → next pitch, plays audio + announces details
//    • swipe down (decrement) → previous pitch, plays audio + announces details
//    • custom action "Play full at-bat" → plays entire pitch sequence
//
//  For non-MLB sports: two-level grouping (Period → Plays flat list).
//

import SwiftUI

// MARK: - Data model helpers

/// One entry in the expanded half-inning list: an at-bat or a player-change event.
private enum HalfInningItem: Identifiable {
    /// A full at-bat (batter vs pitcher sequence).
    case atBat(AtBatGroup)
    /// A mid-inning player substitution — e.g. a pitching change.
    /// `id` is the underlying ESPN play id; `text` is the announcement ("Newcomb relieved Smith").
    case playerChange(id: String, text: String)

    var id: String {
        switch self {
        case .atBat(let ab):             return ab.id
        case .playerChange(let id, _):   return id
        }
    }
}

private struct HalfInningGroup: Identifiable {
    let id: String              // e.g. "Top-3"
    let halfType: String        // "Top" / "Bottom"
    let inningNumber: Int
    let inningLabel: String     // "3rd Inning"
    let items: [HalfInningItem] // at-bats interleaved with player-change banners
    let runsScored: Int         // sum of scoreValue in this half

    /// Number of actual at-bat entries (excludes player-change rows).
    var atBatCount: Int {
        items.reduce(0) { total, item in
            if case .atBat = item { return total + 1 }
            return total
        }
    }
}

private struct AtBatGroup: Identifiable {
    let id: String              // atBatId
    let headerText: String      // "Lopez pitches to Meadows"
    let resultText: String?     // "Meadows grounded out…"
    let pitches: [GameDetails.Play]
    let notePlay: GameDetails.Play?   // the result play (N or S type)
    let isScoringPlay: Bool          // true when summaryType == "S"
    let awayScoreAfter: Int?         // score after this at-bat (scoring plays only)
    let homeScoreAfter: Int?         // score after this at-bat (scoring plays only)
}

private struct InningGroup: Identifiable {
    let id: String
    let label: String
    let halves: [HalfInningGroup]
    let scoreSummary: String?   // e.g. "Away scored 2" or nil
}

private struct PeriodGroup: Identifiable {
    let id: String
    let label: String
    let plays: [GameDetails.Play]
}

// MARK: - MLB Plays View

struct MLBPlaysView: View {
    let plays: [GameDetails.Play]
    let awayAbbr: String
    let homeAbbr: String
    let awayPreferredName: String
    let homePreferredName: String
    @ObservedObject var audio: PitchAudioEngine

    init(
        plays: [GameDetails.Play],
        awayAbbr: String,
        homeAbbr: String,
        awayPreferredName: String? = nil,
        homePreferredName: String? = nil,
        audio: PitchAudioEngine
    ) {
        self.plays = plays
        self.awayAbbr = awayAbbr
        self.homeAbbr = homeAbbr
        self.awayPreferredName = awayPreferredName ?? awayAbbr
        self.homePreferredName = homePreferredName ?? homeAbbr
        self.audio = audio
    }

    @State private var expandedInnings: Set<String> = []
    @State private var expandedHalves: Set<String> = []
    @State private var expandedAtBats: Set<String> = []
    /// Per-at-bat pitch navigation index.
    /// -1 = showing at-bat result (initial). 0..N-1 = pitch at that index.
    @State private var voicePitchIndex: [String: Int] = [:]

    private var innings: [InningGroup] { buildInnings() }

    var body: some View {
        ScrollView {
            if innings.isEmpty {
                Text("Play-by-play not available")
                    .foregroundColor(.secondary)
                    .padding()
            } else {
                // Audio status banner
                audioBanner
                    .padding(.horizontal)
                    .padding(.top, 8)

                LazyVStack(spacing: 6, pinnedViews: []) {
                    ForEach(innings) { inning in
                        inningSection(inning)
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 16)
            }
        }
    }

    // MARK: - Audio Banner

    private var audioBanner: some View {
        HStack(spacing: 10) {
            Spacer()
            if audio.isPlaying {
                Button("Stop") { audio.stop() }
                    .font(.caption.bold())
                    .buttonStyle(.borderedProminent)
                    .tint(.red)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .cornerRadius(10)
    }

    // MARK: - Inning level

    @ViewBuilder
    private func inningSection(_ inning: InningGroup) -> some View {
        let isOpen = expandedInnings.contains(inning.id)

        VStack(spacing: 0) {
            // Inning header button
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if isOpen { expandedInnings.remove(inning.id) }
                    else { expandedInnings.insert(inning.id) }
                }
            } label: {
                HStack {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .frame(width: 16)
                    Text(inning.label)
                        .font(.headline)
                    Spacer()
                    if let summary = inning.scoreSummary {
                        Text(summary)
                            .font(.caption.bold())
                            .foregroundColor(.green)
                    }
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(inning.label + (inning.scoreSummary.map { ", \($0)" } ?? ""))
            .accessibilityHint(isOpen ? "Double tap to collapse." : "Double tap to expand.")

            if isOpen {
                Divider().padding(.horizontal)
                VStack(spacing: 4) {
                    ForEach(inning.halves) { half in
                        halfSection(half)
                    }
                }
                .padding(.bottom, 4)
            }
        }
        .background(Color.secondary.opacity(0.07))
        .cornerRadius(10)
    }

    // MARK: - Half-inning level

    @ViewBuilder
    private func halfSection(_ half: HalfInningGroup) -> some View {
        let isOpen = expandedHalves.contains(half.id)
        let teamName = half.halfType == "Top" ? awayAbbr : homeAbbr
        let runsText = half.runsScored > 0 ? ", \(half.runsScored) run\(half.runsScored == 1 ? "" : "s")" : ""
        let halfLabel = "\(half.halfType) — \(teamName) Batting"
        let halfLabelFull = halfLabel + runsText

        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if isOpen { expandedHalves.remove(half.id) }
                    else { expandedHalves.insert(half.id) }
                }
            } label: {
                HStack {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .frame(width: 16)
                    Text(halfLabel)
                        .font(.subheadline.bold())
                    Spacer()
                    if half.runsScored > 0 {
                        Text("\(half.runsScored)R")
                            .font(.caption.bold())
                            .foregroundColor(.green)
                    } else {
                        Text("\(half.atBatCount) AB")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.leading, 12)
            .accessibilityLabel(halfLabelFull)
            .accessibilityHint(isOpen ? "Double tap to collapse." : "Double tap to expand.")

            if isOpen {
                VStack(spacing: 3) {
                    ForEach(half.items) { item in
                        halfInningItemView(item)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 4)
            }
        }
        .background(Color.secondary.opacity(0.04))
        .cornerRadius(8)
        .padding(.horizontal, 4)
    }

    // MARK: - Half-inning item dispatch

    @ViewBuilder
    private func halfInningItemView(_ item: HalfInningItem) -> some View {
        switch item {
        case .atBat(let ab):
            atBatRow(ab)
        case .playerChange(_, let text):
            playerChangeRow(text)
        }
    }

    /// A compact banner shown between at-bats when a player substitution occurs
    /// (e.g. a pitching change).  Uses summaryType == "C" from the ESPN API.
    private func playerChangeRow(_ text: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .font(.caption.bold())
                .foregroundColor(.orange)
                .frame(width: 22)
            Text(text)
                .font(.caption.bold())
                .foregroundColor(.primary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.orange.opacity(0.10))
        .cornerRadius(6)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Player change: \(text)")
        .accessibilityAddTraits(.isStaticText)
    }

    // MARK: - At-bat level (with VoiceOver adjustable pitches)

    @ViewBuilder
    private func atBatRow(_ ab: AtBatGroup) -> some View {
        let isOpen = expandedAtBats.contains(ab.id)
        let pitchCount = ab.pitches.count
        let currentIdx = voicePitchIndex[ab.id] ?? -1   // -1 = result (initial)

        VStack(spacing: 0) {
            // At-bat header
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    if isOpen { expandedAtBats.remove(ab.id) }
                    else { expandedAtBats.insert(ab.id) }
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .frame(width: 14)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(ab.headerText)
                            .font(.subheadline)
                            .lineLimit(1)
                        if let result = ab.resultText {
                            Text(result)
                                .font(.caption)
                                .foregroundColor(ab.isScoringPlay ? .green : .secondary)
                                .lineLimit(2)
                        }
                        // Show updated score after a scoring play
                        if ab.isScoringPlay,
                           let away = ab.awayScoreAfter,
                           let home = ab.homeScoreAfter {
                            Text("\(awayAbbr) \(away) – \(homeAbbr) \(home)")
                                .font(.caption.bold())
                                .foregroundColor(.green)
                        }
                    }

                    Spacer()

                    // Pitch count + result dots
                    if pitchCount > 0 {
                        HStack(spacing: 2) {
                            ForEach(ab.pitches, id: \.id) { p in
                                pitchDot(p)
                            }
                        }
                        Text("\(pitchCount)p")
                            .font(.caption2.monospacedDigit())
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            // VoiceOver: swipe up/down to step through pitches
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(ab.headerText)
            .accessibilityValue(pitchAccessibilityValue(ab: ab, index: currentIdx))
            .accessibilityAdjustableAction { direction in
                guard pitchCount > 0 else { return }
                var idx = voicePitchIndex[ab.id] ?? -1  // -1 = result state
                switch direction {
                case .increment:
                    // Swipe up: step forward through pitches
                    if idx < pitchCount - 1 { idx += 1 }
                    voicePitchIndex[ab.id] = idx
                    if idx >= 0 { audio.play(ab.pitches[idx]) }
                case .decrement:
                    if idx > 0 {
                        // Step back through pitches
                        idx -= 1
                        voicePitchIndex[ab.id] = idx
                        audio.play(ab.pitches[idx])
                    } else if idx == 0 {
                        // Back to result
                        voicePitchIndex[ab.id] = -1
                    } else {
                        // Already at result (idx == -1): play full sequence
                        audio.playSequence(ab.pitches)
                    }
                @unknown default: break
                }
            }
            .accessibilityHint(pitchCount > 0
                ? "Swipe up to step through pitches. Swipe down from result to play full sequence."
                : "")

            // Expanded: pitch rows
            if isOpen && pitchCount > 0 {
                Divider().padding(.horizontal, 10)
                ForEach(Array(ab.pitches.enumerated()), id: \.element.id) { i, pitch in
                    pitchRow(pitch, number: i + 1, batterHand: ab.pitches.first?.bats?.abbreviation)
                }
            }
        }
        .background(Color(uiColor: .systemBackground))
        .cornerRadius(8)
        .shadow(color: .black.opacity(0.04), radius: 1, x: 0, y: 1)
    }

    private func pitchAccessibilityValue(ab: AtBatGroup, index: Int) -> String {
        // index == -1 (or no pitches): show at-bat result + score if scoring play
        if index < 0 || ab.pitches.isEmpty {
            var parts: [String] = []
            if let r = ab.resultText { parts.append(r) }
            if ab.isScoringPlay, let away = ab.awayScoreAfter, let home = ab.homeScoreAfter {
                parts.append("Score: \(awayAbbr) \(away), \(homeAbbr) \(home)")
            }
            return parts.joined(separator: ". ")
        }
        guard index < ab.pitches.count else { return ab.resultText ?? "" }
        let p = ab.pitches[index]
        let num = "Pitch \(index + 1) of \(ab.pitches.count)"
        let type_ = p.pitchType?.text ?? p.type.text
        let vel = p.pitchVelocity.map { "\($0) mph" } ?? ""
        let loc = p.locationDescription(batterHand: p.bats?.abbreviation)
        let result = p.type.text
        return [num, type_, vel, loc, result].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    // MARK: - Pitch row (sighted expanded view)

    private func pitchRow(_ pitch: GameDetails.Play, number: Int, batterHand: String?) -> some View {
        Button {
            audio.play(pitch)
        } label: {
            HStack(spacing: 8) {
                Text("\(number)")
                    .font(.caption2.monospacedDigit())
                    .foregroundColor(.secondary)
                    .frame(width: 18, alignment: .trailing)

                pitchDot(pitch)

                VStack(alignment: .leading, spacing: 1) {
                    Text(pitch.pitchType?.text ?? pitch.type.text)
                        .font(.caption.bold())
                    if let vel = pitch.pitchVelocity {
                        Text("\(vel) mph")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .frame(width: 110, alignment: .leading)

                Text(pitch.locationDescription(batterHand: batterHand))
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if let count = pitch.resultCount {
                    Text("\(count.balls)-\(count.strikes)")
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(.secondary)
                        .frame(width: 26, alignment: .trailing)
                }

                Image(systemName: "speaker.wave.1")
                    .font(.caption2)
                    .foregroundColor(.blue.opacity(0.7))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(pitch.pitchType?.text ?? "Pitch") \(pitch.pitchVelocity.map { "\($0) mph" } ?? ""), \(pitch.locationDescription(batterHand: batterHand)), \(pitch.type.text)")
    }

    @ViewBuilder
    private func pitchDot(_ pitch: GameDetails.Play) -> some View {
        let label = pitch.pitchResultLabel
        let color  = pitchResultColor(pitch)
        Text(label)
            .font(.system(size: 9, weight: .bold, design: .monospaced))
            .foregroundColor(.white)
            .frame(width: 16, height: 16)
            .background(color)
            .cornerRadius(3)
    }

    private func pitchResultColor(_ pitch: GameDetails.Play) -> Color {
        switch pitch.type.type {
        case "ball":                              return .blue
        case "called-strike", "swinging-strike": return .red
        case "foul":                              return .orange
        case "in-play-out":                       return .gray
        case "in-play-score", "in-play-no-out":  return .green
        default:                                  return Color.secondary
        }
    }

    // MARK: - Build data

    private func buildInnings() -> [InningGroup] {
        // Only process non-empty plays
        let relevant = plays.filter { $0.summaryType != nil }
        guard !relevant.isEmpty else { return [] }

        // Build ordered list of unique (halfType, inningNumber) keys
        var halfOrder: [String] = []
        var halfPlays: [String: [GameDetails.Play]] = [:]
        var halfMeta: [String: (type: String, number: Int, label: String)] = [:]

        for play in relevant {
            guard let halfType = play.period?.type,
                  let num = play.period?.number else { continue }
            let key = "\(halfType)-\(num)"
            if halfPlays[key] == nil {
                halfOrder.append(key)
                halfMeta[key] = (halfType, num, play.period?.displayValue ?? "Inning \(num)")
            }
            halfPlays[key, default: []].append(play)
        }

        // Group half-innings into innings
        var inningOrder: [Int] = []
        var inningHalves: [Int: [String]] = [:]
        for key in halfOrder {
            guard let meta = halfMeta[key] else { continue }
            if inningHalves[meta.number] == nil { inningOrder.append(meta.number) }
            inningHalves[meta.number, default: []].append(key)
        }

        return inningOrder.map { num in
            let keys = inningHalves[num] ?? []
            let halves: [HalfInningGroup] = keys.compactMap { key in
                guard let meta = halfMeta[key],
                      let plays = halfPlays[key] else { return nil }
                return buildHalf(key: key, meta: meta, plays: plays)
            }
            let label = halves.first?.inningLabel ?? "Inning \(num)"
            // Build score summary: mention halves where runs scored
            let scoreParts: [String] = halves.compactMap { half in
                guard half.runsScored > 0 else { return nil }
                let team = half.halfType == "Top" ? awayPreferredName : homePreferredName
                let runs = half.runsScored
                return "\(team) \(runs)\(runs == 1 ? " run" : " runs")"
            }
            
            // Find the final score after this inning by checking the last play with score info
            var finalScore: String? = nil
            for key in keys.reversed() {
                if let plays = halfPlays[key] {
                    for play in plays.reversed() {
                        if let away = play.awayScore, let home = play.homeScore {
                            finalScore = "Score: \(away)-\(home)"
                            break
                        }
                    }
                }
                if finalScore != nil { break }
            }
            
            // Combine runs summary with final score
            var summaryParts = scoreParts
            if let score = finalScore {
                summaryParts.append(score)
            }
            let scoreSummary = summaryParts.isEmpty ? nil : summaryParts.joined(separator: ", ")
            return InningGroup(id: "I-\(num)", label: label, halves: halves, scoreSummary: scoreSummary)
        }
    }

    private func buildHalf(
        key: String,
        meta: (type: String, number: Int, label: String),
        plays: [GameDetails.Play]
    ) -> HalfInningGroup {
        // Group by atBatId, preserving order
        var abOrder: [String] = []
        var abPlays: [String: [GameDetails.Play]] = [:]
        for play in plays {
            let abKey = play.atBatId ?? play.id
            if abPlays[abKey] == nil { abOrder.append(abKey) }
            abPlays[abKey, default: []].append(play)
        }

        // Build interleaved list of at-bats and player-change banners.
        var items: [HalfInningItem] = []

        for abKey in abOrder {
            guard let group = abPlays[abKey] else { continue }

            // Emit any player-change (summaryType == "C") plays that appear before
            // the at-bat marker.  ESPN places mid-inning substitutions (pitching
            // changes, defensive replacements) at the start of the next batter's group.
            let aIndex = group.firstIndex(where: { $0.summaryType == "A" })
            let preRange = aIndex.map { group[..<$0] } ?? ArraySlice(group)
            for play in preRange where play.summaryType == "C" {
                if let txt = play.text, !txt.isEmpty {
                    items.append(.playerChange(id: "chg-\(play.id)", text: txt))
                }
            }

            // If there is no at-bat marker this group is substitution-only — done.
            guard let aIdx = aIndex else { continue }

            let header = group[aIdx].text ?? "At-bat"

            // Only search for the result AFTER the 'A' marker so that pre-at-bat
            // substitution 'N' plays ("Gilbert in center field.") aren't mistaken for results.
            let playsAfterABat = Array(group[aIdx...])
            let resultPlay = playsAfterABat.first(where: { $0.summaryType == "S" })
                          ?? playsAfterABat.first(where: { $0.summaryType == "N" })
            let result = resultPlay?.text
            let pitches = group.filter { $0.summaryType == "P" && $0.isPitch }
            let isScoringPlay = resultPlay?.summaryType == "S"
            items.append(.atBat(AtBatGroup(
                id: abKey,
                headerText: header,
                resultText: result,
                pitches: pitches,
                notePlay: resultPlay,
                isScoringPlay: isScoringPlay,
                awayScoreAfter: isScoringPlay ? resultPlay?.awayScore : nil,
                homeScoreAfter: isScoringPlay ? resultPlay?.homeScore : nil
            )))
        }

        let runsScored = plays.reduce(0) { $0 + max(0, $1.scoreValue ?? 0) }
        return HalfInningGroup(
            id: key,
            halfType: meta.type,
            inningNumber: meta.number,
            inningLabel: meta.label,
            items: items,
            runsScored: runsScored
        )
    }
}

// MARK: - Generic (non-MLB) Plays View

struct GenericPlaysView: View {
    let plays: [GameDetails.Play]
    let awayAbbr: String
    let homeAbbr: String

    /// Set for basketball and hockey, whose plays carry court/rink coordinates;
    /// nil for every other sport, which leaves the audio actions off entirely.
    var sport: Sport?
    var audio: PitchAudioEngine?

    @State private var expandedPeriods: Set<String> = []

    /// True when this sport's plays can be sonified and an engine was handed in.
    private var canPlayAudio: Bool {
        guard let sport, audio != nil else { return false }
        return PlayAudioGeometry.supports(sport)
    }

    /// Play one play's location, and say what was played — or why nothing was.
    private func playLocation(_ play: GameDetails.Play) {
        guard let sport, let audio else { return }
        if let description = audio.playLocatedPlay(play, sport: sport) {
            TouchTourAnnouncementService.shared.announce(description)
        } else {
            // Normal rather than broken: a third of basketball plays and six
            // percent of hockey plays have no coordinates.
            TouchTourAnnouncementService.shared.announce("This play has no location")
        }
    }

    /// Play every located play in a period, in order.
    private func playPeriodLocations(_ period: PeriodGroup) {
        guard let sport, let audio else { return }
        let count = audio.playLocatedSequence(period.plays, sport: sport)
        TouchTourAnnouncementService.shared.announce(
            count > 0
                ? "Playing \(count) of \(period.plays.count) plays in \(period.label)"
                : "No plays in \(period.label) have a location"
        )
    }

    private func locatedCount(_ period: PeriodGroup) -> Int {
        period.plays.filter { $0.hasPlayLocation }.count
    }

    private var periods: [PeriodGroup] {
        var order: [String] = []
        var groups: [String: [GameDetails.Play]] = [:]
        for play in plays {
            let key = play.period?.displayValue ?? "Game"
            if groups[key] == nil { order.append(key) }
            groups[key, default: []].append(play)
        }
        return order.map { PeriodGroup(id: $0, label: $0, plays: groups[$0] ?? []) }
    }

    var body: some View {
        ScrollView {
            if periods.isEmpty {
                Text("Play-by-play not available")
                    .foregroundColor(.secondary)
                    .padding()
            } else {
                LazyVStack(spacing: 6) {
                    ForEach(periods) { period in
                        periodSection(period)
                    }
                }
                .padding()
            }
        }
    }

    @ViewBuilder
    private func periodSection(_ period: PeriodGroup) -> some View {
        let isOpen = expandedPeriods.contains(period.id)
        let scoringCount = period.plays.filter { $0.scoreValue ?? 0 > 0 }.count
        let changeCount  = period.plays.filter { Self.isPlayerChangePlay($0) }.count
        
        // Find the final score after this period by checking the last play with score info
        let finalScore: String? = {
            period.plays.reversed().first { play in
                play.awayScore != nil && play.homeScore != nil
            }.flatMap { play in
                guard let away = play.awayScore, let home = play.homeScore else { return nil }
                return "\(away)-\(home)"
            }
        }()
        
        let a11yHeader: String = {
            var parts = ["\(period.label)", "\(period.plays.count) plays"]
            if scoringCount > 0 { parts.append("\(scoringCount) scoring") }
            if changeCount  > 0 { parts.append("\(changeCount) player change\(changeCount == 1 ? "" : "s")") }
            if let score = finalScore { parts.append("Score \(score)") }
            // Say how many can be heard, so the Play locations action is not a
            // shot in the dark — plenty of plays arrive with no coordinates.
            if canPlayAudio {
                let located = locatedCount(period)
                if located > 0 { parts.append("\(located) with a location") }
            }
            return parts.joined(separator: ", ")
        }()

        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if isOpen { expandedPeriods.remove(period.id) }
                    else { expandedPeriods.insert(period.id) }
                }
            } label: {
                HStack {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .frame(width: 16)
                    Text(period.label)
                        .font(.headline)
                    Spacer()
                    if let score = finalScore {
                        Text(score)
                            .font(.subheadline.bold())
                            .foregroundColor(.blue)
                            .padding(.trailing, 4)
                    }
                    if scoringCount > 0 {
                        Label("\(scoringCount)", systemImage: "star.fill")
                            .font(.caption.bold())
                            .foregroundColor(.green)
                            .labelStyle(.titleAndIcon)
                    }
                    Text("\(period.plays.count) plays")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(a11yHeader)
            .accessibilityHint(isOpen ? "Double tap to collapse." : "Double tap to expand.")
            .accessibilityAction(named: "Play locations") {
                playPeriodLocations(period)
            }

            if isOpen {
                Divider().padding(.horizontal)
                ForEach(period.plays, id: \.id) { play in
                    genericPlayRow(play)
                    if play.id != period.plays.last?.id {
                        Divider().padding(.leading, 12)
                    }
                }
            }
        }
        .background(Color.secondary.opacity(0.07))
        .cornerRadius(10)
    }

    private func genericPlayRow(_ play: GameDetails.Play) -> some View {
        let isPlayerChange = Self.isPlayerChangePlay(play)
        let playText = play.text.flatMap { $0.isEmpty ? nil : $0 } ?? play.type.text
        // Where the play happened, when this sport has coordinates and this play
        // carries them. Spoken as part of the row, not only played as a tone.
        let location = sport.flatMap { PlayAudioGeometry.location(for: $0, play: play) }
        let a11yLabel = Self.playAccessibilityLabel(
            play: play, playText: playText,
            awayAbbr: awayAbbr, homeAbbr: homeAbbr
        ) + (location.map { ", \($0.description)" } ?? "")

        return HStack(alignment: .top, spacing: 10) {
            // Icon column
            if isPlayerChange {
                Image(systemName: "person.2.fill")
                    .font(.caption)
                    .foregroundColor(.purple)
                    .frame(width: 18)
                    .padding(.top, 3)
            } else if play.type.text.lowercased().contains("timeout") {
                Image(systemName: "hand.raised.fill")
                    .font(.caption)
                    .foregroundColor(.orange)
                    .frame(width: 18)
                    .padding(.top, 3)
            } else {
                Spacer().frame(width: 18)
            }

            VStack(alignment: .leading, spacing: 3) {
                // What happened — most important, always first
                Text(playText)
                    .font(isPlayerChange ? .callout : .body)
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                // When + impact — secondary context below
                HStack(spacing: 6) {
                    if let clock = play.clock {
                        Text(clock.displayValue)
                            .font(.caption.bold())
                            .foregroundColor(isPlayerChange ? .secondary : .blue)
                    }
                    Spacer()
                    if let away = play.awayScore, let home = play.homeScore {
                        Text("\(awayAbbr) \(away)–\(home) \(homeAbbr)")
                            .font(.caption.monospacedDigit())
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(isPlayerChange ? Color.purple.opacity(0.06) : Color.clear)
        // Each play is a single VoiceOver stop — no individual Text elements
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(a11yLabel)
        // Offered only on the plays that actually have somewhere to play, so the
        // rotor is not full of actions that would answer "no location".
        .accessibilityAction(named: "Play location") {
            if canPlayAudio && play.hasPlayLocation { playLocation(play) }
        }
        .accessibilityHint(
            canPlayAudio && play.hasPlayLocation
                ? "Actions available to hear where this play happened."
                : ""
        )
        // Tapping the row does the same thing for anyone not using VoiceOver.
        .onTapGesture {
            if canPlayAudio && play.hasPlayLocation { playLocation(play) }
        }
    }

    // MARK: - Helpers (static so they can be used from accessibility label builder)

    private static func isPlayerChangePlay(_ play: GameDetails.Play) -> Bool {
        let typeText = play.type.text.lowercased()
        return typeText == "substitution"
            || typeText.contains("line change")
            || (play.text?.lowercased().contains("enters the game for") == true)
    }

    private static func playAccessibilityLabel(
        play: GameDetails.Play,
        playText: String,
        awayAbbr: String,
        homeAbbr: String
    ) -> String {
        // Order: what happened → when → impact (score)
        var parts: [String] = []
        parts.append(playText)
        if let clock = play.clock?.displayValue { parts.append(clock) }
        if let away = play.awayScore, let home = play.homeScore {
            parts.append("\(awayAbbr) \(away), \(homeAbbr) \(home)")
        }
        return parts.joined(separator: ". ")
    }
}

// MARK: - NFL Drives View

/// Quarter → Drive (collapsible) → individual plays.
/// Uses the `drives` data from the ESPN summary API.
struct NFLDrivesView: View {
    let drives: [GameDetails.Drive]
    let awayAbbr: String
    let homeAbbr: String

    @State private var expandedQuarters: Set<Int> = [1]
    @State private var expandedDrives: Set<String> = []

    /// Organise drives into quarters, ignoring duplicates / bad data.
    private var quarterGroups: [(quarter: Int, label: String, drives: [GameDetails.Drive])] {
        let sorted = drives.sorted {
            if $0.quarterNumber != $1.quarterNumber { return $0.quarterNumber < $1.quarterNumber }
            return ($0.start?.period?.number ?? 0) < ($1.start?.period?.number ?? 0)
        }
        var groups: [(quarter: Int, label: String, drives: [GameDetails.Drive])] = []
        for drive in sorted {
            let q = drive.quarterNumber
            if let idx = groups.firstIndex(where: { $0.quarter == q }) {
                groups[idx].drives.append(drive)
            } else {
                let label: String
                switch q {
                case 1: label = "1st Quarter"
                case 2: label = "2nd Quarter"
                case 3: label = "3rd Quarter"
                case 4: label = "4th Quarter"
                default: label = "OT \(q - 4)"
                }
                groups.append((quarter: q, label: label, drives: [drive]))
            }
        }
        return groups
    }

    var body: some View {
        ScrollView {
            if drives.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "figure.american.football")
                        .font(.system(size: 36))
                        .foregroundColor(.secondary)
                    Text("Drives not available")
                        .foregroundColor(.secondary)
                }
                .padding(.top, 40)
            } else {
                LazyVStack(spacing: 6) {
                    ForEach(quarterGroups, id: \.quarter) { group in
                        quarterSection(group)
                    }
                }
                .padding()
            }
        }
    }

    // MARK: - Quarter section

    @ViewBuilder
    private func quarterSection(_ group: (quarter: Int, label: String, drives: [GameDetails.Drive])) -> some View {
        let isOpen = expandedQuarters.contains(group.quarter)

        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if isOpen { expandedQuarters.remove(group.quarter) }
                    else      { expandedQuarters.insert(group.quarter) }
                }
            } label: {
                HStack {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary).frame(width: 16)
                    Text(group.label).font(.headline)
                    Spacer()
                    Text("\(group.drives.count) drive\(group.drives.count == 1 ? "" : "s")")
                        .font(.caption).foregroundColor(.secondary)
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(group.label), \(group.drives.count) drives")
            .accessibilityHint(isOpen ? "Double tap to collapse." : "Double tap to expand.")

            if isOpen {
                Divider().padding(.horizontal)
                VStack(spacing: 4) {
                    ForEach(group.drives) { drive in
                        driveRow(drive)
                    }
                }
                .padding(.bottom, 4)
            }
        }
        .background(Color.secondary.opacity(0.07))
        .cornerRadius(10)
    }

    // MARK: - Drive row

    @ViewBuilder
    private func driveRow(_ drive: GameDetails.Drive) -> some View {
        let isOpen = expandedDrives.contains(drive.id)
        let plays  = drive.plays ?? []
        let teamAbbr = drive.team?.abbreviation ?? "?"
        let result   = drive.result ?? "Unknown"
        let yards    = drive.yards.map { "\($0) yds" } ?? ""
        let playCount = drive.offensivePlays.map { "\($0) plays" } ?? "\(plays.count) plays"

        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    if isOpen { expandedDrives.remove(drive.id) }
                    else      { expandedDrives.insert(drive.id) }
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary).frame(width: 14)

                    Text(drive.resultEmoji)
                        .font(.title3)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(teamAbbr).font(.subheadline.bold())
                            Text(result).font(.subheadline).foregroundColor(drive.isScore == true ? .green : .primary)
                        }
                        if let desc = drive.description, !desc.isEmpty {
                            Text(desc).font(.caption).foregroundColor(.secondary).lineLimit(1)
                        }
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 2) {
                        Text(yards).font(.caption.bold())
                        Text(playCount).font(.caption2).foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(teamAbbr) drive, \(result), \(yards), \(playCount)")
            .accessibilityHint(isOpen ? "Double tap to collapse." : "Double tap to expand plays.")

            if isOpen {
                VStack(spacing: 0) {
                    ForEach(plays) { play in
                        drivePlayRow(play)
                        if play.id != plays.last?.id {
                            Divider().padding(.leading, 28)
                        }
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 4)
            }
        }
        .background(Color.secondary.opacity(0.04))
        .cornerRadius(8)
        .padding(.horizontal, 4)
    }

    // MARK: - Drive play row

    private func drivePlayRow(_ play: GameDetails.Drive.DrivePlay) -> some View {
        HStack(alignment: .top, spacing: 8) {
            if let clock = play.clock?.displayValue {
                Text(clock)
                    .font(.caption.bold())
                    .foregroundColor(.blue)
                    .frame(width: 48, alignment: .leading)
            }
            VStack(alignment: .leading, spacing: 2) {
                if let text = play.text, !text.isEmpty {
                    Text(text).font(.callout)
                } else if let typeText = play.type?.text {
                    Text(typeText).font(.caption).foregroundColor(.secondary)
                }
                if let yards = play.statYardage {
                    Text("\(yards > 0 ? "+" : "")\(yards) yards")
                        .font(.caption2)
                        .foregroundColor(yards > 0 ? .green : yards < 0 ? .red : .secondary)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }
}

