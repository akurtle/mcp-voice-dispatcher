from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from .config import Settings


class OpenAITranscriber:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.transcription_model

    def transcribe(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            response = self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
            )
        text = getattr(response, "text", "").strip()
        if not text:
            raise RuntimeError("The transcription response was empty.")
        return text

