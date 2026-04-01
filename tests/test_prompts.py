import unittest

from mcp_voice_dispatcher.prompts import PromptTemplateLibrary


class PromptTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = PromptTemplateLibrary()

    def test_email_language_selects_email_template(self) -> None:
        template = self.library.select_template(
            "Email Maya and Jordan with the revised launch subject and cc finance."
        )
        self.assertEqual(template, "email")

    def test_note_language_selects_notion_template(self) -> None:
        template = self.library.select_template(
            "Create a Notion page with retro notes and save blockers for tomorrow."
        )
        self.assertEqual(template, "notion")


if __name__ == "__main__":
    unittest.main()
