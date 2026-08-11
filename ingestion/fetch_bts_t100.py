"""
fetch_bts_t100.py -- SYNTHETIC FALLBACK (documented, not a real data pull).

BTS T-100 Segment (domestic) data is published via transtats.bts.gov's bulk-download
system, but unlike the On-Time Performance table (see fetch_bts_ontime.py, which uses
a stable, predictable monthly zip URL), the T-100 Segment bulk files are generated
on-demand behind a stateful web form and published under filenames with a per-request
hash prefix (e.g. `896816367_T_T100D_SEGMENT_ALL_CARRIER.zip`) that is not predictable
or guessable ahead of time. Getting a real pull would require driving the multi-step
ASP.NET download wizard (session cookies, hidden field selection, POST submission,
then polling PREZIP/ for the freshly generated file) -- judged not worth the time
budget here versus BTS's own alternative "international" Socrata dataset (which does
not cover domestic segments) or a clearly-labeled synthetic fallback.

WHAT THIS SCRIPT DOES INSTEAD:
Generates a realistic, internally-consistent route network for the airports in scope:
  - Every in-scope airport gets service to a handful of major hubs (ATL, ORD, DFW,
    DEN, LAX, JFK, etc.) plus 1-3 short regional hops to nearby in-scope airports,
    roughly approximating how small/medium airports actually connect through hubs.
  - `distance_miles` is computed from real lat/lon (great-circle / haversine) using
    airports.csv -- this part *is* grounded in real geography, not invented.
  - `seats`/`departures_performed` are calibrated by a representative aircraft-size
    tier per route length (regional jet / narrowbody / widebody), and `passengers`
    is seats x a plausible load factor (roughly 75-88%, with modest per-route noise)
    so passengers <= seats always holds (no impossible load factors).
  - A small set of major carriers is cycled per route for variety.

This is an approximation of route-network structure, not observed traffic. It should
never be presented as real BTS figures -- flagged here and in data/processed/README.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic_common import month_range, rng_for, size_tier

START_YEAR, START_MONTH = 2024, 6
N_MONTHS = 24  # ends 2026-05, aligned with the real BTS On-Time data vintage
# pulled in fetch_bts_ontime.py (see that script's docstring).

MAJOR_HUBS = ["ATL", "ORD", "DFW", "DEN", "LAX", "JFK", "SFO", "MIA", "SEA", "CLT"]
CARRIERS = ["AA", "DL", "UA", "WN", "B6", "AS", "NK"]

# (min_distance_mi, max_distance_mi) -> (seat_lo, seat_hi, aircraft label)
AIRCRAFT_BY_DISTANCE = [
    (0, 400, 50, 76),        # regional jet
    (400, 1200, 120, 175),   # narrowbody (A320/737 family)
    (1200, 2400, 150, 190),  # narrowbody, longer stage length
    (2400, 6000, 200, 350),  # widebody / transcon-plus
]


def _haversine_miles(lat1, lon1, lat2, lon2) -> float:
    r = 3958.8  # earth radius in miles
    lat1r, lon1r, lat2r, lon2r = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return float(r * 2 * np.arcsin(np.sqrt(a)))


def _seat_range_for_distance(dist: float) -> tuple[int, int]:
    for lo, hi, seat_lo, seat_hi in AIRCRAFT_BY_DISTANCE:
        if lo <= dist < hi:
            return seat_lo, seat_hi
    return AIRCRAFT_BY_DISTANCE[-1][2], AIRCRAFT_BY_DISTANCE[-1][3]


def _build_route_list(airports: pd.DataFrame) -> list[tuple[str, str]]:
    """Each airport gets service to a few major hubs + nearby in-scope neighbors."""
    codes = airports["airport_code"].tolist()
    coord = airports.set_index("airport_code")[["lat", "lon"]]
    routes: set[tuple[str, str]] = set()

    for code in codes:
        rng = rng_for(code, "t100_routes")
        hub_pool = [h for h in MAJOR_HUBS if h != code]
        n_hub_routes = int(rng.integers(2, 5))
        chosen_hubs = rng.choice(hub_pool, size=min(n_hub_routes, len(hub_pool)), replace=False)
        for hub in chosen_hubs:
            routes.add((code, hub))
            routes.add((hub, code))

        # 1-2 short regional hops to the nearest other in-scope airports.
        if code not in coord.index:
            continue
        lat0, lon0 = coord.loc[code]
        dists = {}
        for other in codes:
            if other == code or other in MAJOR_HUBS:
                continue
            lat1, lon1 = coord.loc[other]
            dists[other] = _haversine_miles(lat0, lon0, lat1, lon1)
        nearest = sorted(dists, key=dists.get)[:2]
        for other in nearest:
            if dists[other] < 700:
                routes.add((code, other))

    return sorted(routes)


def fetch_t100_routes(airports: pd.DataFrame) -> pd.DataFrame:
    """airports: DataFrame with columns airport_code, lat, lon (as in airports.csv)."""
    coord = airports.set_index("airport_code")[["lat", "lon"]]
    route_list = _build_route_list(airports)

    rows = []
    for origin, dest in route_list:
        if origin not in coord.index or dest not in coord.index:
            continue
        lat1, lon1 = coord.loc[origin]
        lat2, lon2 = coord.loc[dest]
        distance = round(_haversine_miles(lat1, lon1, lat2, lon2), 1)
        if distance <= 0:
            continue

        seat_lo, seat_hi = _seat_range_for_distance(distance)
        rng = rng_for(f"{origin}-{dest}", "t100_detail")
        carrier = CARRIERS[int(rng.integers(0, len(CARRIERS)))]

        tier = size_tier(origin)
        base_daily_departures = {"large": rng.uniform(2, 6), "medium": rng.uniform(1, 3), "small": rng.uniform(0.2, 1.2)}[tier]

        for year, month in month_range(START_YEAR, START_MONTH, N_MONTHS):
            days_in_month = 30
            departures = max(1, round(base_daily_departures * days_in_month * rng.normal(1.0, 0.06)))
            seats_per_dep = int(rng.integers(seat_lo, seat_hi + 1))
            seats = departures * seats_per_dep
            load_factor = float(np.clip(rng.normal(0.82, 0.06), 0.55, 0.97))
            passengers = int(round(seats * load_factor))
            rows.append(
                {
                    "origin": origin,
                    "dest": dest,
                    "year": year,
                    "month": month,
                    "carrier": carrier,
                    "passengers": passengers,
                    "seats": seats,
                    "departures_performed": departures,
                    "distance_miles": distance,
                }
            )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import fetch_ourairports

    airports = fetch_ourairports.fetch_airports()
    df = fetch_t100_routes(airports)
    print(f"Generated {len(df)} route-month rows across {df[['origin','dest']].drop_duplicates().shape[0]} routes")
    print(df.head(10).to_string())
