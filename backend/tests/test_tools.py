"""Tests for backend/tools.py: schema well-formedness + real dispatch against
the real merged data/processed/*.csv (via scoring/). No mocking of scoring
functions -- these are the real, working functions per the task instructions.
"""

from __future__ import annotations

from backend.tools import TOOL_SCHEMAS, execute_tool, lookup_airports


def test_tool_schemas_well_formed():
    names = set()
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert isinstance(fn["name"], str) and fn["name"]
        assert isinstance(fn["description"], str) and fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        names.add(fn["name"])
    # every dispatch target in execute_tool has a corresponding schema
    expected = {
        "lookup_airports",
        "compute_composite_score",
        "compute_capacity_utilization",
        "compute_traffic_growth",
        "compute_delay_burden",
        "compute_load_factor",
        "compute_long_haul_share",
    }
    assert names == expected


def test_lookup_airports_by_region_new_england():
    result = lookup_airports(region="New England")
    assert result["count"] > 0
    assert all(a["region"] == "New England" for a in result["airports"])


def test_lookup_airports_by_query_santa_ana():
    result = lookup_airports(query="Santa Ana")
    codes = {a["airport_code"] for a in result["airports"]}
    assert "SNA" in codes


def test_lookup_airports_by_explicit_codes():
    result = lookup_airports(airport_codes=["LAX", "SNA"])
    codes = {a["airport_code"] for a in result["airports"]}
    assert codes == {"LAX", "SNA"}


def test_lookup_airports_no_match_returns_empty_not_error():
    result = lookup_airports(query="ThisIsNotARealAirportNameXYZ")
    assert result == {"count": 0, "airports": []}


def test_execute_tool_composite_score_real_data():
    out = execute_tool("compute_composite_score", {"airport_codes": ["SFO", "ACK"]})
    assert set(out.keys()) == {"SFO", "ACK"}
    for code, breakdown in out.items():
        assert breakdown["airport_code"] == code
        assert "kpis" in breakdown
        assert set(breakdown["kpis"].keys()) == {
            "capacity_utilization",
            "traffic_growth",
            "delay_burden",
            "load_factor",
        }


def test_execute_tool_single_kpi_real_data():
    out = execute_tool("compute_capacity_utilization", {"airport_code": "SFO"})
    assert out["name"] == "capacity_utilization"
    assert out["confidence"] in {"actual", "estimated", "unavailable"}


def test_execute_tool_long_haul_share_anc():
    out = execute_tool("compute_long_haul_share", {"airport_code": "ANC"})
    assert out["airport_code"] == "ANC"
    assert 0.0 <= out["pct_long_haul_flights"] <= 1.0


def test_execute_tool_long_haul_share_unknown_airport_does_not_crash():
    out = execute_tool("compute_long_haul_share", {"airport_code": "ZZZ"})
    assert out["confidence"] == "unavailable"
    assert "error" in out


def test_execute_tool_unknown_tool_raises():
    import pytest

    with pytest.raises(ValueError):
        execute_tool("not_a_real_tool", {})
