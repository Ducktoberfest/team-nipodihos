"""Fake model clients so AI tests run offline, instantly and for free."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from foundit_ai.llm_client import AIUnavailable


class FakeLLM:
    """Stands in for ModelClient. Returns a preset answer or raises AIUnavailable.

    `answer` may be a Pydantic object, an exception instance, or a function
    (system, user, output_model) -> object, for answers that depend on the prompt.
    """

    def __init__(self, answer: Any = None) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, system, user, output_model, *, effort="medium"):
        self.calls.append({"system": system, "user": user,
                           "output_model": output_model, "effort": effort})
        if self.answer is None:
            raise AIUnavailable("fake: no answer configured")
        if isinstance(self.answer, Exception):
            raise self.answer
        if callable(self.answer):
            return self.answer(system, user, output_model)
        return self.answer


class FakeOpenAISDK:
    """Mimics openai.OpenAI().chat.completions.create for ModelClient tests.

    `replies` is consumed in order; each is a JSON string or an exception to raise.
    """

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.models_called: list[str] = []
        self.kwargs: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, **kwargs):
        self.models_called.append(model)
        self.kwargs.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(total_tokens=100),
        )
