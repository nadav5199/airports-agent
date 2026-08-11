"""Tests for backend/agent.py's tool-calling control flow, against a
hand-built MOCKED OpenAI response (never a real API call -- no key available
in this environment). Verifies: dispatch tool_call -> execute REAL scoring
function -> feed result back -> model produces a final reply.
"""

from __future__ import annotations

from backend.agent import run_agent_turn
from backend.tests.fakes import FakeOpenAIClient, final_response, tool_call_response


def test_single_tool_call_round_trip_real_scoring():
    client = FakeOpenAIClient.from_responses(
        [
            tool_call_response(
                [("compute_capacity_utilization", {"airport_code": "SFO"})]
            ),
            final_response(
                "SFO's capacity utilization is high, per FAA ATADS + Capacity Profile data."
            ),
        ]
    )
    reply, history, tool_results = run_agent_turn(client, [], "How congested is SFO?")

    assert "SFO" in reply
    assert len(tool_results) == 1
    assert tool_results[0]["name"] == "capacity_utilization"
    # confirm two rounds were actually issued to the (fake) client
    assert len(client.chat.completions.calls) == 2
    # history should contain the tool call, tool result, and final assistant msg
    roles = [m["role"] for m in history]
    assert "tool" in roles
    assert roles[-1] == "assistant"


def test_lookup_then_score_multi_tool_round_trip():
    """Simulates: 'Which New England airports are strong candidates?' ->
    lookup_airports -> compute_composite_score -> final prose reply."""
    client = FakeOpenAIClient.from_responses(
        [
            tool_call_response([("lookup_airports", {"region": "New England"})]),
            tool_call_response(
                [
                    (
                        "compute_composite_score",
                        {"airport_codes": ["ACK", "BOS", "PVD"]},
                    )
                ]
            ),
            final_response("Boston (BOS) scores highest among New England airports."),
        ]
    )
    reply, history, tool_results = run_agent_turn(
        client, [], "Which New England airports are strong expansion candidates?"
    )

    assert "BOS" in reply
    assert len(tool_results) == 2
    assert "airports" in tool_results[0]  # lookup_airports result
    assert "BOS" in tool_results[1]  # compute_composite_score result keyed by code
    assert tool_results[1]["BOS"]["airport_code"] == "BOS"
    assert len(client.chat.completions.calls) == 3


def test_no_tool_call_direct_reply():
    client = FakeOpenAIClient.from_responses([final_response("Hi, how can I help?")])
    reply, history, tool_results = run_agent_turn(client, [], "hello")
    assert reply == "Hi, how can I help?"
    assert tool_results == []


def test_multi_turn_history_is_threaded_into_next_call():
    client = FakeOpenAIClient.from_responses(
        [final_response("first reply"), final_response("second reply")]
    )
    _, history1, _ = run_agent_turn(client, [], "first message")
    reply2, history2, _ = run_agent_turn(client, history1, "second message")

    assert reply2 == "second reply"
    # second call's messages should include the first turn's history
    second_call_messages = client.chat.completions.calls[1]["messages"]
    contents = [m.get("content") for m in second_call_messages]
    assert "first message" in contents
    assert "first reply" in contents


def test_tool_error_does_not_crash_loop():
    """If a tool raises (e.g. bad args), execute the loop gracefully and feed
    an error dict back to the model rather than raising out of run_agent_turn."""
    client = FakeOpenAIClient.from_responses(
        [
            tool_call_response([("compute_capacity_utilization", {})]),  # missing required arg
            final_response("I couldn't compute that KPI due to a missing airport code."),
        ]
    )
    reply, history, tool_results = run_agent_turn(client, [], "score something")
    assert "error" in tool_results[0]
    assert reply
