from __future__ import annotations

import re

from .config import Settings
from .models import DispatchRoute, RoutedIntent

_AMBIGUOUS_TIME_PATTERN = re.compile(
    r"\b(today|tomorrow|yesterday|tonight|this afternoon|this evening|next week|next month|next friday|next monday|later)\b",
    re.IGNORECASE,
)


class RoutingGuardrails:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def apply(self, transcript: str, intent: RoutedIntent) -> RoutedIntent:
        if intent.route in {DispatchRoute.CLARIFY, DispatchRoute.NOOP}:
            return intent
        if intent.confidence < self._settings.routing_confidence_threshold:
            return self._clarify(
                f"I am not confident enough to act on that yet. {self._route_specific_question(intent)}"
            )
        if intent.route == DispatchRoute.GMAIL_SEND_EMAIL:
            return self._guard_email(transcript, intent)
        if intent.route == DispatchRoute.NOTION_CREATE_PAGE:
            return self._guard_notion(transcript, intent)
        return intent

    def _guard_email(self, transcript: str, intent: RoutedIntent) -> RoutedIntent:
        assert intent.gmail is not None
        resolved_to, unresolved_to = self._resolve_recipients(intent.gmail.to)
        resolved_cc, unresolved_cc = self._resolve_recipients(intent.gmail.cc)
        if unresolved_to or unresolved_cc:
            missing = ", ".join(unresolved_to + unresolved_cc)
            return self._clarify(
                f"I could not resolve these recipients: {missing}. Please provide full email addresses or configure aliases."
            )
        if self._contains_ambiguous_time(transcript) or self._contains_ambiguous_time(intent.gmail.body_text):
            return self._clarify(
                "Your email includes an ambiguous time reference. What exact date or time should I use?"
            )
        updated = intent.model_copy(
            update={
                "gmail": intent.gmail.model_copy(update={"to": resolved_to, "cc": resolved_cc}),
            }
        )
        return updated

    def _guard_notion(self, transcript: str, intent: RoutedIntent) -> RoutedIntent:
        assert intent.notion is not None
        database_id = intent.notion.database_id
        if database_id:
            resolved_database_id = self._settings.notion_database_aliases.get(database_id.casefold())
            if resolved_database_id:
                return intent.model_copy(
                    update={
                        "notion": intent.notion.model_copy(update={"database_id": resolved_database_id}),
                    }
                )
            if not self._looks_like_database_id(database_id):
                return self._clarify(
                    f"I could not resolve the Notion database '{database_id}'. Please provide a configured database alias or an exact database ID."
                )
        if self._contains_ambiguous_time(transcript) and "reminder" in transcript.casefold():
            return self._clarify(
                "The note mentions a relative time. What exact date should I capture in Notion?"
            )
        return intent

    def _resolve_recipients(self, recipients: list[str]) -> tuple[list[str], list[str]]:
        resolved: list[str] = []
        unresolved: list[str] = []
        for recipient in recipients:
            normalized = recipient.strip()
            if "@" in normalized:
                resolved.append(normalized.lower())
                continue
            alias = self._settings.contact_aliases.get(normalized.casefold())
            if alias:
                resolved.append(alias.lower())
            else:
                unresolved.append(normalized)
        return resolved, unresolved

    def _contains_ambiguous_time(self, value: str) -> bool:
        return bool(_AMBIGUOUS_TIME_PATTERN.search(value))

    def _looks_like_database_id(self, value: str) -> bool:
        compact = value.replace("-", "")
        return len(compact) >= 24 and compact.isalnum()

    def _route_specific_question(self, intent: RoutedIntent) -> str:
        if intent.route == DispatchRoute.GMAIL_SEND_EMAIL:
            return "Who should receive the email, and what exact wording should I send?"
        if intent.route == DispatchRoute.NOTION_CREATE_PAGE:
            return "Which database should I use, and what exact note should I create?"
        return "Please clarify the request."

    def _clarify(self, question: str) -> RoutedIntent:
        return RoutedIntent(
            route=DispatchRoute.CLARIFY,
            confidence=0.0,
            summary="Needs clarification before execution.",
            clarification_question=question,
        )
