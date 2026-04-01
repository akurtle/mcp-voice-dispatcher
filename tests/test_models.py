import unittest

from pydantic import ValidationError

from mcp_voice_dispatcher.models import DispatchRoute, GmailDraft, RoutedIntent


class RoutedIntentTests(unittest.TestCase):
    def test_gmail_route_requires_gmail_payload(self) -> None:
        with self.assertRaises(ValidationError):
            RoutedIntent(
                route=DispatchRoute.GMAIL_SEND_EMAIL,
                confidence=0.8,
                summary="send an email",
            )

    def test_tool_arguments_map_to_mcp_shape(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.GMAIL_SEND_EMAIL,
            confidence=0.9,
            summary="send an email",
            gmail=GmailDraft(
                to=["team@example.com"],
                subject="Status update",
                body_text="Deployment moved to Friday.",
            ),
        )
        self.assertEqual(
            intent.tool_arguments(),
            {
                "to": ["team@example.com"],
                "cc": [],
                "subject": "Status update",
                "bodyText": "Deployment moved to Friday.",
            },
        )

    def test_payload_edits_are_validated(self) -> None:
        intent = RoutedIntent(
            route=DispatchRoute.NOTION_CREATE_PAGE,
            confidence=0.9,
            summary="create a notion page",
            notion={
                "title": "Retro",
                "content_markdown": "- wins",
            },
        )
        updated = intent.with_payload_edits(
            {
                "title": "Retro Updated",
                "content_markdown": "- wins\n- blockers",
                "database_id": "db_123",
            }
        )
        self.assertEqual(updated.editable_payload()["title"], "Retro Updated")
        self.assertEqual(updated.tool_arguments()["databaseId"], "db_123")


if __name__ == "__main__":
    unittest.main()
