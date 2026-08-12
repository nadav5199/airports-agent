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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    print("Fetching airports.csv (REAL: OurAirports)")
    print("=" * 70)
    airports = fetch_ourairports.fetch_airports()
    airports.to_csv(OUT_DIR / "airports.csv", index=False)
    print(f"  -> wrote {len(airports)} rows to airports.csv")

    airport_codes = airports["airport_code"].tolist()

    # The remaining four sources don't depend on each other, only on airports/
    # airport_codes above -- run them concurrently so the CPU-bound synthetic
    # generation and the instant hardcoded table overlap with the network-bound
    # BTS On-Time download (the actual long pole of the pipeline).
    print("=" * 70)
    print("Fetching operations / t100_routes / ontime_delays / capacity_profiles (parallel)")
    print("=" * 70)
    jobs = {
        "operations.csv": lambda: fetch_faa_atads.fetch_operations(airport_codes),
        "t100_routes.csv": lambda: fetch_bts_t100.fetch_t100_routes(airports),
        "ontime_delays.csv": lambda: fetch_bts_ontime.fetch_ontime_delays(airport_codes),
        "capacity_profiles.csv": lambda: capacity_profiles.build_capacity_profiles(),
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            df = future.result()
            df.to_csv(OUT_DIR / name, index=False)
            print(f"  -> wrote {len(df)} rows to {name}")

    print("=" * 70)
    print("Done. All five processed CSVs written to", OUT_DIR)
    print("=" * 70)


if __name__ == "__main__":
    main()
