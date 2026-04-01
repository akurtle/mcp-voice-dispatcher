from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from .audio import MicrophoneRecorder
from .config import Settings
from .mcp_client import MCPClientPool, extract_text_content, tool_to_dict
from .models import RoutedIntent
from .observability import get_logger, log_event
from .router import IntentRouter, RoutingDecision
from .transcriber import OpenAITranscriber


@dataclass(slots=True)
class DispatchReport:
    request_id: str | None
    source: str
    audio_path: Path
    transcript: str
    routing: RoutingDecision
    tool_result: dict[str, Any] | None
    tool_result_text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source": self.source,
            "audio_path": str(self.audio_path),
            "transcript": self.transcript,
            "prompt_template": self.routing.prompt_template,
            "intent": self.routing.intent.model_dump(mode="json", exclude_none=True),
            "tool_result": self.tool_result,
            "tool_result_text": self.tool_result_text,
        }


@dataclass(slots=True)
class ToolExecutionResult:
    tool_result: dict[str, Any]
    tool_result_text: str | None


class VoiceDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._recorder = MicrophoneRecorder(
            sample_rate=settings.microphone_sample_rate,
            channels=settings.microphone_channels,
        )
        self._transcriber: OpenAITranscriber | None = None
        self._router: IntentRouter | None = None
        self._mcp_pool = MCPClientPool(
            command=settings.mcp_server_command,
            cwd=settings.workspace_root,
            max_size=settings.mcp_pool_size,
        )
        self._logger = get_logger(__name__)

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

    def dispatch_file(self, audio_path: Path, request_id: str | None = None) -> DispatchReport:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
        started_at = perf_counter()
        transcript = self._transcriber_client.transcribe(audio_path)
        log_event(
            self._logger,
            "transcription_completed",
            request_id=request_id,
            audio_path=audio_path,
            transcript_length=len(transcript),
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return self.dispatch_transcript(
            transcript=transcript,
            audio_path=audio_path,
            source="audio",
            request_id=request_id,
        )

    def dispatch_transcript(
        self,
        transcript: str,
        audio_path: Path | None = None,
        source: str = "text",
        request_id: str | None = None,
    ) -> DispatchReport:
        normalized_transcript = transcript.strip()
        if not normalized_transcript:
            raise ValueError("Transcript must not be empty.")
        started_at = perf_counter()
        with self._mcp_pool.session() as mcp_client:
            tools = [tool_to_dict(tool) for tool in mcp_client.list_tools()]
            routing = self._router_client.route(normalized_transcript, tools, request_id=request_id)
        log_event(
            self._logger,
            "dispatch_preview_completed",
            request_id=request_id,
            source=source,
            transcript_length=len(normalized_transcript),
            route=routing.intent.route.value,
            confidence=routing.intent.confidence,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return DispatchReport(
            request_id=request_id,
            source=source,
            audio_path=audio_path or Path("<text-input>"),
            transcript=normalized_transcript,
            routing=routing,
            tool_result=None,
            tool_result_text=None,
        )

    def dispatch_microphone(self, seconds: int | None = None, request_id: str | None = None) -> DispatchReport:
        record_seconds = seconds or self._settings.microphone_seconds
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
            audio_path = Path(handle.name)
        try:
            self._recorder.record(audio_path, seconds=record_seconds)
            report = self.dispatch_file(audio_path, request_id=request_id)
        finally:
            audio_path.unlink(missing_ok=True)
        report.audio_path = Path("<microphone-recording>")
        return report

    def list_tools(self, request_id: str | None = None) -> list[dict[str, Any]]:
        started_at = perf_counter()
        with self._mcp_pool.session() as mcp_client:
            tools = [tool_to_dict(tool) for tool in mcp_client.list_tools()]
        log_event(
            self._logger,
            "mcp_tools_listed",
            request_id=request_id,
            tool_count=len(tools),
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return tools

    def execute_intent(self, intent: RoutedIntent, request_id: str | None = None) -> ToolExecutionResult:
        if not intent.tool_name:
            raise ValueError("Only actionable MCP routes can be executed.")
        started_at = perf_counter()
        with self._mcp_pool.session() as mcp_client:
            try:
                tool_result = mcp_client.call_tool(
                    intent.tool_name,
                    intent.tool_arguments(),
                )
            except Exception as error:
                log_event(
                    self._logger,
                    "mcp_tool_failed",
                    request_id=request_id,
                    tool_name=intent.tool_name,
                    failure_type=type(error).__name__,
                    latency_ms=round((perf_counter() - started_at) * 1000, 2),
                )
                raise
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        log_event(
            self._logger,
            "mcp_tool_completed",
            request_id=request_id,
            tool_name=intent.tool_name,
            latency_ms=latency_ms,
            is_error=bool(tool_result.get("isError")),
        )
        return ToolExecutionResult(
            tool_result=tool_result,
            tool_result_text=extract_text_content(tool_result),
        )

    def close(self) -> None:
        self._mcp_pool.close()
