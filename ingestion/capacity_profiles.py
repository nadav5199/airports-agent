"""
capacity_profiles.py -- NOT A SCRAPER. Manually-curated hardcoded lookup table.

FAA Airport Capacity Profiles are published as individual PDF documents per airport
(https://www.faa.gov/airports/planning_capacity/profiles/) with no API or bulk CSV
export. Per docs/contracts.md and CLAUDE.md, this is a deliberate, explicitly-flagged
deviation from "use public APIs": we hand-transcribe representative VMC (visual
meteorological conditions) and IMC (instrument meteorological conditions) hourly
runway operations capacity for a curated set of ~15-20 major US airports.

METHODOLOGY / HONESTY NOTE:
  Values below are REPRESENTATIVE/APPROXIMATE figures sourced from public knowledge of
  these airports' well-documented runway configurations and commonly-cited FAA/ATC
  capacity figures (e.g. FAA Airport Capacity Benchmark Report, published Capacity
  Profile summaries, and airport-specific ATC facility public statements). They are
  NOT verified line-by-line against the current official FAA Airport Capacity Profile
  PDF for every airport -- treat them as reasonable, internally-consistent estimates
  for demo/scoring purposes, not authoritative operational figures. Every row's
  `source` column is set to "faa_profile_approx" to flag this explicitly (as opposed
  to a hypothetical fully-verified "faa_profile" source), and this caveat is repeated
  in data/processed/README.md.

  Airports NOT in this table fall back to a runway-count-based proxy at scoring time
  (per docs/contracts.md), with confidence="estimated" -- that fallback logic lives in
  scoring/, not here.

Coverage requirement (per task spec): must include LAX, SNA, ANC, SFO, BOS at minimum,
plus a reasonable spread of other major/OEP-35-style airports. 20 airports covered here.
"""
from __future__ import annotations

import pandas as pd

# airport_code -> (vmc_hourly_capacity, imc_hourly_capacity)
# Figures are operations/hour (arrivals + departures combined), representative of
# each airport's dominant runway configuration.
CAPACITY_PROFILES: dict[str, tuple[int, int]] = {
    # Exam-required coverage
    "LAX": (149, 128),   # 4 parallel runways, dual east/west complex
    "SNA": (56, 38),     # Single primary runway (John Wayne / Santa Ana)
    "ANC": (108, 78),    # 3 runways, general/cargo hub, seasonal IMC (fog)
    "SFO": (120, 60),    # Close-spaced parallel runways -- large VMC/IMC gap (famous fog constraint)
    "BOS": (126, 96),    # Logan, 6 runways but complex crossing geometry
    # Other major / OEP-35-style airports
    "JFK": (100, 88),
    "EWR": (94, 78),
    "LGA": (81, 74),     # Single/dual close runways, historically slot-constrained
    "ORD": (170, 130),   # Extensive parallel/diagonal runway system post-O'Hare Modernization
    "ATL": (200, 176),   # 5 parallel runways, world's busiest by ops
    "DFW": (196, 164),   # 7 runways
    "DEN": (216, 189),   # 6 runways, very high VMC capacity, wide open airfield
    "SEA": (98, 68),     # Primarily 2 close-parallel + 1 third runway; IMC/rain constrained
    "MIA": (124, 96),
    "PHX": (140, 118),
    "IAH": (156, 128),
    "MCO": (146, 120),
    "LAS": (130, 108),
    "MSP": (144, 120),
    "DTW": (150, 128),
    "PHL": (108, 76),    # Historically capacity-constrained, intersecting/close runways
    "CLT": (140, 108),
}

SOURCE_LABEL = "faa_profile_approx"


def build_capacity_profiles() -> pd.DataFrame:
    """Return the capacity_profiles.csv DataFrame per the contract schema."""
    rows = [
        {
            "airport_code": code,
            "vmc_hourly_capacity": vmc,
            "imc_hourly_capacity": imc,
            "source": SOURCE_LABEL,
        }
        for code, (vmc, imc) in sorted(CAPACITY_PROFILES.items())
    ]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build_capacity_profiles()
    print(f"Built capacity profiles for {len(df)} airports")
    print(df.to_string())
