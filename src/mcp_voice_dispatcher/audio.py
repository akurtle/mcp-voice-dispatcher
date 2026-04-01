from __future__ import annotations

import wave
from pathlib import Path

import sounddevice as sd


class MicrophoneRecorder:
    def __init__(self, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    def record(self, destination: Path, seconds: int) -> Path:
        frame_count = int(seconds * self._sample_rate)
        recording = sd.rec(
            frame_count,
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
        )
        sd.wait()
        with wave.open(str(destination), "wb") as handle:
            handle.setnchannels(self._channels)
            handle.setsampwidth(2)
            handle.setframerate(self._sample_rate)
            handle.writeframes(recording.tobytes())
        return destination

