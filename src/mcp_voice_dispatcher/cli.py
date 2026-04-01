from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings
from .dispatcher import VoiceDispatcher
from .mcp_client import StdioMCPClient, tool_to_dict


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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.from_env(require_openai=args.command != "tools")

    if args.command == "tools":
        with StdioMCPClient(
            command=settings.mcp_server_command,
            cwd=settings.workspace_root,
        ) as client:
            tools = [tool_to_dict(tool) for tool in client.list_tools()]
        print(json.dumps(tools, indent=2))
        return

    dispatcher = VoiceDispatcher(settings)
    if args.command == "listen":
        report = dispatcher.dispatch_microphone(
            seconds=args.seconds,
            dry_run=args.dry_run,
        )
    else:
        report = dispatcher.dispatch_file(
            audio_path=args.audio,
            dry_run=args.dry_run,
        )
    print(json.dumps(report.as_dict(), indent=2))
