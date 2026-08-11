"""
run_all.py -- orchestrates all five ingestion sources and writes
data/processed/*.csv per the schemas in docs/contracts.md.

Real vs. synthetic (see each script's own docstring for full rationale):
  - airports.csv          REAL   (fetch_ourairports.py -- OurAirports CSV feed)
  - ontime_delays.csv     REAL   (fetch_bts_ontime.py -- BTS On-Time Performance,
                                   filtered to in-scope airports/recent months)
  - t100_routes.csv       SYNTHETIC (fetch_bts_t100.py -- BTS T-100 Segment bulk
                                   files are not reachable via a stable/predictable
                                   URL; see docstring)
  - operations.csv        SYNTHETIC (fetch_faa_atads.py -- FAA ATADS has no stable
                                   bulk endpoint, session/ViewState-gated; see
                                   docstring)
  - capacity_profiles.csv HARDCODED (capacity_profiles.py -- FAA Capacity Profiles
                                   are PDF-only by design, not an API; required by
                                   the task spec to be a manually-curated table)

Usage: python ingestion/run_all.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capacity_profiles
import fetch_bts_ontime
import fetch_bts_t100
import fetch_faa_atads
import fetch_ourairports

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "processed"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("1/5  Fetching airports.csv (REAL: OurAirports)")
    print("=" * 70)
    airports = fetch_ourairports.fetch_airports()
    airports.to_csv(OUT_DIR / "airports.csv", index=False)
    print(f"  -> wrote {len(airports)} rows to airports.csv")

    airport_codes = airports["airport_code"].tolist()

    print("=" * 70)
    print("2/5  Fetching operations.csv (SYNTHETIC: FAA ATADS fallback)")
    print("=" * 70)
    operations = fetch_faa_atads.fetch_operations(airport_codes)
    operations.to_csv(OUT_DIR / "operations.csv", index=False)
    print(f"  -> wrote {len(operations)} rows to operations.csv")

    print("=" * 70)
    print("3/5  Fetching t100_routes.csv (SYNTHETIC: BTS T-100 fallback)")
    print("=" * 70)
    t100 = fetch_bts_t100.fetch_t100_routes(airports)
    t100.to_csv(OUT_DIR / "t100_routes.csv", index=False)
    print(f"  -> wrote {len(t100)} rows to t100_routes.csv")

    print("=" * 70)
    print("4/5  Fetching ontime_delays.csv (REAL: BTS On-Time Performance)")
    print("=" * 70)
    ontime = fetch_bts_ontime.fetch_ontime_delays(airport_codes)
    ontime.to_csv(OUT_DIR / "ontime_delays.csv", index=False)
    print(f"  -> wrote {len(ontime)} rows to ontime_delays.csv")

    print("=" * 70)
    print("5/5  Building capacity_profiles.csv (HARDCODED: FAA Capacity Profiles)")
    print("=" * 70)
    capacity = capacity_profiles.build_capacity_profiles()
    capacity.to_csv(OUT_DIR / "capacity_profiles.csv", index=False)
    print(f"  -> wrote {len(capacity)} rows to capacity_profiles.csv")

    print("=" * 70)
    print("Done. All five processed CSVs written to", OUT_DIR)
    print("=" * 70)


if __name__ == "__main__":
    main()
