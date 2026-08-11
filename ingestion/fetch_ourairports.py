"""
fetch_ourairports.py -- REAL DATA PULL (no API key required).

Pulls airport reference data from OurAirports' free, nightly-updated CSV feeds:
  - https://davidmegginson.github.io/ourairports-data/airports.csv
  - https://davidmegginson.github.io/ourairports-data/runways.csv

Produces the rows for `airports.csv` per docs/contracts.md:
  airport_code, name, city, state, region, lat, lon, runway_count, longest_runway_ft

Scope: all New England airports with scheduled commercial service (discovered live
from the feed, not hardcoded) + the exam's named airports (LAX, SNA, ANC, SFO) + a
curated spread of other major US airports (see airport_scope.MAJOR_AIRPORTS).

This is the one ingestion source with a genuinely simple, reliable public API (plain
CSV over HTTPS, no auth, no scraping) -- so unlike t100/atads it required no fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from airport_scope import MAJOR_AIRPORTS, NEW_ENGLAND_STATES, region_for_state

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"


def _fetch_csv(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    from io import StringIO

    return pd.read_csv(StringIO(resp.text), low_memory=False)


def fetch_airports() -> pd.DataFrame:
    """Return the airports.csv DataFrame per the contract schema."""
    airports = _fetch_csv(AIRPORTS_URL)
    runways = _fetch_csv(RUNWAYS_URL)

    airports = airports[airports["iso_country"] == "US"].copy()
    airports["state"] = airports["iso_region"].str.replace("US-", "", regex=False)

    # New England: all airports with scheduled commercial service in the 6 NE states.
    ne_mask = (
        airports["state"].isin(NEW_ENGLAND_STATES)
        & (airports["scheduled_service"] == "yes")
        & airports["iata_code"].notna()
    )
    ne_airports = airports[ne_mask]

    # Major airports: curated IATA code list (exam-named + OEP-35-style spread).
    major_mask = airports["iata_code"].isin(MAJOR_AIRPORTS)
    major_airports = airports[major_mask]

    scope = pd.concat([ne_airports, major_airports]).drop_duplicates(subset="iata_code")

    # Runway aggregates: count of (non-closed) runways + longest runway length.
    open_runways = runways[runways["closed"] != 1]
    runway_agg = (
        open_runways.groupby("airport_ident")
        .agg(runway_count=("id", "count"), longest_runway_ft=("length_ft", "max"))
        .reset_index()
        .rename(columns={"airport_ident": "ident"})
    )

    scope = scope.merge(runway_agg, on="ident", how="left")
    scope["runway_count"] = scope["runway_count"].fillna(0).astype(int)
    scope["longest_runway_ft"] = scope["longest_runway_ft"].fillna(0.0).astype(float)

    scope["region"] = scope["state"].apply(region_for_state)

    out = pd.DataFrame(
        {
            "airport_code": scope["iata_code"],
            "name": scope["name"],
            "city": scope["municipality"],
            "state": scope["state"],
            "region": scope["region"],
            "lat": scope["latitude_deg"].astype(float),
            "lon": scope["longitude_deg"].astype(float),
            "runway_count": scope["runway_count"],
            "longest_runway_ft": scope["longest_runway_ft"],
        }
    )
    out = out.sort_values("airport_code").reset_index(drop=True)
    return out


if __name__ == "__main__":
    df = fetch_airports()
    print(f"Fetched {len(df)} airports")
    print(df.head(10).to_string())
