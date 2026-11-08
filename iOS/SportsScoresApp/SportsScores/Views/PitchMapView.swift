//
//  PitchMapView.swift
//  SportsScores
//
//  Pitch sonification view for MLB games.
//
//  • Visual strike-zone chart (Swift Charts) — VoiceOver automatically provides
//    an AudioGraph (data-sonification sweep) for accessibility.
//  • Interactive per-pitch audio (PitchAudioEngine) — stereo sine tones mapping
//    vertical position → frequency and horizontal position → left/right pan,
//    mirroring the Python stereo_audio_mapper.py system.
//

import SwiftUI
import Charts

// MARK: - At-Bat grouping helper

private struct AtBat: Identifiable {
    let id: String          // atBatId
    let inning: String
    let pitches: [GameDetails.Play]
    
    var result: String? { pitches.last?.text }
    var batterHand: String? { pitches.first?.bats?.abbreviation }
}

// MARK: - PitchMapView

struct PitchMapView: View {
    
    let plays: [GameDetails.Play]
    
    @StateObject private var audio = PitchAudioEngine()
    @State private var selectedPitchId: String?
    @State private var expandedAtBats: Set<String> = []
    
    // Pitch plays only (filter out non-pitch events like inning-start markers)
    private var pitchPlays: [GameDetails.Play] {
        plays.filter { $0.isPitch }
    }
    
    // Group pitches by at-bat, preserving inning order
    private var atBats: [AtBat] {
        var groups: [String: [GameDetails.Play]] = [:]
        var order: [String] = []
        for play in pitchPlays {
            let key = play.atBatId ?? play.id
            if groups[key] == nil { order.append(key) }
            groups[key, default: []].append(play)
        }
        return order.compactMap { key in
            guard let pitches = groups[key], !pitches.isEmpty else { return nil }
            let inning = pitches.first?.period?.displayValue ?? ""
            return AtBat(id: key, inning: inning, pitches: pitches)
        }
    }
    
    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                
                summaryHeader
                
                if !pitchPlays.isEmpty {
                    strikeZoneChart
                    audioStatusBar
                    atBatList
                } else {
                    Text("Pitch coordinate data not available for this game.")
                        .foregroundColor(.secondary)
                        .padding()
                }
            }
            .padding()
        }
    }
    
    // MARK: - Summary Header
    
    private var summaryHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Label("\(pitchPlays.count) pitches", systemImage: "baseball")
                    .font(.headline)
                Spacer()
                Label("\(atBats.count) at-bats", systemImage: "figure.baseball")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            Text("Tap a pitch row to hear its location · Tap ▶ to play sequence")
                .font(.caption)
                .foregroundColor(.secondary)
                // In words: VoiceOver reads the triangle by its name, not as the Play button.
                .accessibilityLabel("Tap a pitch row to hear its location. Tap Play to play the sequence.")
        }
        .padding()
        .background(Color.secondary.opacity(0.08))
        .cornerRadius(10)
    }
    
    // MARK: - Strike Zone Chart (Swift Charts · VoiceOver AudioGraph)
    
    private var strikeZoneChart: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Strike Zone")
                    .font(.headline)
                Spacer()
                Text("Color = result")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Chart(pitchPlays, id: \.id) { pitch in
                if let coord = pitch.pitchCoordinate {
                    PointMark(
                        // x: catcher's perspective (0=left, 255=right)
                        x: .value("Horizontal", coord.x),
                        // Flip y so that top of zone appears at top of chart
                        y: .value("Height", 255 - coord.y)
                    )
                    .foregroundStyle(by: .value("Result", pitch.type.text))
                    .symbolSize(pitch.id == selectedPitchId ? 120 : 60)
                    .accessibilityLabel("\(pitch.pitchType?.text ?? "Pitch") \(pitch.locationDescription(batterHand: nil))")
                    .accessibilityValue("\(pitch.pitchVelocity.map { "\($0) mph" } ?? "") · \(pitch.type.text)")
                }
            }
            .chartXScale(domain: 0...255)
            .chartYScale(domain: 0...255)
            // Draw the strike zone rectangle (centres roughly in ESPN's coordinate space)
            .chartOverlay { proxy in
                GeometryReader { _ in
                    if let x1 = proxy.position(forX: 90),
                       let x2 = proxy.position(forX: 165),
                       // Inverted Y: original y=80 (top of zone) → plotted as 255-80=175
                       //             original y=175 (bottom)     → plotted as 255-175=80
                       let yTop    = proxy.position(forY: 175),  // screen-top of zone
                       let yBottom = proxy.position(forY: 80) {  // screen-bottom of zone
                        let w = abs(x2 - x1)
                        let h = abs(yBottom - yTop)
                        Rectangle()
                            .stroke(Color.gray, lineWidth: 1.5)
                            .frame(width: w, height: h)
                            .position(x: (x1 + x2) / 2, y: (yTop + yBottom) / 2)
                    }
                }
            }
            .frame(height: 240)
            .padding(4)
            .background(Color.secondary.opacity(0.05))
            .cornerRadius(10)
            // VoiceOver AudioGraph: describes the pitch scatter as a sonified sweep
            .accessibilityChartDescriptor(PitchChartDescriptor(plays: pitchPlays))
        }
    }
    
    // MARK: - Audio Status Bar
    
    private var audioStatusBar: some View {
        HStack(spacing: 12) {
            Image(systemName: audio.isPlaying ? "speaker.wave.3.fill" : "speaker.slash")
                .foregroundColor(audio.isPlaying ? .blue : .secondary)
                .animation(.easeInOut, value: audio.isPlaying)
            
            Text(audio.statusMessage.isEmpty ? "Select a pitch to hear its location" : audio.statusMessage)
                .font(.caption)
                .foregroundColor(audio.isPlaying ? .primary : .secondary)
                .animation(.easeInOut, value: audio.statusMessage)
            
            Spacer()
            
            if audio.isPlaying {
                Button("Stop") { audio.stop() }
                    .font(.caption.bold())
                    .buttonStyle(.bordered)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.secondary.opacity(0.08))
        .cornerRadius(10)
    }
    
    // MARK: - At-Bat List
    
    private var atBatList: some View {
        VStack(spacing: 12) {
            ForEach(atBats) { atBat in
                atBatCard(atBat)
            }
        }
    }
    
    private func atBatCard(_ atBat: AtBat) -> some View {
        let isExpanded = expandedAtBats.contains(atBat.id)
        
        return VStack(spacing: 0) {
            // At-bat header
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if isExpanded { expandedAtBats.remove(atBat.id) }
                    else          { expandedAtBats.insert(atBat.id) }
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .foregroundColor(.secondary)
                        .frame(width: 16)
                    
                    VStack(alignment: .leading, spacing: 2) {
                        Text(atBat.inning)
                            .font(.subheadline.bold())
                        if let result = atBat.result {
                            Text(result)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }
                    
                    Spacer()
                    
                    // Pitch result dots
                    HStack(spacing: 3) {
                        ForEach(atBat.pitches, id: \.id) { p in
                            Text(p.pitchResultLabel)
                                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                                .foregroundColor(resultColor(p))
                        }
                    }
                    
                    // Sequence play button
                    Button {
                        audio.playSequence(atBat.pitches)
                    } label: {
                        Label("Play", systemImage: "play.fill")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                    .tint(.blue)
                    .accessibilityLabel("Play all \(atBat.pitches.count) pitches in this at-bat")
                }
                .padding(12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            
            // Expanded pitch rows
            if isExpanded {
                Divider().padding(.horizontal)
                ForEach(Array(atBat.pitches.enumerated()), id: \.element.id) { index, pitch in
                    pitchRow(pitch, number: index + 1, batterHand: atBat.batterHand)
                    if index < atBat.pitches.count - 1 {
                        Divider().padding(.leading, 44)
                    }
                }
            }
        }
        .background(Color.secondary.opacity(0.06))
        .cornerRadius(12)
    }
    
    private func pitchRow(_ pitch: GameDetails.Play, number: Int, batterHand: String?) -> some View {
        let isSelected = selectedPitchId == pitch.id
        
        return Button {
            selectedPitchId = pitch.id
            audio.play(pitch)
        } label: {
            HStack(spacing: 10) {
                // Pitch number
                Text("\(number)")
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.secondary)
                    .frame(width: 20, alignment: .trailing)
                
                // Result badge
                Text(pitch.pitchResultLabel)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundColor(.white)
                    .frame(width: 22, height: 22)
                    .background(resultColor(pitch))
                    .cornerRadius(4)
                
                // Pitch type + velocity
                VStack(alignment: .leading, spacing: 1) {
                    Text(pitch.pitchType?.text ?? pitch.type.text)
                        .font(.caption.bold())
                    if let vel = pitch.pitchVelocity {
                        Text("\(vel) mph")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                
                // Location
                if let _ = pitch.pitchCoordinate {
                    Text(pitch.locationDescription(batterHand: batterHand))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                
                Spacer()
                
                // Count after pitch
                if let count = pitch.resultCount {
                    Text("\(count.balls)-\(count.strikes)")
                        .font(.caption.monospacedDigit())
                        .foregroundColor(.secondary)
                }
                
                // Audio indicator
                Image(systemName: isSelected && audio.isPlaying ? "speaker.wave.2.fill" : "speaker")
                    .font(.caption)
                    .foregroundColor(isSelected ? .blue : .secondary.opacity(0.4))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? Color.blue.opacity(0.08) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(buildAccessibilityLabel(pitch, number: number, batterHand: batterHand))
    }
    
    // MARK: - Helpers
    
    private func resultColor(_ pitch: GameDetails.Play) -> Color {
        switch pitch.pitchResultColorName {
        case "blue":    return .blue
        case "red":     return .red
        case "orange":  return .orange
        case "gray":    return .gray
        case "green":   return .green
        default:        return Color.secondary
        }
    }
    
    private func buildAccessibilityLabel(_ pitch: GameDetails.Play, number: Int, batterHand: String?) -> String {
        var parts = ["Pitch \(number)"]
        if let t = pitch.pitchType?.text { parts.append(t) }
        if let v = pitch.pitchVelocity   { parts.append("\(v) miles per hour") }
        parts.append(pitch.locationDescription(batterHand: batterHand))
        parts.append(pitch.type.text)
        if let c = pitch.resultCount { parts.append("Count: \(c.balls) and \(c.strikes)") }
        parts.append("Tap to hear audio")
        return parts.joined(separator: ". ")
    }
}

// MARK: - Swift Charts AudioGraph Descriptor
//
// When VoiceOver is active, this provides a sonified sweep of the pitch scatter
// using the iOS AudioGraph accessibility API (AXChartDescriptor).

private struct PitchChartDescriptor: AXChartDescriptorRepresentable {
    let plays: [GameDetails.Play]
    
    func makeChartDescriptor() -> AXChartDescriptor {
        let pitchAxis = AXNumericDataAxisDescriptor(
            title: "Horizontal Position",
            range: 0.0...255.0,
            gridlinePositions: [90.0, 165.0]
        ) { value in "Position \(Int(value))" }
        
        let heightAxis = AXNumericDataAxisDescriptor(
            title: "Height in Zone",
            range: 0.0...255.0,
            gridlinePositions: [80.0, 175.0]
        ) { value in
            switch Int(value) {
            case 0..<85:  return "Low"
            case 85..<170: return "Middle"
            default:       return "High"
            }
        }
        
        // Group by result type for separate sonification series
        var grouped: [String: [GameDetails.Play]] = [:]
        for play in plays {
            let key = play.type.text
            grouped[key, default: []].append(play)
        }
        
        let series = grouped.map { (resultText, pitches) in
            AXDataSeriesDescriptor(
                name: resultText,
                isContinuous: false,
                dataPoints: pitches.compactMap { p in
                    guard let c = p.pitchCoordinate else { return nil }
                    return AXDataPoint(
                        x: Double(c.x),
                        y: Double(255 - c.y),  // flip Y so top = high value
                        additionalValues: [],
                        label: p.pitchType?.text
                    )
                }
            )
        }
        
        return AXChartDescriptor(
            title: "Pitch locations — \(plays.count) pitches",
            summary: "Scatter chart of pitch coordinates. Inside/outside on horizontal axis, high/low on vertical axis.",
            xAxis: pitchAxis,
            yAxis: heightAxis,
            additionalAxes: [],
            series: series
        )
    }
}

#Preview {
    let sampleCoord = GameDetails.Play.PitchCoordinate(x: 127, y: 100)
    let sampleType  = GameDetails.Play.PitchTypeInfo(text: "Four-seam FB", abbreviation: "FF")
    let sampleHand  = GameDetails.Play.BatterHand(abbreviation: "R")
    let count       = GameDetails.Play.PitchCount(balls: 0, strikes: 1)
    let period      = GameDetails.Play.Period(displayValue: "Top 1st", type: "Top", number: 1)
    let playType    = GameDetails.Play.PlayType(text: "Called Strike", type: "called-strike")
    
    let fakePlay = GameDetails.Play(
        id: "1",
        text: "Pitch 1: Called Strike 1",
        type: playType,
        scoreValue: 0,
        period: period,
        pitchCoordinate: sampleCoord,
        pitchType: sampleType,
        pitchVelocity: 95,
        bats: sampleHand,
        atBatId: "ab1",
        atBatPitchNumber: 1,
        resultCount: count,
        outs: 0
    )
    
    NavigationStack {
        PitchMapView(plays: [fakePlay])
            .navigationTitle("Pitches")
    }
}
