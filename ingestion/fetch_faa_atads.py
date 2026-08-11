"""
fetch_faa_atads.py -- SYNTHETIC FALLBACK (documented, not a real data pull).

FAA ATADS (Air Traffic Activity Data System, https://aspm.faa.gov/opsnet/sys/Airport.asp)
publishes monthly airport operations counts, but only through a stateful, ASP.NET
ViewState-driven report generator -- there is no stable REST/CSV bulk endpoint to hit
with a single HTTP request. This is the same category of gate that CLAUDE.md already
excludes FAA ASPM for (its sibling system). A real pull would require full browser-style
session scraping (cookies, hidden form tokens, multi-step report wizard), which was
judged not worth the time budget for this exercise versus a clearly-labeled synthetic
fallback -- exactly the fallback path the task spec anticipates.

WHAT THIS SCRIPT DOES INSTEAD:
Generates internally-consistent, realistic monthly `operations_total` /
`itinerant_ops` / `local_ops` figures per airport for a 2-year window, using:
  - Airport-size tiering (large hub / medium / small -- see synthetic_common.py)
    to set a plausible base monthly operations level (order-of-magnitude realistic:
    e.g. ATL/ORD-scale hubs ~28-34k ops/month, small NE GA fields ~200-900 ops/month).
  - A shared seasonal index (summer peak, winter trough) applied to every airport.
  - A small per-airport year-over-year growth/decline trend (drawn once per airport,
    deterministically seeded) so the traffic-growth-rate KPI in scoring/ has a
    meaningful, non-degenerate signal to compute a CAGR from.
  - itinerant vs. local ops split calibrated by tier: large commercial hubs are almost
    all itinerant traffic (~93-97%); small GA-heavy fields have a much larger local
    (touch-and-go/training) share (~25-45%).

Every row in operations.csv should be read as an ESTIMATE, not an FAA-sourced figure.
This is called out again in data/processed/README.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_common import SEASONAL_INDEX, month_range, rng_for, size_tier

START_YEAR, START_MONTH = 2024, 6
N_MONTHS = 24  # 2 full years -> enough for a multi-year CAGR (traffic growth KPI);
# ends 2026-05, aligned with the real BTS On-Time data vintage pulled in
# fetch_bts_ontime.py so the demo dataset reads as one coherent (if partly
# synthetic) time window rather than sources from visibly different eras.

BASE_OPS_BY_TIER = {
    "large": (24000, 34000),
    "medium": (6000, 16000),
    "small": (200, 3500),
}
LOCAL_SHARE_BY_TIER = {
    "large": (0.03, 0.07),
    "medium": (0.08, 0.18),
    "small": (0.25, 0.45),
}
ANNUAL_GROWTH_RANGE = (-0.03, 0.06)  # -3% to +6% YoY drift, drawn per airport


def fetch_operations(airport_codes: list[str]) -> pd.DataFrame:
    rows = []
    for code in sorted(set(airport_codes)):
        tier = size_tier(code)
        rng = rng_for(code, "atads")

        base_lo, base_hi = BASE_OPS_BY_TIER[tier]
        base = rng.uniform(base_lo, base_hi)
        annual_growth = rng.uniform(*ANNUAL_GROWTH_RANGE)
        monthly_growth = (1 + annual_growth) ** (1 / 12)

        local_lo, local_hi = LOCAL_SHARE_BY_TIER[tier]
        local_share = rng.uniform(local_lo, local_hi)

        # Small month-to-month noise on top of trend + seasonality, kept modest
        # (+-4%) so it reads as realistic operational variance, not randomness.
        noise = rng.normal(1.0, 0.04, size=N_MONTHS)

        for i, (year, month) in enumerate(month_range(START_YEAR, START_MONTH, N_MONTHS)):
            level = base * (monthly_growth**i) * SEASONAL_INDEX[month] * noise[i]
            operations_total = max(1, round(level))
            local_ops = round(operations_total * local_share)
            itinerant_ops = operations_total - local_ops
            rows.append(
                {
                    "airport_code": code,
                    "year": year,
                    "month": month,
                    "operations_total": int(operations_total),
                    "itinerant_ops": int(itinerant_ops),
                    "local_ops": int(local_ops),
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = fetch_operations(["BOS", "LAX", "ANC"])
    print(df.head(10).to_string())
