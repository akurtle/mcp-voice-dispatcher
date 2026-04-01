from __future__ import annotations

import json
import queue
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MCPTool:
    name: str
    description: str | None
    input_schema: dict[str, Any]


class MCPProtocolError(RuntimeError):
    pass


class StdioMCPClient:
    def __init__(
        self,
        command: Sequence[str],
        cwd: Path,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._pending: dict[int, dict[str, Any]] = {}
        self._next_id = 1
        self._stderr_lines: list[str] = []
        self._threads: list[threading.Thread] = []

    def __enter__(self) -> "StdioMCPClient":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self._command,
            cwd=self._cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        self._initialize()

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.stdin:
            self._process.stdin.close()
        self._process.terminate()
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=3)
        self._process = None

    def list_tools(self) -> list[MCPTool]:
        payload = self._request("tools/list", {})
        tools = payload.get("tools", [])
        return [
            MCPTool(
                name=tool["name"],
                description=tool.get("description"),
                input_schema=tool.get("inputSchema", {}),
            )
            for tool in tools
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-voice-dispatcher",
                    "version": "0.1.0",
                },
            },
        )
        self._notify("notifications/initialized", {})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        message = self._wait_for_response(request_id)
        if "error" in message:
            raise MCPProtocolError(str(message["error"]))
        return message.get("result", {})

    def _wait_for_response(self, request_id: int) -> dict[str, Any]:
        if request_id in self._pending:
            return self._pending.pop(request_id)
        while True:
            try:
                message = self._messages.get(timeout=self._timeout_seconds)
            except queue.Empty as error:
                raise MCPProtocolError(self._timeout_message()) from error
            message_id = message.get("id")
            if message_id == request_id:
                return message
            if message_id is not None:
                self._pending[int(message_id)] = message

    def _timeout_message(self) -> str:
        stderr_tail = "\n".join(self._stderr_lines[-10:])
        process_state = None if self._process is None else self._process.poll()
        return (
            f"Timed out waiting for MCP server response. "
            f"Exit code={process_state}. Stderr tail:\n{stderr_tail}"
        )

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPProtocolError("MCP server process is not running.")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for line in self._process.stdout:
            content = line.strip()
            if not content:
                continue
            self._messages.put(json.loads(content))

    def _read_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr_lines.append(line.rstrip())


def tool_to_dict(tool: MCPTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
    }


def extract_text_content(tool_result: dict[str, Any]) -> str:
    parts: list[str] = []
    for content in tool_result.get("content", []):
        if content.get("type") == "text":
            parts.append(content.get("text", ""))
    return "\n".join(part for part in parts if part).strip()
