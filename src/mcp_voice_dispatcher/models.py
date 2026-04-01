from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DispatchRoute(str, Enum):
    GMAIL_SEND_EMAIL = "gmail_send_email"
    NOTION_CREATE_PAGE = "notion_create_page"
    CLARIFY = "clarify"
    NOOP = "noop"


class GmailDraft(BaseModel):
    to: list[str] = Field(min_length=1)
    cc: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1, max_length=160)
    body_text: str = Field(min_length=1)


class NotionPageDraft(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content_markdown: str = Field(min_length=1)
    database_id: str | None = None


class RoutedIntent(BaseModel):
    route: DispatchRoute
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=280)
    clarification_question: str | None = None
    gmail: GmailDraft | None = None
    notion: NotionPageDraft | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "RoutedIntent":
        if self.route == DispatchRoute.GMAIL_SEND_EMAIL and self.gmail is None:
            raise ValueError("gmail payload is required when route is gmail_send_email.")
        if self.route == DispatchRoute.NOTION_CREATE_PAGE and self.notion is None:
            raise ValueError("notion payload is required when route is notion_create_page.")
        if self.route == DispatchRoute.CLARIFY and not self.clarification_question:
            raise ValueError("clarification_question is required when route is clarify.")
        return self

    @property
    def tool_name(self) -> str | None:
        if self.route in {DispatchRoute.GMAIL_SEND_EMAIL, DispatchRoute.NOTION_CREATE_PAGE}:
            return self.route.value
        return None

    def editable_payload(self) -> dict[str, Any]:
        if self.route == DispatchRoute.GMAIL_SEND_EMAIL and self.gmail is not None:
            return self.gmail.model_dump(mode="json")
        if self.route == DispatchRoute.NOTION_CREATE_PAGE and self.notion is not None:
            return self.notion.model_dump(mode="json", exclude_none=True)
        return {}

    def with_payload_edits(self, payload: dict[str, Any]) -> "RoutedIntent":
        if self.route == DispatchRoute.GMAIL_SEND_EMAIL:
            updated = GmailDraft.model_validate(payload)
            return self.model_copy(update={"gmail": updated})
        if self.route == DispatchRoute.NOTION_CREATE_PAGE:
            updated = NotionPageDraft.model_validate(payload)
            return self.model_copy(update={"notion": updated})
        return self

    def tool_arguments(self) -> dict[str, Any]:
        if self.route == DispatchRoute.GMAIL_SEND_EMAIL and self.gmail is not None:
            return {
                "to": self.gmail.to,
                "cc": self.gmail.cc,
                "subject": self.gmail.subject,
                "bodyText": self.gmail.body_text,
            }
        if self.route == DispatchRoute.NOTION_CREATE_PAGE and self.notion is not None:
            arguments = {
                "title": self.notion.title,
                "contentMarkdown": self.notion.content_markdown,
                "databaseId": self.notion.database_id,
            }
            return {key: value for key, value in arguments.items() if value is not None}
        return {}
