import unittest
from pathlib import Path

from mcp_voice_dispatcher.mcp_client import MCPClientPool


class FakeClient:
    instances = []

    def __init__(self, command, cwd, timeout_seconds):
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.started = 0
        self.closed = 0
        FakeClient.instances.append(self)

    def start(self):
        self.started += 1

    def close(self):
        self.closed += 1


class MCPClientPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeClient.instances = []

    def test_pool_reuses_existing_client(self) -> None:
        pool = MCPClientPool(
            command=["node", "server.js"],
            cwd=Path("."),
            max_size=1,
            client_factory=FakeClient,
        )
        with pool.session() as first:
            self.assertEqual(first.started, 1)
        with pool.session() as second:
            self.assertIs(first, second)
        pool.close()
        self.assertEqual(len(FakeClient.instances), 1)

    def test_pool_discards_client_after_error(self) -> None:
        pool = MCPClientPool(
            command=["node", "server.js"],
            cwd=Path("."),
            max_size=1,
            client_factory=FakeClient,
        )
        with self.assertRaises(RuntimeError):
            with pool.session():
                raise RuntimeError("boom")
        with pool.session():
            pass
        pool.close()
        self.assertEqual(len(FakeClient.instances), 2)
        self.assertGreaterEqual(FakeClient.instances[0].closed, 1)


if __name__ == "__main__":
    unittest.main()
