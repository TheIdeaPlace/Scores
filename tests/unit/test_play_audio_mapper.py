"""Checks the basketball/hockey play audio mapper.

winsound only exists on Windows, so `_play_stereo_tone` writes its WAV and then
skips playback everywhere else. That is enough to verify the tone itself — the
file it hands winsound is the whole output.
"""

import os
import wave

import pytest

from play_audio_mapper import PlayAudioMapper


def nba_play(x, y, text="Jump Shot"):
    return {"text": text, "type": {"text": text}, "coordinate": {"x": x, "y": y}}


def unlocated_play(text="Substitution"):
    # What ESPN actually sends for a play with no location.
    return {
        "text": text,
        "type": {"text": text},
        "coordinate": {"x": -214748340, "y": -214748365},
    }


@pytest.fixture
def mapper():
    m = PlayAudioMapper()
    yield m
    m.cleanup()


class TestSupports:
    @pytest.mark.parametrize("league", ["NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "NCAAH"])
    def test_supported_leagues(self, mapper, league):
        assert mapper.supports(league)

    @pytest.mark.parametrize("league", ["MLB", "NFL", "NCAAF", "Soccer", "Generic", None])
    def test_unsupported_leagues(self, mapper, league):
        assert not mapper.supports(league)


class TestDescribePlay:
    def test_describes_a_located_play(self, mapper):
        assert mapper.describe_play("NBA", nba_play(25, 3)) == "at the rim"

    def test_returns_none_for_an_unlocated_play(self, mapper):
        assert mapper.describe_play("NBA", unlocated_play()) is None

    def test_returns_none_for_an_unsupported_league(self, mapper):
        assert mapper.describe_play("NFL", nba_play(25, 3)) is None


class TestGeneratePlayAudio:
    def test_returns_the_description_it_played(self, mapper):
        assert mapper.generate_play_audio("NBA", nba_play(25, 3)) == "at the rim"

    def test_unlocated_play_is_not_an_error(self, mapper):
        errors = []
        mapper.audio_error.connect(errors.append)
        assert mapper.generate_play_audio("NBA", unlocated_play()) is None
        assert errors == []

    def test_unsupported_league_returns_none(self, mapper):
        assert mapper.generate_play_audio("NFL", nba_play(25, 3)) is None

    def test_emits_accessible_feedback(self, mapper):
        messages = []
        mapper.audio_generated.connect(messages.append)
        mapper.generate_play_audio("NHL", {"coordinate": {"x": 85, "y": 0}})
        assert messages == ["Audio: far end, in the slot"]


class TestGeneratePlaySequence:
    def test_counts_only_the_located_plays(self, mapper):
        plays = [
            nba_play(25, 3),
            unlocated_play(),
            nba_play(3, 3),
            unlocated_play("Full Timeout"),
            nba_play(25, 27),
        ]
        assert mapper.generate_play_sequence("NBA", plays) == 3

    def test_empty_when_nothing_has_a_location(self, mapper):
        assert mapper.generate_play_sequence("NBA", [unlocated_play()] * 4) == 0

    def test_empty_list(self, mapper):
        assert mapper.generate_play_sequence("NBA", []) == 0


class TestToneGeneration:
    """The WAV is the output, so check it directly."""

    def _render(self, mapper, frequency, duration, balance):
        mapper._play_stereo_tone(frequency, duration, balance)
        path = mapper.temp_files[-1]
        assert os.path.exists(path)
        with wave.open(path, "rb") as w:
            assert w.getnchannels() == 2
            assert w.getsampwidth() == 2
            assert w.getframerate() == 44100
            frames = w.readframes(w.getnframes())
        return frames

    def test_writes_a_stereo_wav_of_the_right_length(self, mapper):
        frames = self._render(mapper, 440.0, 0.25, 0.5)
        # 44100 Hz, 0.25 s, 2 channels, 2 bytes per sample
        assert len(frames) == pytest.approx(44100 * 0.25 * 4, rel=0.01)

    def test_hard_left_is_silent_on_the_right(self, mapper):
        import struct

        frames = self._render(mapper, 440.0, 0.1, 0.0)
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        left = samples[0::2]
        right = samples[1::2]
        assert max(abs(s) for s in left) > 1000
        assert max(abs(s) for s in right) < 10

    def test_hard_right_is_silent_on_the_left(self, mapper):
        import struct

        frames = self._render(mapper, 440.0, 0.1, 1.0)
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        left = samples[0::2]
        right = samples[1::2]
        assert max(abs(s) for s in left) < 10
        assert max(abs(s) for s in right) > 1000

    def test_starts_and_ends_near_silence_so_there_is_no_click(self, mapper):
        import struct

        frames = self._render(mapper, 440.0, 0.2, 0.5)
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        assert abs(samples[0]) < 100
        assert abs(samples[-1]) < 100

    def test_never_clips(self, mapper):
        import struct

        # The harmonic mix has to stay inside 16-bit range at every note.
        for frequency in (220.0, 880.0, 1567.98):
            frames = self._render(mapper, frequency, 0.1, 0.5)
            samples = struct.unpack(f"<{len(frames) // 2}h", frames)
            assert max(abs(s) for s in samples) < 32767


class TestCleanup:
    def test_removes_its_temp_files(self):
        mapper = PlayAudioMapper()
        mapper._play_stereo_tone(440.0, 0.05, 0.5)
        paths = list(mapper.temp_files)
        assert paths and all(os.path.exists(p) for p in paths)
        mapper.cleanup()
        assert not any(os.path.exists(p) for p in paths)
        assert mapper.temp_files == []
