"""Pydantic models shared by scoring/, backend/, and frontend/.

Authoritative spec: docs/contracts.md ("Scoring engine" section). Do not diverge
from those field names/types without updating that doc.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["actual", "estimated", "unavailable"]


class KPIResult(BaseModel):
    """One KPI for one airport."""

    name: str
    # "capacity_utilization" | "traffic_growth" | "delay_burden" | "load_factor"
    raw_value: float | None = None
    # underlying metric, e.g. 0.92 for 92% utilization; None if unavailable
    normalized_0_100: float | None = None
    # percentile rank within the comparison set; None if unavailable
    weight: float
    # 0.35 / 0.25 / 0.25 / 0.15 respectively
    confidence: Confidence
    source: str
    # e.g. "FAA ATADS + FAA Capacity Profile", or "estimated via runway count proxy"
    # -- also where data-source honesty (real/synthetic/approximate) is disclosed,
    # per data/processed/README.md
    as_of: str
    # data vintage, e.g. "2025-12" or the max year-month covered


class ScoreBreakdown(BaseModel):
    """Composite "Expansion Candidate Score" for one airport."""

    airport_code: str
    composite_score: float | None = None
    # None only if every KPI is unavailable
    kpis: dict[str, KPIResult] = Field(default_factory=dict)
    # keyed by KPIResult.name


class LongHaulShare(BaseModel):
    """Standalone descriptive stat -- not part of the composite score."""

    airport_code: str
    threshold_miles: float = 2400.0
    pct_long_haul_flights: float
    pct_long_haul_seats: float
    as_of: str
