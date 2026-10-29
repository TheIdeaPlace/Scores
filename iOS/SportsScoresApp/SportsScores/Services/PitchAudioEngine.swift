//
//  PitchAudioEngine.swift
//  SportsScores
//
//  Pitch sonification engine for baseball play-by-play.
//
//  Design goals:
//   • Sound *musical*, not synthetic — uses a harmonic-rich waveform (fundamental +
//     2nd + 3rd partial, like a vibraphone/marimba) rather than a raw sine wave.
//   • Pitch height maps to the A-minor pentatonic scale (always harmonious together).
//   • Stereo pan from X coordinate positions the pitch left↔right on the plate.
//   • Plate velocity → note sustain length (faster = shorter).
//   • AVAudioUnitReverb adds spatial depth identical to what Apple uses in AudioGraph.
//
//  Audio graph:  playerNode ──► reverb ──► mainMixerNode ──► output
//

import AVFoundation
import AudioToolbox
import CoreAudio   // UnsafeMutableAudioBufferListPointer (transitive on iOS, explicit for Mac Catalyst)
import Foundation

@MainActor
final class PitchAudioEngine: ObservableObject {
    
    // MARK: - Published State
    
    @Published var isPlaying = false
    @Published var statusMessage = ""
    
    // MARK: - Private
    
    private var engine: AVAudioEngine?
    private var sequenceTask: Task<Void, Never>?
    private var dragTask: Task<Void, Never>?   // separate slot for continuous-drag tones
    
    private let sampleRate: Double = 44100
    
    // A-minor pentatonic across 3 octaves — always harmonious when played together.
    // Maps the strike zone from bottom (lowest note) to top (highest note).
    private let pentatonicHz: [Double] = [
        // Octave 3: A C D E G
        220.00, 261.63, 293.66, 329.63, 392.00,
        // Octave 4: A C D E G
        440.00, 523.25, 587.33, 659.25, 784.00,
        // Octave 5: A C D E G
        880.00, 1046.50, 1174.66, 1318.51, 1567.98
    ]
    
    // MARK: - Public API
    
    /// Play the audio tone for a single pitch.
    func play(_ pitch: GameDetails.Play) {
        guard let coord = pitch.pitchCoordinate else { return }
        sequenceTask?.cancel()
        let (freq, pan, dur) = audioParams(coord: coord, velocity: pitch.pitchVelocity)
        let desc  = pitch.locationDescription(batterHand: pitch.bats?.abbreviation)
        let vel   = pitch.pitchVelocity.map { "\($0) mph" } ?? ""
        let ptype = pitch.pitchType?.text ?? ""
        statusMessage = [ptype, vel, desc].filter { !$0.isEmpty }.joined(separator: " · ")
        sequenceTask = Task { await self.tone(frequency: freq, pan: pan, duration: dur) }
    }
    
    /// Play every pitch in `pitches` sequentially with a short gap between tones.
    func playSequence(_ pitches: [GameDetails.Play]) {
        sequenceTask?.cancel()
        sequenceTask = Task {
            for (i, pitch) in pitches.enumerated() {
                guard !Task.isCancelled else { break }
                guard let coord = pitch.pitchCoordinate else { continue }
                let (freq, pan, dur) = self.audioParams(coord: coord, velocity: pitch.pitchVelocity)
                let label = pitch.pitchType?.abbreviation ?? "–"
                await MainActor.run {
                    self.statusMessage = "Pitch \(i + 1): \(label) · \(pitch.locationDescription(batterHand: nil))"
                }
                await self.tone(frequency: freq, pan: pan, duration: dur)
                try? await Task.sleep(nanoseconds: 180_000_000)   // 180 ms gap
            }
            await MainActor.run { self.statusMessage = "Sequence complete" }
        }
    }
    
    /// Stop any playing tone / sequence immediately.
    func stop() {
        sequenceTask?.cancel()
        dragTask?.cancel()
        engine?.stop()
        engine = nil
        stopDragTone()
        isPlaying = false
        statusMessage = ""
    }

    // MARK: - Zone Explorer / Field Tour audio

    /// Play a short tone for an arbitrary ESPN 0–255 coordinate.
    /// Cancels any in-flight drag tone before starting — prevents engine pile-up.
    func playCoordinate(espnX: Int, espnY: Int, velocity: Int? = nil) {
        let coord = GameDetails.Play.PitchCoordinate(x: espnX, y: espnY)
        let (freq, pan, _) = audioParams(coord: coord, velocity: velocity)
        dragTask?.cancel()
        dragTask = Task { await self.tone(frequency: freq, pan: pan, duration: 0.35) }
    }

    // MARK: - Basketball and hockey play audio

    /// Play the tone for one basketball or hockey play, and return what it said.
    ///
    /// Returns nil when the play has no location to play. That is not a failure:
    /// roughly a third of basketball plays and six percent of hockey plays
    /// arrive without coordinates — substitutions, timeouts, free throws, most
    /// face-offs — so the caller tells the listener rather than playing a tone
    /// that would be a guess. See `PlayAudioGeometry` for the mapping.
    @discardableResult
    func playLocatedPlay(_ play: GameDetails.Play, sport: Sport) -> String? {
        guard let params = PlayAudioGeometry.audioParameters(for: sport, play: play)
        else { return nil }

        sequenceTask?.cancel()
        statusMessage = [play.type.text, params.description]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
        sequenceTask = Task {
            await self.tone(frequency: params.frequency, pan: params.pan, duration: params.duration)
        }
        return params.description
    }

    /// Walk a period, playing every play in it that has a location.
    ///
    /// Returns how many were sonified, so the caller can say "12 of 31" rather
    /// than leave the listener wondering about the silent ones.
    @discardableResult
    func playLocatedSequence(_ plays: [GameDetails.Play], sport: Sport) -> Int {
        let located = plays.compactMap { play -> (GameDetails.Play, (frequency: Double, pan: Float, duration: Double, description: String))? in
            guard let params = PlayAudioGeometry.audioParameters(for: sport, play: play)
            else { return nil }
            return (play, params)
        }
        guard !located.isEmpty else { return 0 }

        sequenceTask?.cancel()
        sequenceTask = Task {
            for (index, entry) in located.enumerated() {
                guard !Task.isCancelled else { break }
                let (play, params) = entry
                await MainActor.run {
                    self.statusMessage =
                        "Play \(index + 1) of \(located.count): \(play.type.text) · \(params.description)"
                }
                await self.tone(frequency: params.frequency, pan: params.pan, duration: params.duration)
                try? await Task.sleep(nanoseconds: 180_000_000)   // 180 ms gap
            }
            await MainActor.run { self.statusMessage = "Sequence complete" }
        }
        return located.count
    }

    /// Play a spatial tone mapped from real-world field coordinates (feet from home plate).
    /// Cancels any in-flight drag tone before starting — prevents engine pile-up.
    func playFieldCoordinate(fieldX: Double, fieldY: Double,
                             maxHalfWidth: Double, maxDepth: Double) {
        let pan = Float((fieldX / maxHalfWidth).clamped(to: -1.0...1.0))
        let dist = (fieldX * fieldX + fieldY * fieldY).squareRoot()
        let distNorm = (dist / maxDepth).clamped(to: 0.0...1.0)
        let noteIndex = Int(distNorm * Double(pentatonicHz.count - 1))
            .clamped(to: 0..<pentatonicHz.count)
        let freq = pentatonicHz[noteIndex]
        dragTask?.cancel()
        dragTask = Task { await self.tone(frequency: freq, pan: pan, duration: 0.35) }
    }
    
    // MARK: - Parameter Mapping
    
    /// Convert pitch coordinates + velocity to (frequency, pan, duration).
    func audioParams(
        coord: GameDetails.Play.PitchCoordinate,
        velocity: Int?
    ) -> (frequency: Double, pan: Float, duration: Double) {
        
        // Y  0 = top of zone (high pitch), 255 = bottom (low pitch) — invert
        let yNorm = 1.0 - (Double(coord.y) / 255.0).clamped(to: 0...1)
        let xNorm = (Double(coord.x) / 255.0).clamped(to: 0...1)
        
        // Snap to the nearest pentatonic note
        let noteIndex = Int(yNorm * Double(pentatonicHz.count - 1)).clamped(to: 0..<pentatonicHz.count)
        let frequency = pentatonicHz[noteIndex]
        
        // Stereo pan: x → –1.0 (left) … +1.0 (right)
        let pan = Float((xNorm * 2.0 - 1.0).clamped(to: -1.0...1.0))
        
        // Duration: 60–105 mph → 0.55–0.25 s (faster pitch = shorter, crisper note)
        let duration: Double
        if let vel = velocity {
            let velNorm = ((Double(vel) - 60.0) / 45.0).clamped(to: 0...1)
            duration = 0.25 + 0.30 * (1.0 - velNorm)
        } else {
            duration = 0.40
        }
        
        return (frequency, pan, duration)
    }
    
    // MARK: - Tone Generation
    
    /// Generate and play a musical tone with:
    ///   • harmonic-rich waveform  (fundamental + 30% 2nd + 10% 3rd partial → vibraphone-like)
    ///   • reverb                  (smallRoom preset, 35% wet)
    ///   • constant-power stereo pan
    ///   • smooth ADSR envelope    (30 ms attack, exponential decay tail)
    private func tone(frequency: Double, pan: Float, duration: Double) async {
        await MainActor.run { isPlaying = true }
        
        // iOS / Mac Catalyst audio session
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            await MainActor.run { isPlaying = false }
            return
        }
        
        let newEngine = AVAudioEngine()
        engine = newEngine
        let playerNode = AVAudioPlayerNode()
        
        // Reverb — adds the spatial quality Apple uses in built-in AudioGraph tones
        let reverb = AVAudioUnitReverb()
        reverb.loadFactoryPreset(.smallRoom)
        reverb.wetDryMix = 35
        
        newEngine.attach(playerNode)
        newEngine.attach(reverb)
        
        let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2)!
        newEngine.connect(playerNode, to: reverb, format: format)
        newEngine.connect(reverb, to: newEngine.mainMixerNode, format: format)
        
        // Build PCM buffer
        let totalFrames = AVAudioFrameCount(sampleRate * duration)
        let attackFrames = AVAudioFrameCount(sampleRate * 0.03)   // 30 ms attack
        let releaseFrames = AVAudioFrameCount(sampleRate * 0.06)   // 60 ms release
        
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: totalFrames) else {
            await MainActor.run { isPlaying = false }
            return
        }
        buffer.frameLength = totalFrames
        
        // Constant-power panning
        let angle     = Double((pan + 1.0) / 2.0) * .pi / 2.0
        let leftGain  = Float(cos(angle))
        let rightGain = Float(sin(angle))
        
        // Phase increment for fundamental (harmonics derive from phase * 2, phase * 3 —
        // correct even across wrap boundaries because sin is 2π-periodic)
        let phaseStep = 2.0 * Double.pi * frequency / sampleRate
        var phase = 0.0
        
        if let leftData  = buffer.floatChannelData?[0],
           let rightData = buffer.floatChannelData?[1] {
            for i in 0..<Int(totalFrames) {
                // Envelope: attack ramp → exponential decay (marimba-style)
                let fi = AVAudioFrameCount(i)
                let envelope: Float
                if fi < attackFrames {
                    // Linear attack
                    envelope = Float(fi) / Float(attackFrames)
                } else {
                    // Exponential decay from 1 → near-zero over the remaining duration
                    let t = Double(fi - attackFrames) / Double(totalFrames - attackFrames)
                    let decayedAmp = pow(1.0 - t, 1.8)   // slightly faster than linear
                    // Smooth release window at the very end to avoid click
                    let rel = totalFrames - releaseFrames
                    if fi >= rel {
                        let r = Float(totalFrames - fi) / Float(releaseFrames)
                        envelope = Float(decayedAmp) * r
                    } else {
                        envelope = Float(decayedAmp)
                    }
                }
                
                // Harmonic mix: fundamental + 2nd (30%) + 3rd (10%) — vibraphone timbre
                let h1 = sin(phase)
                let h2 = sin(phase * 2.0) * 0.30
                let h3 = sin(phase * 3.0) * 0.10
                let mono = Float((h1 + h2 + h3) / 1.40) * envelope * 0.80
                
                phase += phaseStep
                if phase > 2 * .pi { phase -= 2 * .pi }
                
                leftData[i]  = mono * leftGain
                rightData[i] = mono * rightGain
            }
        }
        
        do { try newEngine.start() } catch {
            await MainActor.run { isPlaying = false }
            return
        }
        
        playerNode.play()
        await playerNode.scheduleBuffer(buffer)
        
        newEngine.stop()
        if engine === newEngine { engine = nil }
        
        await MainActor.run {
            if !(sequenceTask?.isCancelled ?? true) { isPlaying = false }
        }
    }

    // MARK: - Continuous drag tone (real-time zone / field exploration)
    //
    // Uses AVAudioSourceNode — the render callback runs at audio-thread speed and
    // reads `dragState.frequency` written on the main actor. The race is benign:
    // at worst one render quantum (< 3 ms) plays the previous frequency before
    // the new one takes effect. `dragState.phase` is owned solely by the audio
    // thread (written + read inside the callback only).
    //
    // Pan is updated by repositioning the source inside AVAudioEnvironmentNode —
    // the same zero-latency approach FieldAudioEngine uses for terrain panning.

    private let dragState = DragToneState()
    private var ctEngine:  AVAudioEngine?
    private var ctSource:  AVAudioSourceNode?

    /// Begin a continuously-playing spatial tone mapped to the normalised canvas
    /// position (normX 0=left…1=right, normY 0=top…1=bottom). Call on first drag touch.
    func beginDragTone(normX: Double, normY: Double) {
        stopDragTone()   // clean up any previous session

        let (freq, pan) = dragAudioParams(normX: normX, normY: normY)
        dragState.frequency = freq
        dragState.phase     = 0.0

        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
            try AVAudioSession.sharedInstance().setActive(true)
        } catch { return }

        let mono   = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        let stereo = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2)!
        let eng    = AVAudioEngine()
        let env    = AVAudioEnvironmentNode()

        env.listenerPosition = AVAudio3DPoint(x: 0, y: 0, z: 0)

        // Render callback — audio thread, reads dragState by reference (@unchecked Sendable)
        let state = dragState
        let sr = sampleRate
        let src = AVAudioSourceNode(format: mono) { _, _, frameCount, audioBufferList in
            let ablPointer = UnsafeMutableAudioBufferListPointer(audioBufferList)
            let freq = state.frequency
            let step = 2.0 * Double.pi * freq / sr
            for frame in 0..<Int(frameCount) {
                let p = state.phase
                // Harmonic-rich waveform: fundamental + 30% 2nd + 10% 3rd (vibraphone timbre)
                let s = Float(0.35 * (sin(p) + 0.30 * sin(2 * p) + 0.10 * sin(3 * p)))
                state.phase = (p + step).truncatingRemainder(dividingBy: 2.0 * .pi)
                for buf in ablPointer {
                    buf.mData!.assumingMemoryBound(to: Float.self)[frame] = s
                }
            }
            return noErr
        }

        eng.attach(src)
        eng.attach(env)
        eng.connect(src, to: env, format: mono)
        eng.connect(env, to: eng.mainMixerNode, format: stereo)

        guard (try? eng.start()) != nil else { return }

        // Position the source for immediate stereo pan
        src.position = AVAudio3DPoint(x: Float(pan * 4.0), y: 0, z: -1)

        ctEngine = eng
        ctSource  = src
    }

    /// Update frequency and pan on every drag-changed event — no throttle needed.
    func updateDragTone(normX: Double, normY: Double) {
        let (freq, pan) = dragAudioParams(normX: normX, normY: normY)
        dragState.frequency = freq
        ctSource?.position  = AVAudio3DPoint(x: Float(pan * 4.0), y: 0, z: -1)
    }

    /// Stop the continuous drag tone (call on drag end or view disappear).
    func stopDragTone() {
        ctEngine?.stop()
        ctEngine = nil
        ctSource  = nil
    }

    private func dragAudioParams(normX: Double, normY: Double) -> (frequency: Double, pan: Double) {
        // normY: 0=top (high pitch), 1=bottom (low pitch) — invert for note index
        let yNorm     = (1.0 - normY).clamped(to: 0...1)
        let noteIndex = Int(yNorm * Double(pentatonicHz.count - 1)).clamped(to: 0..<pentatonicHz.count)
        let freq      = pentatonicHz[noteIndex]
        let pan       = (normX * 2.0 - 1.0).clamped(to: -1.0...1.0)
        return (freq, pan)
    }
}

// MARK: - Shared drag-tone state (audio-thread ↔ main-actor bridge)

/// Mutable state shared between the main-actor PitchAudioEngine and the
/// audio-thread render callback. Marked @unchecked Sendable — the caller accepts
/// responsibility for the benign frequency-write race.
private final class DragToneState: @unchecked Sendable {
    var frequency: Double = 440.0
    /// Phase accumulator — written and read exclusively on the audio thread.
    var phase:     Double = 0.0
}

// MARK: - Comparable clamp helper

extension Double {
    func clamped(to range: ClosedRange<Double>) -> Double {
        Swift.min(Swift.max(self, range.lowerBound), range.upperBound)
    }
}

extension Int {
    func clamped(to range: Range<Int>) -> Int {
        Swift.min(Swift.max(self, range.lowerBound), range.upperBound - 1)
    }
}


