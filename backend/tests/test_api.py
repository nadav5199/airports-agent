"""FastAPI endpoint tests via Starlette's TestClient (a real ASGI request
through the actual app object, not a bare function call). /api/chat's LLM
step is mocked at the FastAPI dependency boundary (get_openai_client) since
no real OPENAI_API_KEY is available in this environment -- the tool-dispatch
loop and scoring functions underneath it are REAL.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app, get_openai_client
from backend.tests.fakes import FakeOpenAIClient, final_response, tool_call_response

client = TestClient(app)


def test_get_airports_returns_real_data():
    resp = client.get("/api/airports")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 62
    codes = {row["airport_code"] for row in data}
    assert {"LAX", "SNA", "ANC", "SFO", "BOS"}.issubset(codes)
    sample = data[0]
    assert set(sample.keys()) == {
        "airport_code",
        "name",
        "city",
        "state",
        "region",
        "lat",
        "lon",
        "runway_count",
        "longest_runway_ft",
    }


def test_post_chat_direct_reply_no_tools():
    fake_client = FakeOpenAIClient.from_responses([final_response("Hello!")])
    app.dependency_overrides[get_openai_client] = lambda: fake_client
    try:
        resp = client.post("/api/chat", json={"message": "hi", "conversation_id": None})
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "Hello!"
        assert isinstance(body["conversation_id"], str) and body["conversation_id"]
        assert body["breakdown"] == []
    finally:
        app.dependency_overrides.clear()


def test_post_chat_with_composite_score_real_scoring_through_http():
    """Mocked LLM issues a tool call -> real tool-calling loop -> REAL
    scoring.composite.compute_composite_score -> real ScoreBreakdown data
    comes back embedded in the HTTP response's `breakdown` field."""
    fake_client = FakeOpenAIClient.from_responses(
        [
            tool_call_response(
                [("compute_composite_score", {"airport_codes": ["SFO", "ACK"]})]
            ),
            final_response(
                "SFO scores higher than ACK on the composite Expansion Candidate Score."
            ),
        ]
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_client
    try:
        resp = client.post(
            "/api/chat",
            json={"message": "Compare SFO and ACK", "conversation_id": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "SFO" in body["reply"]
        assert len(body["breakdown"]) == 2
        codes = {b["airport_code"] for b in body["breakdown"]}
        assert codes == {"SFO", "ACK"}
        for b in body["breakdown"]:
            assert "composite_score" in b
            assert "kpis" in b
            assert set(b["kpis"].keys()) == {
                "capacity_utilization",
                "traffic_growth",
                "delay_burden",
                "load_factor",
            }
    finally:
        app.dependency_overrides.clear()


def test_post_chat_conversation_id_persists_history():
    fake_client = FakeOpenAIClient.from_responses(
        [final_response("first"), final_response("second")]
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_client
    try:
        r1 = client.post("/api/chat", json={"message": "msg1", "conversation_id": None})
        conv_id = r1.json()["conversation_id"]
        r2 = client.post(
            "/api/chat", json={"message": "msg2", "conversation_id": conv_id}
        )
        assert r2.json()["conversation_id"] == conv_id
        assert r2.json()["reply"] == "second"
    finally:
        app.dependency_overrides.clear()


def test_post_chat_empty_message_rejected():
    # Rejected at the pydantic validation layer (422) before the endpoint body
    # runs. FastAPI's solve_dependencies resolves Depends() alongside body
    # validation in the same pass (regardless of which "fails" first the
    # request never reaches the handler), so override the client dependency
    # with a harmless stand-in purely to isolate this test from requiring
    # OPENAI_API_KEY / a real client -- it's never actually invoked to
    # produce a reply since validation rejects the request either way.
    app.dependency_overrides[get_openai_client] = lambda: object()
    try:
        resp = client.post("/api/chat", json={"message": "   ", "conversation_id": None})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_post_chat_long_haul_share_anc_through_http():
    fake_client = FakeOpenAIClient.from_responses(
        [
            tool_call_response([("compute_long_haul_share", {"airport_code": "ANC"})]),
            final_response("ANC's long-haul share is reported below."),
        ]
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_client
    try:
        resp = client.post(
            "/api/chat",
            json={"message": "% long haul flights out of Anchorage?", "conversation_id": None},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["breakdown"]) == 1
        assert body["breakdown"][0]["airport_code"] == "ANC"
        assert "pct_long_haul_flights" in body["breakdown"][0]
    finally:
        app.dependency_overrides.clear()
