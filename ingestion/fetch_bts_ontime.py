"""
fetch_bts_ontime.py -- REAL DATA PULL from BTS Airline On-Time Performance
(Reporting Carrier On-Time Performance, a.k.a. ASQP-derived).

Source: https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{YEAR}_{MONTH}.zip

Unlike BTS T-100 Segment (see fetch_bts_t100.py, synthetic fallback), the On-Time
Performance table IS published as a stable, predictably-named monthly zip on
transtats.bts.gov's PREZIP bulk-download folder -- no session/form-submission dance
required, just a direct HTTPS GET per (year, month). This is a REAL pull: each file
is BTS's actual full-national flight-level on-time performance extract for that
month (every reporting carrier, every route), which we download and then filter down
to flights touching an airport in our demo scope and aggregate to the monthly
per-airport grain the contract (`ontime_delays.csv`) requires.

Each monthly file is large (all US domestic flights for that month, ~500k-600k rows,
~25-30MB zipped) so we only pull a handful of recent months (see MONTHS_TO_FETCH)
to keep the ingestion run practical, rather than the full 1987-present history.

Aggregation logic (per-airport-per-month, using ORIGIN as the airport dimension --
i.e. delay/cancellation stats for departures FROM that airport):
  - flights_total          = row count for that origin/year/month
  - flights_delayed_15     = count where DepDel15 == 1 (departure delayed 15+ min)
  - avg_delay_min          = mean DepDelayMinutes (delayed flights only would bias
                              upward vs. "average delay" in common usage, so we use
                              the mean over ALL flights, i.e. 0 for on-time ones --
                              this matches how BTS's own average delay stat is framed)
  - pct_delay_nas/weather/carrier/late_aircraft = each cause's SHARE OF TOTAL DELAY
    MINUTES across the month (sum of that cause's delay-minutes column / sum of all
    four cause columns), per docs/contracts.md's "share of delay-minutes" definition.
    Cancelled flights don't carry cause-of-delay minutes in this table and are
    excluded from the cause-share denominator (they still count in flights_total).
"""
from __future__ import annotations

import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

# Recent months to pull (real, bounded pull). Each monthly file is BTS's FULL
# national on-time-performance extract (~500-600k flight rows, ~25-30MB zipped)
# that we download in full and filter client-side -- BTS does not expose this
# table through a filterable query API (checked: their Socrata/data.transportation.gov
# catalog only lists 3 unrelated datasets), so there's no way to request just the
# in-scope-airport rows server-side. Kept to 2 months (not more) as a deliberate
# time-budget tradeoff for this exercise -- this runs once as an offline ingestion
# step (see run_all.py), never at chat/query time, so its runtime doesn't affect
# the live app; it's just slow to iterate on during ingestion. Increase this list
# to pull more history if a full re-run's runtime is acceptable.
MONTHS_TO_FETCH = [
    (2026, 4), (2026, 5),
]

# Columns we actually need from the (large, ~110-column) monthly extract.
USE_COLS = [
    "Year", "Month", "Origin", "DepDel15", "DepDelayMinutes", "Cancelled",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]


def _download_month(year: int, month: int) -> pd.DataFrame | None:
    print(f"  Downloading BTS On-Time Performance {year}-{month:02d} ...")
    url = BASE_URL.format(year=year, month=month)
    resp = requests.get(url, timeout=180)
    if resp.status_code != 200:
        print(f"  [WARN] {year}-{month:02d}: HTTP {resp.status_code}, skipping")
        return None
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(csv_name) as f:
            df = pd.read_csv(f, usecols=lambda c: c.strip() in USE_COLS, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    print(f"  Done downloading {year}-{month:02d} ({len(df)} rows)")
    return df


def fetch_ontime_delays(airport_codes: list[str]) -> pd.DataFrame:
    scope = set(airport_codes)
    monthly_frames = []

    # Each month is an independent HTTP download + zip decompress (I/O-bound), so
    # fetch them concurrently rather than one at a time.
    with ThreadPoolExecutor(max_workers=len(MONTHS_TO_FETCH)) as pool:
        downloaded = list(pool.map(lambda ym: _download_month(*ym), MONTHS_TO_FETCH))

    for (year, month), df in zip(MONTHS_TO_FETCH, downloaded):
        if df is None:
            continue
        df = df[df["Origin"].isin(scope)].copy()
        if df.empty:
            continue

        for col in ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay", "DepDelayMinutes", "DepDel15"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        grouped = df.groupby(["Origin", "Year", "Month"])
        for (origin, y, m), g in grouped:
            total_cause_minutes = g[["CarrierDelay", "WeatherDelay", "NASDelay", "LateAircraftDelay"]].sum().sum()
            flights_total = len(g)
            flights_delayed_15 = int(g["DepDel15"].sum())
            avg_delay_min = float(g["DepDelayMinutes"].mean())

            if total_cause_minutes > 0:
                pct_nas = float(g["NASDelay"].sum() / total_cause_minutes)
                pct_weather = float(g["WeatherDelay"].sum() / total_cause_minutes)
                pct_carrier = float(g["CarrierDelay"].sum() / total_cause_minutes)
                pct_late_aircraft = float(g["LateAircraftDelay"].sum() / total_cause_minutes)
            else:
                pct_nas = pct_weather = pct_carrier = pct_late_aircraft = 0.0

            monthly_frames.append(
                {
                    "airport_code": origin,
                    "year": int(y),
                    "month": int(m),
                    "flights_total": flights_total,
                    "flights_delayed_15": flights_delayed_15,
                    "avg_delay_min": round(avg_delay_min, 2),
                    "pct_delay_nas": round(pct_nas, 4),
                    "pct_delay_weather": round(pct_weather, 4),
                    "pct_delay_carrier": round(pct_carrier, 4),
                    "pct_delay_late_aircraft": round(pct_late_aircraft, 4),
                }
            )

    out = pd.DataFrame(monthly_frames)
    if not out.empty:
        out = out.sort_values(["airport_code", "year", "month"]).reset_index(drop=True)
    return out


if __name__ == "__main__":
    df = fetch_ontime_delays(["BOS", "LAX", "SFO", "ANC", "SNA", "BDL"])
    print(f"Fetched {len(df)} airport-month rows")
    print(df.head(10).to_string())
