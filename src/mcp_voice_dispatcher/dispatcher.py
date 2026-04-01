from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio import MicrophoneRecorder
from .config import Settings
from .mcp_client import StdioMCPClient, extract_text_content, tool_to_dict
from .router import IntentRouter, RoutingDecision
from .transcriber import OpenAITranscriber


@dataclass(slots=True)
class DispatchReport:
    audio_path: Path
    transcript: str
    routing: RoutingDecision
    tool_result: dict[str, Any] | None
    tool_result_text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "audio_path": str(self.audio_path),
            "transcript": self.transcript,
            "prompt_template": self.routing.prompt_template,
            "intent": self.routing.intent.model_dump(mode="json", exclude_none=True),
            "tool_result": self.tool_result,
            "tool_result_text": self.tool_result_text,
        }


class VoiceDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._recorder = MicrophoneRecorder(
            sample_rate=settings.microphone_sample_rate,
            channels=settings.microphone_channels,
        )
        self._transcriber = OpenAITranscriber(settings)
        self._router = IntentRouter(settings)

    def dispatch_file(self, audio_path: Path, dry_run: bool = False) -> DispatchReport:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
        with StdioMCPClient(
            command=self._settings.mcp_server_command,
            cwd=self._settings.workspace_root,
        ) as mcp_client:
            tools = [tool_to_dict(tool) for tool in mcp_client.list_tools()]
            transcript = self._transcriber.transcribe(audio_path)
            routing = self._router.route(transcript, tools)
            tool_result = None
            tool_result_text = None
            if routing.intent.tool_name and not dry_run:
                tool_result = mcp_client.call_tool(
                    routing.intent.tool_name,
                    routing.intent.tool_arguments(),
                )
                tool_result_text = extract_text_content(tool_result)
        return DispatchReport(
            audio_path=audio_path,
            transcript=transcript,
            routing=routing,
            tool_result=tool_result,
            tool_result_text=tool_result_text,
        )

    def dispatch_microphone(self, seconds: int | None = None, dry_run: bool = False) -> DispatchReport:
        record_seconds = seconds or self._settings.microphone_seconds
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
            audio_path = Path(handle.name)
        self._recorder.record(audio_path, seconds=record_seconds)
        return self.dispatch_file(audio_path, dry_run=dry_run)
