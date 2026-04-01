from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PromptContext:
    template_name: str
    messages: list[dict[str, str]]


class PromptTemplateLibrary:
    EMAIL_KEYWORDS = {
        "email",
        "mail",
        "send",
        "message",
        "subject",
        "cc",
        "gmail",
    }
    NOTE_KEYWORDS = {
        "note",
        "notion",
        "page",
        "document",
        "write down",
        "capture",
        "save",
    }

    def select_template(self, transcript: str) -> str:
        normalized = transcript.casefold()
        email_hits = sum(token in normalized for token in self.EMAIL_KEYWORDS)
        notion_hits = sum(token in normalized for token in self.NOTE_KEYWORDS)
        if email_hits > notion_hits:
            return "email"
        if notion_hits > email_hits:
            return "notion"
        return "general"

    def build(self, transcript: str, tools: list[dict[str, Any]]) -> PromptContext:
        template_name = self.select_template(transcript)
        tool_block = json.dumps(tools, indent=2)
        template_instruction = {
            "email": (
                "Bias toward gmail_send_email only when the user clearly wants a message sent. "
                "Infer concise but professional subject lines when the user does not say one. "
                "If recipients are named without clear email resolution, ask to clarify rather than guessing."
            ),
            "notion": (
                "Bias toward notion_create_page when the user is trying to capture notes, plans, or summaries. "
                "Preserve bullet structure in content_markdown whenever it is implied. "
                "If a database target is ambiguous, ask to clarify rather than inventing one."
            ),
            "general": (
                "Choose the single best route. Use clarify when recipients, dates, times, or targets are ambiguous enough that acting would be risky."
            ),
        }[template_name]
        system_prompt = (
            "You are an intent router for a voice automation assistant.\n"
            "Return only the structured schema supplied by the client.\n"
            "Map transcripts into exactly one route.\n"
            "Keep confidence conservative for noisy or underspecified requests.\n"
            "Do not guess exact dates from relative words such as tomorrow or next Friday.\n"
            "Do not guess recipient email addresses or Notion database identifiers.\n"
            f"{template_instruction}\n\n"
            "Available MCP tools:\n"
            f"{tool_block}"
        )
        user_prompt = (
            "Transcribed voice command:\n"
            f"{transcript}\n\n"
            "If the command is incomplete, ask one concise clarification question."
        )
        return PromptContext(
            template_name=template_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
