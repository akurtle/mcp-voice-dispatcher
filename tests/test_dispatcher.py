import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from mcp_voice_dispatcher.dispatcher import DispatchReport, VoiceDispatcher
from mcp_voice_dispatcher.models import DispatchRoute, RoutedIntent
from mcp_voice_dispatcher.router import RoutingDecision


class DispatcherCleanupTests(unittest.TestCase):
    def test_dispatch_microphone_deletes_temp_file(self) -> None:
        dispatcher = VoiceDispatcher.__new__(VoiceDispatcher)
        dispatcher._settings = Mock(microphone_seconds=1)
        dispatcher._recorder = Mock()
        dispatcher._transcriber = None
        dispatcher._router = None
        dispatcher._mcp_pool = Mock()

        captured_path: Path | None = None

        def record(path: Path, seconds: int) -> None:
            nonlocal captured_path
            captured_path = path
            path.write_bytes(b"RIFF")

        dispatcher._recorder.record.side_effect = record

        def dispatch_file(path: Path) -> DispatchReport:
            return DispatchReport(
                source="audio",
                audio_path=path,
                transcript="hello",
                routing=RoutingDecision(
                    prompt_template="general",
                    intent=RoutedIntent(
                        route=DispatchRoute.NOOP,
                        confidence=1.0,
                        summary="noop",
                    ),
                ),
                tool_result=None,
                tool_result_text=None,
            )

        dispatcher.dispatch_file = dispatch_file

        report = VoiceDispatcher.dispatch_microphone(dispatcher)

        self.assertIsNotNone(captured_path)
        self.assertFalse(captured_path.exists())
        self.assertEqual(str(report.audio_path), "<microphone-recording>")


if __name__ == "__main__":
    unittest.main()
