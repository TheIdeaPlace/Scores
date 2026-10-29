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
        try:
            play_in_background(
                self._play_stereo_tone_reporting, frequency, duration_ms / 1000.0, balance
            )
            return description
        except Exception as e:
            self.audio_error.emit(f"Play audio failed: {str(e)}")
            return None

    def generate_play_sequence(self, league, plays):
        """Queue tones for every play that has a location, in order.

        `audio_queue` runs one sound at a time on a single worker thread, so the
        tones play in sequence without overlapping and without holding the UI.
        Returns how many plays were sonified.
        """
        sonified = 0
        for play in plays:
            if not has_coordinate(play):
                continue
            coord = play["coordinate"]
            params = audio_params(league, coord["x"], coord["y"])
            if params is None:
                continue
            frequency, duration_ms, balance, _ = params
            try:
                play_in_background(
                    self._play_stereo_tone_reporting,
                    frequency,
                    duration_ms / 1000.0,
                    balance,
                )
                sonified += 1
            except Exception as e:
                self.audio_error.emit(f"Play audio failed: {str(e)}")
                break

        return sonified

    def _play_stereo_tone_reporting(self, frequency, duration, balance):
        """_play_stereo_tone on the audio thread, reporting failure by signal."""
        try:
            self._play_stereo_tone(frequency, duration, balance)
        except Exception as e:
            self.audio_error.emit(str(e))

    def _play_stereo_tone(self, frequency, duration, balance):
        """Write a stereo WAV for one tone and play it.

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

        if WINSOUND_AVAILABLE:
            winsound.PlaySound(temp_file.name, winsound.SND_FILENAME)

    def cleanup(self):
        """Remove the temporary WAV files this mapper wrote."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass
        self.temp_files.clear()

    def __del__(self):
        self.cleanup()
