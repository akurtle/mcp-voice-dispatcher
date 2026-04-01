from __future__ import annotations

import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import Settings
from .dispatcher import VoiceDispatcher


class TextDispatchRequest(BaseModel):
    command: str = Field(min_length=1)
    dry_run: bool = True


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
    app = FastAPI(title="MCP Voice Dispatcher Dashboard", version="0.1.0")

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
            report = dispatcher.dispatch_transcript(request.command, dry_run=request.dry_run)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return report.as_dict()

    @app.post("/api/dispatch/audio")
    async def dispatch_audio(
        dry_run: bool = True,
        audio: UploadFile = File(...),
    ) -> dict[str, object]:
        suffix = _normalize_suffix(audio.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
            handle.write(await audio.read())
        try:
            report = dispatcher.dispatch_file(temp_path, dry_run=dry_run)
            return report.as_dict()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            temp_path.unlink(missing_ok=True)

    return app


def run_dashboard(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run(create_app(), host=host, port=port)
