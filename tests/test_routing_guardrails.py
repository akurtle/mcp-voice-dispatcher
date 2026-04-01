import unittest
from pathlib import Path

from mcp_voice_dispatcher.config import Settings
from mcp_voice_dispatcher.models import DispatchRoute, GmailDraft, NotionPageDraft, RoutedIntent
from mcp_voice_dispatcher.routing_guardrails import RoutingGuardrails


def build_settings() -> Settings:
    return Settings(
        openai_api_key="test",
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
        contact_aliases={"sarah": "sarah@example.com"},
        notion_database_aliases={"notes": "db_123"},
        workspace_root=Path("."),
    )


class RoutingGuardrailsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guardrails = RoutingGuardrails(build_settings())

    def test_resolves_contact_aliases(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.GMAIL_SEND_EMAIL,
            confidence=0.95,
            summary="send email",
            gmail=GmailDraft(
                to=["Sarah"],
                cc=[],
                subject="Status",
                body_text="Deployment moved.",
            ),
        )
        result = self.guardrails.apply("Email Sarah the update.", intent)
        self.assertEqual(result.gmail.to, ["sarah@example.com"])

    def test_clarifies_ambiguous_time_reference(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.GMAIL_SEND_EMAIL,
            confidence=0.95,
            summary="send email",
            gmail=GmailDraft(
                to=["sarah@example.com"],
                cc=[],
                subject="Status",
                body_text="Let's meet tomorrow morning.",
            ),
        )
        result = self.guardrails.apply("Email Sarah about tomorrow morning.", intent)
        self.assertEqual(result.route, DispatchRoute.CLARIFY)

    def test_resolves_notion_database_alias(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.NOTION_CREATE_PAGE,
            confidence=0.92,
            summary="create note",
            notion=NotionPageDraft(
                title="Retro",
                content_markdown="- wins",
                database_id="notes",
            ),
        )
        result = self.guardrails.apply("Create a notion page in notes database.", intent)
        self.assertEqual(result.notion.database_id, "db_123")

    def test_low_confidence_actionable_route_becomes_clarify(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.NOTION_CREATE_PAGE,
            confidence=0.4,
            summary="create note",
            notion=NotionPageDraft(
                title="Retro",
                content_markdown="- wins",
            ),
        )
        result = self.guardrails.apply("Create a notion page.", intent)
        self.assertEqual(result.route, DispatchRoute.CLARIFY)


if __name__ == "__main__":
    unittest.main()
