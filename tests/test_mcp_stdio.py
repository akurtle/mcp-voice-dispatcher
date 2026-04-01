import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from mcp_voice_dispatcher.mcp_client import StdioMCPClient


class MCPStdioIntegrationTests(unittest.TestCase):
    def test_initialize_list_and_call_tool(self) -> None:
        script = textwrap.dedent(
            """
            import json
            import sys

            for line in sys.stdin:
                message = json.loads(line)
                if message.get("method") == "initialize":
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"capabilities": {}}}) + "\\n")
                    sys.stdout.flush()
                elif message.get("method") == "notifications/initialized":
                    continue
                elif message.get("method") == "tools/list":
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object"}}]}}) + "\\n")
                    sys.stdout.flush()
                elif message.get("method") == "tools/call":
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": message["params"]["arguments"]["value"]}]}}) + "\\n")
                    sys.stdout.flush()
            """
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8") as handle:
            handle.write(script)
            script_path = Path(handle.name)
        try:
            with StdioMCPClient(
                command=[sys.executable, str(script_path)],
                cwd=Path("."),
                timeout_seconds=5,
            ) as client:
                tools = client.list_tools()
                self.assertEqual(tools[0].name, "echo")
                result = client.call_tool("echo", {"value": "hello"})
                self.assertEqual(result["content"][0]["text"], "hello")
        finally:
            script_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
