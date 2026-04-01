import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from mcp_voice_dispatcher.config import Settings
from mcp_voice_dispatcher.dispatcher import DispatchReport, ToolExecutionResult
from mcp_voice_dispatcher.models import DispatchRoute, GmailDraft, RoutedIntent
from mcp_voice_dispatcher.router import RoutingDecision
from mcp_voice_dispatcher.web import create_app


def build_settings() -> Settings:
    return Settings(
        openai_api_key="",
        transcription_model="whisper-1",
        router_model="gpt-4o-mini",
        mcp_server_command=("node", "src/mcp_server/index.js"),
        microphone_sample_rate=16000,
        microphone_channels=1,
        microphone_seconds=6,
        approval_confidence_threshold=0.8,
        approval_ttl_seconds=900,
        mcp_pool_size=1,
        max_upload_bytes=1024,
        max_audio_seconds=120,
        routing_confidence_threshold=0.7,
        contact_aliases={},
        notion_database_aliases={},
        workspace_root=Path("."),
    )


class FakeDispatcher:
    def list_tools(self, request_id=None):
        return [{"name": "gmail_send_email", "description": "Send mail", "inputSchema": {}}]

    def dispatch_transcript(self, transcript, audio_path=None, source="text", request_id=None):
        return DispatchReport(
            request_id=request_id,
            source=source,
            audio_path=audio_path or Path("<text-input>"),
            transcript=transcript,
            routing=RoutingDecision(
                prompt_template="email",
                intent=RoutedIntent(
                    route=DispatchRoute.GMAIL_SEND_EMAIL,
                    confidence=0.93,
                    summary="send email",
                    gmail=GmailDraft(
                        to=["team@example.com"],
                        cc=[],
                        subject="Status",
                        body_text="Deployment moved.",
                    ),
                ),
            ),
            tool_result=None,
            tool_result_text=None,
        )

    def dispatch_file(self, audio_path, request_id=None):
        return self.dispatch_transcript("audio command", audio_path=audio_path, source="audio", request_id=request_id)

    def execute_intent(self, intent, request_id=None):
        return ToolExecutionResult(
            tool_result={"content": [{"type": "text", "text": "sent"}]},
            tool_result_text="sent",
        )

    def close(self):
        return None


class WebApiIntegrationTests(unittest.TestCase):
    def test_preview_and_confirm_flow_returns_request_id(self) -> None:
        client = TestClient(create_app(settings=build_settings(), dispatcher=FakeDispatcher()))
        preview = client.post("/api/dispatch/text", json={"command": "Email team the update"})
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.headers["x-request-id"])
        preview_payload = preview.json()
        self.assertEqual(preview_payload["intent"]["route"], "gmail_send_email")
        confirm = client.post(
            "/api/dispatch/confirm",
            json={
                "confirmation_id": preview_payload["approval"]["confirmation_id"],
                "confirm": True,
                "payload": preview_payload["approval"]["editable_payload"],
            },
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()["tool_result_text"], "sent")


if __name__ == "__main__":
    unittest.main()
