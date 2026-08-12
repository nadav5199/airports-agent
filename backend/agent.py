"""Manual OpenAI tool-calling loop (raw `openai` Python SDK -- no agent
framework), per CLAUDE.md "Agent orchestration".

Design for testability without a real API key: `run_agent_turn` takes a
`client` parameter (anything exposing `.chat.completions.create(...)` with the
OpenAI SDK's response shape). In production `main.py` passes a real
`openai.OpenAI()` client built from `OPENAI_API_KEY`; tests pass a hand-built
fake/mock so the tool-dispatch control flow can be exercised without network
access or a real key. Nothing in this module reaches out to the network
directly -- it only calls whatever `client` it's given.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

from backend.tools import TOOL_SCHEMAS, execute_tool

# Load env vars from backend/.env if present (co-located with .env.example),
# then fall back to python-dotenv's default upward search from the process
# cwd (e.g. a repo-root .env) without overriding anything already loaded.
_BACKEND_ENV = Path(__file__).resolve().parent / ".env"
if _BACKEND_ENV.exists():
    load_dotenv(dotenv_path=_BACKEND_ENV)
load_dotenv()

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """\
You are an investment-analysis assistant for a firm evaluating US airport \
terminal/capacity expansion opportunities. You help analysts identify which \
airports are strong candidates for expansion investment, using a \
deterministic scoring model -- you explain and reason over its output, you \
never invent scores or numbers yourself.

## Grounding rule (must follow strictly)
- You may only state a figure (a score, percentage, KPI value, growth rate, \
delay rate, etc.) if it came directly from a tool result in this \
conversation, or from simple derived arithmetic (a difference, ratio, or \
rank) performed on numbers that themselves came from tool results.
- Never estimate, recall from general/world knowledge, or guess a number \
that a tool did not return -- even if you think you know the real-world \
figure. This dataset and its scoring model are the only source of truth for \
this conversation.
- Every number you state must be attributable to a specific KPI/tool result. \
Say which KPI or tool produced it (e.g. "capacity utilization, from FAA \
ATADS + FAA Capacity Profile data").
- If a tool result has confidence="unavailable" (or a long-haul-share call \
errors because there's no data), say plainly that the figure is unavailable \
for that airport -- do not fill the gap with an estimate of your own. If \
confidence="estimated", say so and note it's a documented proxy/fallback, \
not a directly measured figure.

## Resolving airports
- Users often name a region ("New England"), a metro pair ("LA and Santa \
Ana"), or a city rather than an IATA code. ALWAYS call the lookup_airports \
tool first to resolve these into real airport_codes from the actual \
dataset before calling any scoring tool -- never guess an IATA code \
yourself. If lookup_airports returns zero matches, say so; don't guess.

## Composite scores
- The composite "Expansion Candidate Score" from compute_composite_score is \
0-100, percentile-ranked within the specific set of airports it was called \
with (so scores are only comparable within one call's airport_codes set, not \
globally).
- When you report a composite score, state the airport and its score, then \
give ONE brief high-level driver in a single clause (e.g. "driven mainly by \
high capacity utilization") -- do NOT enumerate every KPI's weight, raw \
value, or percentile score in your prose. That level of detail is already \
shown to the user in a separate "show the math" panel; repeating it in your \
reply is redundant.
- If a KPI was unavailable or estimated in a way that materially affects the \
score, say so briefly (e.g. "delay burden data was unavailable for this \
airport") -- but don't walk through all four KPIs one by one.
- Long-haul share is a separate descriptive stat, not part of the composite \
score -- don't conflate the two.

## Style
- Be concise and analytical. Cite sources inline briefly rather than \
dumping raw JSON -- the structured tool results are already returned \
separately to the UI for a "show the math" view, so your prose should \
summarize and interpret, not repeat every field.
"""

MAX_TOOL_ROUNDS = 6


class ChatClient(Protocol):
    """Minimal shape this module needs from an OpenAI client (or a mock)."""

    chat: Any


def _tool_call_to_dict(tool_call: Any) -> dict[str, Any]:
    """Normalize an OpenAI SDK tool_call object (or a plain dict, for tests)
    into the dict shape we need: {id, name, arguments (parsed dict)}."""
    if isinstance(tool_call, dict):
        fn = tool_call["function"]
        name = fn["name"] if isinstance(fn, dict) else fn.name
        raw_args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
        call_id = tool_call["id"]
    else:
        name = tool_call.function.name
        raw_args = tool_call.function.arguments
        call_id = tool_call.id
    try:
        arguments = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError:
        arguments = {}
    return {"id": call_id, "name": name, "arguments": arguments}


def run_agent_turn(
    client: ChatClient,
    history: list[dict[str, Any]],
    user_message: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run one user turn through the tool-calling loop.

    `history` is the prior list of OpenAI-format messages for this
    conversation (system prompt not included -- added here). Mutated copy is
    returned as the new history to store.

    Returns (reply_text, new_history, tool_results) where tool_results is the
    list of raw dicts returned by every tool call made during this turn (used
    by main.py to populate the `breakdown` field of the API response).
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    tool_results: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        choice = response.choices[0]
        msg = choice.message

        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            reply = msg.content or ""
            new_history = messages[1:] + [{"role": "assistant", "content": reply}]
            return reply, new_history, tool_results

        # Record the assistant's tool-call turn in the running message list.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id if not isinstance(tc, dict) else tc["id"],
                        "type": "function",
                        "function": {
                            "name": (
                                tc.function.name
                                if not isinstance(tc, dict)
                                else tc["function"]["name"]
                            ),
                            "arguments": (
                                tc.function.arguments
                                if not isinstance(tc, dict)
                                else tc["function"]["arguments"]
                            ),
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            parsed = _tool_call_to_dict(tc)
            try:
                result = execute_tool(parsed["name"], parsed["arguments"])
            except Exception as exc:  # noqa: BLE001 -- surface to the LLM, don't crash the turn
                result = {"error": str(exc)}
            tool_results.append(result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": parsed["id"],
                    "content": json.dumps(result, default=str),
                }
            )

    # Ran out of tool-call rounds without a final answer -- fail gracefully.
    fallback = (
        "I wasn't able to finish reasoning over the tool results in the "
        "allotted steps. Please try rephrasing or narrowing the question."
    )
    new_history = messages[1:] + [{"role": "assistant", "content": fallback}]
    return fallback, new_history, tool_results


def build_openai_client() -> Any:
    """Construct a real openai.OpenAI() client from OPENAI_API_KEY.

    Kept as a separate function (rather than a module-level client instance)
    so main.py / tests can avoid constructing a real client at import time --
    the constructor raises if OPENAI_API_KEY is unset, and this environment
    has no key available.
    """
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy backend/.env.example to .env and "
            "fill in a real key, or inject a mock client for testing."
        )
    return OpenAI(api_key=api_key)
