from __future__ import annotations

import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import Settings
from .dispatcher import VoiceDispatcher
from .models import RoutedIntent


class TextDispatchRequest(BaseModel):
    command: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    confirm: bool = Field(default=False)
    payload: dict[str, object] = Field(default_factory=dict)


@dataclass(slots=True)
class PendingApproval:
    created_at: float
    report: dict[str, object]
    intent: RoutedIntent


class ApprovalStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._items: dict[str, PendingApproval] = {}

    def create(self, report: dict[str, object], intent: RoutedIntent) -> str:
        self.prune()
        confirmation_id = uuid4().hex
        self._items[confirmation_id] = PendingApproval(
            created_at=time.time(),
            report=report,
            intent=intent,
        )
        return confirmation_id

    def pop(self, confirmation_id: str) -> PendingApproval:
        self.prune()
        approval = self._items.pop(confirmation_id, None)
        if approval is None:
            raise KeyError("Approval request was not found or has expired.")
        return approval

    def prune(self) -> None:
        cutoff = time.time() - self._ttl_seconds
        expired = [
            confirmation_id
            for confirmation_id, approval in self._items.items()
            if approval.created_at < cutoff
        ]
        for confirmation_id in expired:
            self._items.pop(confirmation_id, None)


def _web_dir() -> Path:
    return Path(__file__).resolve().parent / "web"


def _normalize_suffix(filename: str | None) -> str:
    if not filename:
        return ".webm"
    suffix = Path(filename).suffix
    return suffix if suffix else ".webm"


def create_app() -> FastAPI:
    settings = Settings.from_env(require_openai=False)
    dispatcher = VoiceDispatcher(settings)
    web_dir = _web_dir()
    approvals = ApprovalStore(settings.approval_ttl_seconds)
    app = FastAPI(title="MCP Voice Dispatcher Dashboard", version="0.1.0")
    app.add_event_handler("shutdown", dispatcher.close)

    def preview_response(report: dict[str, object], intent: RoutedIntent) -> dict[str, object]:
        approval: dict[str, object] | None = None
        if intent.tool_name:
            approval = {
                "required": True,
                "confirmation_id": approvals.create(report, intent),
                "confidence_threshold": settings.approval_confidence_threshold,
                "confidence_ok": intent.confidence >= settings.approval_confidence_threshold,
                "editable_payload": intent.editable_payload(),
                "expires_in_seconds": settings.approval_ttl_seconds,
            }
        return {
            **report,
            "approval": approval,
        }

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @app.get("/style.css", include_in_schema=False)
    async def style() -> FileResponse:
        return FileResponse(web_dir / "style.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    async def script() -> FileResponse:
        return FileResponse(web_dir / "app.js", media_type="application/javascript")

    @app.get("/api/tools")
    async def list_tools() -> list[dict[str, object]]:
        return dispatcher.list_tools()

    @app.post("/api/dispatch/text")
    async def dispatch_text(request: TextDispatchRequest) -> dict[str, object]:
        try:
            result = dispatcher.dispatch_transcript(request.command)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return preview_response(result.as_dict(), result.routing.intent)

    @app.post("/api/dispatch/audio")
    async def dispatch_audio(
        audio: UploadFile = File(...),
    ) -> dict[str, object]:
        suffix = _normalize_suffix(audio.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
            handle.write(await audio.read())
        try:
            result = dispatcher.dispatch_file(temp_path)
            return preview_response(result.as_dict(), result.routing.intent)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            temp_path.unlink(missing_ok=True)

    @app.post("/api/dispatch/confirm")
    async def confirm_dispatch(request: ApprovalRequest) -> dict[str, object]:
        if not request.confirm:
            raise HTTPException(status_code=400, detail="Explicit confirmation is required.")
        try:
            pending = approvals.pop(request.confirmation_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        intent = pending.intent
        if intent.confidence < settings.approval_confidence_threshold:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The routed intent is below the execution confidence threshold. "
                    "Review or rephrase the command before retrying."
                ),
            )
        try:
            approved_intent = intent.with_payload_edits(request.payload or intent.editable_payload())
            execution = dispatcher.execute_intent(approved_intent)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        response = dict(pending.report)
        response["intent"] = approved_intent.model_dump(mode="json", exclude_none=True)
        response["tool_result"] = execution.tool_result
        response["tool_result_text"] = execution.tool_result_text
        response["approval"] = {
            "required": True,
            "confirmed": True,
            "confidence_threshold": settings.approval_confidence_threshold,
            "confidence_ok": True,
            "editable_payload": approved_intent.editable_payload(),
        }
        return response

    return app


def run_dashboard(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(create_app(), host=host, port=port)
