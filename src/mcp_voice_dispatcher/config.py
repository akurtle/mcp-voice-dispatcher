from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _split_command(command: str) -> tuple[str, ...]:
    if os.name == "nt":
        return tuple(shlex.split(command, posix=False))
    return tuple(shlex.split(command))


@dataclass(slots=True)
class Settings:
    openai_api_key: str
    transcription_model: str
    router_model: str
    mcp_server_command: tuple[str, ...]
    microphone_sample_rate: int
    microphone_channels: int
    microphone_seconds: int
    approval_confidence_threshold: float
    approval_ttl_seconds: int
    workspace_root: Path

    @classmethod
    def from_env(cls, require_openai: bool = True) -> "Settings":
        load_dotenv()
        workspace_root = Path(__file__).resolve().parents[2]
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if require_openai and not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be set in the environment or .env file.")
        return cls(
            openai_api_key=openai_api_key,
            transcription_model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
            router_model=os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini"),
            mcp_server_command=_split_command(
                os.getenv("MCP_SERVER_COMMAND", "node src/mcp_server/index.js")
            ),
            microphone_sample_rate=int(os.getenv("MICROPHONE_SAMPLE_RATE", "16000")),
            microphone_channels=int(os.getenv("MICROPHONE_CHANNELS", "1")),
            microphone_seconds=int(os.getenv("MICROPHONE_SECONDS", "6")),
            approval_confidence_threshold=float(
                os.getenv("APPROVAL_CONFIDENCE_THRESHOLD", "0.8")
            ),
            approval_ttl_seconds=int(os.getenv("APPROVAL_TTL_SECONDS", "900")),
            workspace_root=workspace_root,
        )
