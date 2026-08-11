"""
synthetic_common.py -- shared helpers for the SYNTHETIC-FALLBACK ingestion scripts
(fetch_faa_atads.py and fetch_bts_t100.py).

Both FAA ATADS and BTS T-100 Segment turned out not to have a clean, reliably
reachable programmatic pull within a reasonable effort budget for this exercise:
  - FAA ATADS (aspm.faa.gov) is served through a session/ViewState-driven ASP.NET
    report generator with no stable bulk-CSV or REST endpoint (CLAUDE.md already
    flags FAA ASPM as excluded for the same login/session-gated reason).
  - BTS T-100 Segment bulk files on transtats.bts.gov are generated on-demand behind
    a stateful web form (the PREZIP filenames include a per-request hash prefix,
    e.g. `896816367_T_T100D_SEGMENT_ALL_CARRIER.zip`, that isn't predictable/stable),
    unlike the On-Time Performance monthly files which do have a stable, predictable
    URL pattern (used for real in fetch_bts_ontime.py).

Per the task's explicit fallback allowance, these two sources are therefore
SYNTHETIC: generated with a fixed random seed so runs are reproducible, calibrated
to be internally consistent and realistic (airport-size-tiered volumes, seasonality,
modest year-over-year growth/decline trends) rather than arbitrary noise. This is
declared loudly in each script's own docstring, in the `source`-style documentation
in data/processed/README.md, and nowhere is it mixed silently with real rows.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Airports treated as "large hub" tier for synthetic volume calibration.
LARGE_HUBS = {
    "ATL", "ORD", "DFW", "DEN", "LAX", "JFK", "SFO", "LAS", "MCO", "CLT",
    "PHX", "IAH", "MIA", "SEA", "EWR", "MSP", "DTW", "BOS", "PHL", "LGA",
}
MEDIUM_HUBS = {
    "SAN", "TPA", "PDX", "STL", "IAD", "DCA", "HNL", "FLL", "BNA", "AUS",
    "RDU", "MSY", "SMF", "OAK", "SLC", "BWI", "SNA", "ANC", "BDL", "PVD",
    "PWM",
}
# Everything else in scope (small NE regionals, GA fields, etc.) is "small" tier.

SEASONAL_INDEX = {
    1: 0.85, 2: 0.85, 3: 0.95, 4: 1.00, 5: 1.05, 6: 1.15,
    7: 1.20, 8: 1.18, 9: 1.02, 10: 1.00, 11: 0.90, 12: 0.95,
}


def size_tier(airport_code: str) -> str:
    if airport_code in LARGE_HUBS:
        return "large"
    if airport_code in MEDIUM_HUBS:
        return "medium"
    return "small"


def month_range(start_year: int, start_month: int, n_months: int):
    """Yield (year, month) tuples for n_months starting at start_year-start_month."""
    y, m = start_year, start_month
    for _ in range(n_months):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def rng_for(airport_code: str, salt: str, seed_base: int = 42) -> np.random.Generator:
    """Deterministic per-airport RNG so re-running the generator is reproducible.

    Uses zlib.crc32 rather than Python's built-in hash(), since str hashing is
    randomized per-process (PYTHONHASHSEED) unless disabled -- crc32 is stable
    across runs/machines, which is what "reproducible" requires here.
    """
    import zlib

    key = f"{airport_code}:{salt}".encode("utf-8")
    seed = (zlib.crc32(key) + seed_base) % (2**32)
    return np.random.default_rng(seed)
