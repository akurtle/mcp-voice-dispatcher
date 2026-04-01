from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import RoutedIntent
from .observability import get_logger, log_event
from .prompts import PromptTemplateLibrary
from .routing_guardrails import RoutingGuardrails


@dataclass(slots=True)
class RoutingDecision:
    prompt_template: str
    intent: RoutedIntent


class IntentRouter:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.router_model
        self._prompts = PromptTemplateLibrary()
        self._guardrails = RoutingGuardrails(settings)
        self._logger = get_logger(__name__)

    def route(
        self,
        transcript: str,
        tools: list[dict[str, Any]],
        request_id: str | None = None,
    ) -> RoutingDecision:
        prompt_context = self._prompts.build(transcript, tools)
        started_at = perf_counter()
        response = self._client.responses.parse(
            model=self._model,
            input=prompt_context.messages,
            text_format=RoutedIntent,
        )
        intent = getattr(response, "output_parsed", None)
        if intent is None:
            raise RuntimeError("OpenAI did not return a parsed intent object.")
        guarded_intent = self._guardrails.apply(transcript, intent)
        log_event(
            self._logger,
            "routing_completed",
            request_id=request_id,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            prompt_template=prompt_context.template_name,
            route=guarded_intent.route.value,
            confidence=guarded_intent.confidence,
            transcript_length=len(transcript),
        )
        return RoutingDecision(prompt_template=prompt_context.template_name, intent=guarded_intent)
