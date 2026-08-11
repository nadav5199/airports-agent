"""Composite "Expansion Candidate Score" -- percentile-rank normalization + the
0.35/0.25/0.25/0.15 weighted sum, reweighted across available KPIs per airport.

See CLAUDE.md "Scoring Methodology" and docs/contracts.md for the spec this
implements. All four KPIs are "higher raw value = stronger investment case"
(higher utilization, faster growth, higher delay burden i.e. more unmet demand,
higher load factor), so no direction-flipping is needed before ranking.
"""

from __future__ import annotations

import pandas as pd

from scoring.kpis import (
    compute_capacity_utilization,
    compute_delay_burden,
    compute_load_factor,
    compute_traffic_growth,
)
from scoring.schemas import KPIResult, ScoreBreakdown

_KPI_FUNCS = (
    compute_capacity_utilization,
    compute_traffic_growth,
    compute_delay_burden,
    compute_load_factor,
)


def compute_composite_score(airport_codes: list[str]) -> dict[str, ScoreBreakdown]:
    """Compute ScoreBreakdown for each airport in airport_codes.

    Percentile rank normalization is computed **within this airport_codes set
    only** -- call this again with a different set (e.g. just two airports for
    a head-to-head comparison, or a whole region) to get a different, and
    equally valid, set of normalized_0_100 values. This is by design per
    CLAUDE.md: percentile rank is deliberately relative to "the current
    comparison set", not a fixed global population.
    """
    if not airport_codes:
        return {}

    # airport_code -> kpi_name -> KPIResult (raw, not yet normalized)
    raw_results: dict[str, dict[str, KPIResult]] = {}
    for code in airport_codes:
        raw_results[code] = {}
        for fn in _KPI_FUNCS:
            result = fn(code)
            raw_results[code][result.name] = result

    kpi_names = [
        "capacity_utilization",
        "traffic_growth",
        "delay_burden",
        "load_factor",
    ]

    # Percentile-rank normalize each KPI independently across the set. NaN
    # (unavailable/None raw_value) stays NaN and is excluded from ranking and
    # from reweighting below -- never silently treated as 0.
    normalized: dict[str, dict[str, float | None]] = {code: {} for code in airport_codes}
    for kpi_name in kpi_names:
        series = pd.Series(
            {
                code: raw_results[code][kpi_name].raw_value
                for code in airport_codes
                if raw_results[code][kpi_name].confidence != "unavailable"
                and raw_results[code][kpi_name].raw_value is not None
            }
        )
        if series.empty:
            for code in airport_codes:
                normalized[code][kpi_name] = None
            continue
        # pct=True -> rank / count, in (0, 1]; scale to 0-100. A single-airport
        # set trivially percentile-ranks at 100 (it's the max of a set of one).
        pct_ranks = series.rank(pct=True) * 100.0
        for code in airport_codes:
            normalized[code][kpi_name] = (
                float(pct_ranks[code]) if code in pct_ranks.index else None
            )

    breakdowns: dict[str, ScoreBreakdown] = {}
    for code in airport_codes:
        kpis: dict[str, KPIResult] = {}
        weighted_sum = 0.0
        weight_total = 0.0
        for kpi_name in kpi_names:
            result = raw_results[code][kpi_name]
            norm = normalized[code][kpi_name]
            # Attach the normalized score (computed above) to a fresh KPIResult
            # copy -- the per-KPI functions themselves don't know the comparison
            # set, so they always return normalized_0_100=None.
            result = result.model_copy(update={"normalized_0_100": norm})
            kpis[kpi_name] = result
            if result.confidence != "unavailable" and norm is not None:
                weighted_sum += norm * result.weight
                weight_total += result.weight

        composite_score = (weighted_sum / weight_total) if weight_total > 0 else None
        breakdowns[code] = ScoreBreakdown(
            airport_code=code,
            composite_score=composite_score,
            kpis=kpis,
        )

    return breakdowns
