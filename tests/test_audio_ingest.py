import tempfile
import unittest
import wave
from pathlib import Path

from mcp_voice_dispatcher.audio_ingest import (
    AudioValidationError,
    validate_upload_metadata,
    wav_duration_seconds,
)


class AudioIngestTests(unittest.TestCase):
    def test_rejects_unsupported_extension(self) -> None:
        with self.assertRaises(AudioValidationError):
            validate_upload_metadata("notes.txt", "audio/wav")

    def test_rejects_unsupported_content_type(self) -> None:
        with self.assertRaises(AudioValidationError):
            validate_upload_metadata("voice.wav", "application/octet-stream")

    def test_measures_wav_duration(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
            path = Path(handle.name)
        try:
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 16000)
            self.assertAlmostEqual(wav_duration_seconds(path), 1.0, places=2)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
