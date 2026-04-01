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
    source: str
    audio_path: Path
    transcript: str
    routing: RoutingDecision
    tool_result: dict[str, Any] | None
    tool_result_text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
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
        self._transcriber: OpenAITranscriber | None = None
        self._router: IntentRouter | None = None

    def _require_openai(self) -> None:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be set before dispatching text or audio commands.")

    @property
    def _transcriber_client(self) -> OpenAITranscriber:
        self._require_openai()
        if self._transcriber is None:
            self._transcriber = OpenAITranscriber(self._settings)
        return self._transcriber

    @property
    def _router_client(self) -> IntentRouter:
        self._require_openai()
        if self._router is None:
            self._router = IntentRouter(self._settings)
        return self._router

    def dispatch_file(self, audio_path: Path, dry_run: bool = False) -> DispatchReport:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
        transcript = self._transcriber_client.transcribe(audio_path)
        return self.dispatch_transcript(
            transcript=transcript,
            dry_run=dry_run,
            audio_path=audio_path,
            source="audio",
        )

    def dispatch_transcript(
        self,
        transcript: str,
        dry_run: bool = False,
        audio_path: Path | None = None,
        source: str = "text",
    ) -> DispatchReport:
        normalized_transcript = transcript.strip()
        if not normalized_transcript:
            raise ValueError("Transcript must not be empty.")
        with StdioMCPClient(
            command=self._settings.mcp_server_command,
            cwd=self._settings.workspace_root,
        ) as mcp_client:
            tools = [tool_to_dict(tool) for tool in mcp_client.list_tools()]
            routing = self._router_client.route(normalized_transcript, tools)
            tool_result = None
            tool_result_text = None
            if routing.intent.tool_name and not dry_run:
                tool_result = mcp_client.call_tool(
                    routing.intent.tool_name,
                    routing.intent.tool_arguments(),
                )
                tool_result_text = extract_text_content(tool_result)
        return DispatchReport(
            source=source,
            audio_path=audio_path or Path("<text-input>"),
            transcript=normalized_transcript,
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

    def list_tools(self) -> list[dict[str, Any]]:
        with StdioMCPClient(
            command=self._settings.mcp_server_command,
            cwd=self._settings.workspace_root,
        ) as mcp_client:
            return [tool_to_dict(tool) for tool in mcp_client.list_tools()]
