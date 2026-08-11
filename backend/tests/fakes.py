"""Hand-built fake OpenAI client objects for testing the tool-calling loop
without a real API key / network call. Mirrors just enough of the openai
Python SDK's response shape (response.choices[0].message.{content,tool_calls},
tool_calls[i].id / .function.name / .function.arguments) for backend/agent.py
to consume.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeFunction:
    name: str
    arguments: str  # JSON string, matching the real SDK


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction
    type: str = "function"


@dataclass
class FakeMessage:
    content: str | None = None
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeResponse:
    choices: list[FakeChoice]


@dataclass
class FakeCompletions:
    """Returns queued responses in order, one per .create() call."""

    responses: list[FakeResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        response = self.responses[self._index]
        self._index += 1
        return response


@dataclass
class FakeChat:
    completions: FakeCompletions


@dataclass
class FakeOpenAIClient:
    """Drop-in stand-in for openai.OpenAI() -- only exposes .chat.completions.create."""

    chat: FakeChat

    @classmethod
    def from_responses(cls, responses: list[FakeResponse]) -> "FakeOpenAIClient":
        return cls(chat=FakeChat(completions=FakeCompletions(responses=responses)))


def tool_call_response(calls: list[tuple[str, dict[str, Any]]], call_id_prefix: str = "call") -> FakeResponse:
    """Build a FakeResponse where the assistant issues one or more tool calls."""
    tool_calls = [
        FakeToolCall(
            id=f"{call_id_prefix}_{i}",
            function=FakeFunction(name=name, arguments=json.dumps(args)),
        )
        for i, (name, args) in enumerate(calls)
    ]
    return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=None, tool_calls=tool_calls))])


def final_response(text: str) -> FakeResponse:
    return FakeResponse(choices=[FakeChoice(message=FakeMessage(content=text, tool_calls=None))])
