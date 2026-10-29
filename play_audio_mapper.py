#!/usr/bin/env python3
"""Plays spatial audio for basketball and hockey plays.

The baseball counterpart is `simple_audio_mapper` / `stereo_audio_mapper`: a
pitch's strike-zone coordinates become a frequency and a stereo balance, and the
tone says where the ball crossed the plate. Basketball and hockey plays carry
coordinates in the same `summary` feed, so a shot or a scoring chance can be
heard the same way.

`play_geometry` holds the mapping and carries no PyQt or winsound import, so it
is unit-tested on any platform. This module is the thin playback layer: it
generates a stereo WAV the way `stereo_audio_mapper` does and queues it through
`audio_queue` so it never blocks the UI thread.
"""

import math
import os
import platform
import struct
import tempfile
import time
import wave

from PyQt6.QtCore import QObject, pyqtSignal

from audio_queue import play_in_background
from play_geometry import audio_params, has_coordinate, league_family, locate

if platform.system() == "Windows":
    try:
        import winsound
        WINSOUND_AVAILABLE = True
    except ImportError:
        WINSOUND_AVAILABLE = False
else:
    WINSOUND_AVAILABLE = False

# Silence after each tone in a period sequence; iOS's playLocatedSequence
# leaves the same 180 ms.
SEQUENCE_GAP_SECONDS = 0.18


class PlayAudioMapper(QObject):
    """Spatial audio for a basketball or hockey play's location."""

    # No "audio_generated" signal on purpose. The tone is the output here;
    # speaking the location on top of it would only repeat what the screen
    # reader already said when focus landed on the play, and talk over the
    # sound it is describing.
    audio_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True  # WAV generation works regardless of winsound
        self.temp_files = []
        # Bumped by stop(). Each queued tone remembers the generation it was
        # queued under and is skipped once that has moved on, so a new Alt+P or
        # Alt+S, or closing the plays dialog, cuts off a period still playing
        # instead of waiting 30 seconds behind it.
        self._generation = 0
        # One error report per playback run, not one per queued tone.
        self._error_reported_for = None

    def stop(self):
        """Drop every tone still queued from earlier playback."""
        self._generation += 1

    def supports(self, league):
        """True when this league's plays carry coordinates worth sonifying."""
        return league_family(league) is not None

    def describe_play(self, league, play):
        """Spoken location for a play, or None if it has no usable location."""
        if not has_coordinate(play):
            return None
        coord = play["coordinate"]
        location = locate(league, coord["x"], coord["y"])
        return location.description if location else None

    def generate_play_audio(self, league, play):
        """Play the tone for a single play. Returns the spoken location, or None.

        A play with no location — a substitution, a timeout, a free throw, most
        face-offs — is not an error; roughly a third of basketball plays and six
        percent of hockey plays have none. The caller gets None so it can say so
        rather than play a misleading tone.
        """
        if not has_coordinate(play):
            return None

        coord = play["coordinate"]
        params = audio_params(league, coord["x"], coord["y"])
        if params is None:
            return None

        frequency, duration_ms, balance, description = params
        self.stop()
        generation = self._generation
        try:
            play_in_background(
                self._play_queued_tone, generation, frequency, duration_ms / 1000.0, balance, 0.0
            )
            return description
        except Exception as e:
            self.audio_error.emit(f"Play audio failed: {str(e)}")
            return None

    def generate_play_sequence(self, league, plays):
        """Queue tones for every play that has a location, in order.

        `audio_queue` runs one sound at a time on a single worker thread, so the
        tones play in sequence without overlapping and without holding the UI.
        Each is followed by the same short gap iOS leaves, so two shots from the
        same spot are heard as two tones rather than one long one. Returns how
        many plays were queued.
        """
        located = []
        for play in plays:
            if not has_coordinate(play):
                continue
            coord = play["coordinate"]
            params = audio_params(league, coord["x"], coord["y"])
            if params is not None:
                located.append(params)

        if not located:
            return 0

        self.stop()
        generation = self._generation
        sonified = 0
        for frequency, duration_ms, balance, _ in located:
            try:
                play_in_background(
                    self._play_queued_tone,
                    generation,
                    frequency,
                    duration_ms / 1000.0,
                    balance,
                    SEQUENCE_GAP_SECONDS,
                )
                sonified += 1
            except Exception as e:
                self.audio_error.emit(f"Play audio failed: {str(e)}")
                break

        return sonified

    def _play_queued_tone(self, generation, frequency, duration, balance, gap):
        """Runs on the audio thread: play one tone unless it has been superseded."""
        if generation != self._generation:
            return
        try:
            self._play_stereo_tone(frequency, duration, balance)
        except Exception as e:
            # Report once per run. Success is silent, so without this a missing
            # or busy output device would sound exactly like it worked.
            if self._error_reported_for != generation:
                self._error_reported_for = generation
                self.audio_error.emit(str(e))
            return
        if gap and generation == self._generation:
            time.sleep(gap)

    def _play_stereo_tone(self, frequency, duration, balance):
        """Write one tone's WAV, play it, and remove it."""
        path = self._write_tone_wav(frequency, duration, balance)
        try:
            if WINSOUND_AVAILABLE:
                winsound.PlaySound(path, winsound.SND_FILENAME)
        finally:
            self._remove_temp_file(path)

    def _write_tone_wav(self, frequency, duration, balance):
        """Write a stereo WAV for one tone and return its path.

        Mirrors `stereo_audio_mapper._play_stereo_beep`: constant-power panning
        so the tone keeps a steady loudness as it moves across the stereo field,
        and a short fade at each end so there is no click.
        """
        sample_rate = 44100
        samples = int(sample_rate * duration)
        fade = int(sample_rate * 0.02)  # 20 ms, enough to kill the click

        left_volume = math.cos(balance * math.pi / 2)
        right_volume = math.sin(balance * math.pi / 2)

        frames = []
        for i in range(samples):
            t = i / sample_rate
            # Fundamental plus a quiet second and third partial, which is what
            # gives the iOS tones their marimba quality instead of a flat sine.
            value = (
                math.sin(2 * math.pi * frequency * t)
                + 0.30 * math.sin(4 * math.pi * frequency * t)
                + 0.10 * math.sin(6 * math.pi * frequency * t)
            ) / 1.40

            if i < fade:
                value *= i / fade
            elif i > samples - fade:
                value *= (samples - i) / fade

            frames.append(
                struct.pack(
                    "<hh",
                    int(value * left_volume * 32767),
                    int(value * right_volume * 32767),
                )
            )

        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_files.append(temp_file.name)
        temp_file.close()

        with wave.open(temp_file.name, "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(frames))

        return temp_file.name

    def _remove_temp_file(self, path):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
        try:
            self.temp_files.remove(path)
        except ValueError:
            pass

    def cleanup(self):
        """Remove any temporary WAV files this mapper still holds."""
        for temp_file in list(self.temp_files):
            self._remove_temp_file(temp_file)

    def __del__(self):
        self.cleanup()
