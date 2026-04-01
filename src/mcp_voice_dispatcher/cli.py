from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .dispatcher import VoiceDispatcher
from .mcp_client import StdioMCPClient, tool_to_dict
from .web import run_dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Voice-driven MCP dispatcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    listen_parser = subparsers.add_parser("listen", help="Record from microphone and dispatch")
    listen_parser.add_argument("--seconds", type=int, default=None)
    listen_parser.add_argument("--dry-run", action="store_true")

    file_parser = subparsers.add_parser("dispatch", help="Dispatch an existing WAV file")
    file_parser.add_argument("--audio", type=Path, required=True)
    file_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("tools", help="List tools exposed by the MCP server")
    serve_parser = subparsers.add_parser("serve", help="Run the web dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env(require_openai=args.command in {"listen", "dispatch"})

    if args.command == "tools":
        with StdioMCPClient(
            command=settings.mcp_server_command,
            cwd=settings.workspace_root,
        ) as client:
            tools = [tool_to_dict(tool) for tool in client.list_tools()]
        print(json.dumps(tools, indent=2))
        return
    if args.command == "serve":
        run_dashboard(host=args.host, port=args.port)
        return

    dispatcher = VoiceDispatcher(settings)
    if args.command == "listen":
        report = dispatcher.dispatch_microphone(
            seconds=args.seconds,
        )
    else:
        report = dispatcher.dispatch_file(
            audio_path=args.audio,
        )
    print(json.dumps(report.as_dict(), indent=2))
    intent = report.routing.intent
    if args.dry_run or not intent.tool_name:
        return
    if intent.confidence < settings.approval_confidence_threshold:
        print(
            json.dumps(
                {
                    "execution_blocked": True,
                    "reason": "Intent confidence is below the approval threshold.",
                    "confidence": intent.confidence,
                    "threshold": settings.approval_confidence_threshold,
                },
                indent=2,
            )
        )
        return
    editable_payload = intent.editable_payload()
    print(json.dumps({"editable_payload": editable_payload}, indent=2))
    payload_override = input("Optional JSON payload edits, or press Enter to keep the preview: ").strip()
    if payload_override:
        intent = intent.with_payload_edits(json.loads(payload_override))
    approved = input("Approve this MCP action? [y/N]: ").strip().lower()
    if approved not in {"y", "yes"}:
        print(json.dumps({"execution_cancelled": True}, indent=2))
        return
    execution = dispatcher.execute_intent(intent)
    final_report = report.as_dict()
    final_report["intent"] = intent.model_dump(mode="json", exclude_none=True)
    final_report["tool_result"] = execution.tool_result
    final_report["tool_result_text"] = execution.tool_result_text
    print(json.dumps(final_report, indent=2))
