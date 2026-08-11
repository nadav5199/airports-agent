"""OpenAI tool/function schemas + dispatch, wrapping the real scoring/ functions.

Per docs/contracts.md section 3: "Tools wrap the scoring/ functions exactly (not
reimplement them) -- the LLM must call these tools to get any number, per the
grounding rule in CLAUDE.md."

This module defines:
  - TOOL_SCHEMAS: the list of OpenAI tool-call JSON schemas (the `tools=` param
    passed to the Chat Completions API).
  - execute_tool(name, arguments): dispatches a tool call by name to the real
    scoring.* function (or the airport-lookup helper below) and returns a
    JSON-serializable dict.

Airport lookup: the LLM needs a way to resolve natural-language references
("New England airports", "LA and Santa Ana") into concrete airport_codes
*before* calling the scoring tools, since compute_composite_score/etc. all
take airport_code(s), not free text. `lookup_airports` does that by filtering
the real data/processed/airports.csv (via scoring.data_loader) on region,
state, city, name, or airport_code substrings -- deterministic filtering, not
LLM guessing.
"""

from __future__ import annotations

from typing import Any

from scoring import data_loader as dl
from scoring.composite import compute_composite_score
from scoring.kpis import (
    compute_capacity_utilization,
    compute_delay_burden,
    compute_load_factor,
    compute_long_haul_share,
    compute_traffic_growth,
)

# ---------------------------------------------------------------------------
# Airport lookup tool (resolves NL references -> airport_code list)
# ---------------------------------------------------------------------------


def lookup_airports(
    region: str | None = None,
    state: str | None = None,
    query: str | None = None,
    airport_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Filter the real airports.csv by region/state/free-text/explicit codes.

    All filters are ANDed together when multiple are given. `query` does a
    case-insensitive substring match against city, name, and airport_code (so
    "Santa Ana" matches SNA via city or name, "LA" won't reliably match LAX by
    itself -- callers should prefer explicit airport_codes like "LAX" when the
    user names an airport directly, and use `query`/`region`/`state` only for
    genuinely descriptive/regional phrasing).
    """
    airports = dl.load_airports().copy()

    if airport_codes:
        codes_upper = {c.strip().upper() for c in airport_codes}
        airports = airports[airports["airport_code"].str.upper().isin(codes_upper)]
    if region:
        airports = airports[
            airports["region"].str.contains(region, case=False, na=False)
        ]
    if state:
        airports = airports[airports["state"].str.upper() == state.strip().upper()]
    if query:
        q = query.strip().lower()
        mask = (
            airports["city"].str.lower().str.contains(q, na=False)
            | airports["name"].str.lower().str.contains(q, na=False)
            | airports["airport_code"].str.lower().str.contains(q, na=False)
        )
        airports = airports[mask]

    records = airports[
        [
            "airport_code",
            "name",
            "city",
            "state",
            "region",
            "runway_count",
            "longest_runway_ft",
        ]
    ].to_dict(orient="records")
    return {"count": len(records), "airports": records}


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI Chat Completions `tools=` format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_airports",
            "description": (
                "Resolve a natural-language airport reference (a region like "
                "'New England', a US state, a city/name substring, or a list of "
                "known IATA codes) into the matching airport rows from the real "
                "airports.csv dataset (62 airports: New England + LAX/SNA/ANC/SFO "
                "+ other major US airports). ALWAYS call this first to resolve "
                "airport_codes before calling any scoring tool with a region/city "
                "name -- never guess an IATA code from general knowledge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": (
                            "Region substring to filter on, e.g. 'New England', "
                            "'West Coast', 'Alaska'."
                        ),
                    },
                    "state": {
                        "type": "string",
                        "description": "2-letter US state code, e.g. 'CA'.",
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text substring matched against city, airport "
                            "name, and IATA code, e.g. 'Santa Ana' or 'Anchorage'."
                        ),
                    },
                    "airport_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Explicit IATA codes to filter to, e.g. ['LAX','SNA'], "
                            "if already known."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_composite_score",
            "description": (
                "Compute the deterministic 0-100 'Expansion Candidate Score' "
                "(weighted composite of capacity utilization 35%, traffic "
                "growth 25%, delay burden 25%, load factor 15%) for a list of "
                "airport_codes, percentile-ranked WITHIN that set. Use this for "
                "ranking/comparing/identifying strong terminal-expansion "
                "candidates. Resolve airport_codes via lookup_airports first if "
                "the user named a region/city rather than IATA codes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IATA airport codes to score and compare.",
                    },
                },
                "required": ["airport_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_capacity_utilization",
            "description": (
                "Single KPI (weight 0.35): peak-period operations / FAA hourly "
                "runway capacity for one airport. Returns raw_value, confidence "
                "(actual/estimated/unavailable), and source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_code": {"type": "string", "description": "IATA code."},
                },
                "required": ["airport_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_traffic_growth",
            "description": (
                "Single KPI (weight 0.25): multi-year CAGR of operations for one "
                "airport. Returns raw_value, confidence, and source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_code": {"type": "string", "description": "IATA code."},
                },
                "required": ["airport_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_delay_burden",
            "description": (
                "Single KPI (weight 0.25): % flights delayed 15+ min, weighted "
                "toward NAS/volume-attributed causes, for one airport. Also the "
                "primary signal behind 'unmet demand' questions when combined "
                "with high capacity utilization. Returns raw_value, confidence, "
                "and source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_code": {"type": "string", "description": "IATA code."},
                },
                "required": ["airport_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_load_factor",
            "description": (
                "Single KPI (weight 0.15): passengers / seats for one airport, "
                "trailing up to 12 months. Returns raw_value, confidence, and "
                "source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_code": {"type": "string", "description": "IATA code."},
                },
                "required": ["airport_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_long_haul_share",
            "description": (
                "Standalone descriptive stat (NOT part of the composite score): "
                "% of flights and % of seats out of one airport with great-"
                "circle distance over threshold_miles (default 2400, the "
                "long-haul industry threshold). Use for literal 'what % of "
                "flights out of X are long haul' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_code": {"type": "string", "description": "IATA code."},
                    "threshold_miles": {
                        "type": "number",
                        "description": "Long-haul distance threshold in miles. Default 2400.",
                    },
                },
                "required": ["airport_code"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name to the real underlying function.

    Returns a JSON-serializable dict (pydantic models -> .model_dump()).
    Raises ValueError for an unknown tool name.
    """
    if name == "lookup_airports":
        return lookup_airports(
            region=arguments.get("region"),
            state=arguments.get("state"),
            query=arguments.get("query"),
            airport_codes=arguments.get("airport_codes"),
        )

    if name == "compute_composite_score":
        codes = arguments.get("airport_codes") or []
        breakdowns = compute_composite_score(codes)
        return {code: bd.model_dump() for code, bd in breakdowns.items()}

    if name == "compute_capacity_utilization":
        return compute_capacity_utilization(arguments["airport_code"]).model_dump()

    if name == "compute_traffic_growth":
        return compute_traffic_growth(arguments["airport_code"]).model_dump()

    if name == "compute_delay_burden":
        return compute_delay_burden(arguments["airport_code"]).model_dump()

    if name == "compute_load_factor":
        return compute_load_factor(arguments["airport_code"]).model_dump()

    if name == "compute_long_haul_share":
        kwargs: dict[str, Any] = {"airport_code": arguments["airport_code"]}
        if arguments.get("threshold_miles") is not None:
            kwargs["threshold_miles"] = arguments["threshold_miles"]
        try:
            return compute_long_haul_share(**kwargs).model_dump()
        except ValueError as exc:
            # compute_long_haul_share raises for unknown/no-T100-data airports
            # (see scoring/kpis.py) rather than returning a fabricated 0%.
            # Surface this to the LLM as an explicit unavailable result instead
            # of letting the tool-call loop crash.
            return {
                "airport_code": arguments["airport_code"],
                "error": str(exc),
                "confidence": "unavailable",
            }

    raise ValueError(f"Unknown tool: {name}")
