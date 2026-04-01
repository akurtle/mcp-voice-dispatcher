from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import RoutedIntent
from .prompts import PromptTemplateLibrary


@dataclass(slots=True)
class RoutingDecision:
    prompt_template: str
    intent: RoutedIntent


class IntentRouter:
    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.router_model
        self._prompts = PromptTemplateLibrary()

    def route(self, transcript: str, tools: list[dict[str, Any]]) -> RoutingDecision:
        prompt_context = self._prompts.build(transcript, tools)
        response = self._client.responses.parse(
            model=self._model,
            input=prompt_context.messages,
            text_format=RoutedIntent,
        )
        intent = getattr(response, "output_parsed", None)
        if intent is None:
            raise RuntimeError("OpenAI did not return a parsed intent object.")
        return RoutingDecision(prompt_template=prompt_context.template_name, intent=intent)

