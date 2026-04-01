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


if __name__ == "__main__":
    unittest.main()

