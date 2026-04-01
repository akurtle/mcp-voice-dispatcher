from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from .config import Settings

SUPPORTED_UPLOAD_MIME_TYPES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
}

SUPPORTED_UPLOAD_SUFFIXES = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".webm",
}

_UPLOAD_CHUNK_SIZE = 1024 * 1024


class AudioValidationError(ValueError):
    pass


@dataclass(slots=True)
class PreparedAudioFile:
    path: Path
    duration_seconds: float
    cleanup_paths: tuple[Path, ...]

    def cleanup(self) -> None:
        for cleanup_path in self.cleanup_paths:
            cleanup_path.unlink(missing_ok=True)


def _normalized_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def validate_upload_metadata(filename: str | None, content_type: str | None) -> str:
    normalized_content_type = _normalized_content_type(content_type)
    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_UPLOAD_SUFFIXES))
        raise AudioValidationError(
            f"Unsupported audio file extension '{suffix}'. Supported extensions: {supported}."
        )
    if normalized_content_type and normalized_content_type not in SUPPORTED_UPLOAD_MIME_TYPES:
        supported = ", ".join(sorted(SUPPORTED_UPLOAD_MIME_TYPES))
        raise AudioValidationError(
            f"Unsupported audio content type '{normalized_content_type}'. Supported audio types: {supported}."
        )
    if suffix:
        return suffix
    if normalized_content_type:
        return SUPPORTED_UPLOAD_MIME_TYPES[normalized_content_type]
    raise AudioValidationError(
        "Could not determine the uploaded audio format. Provide a supported audio filename or content type."
    )


def wav_duration_seconds(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as handle:
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
    if frame_rate <= 0:
        raise AudioValidationError("The normalized WAV file has an invalid sample rate.")
    return frame_count / frame_rate


def transcode_to_wav(source_path: Path, sample_rate: int, channels: int) -> Path:
    if shutil.which("ffmpeg") is None:
        raise AudioValidationError(
            "ffmpeg is required to normalize uploaded audio but was not found on PATH."
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
        output_path = Path(handle.name)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        str(output_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or ["unknown ffmpeg error"]
        raise AudioValidationError(
            f"Uploaded audio could not be normalized. ffmpeg error: {stderr_tail[0]}"
        )
    return output_path


async def prepare_uploaded_audio(upload: UploadFile, settings: Settings) -> PreparedAudioFile:
    suffix = validate_upload_metadata(upload.filename, upload.content_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        source_path = Path(handle.name)
        total_bytes = 0
        try:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    raise AudioValidationError(
                        f"Uploaded audio exceeds the {settings.max_upload_bytes} byte limit."
                    )
                handle.write(chunk)
        except Exception:
            source_path.unlink(missing_ok=True)
            raise
    normalized_path: Path | None = None
    try:
        normalized_path = await asyncio.to_thread(
            transcode_to_wav,
            source_path,
            settings.microphone_sample_rate,
            settings.microphone_channels,
        )
        duration_seconds = await asyncio.to_thread(wav_duration_seconds, normalized_path)
        if duration_seconds <= 0:
            raise AudioValidationError("Uploaded audio did not contain any playable audio frames.")
        if duration_seconds > settings.max_audio_seconds:
            raise AudioValidationError(
                f"Uploaded audio is {duration_seconds:.1f}s long, which exceeds the {settings.max_audio_seconds}s limit."
            )
    except Exception:
        source_path.unlink(missing_ok=True)
        if normalized_path is not None:
            normalized_path.unlink(missing_ok=True)
        raise
    return PreparedAudioFile(
        path=normalized_path,
        duration_seconds=duration_seconds,
        cleanup_paths=(source_path, normalized_path),
    )
