"""FastAPI app: POST /api/chat and GET /api/airports, per docs/contracts.md
section 3. See backend/README.md for how to run it and what's been tested.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from backend.agent import build_openai_client, run_agent_turn
from scoring import data_loader as dl

app = FastAPI(title="Airport Investment Intelligence Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo/take-home scope; would be locked down in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation history, keyed by conversation_id. Fine for this
# scope per CLAUDE.md's "Data storage" decision (no database) -- process
# restart loses history, which is an accepted limitation for a take-home demo.
_conversations: dict[str, list[dict[str, Any]]] = {}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def message_must_be_non_empty(cls, v: str) -> str:
        # Validated at the pydantic layer (before any Depends() are resolved,
        # e.g. get_openai_client) so an empty message never triggers a
        # (possibly missing/unset) OpenAI client construction.
        if not v or not v.strip():
            raise ValueError("message must be non-empty")
        return v


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    breakdown: list[dict[str, Any]]


def get_openai_client() -> Any:
    """FastAPI dependency producing the OpenAI (or mock) client for /api/chat.

    Overridden in tests via app.dependency_overrides[get_openai_client] to
    inject a hand-built mock, so the full HTTP round-trip (real FastAPI
    server -> real tool-dispatch loop -> real scoring functions) can be
    exercised without a real OPENAI_API_KEY. In production this builds a real
    openai.OpenAI() client from the env var.
    """
    return build_openai_client()


@app.get("/api/airports")
def get_airports() -> list[dict[str, Any]]:
    """Array of airports.csv rows, for the frontend's airport picker."""
    airports = dl.load_airports()
    # NaN -> None so the JSON response has valid nulls instead of NaN literals.
    return airports.where(airports.notna(), None).to_dict(orient="records")


@app.post("/api/chat", response_model=ChatResponse)
def post_chat(
    req: ChatRequest, client: Any = Depends(get_openai_client)
) -> ChatResponse:
    conversation_id = req.conversation_id or str(uuid.uuid4())
    history = _conversations.get(conversation_id, [])

    reply, new_history, tool_results = run_agent_turn(client, history, req.message)

    _conversations[conversation_id] = new_history

    return ChatResponse(
        reply=reply,
        conversation_id=conversation_id,
        breakdown=_flatten_breakdown(tool_results),
    )


def _flatten_breakdown(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull ScoreBreakdown/LongHaulShare-shaped objects out of raw tool
    results for the `breakdown` field of the chat response.

    compute_composite_score's tool result is {airport_code: ScoreBreakdown, ...}
    (a dict keyed by code); everything else (single-KPI tools, long-haul
    share) is already one object per call. lookup_airports results are
    excluded -- they're plain airport metadata, not a score/KPI breakdown.
    """
    breakdown: list[dict[str, Any]] = []
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        if "airports" in result and "count" in result:
            continue  # lookup_airports result, not a score breakdown
        if "kpis" in result or "composite_score" in result:
            breakdown.append(result)
            continue
        if "pct_long_haul_flights" in result:
            breakdown.append(result)
            continue
        # dict of {airport_code: ScoreBreakdown} from compute_composite_score
        if result and all(isinstance(v, dict) and "kpis" in v for v in result.values()):
            breakdown.extend(result.values())
            continue
        if "raw_value" in result or "confidence" in result:
            breakdown.append(result)  # single-KPI tool result
    return breakdown
