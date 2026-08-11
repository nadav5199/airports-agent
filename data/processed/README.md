# Processed Data (`data/processed/`)

Output of the ingestion layer (`ingestion/run_all.py`). These are static, offline-generated
CSVs -- the scoring engine, backend, and frontend built by later agents only ever read these
files with pandas; nothing in the app re-fetches from the network at chat/query time. See
`CLAUDE.md` for the full rationale ("batch-downloaded/cached... not queried live per chat
turn").

## Real vs. synthetic, per file -- READ THIS FIRST

| File | Status | Source |
|---|---|---|
| `airports.csv` | **REAL** | OurAirports free CSV feed (`davidmegginson.github.io/ourairports-data`), no key required |
| `ontime_delays.csv` | **REAL** | BTS Airline On-Time Performance monthly bulk extracts (`transtats.bts.gov/PREZIP`), filtered to in-scope airports |
| `operations.csv` | **SYNTHETIC** | Generated fallback -- FAA ATADS has no stable bulk/REST endpoint (session/ViewState-gated report generator; see `ingestion/fetch_faa_atads.py` docstring) |
| `t100_routes.csv` | **SYNTHETIC** | Generated fallback -- BTS T-100 Segment bulk files are published behind a stateful form with non-predictable per-request filenames (see `ingestion/fetch_bts_t100.py` docstring) |
| `capacity_profiles.csv` | **HARDCODED (by design)** | Manually-curated approximate figures -- FAA Capacity Profiles are PDF-only with no API at all; this is a deliberate, spec-required deviation (see `ingestion/capacity_profiles.py` docstring), not a shortcut taken to save time |

Every synthetic value is produced by a **deterministic, seeded generator** (see
`ingestion/synthetic_common.py`) so re-running `run_all.py` reproduces identical numbers --
this is a stand-in dataset, not random noise, and is calibrated to be internally consistent
(airport-size tiering, seasonality, plausible load factors, etc.) but should never be quoted
as real FAA/BTS figures.

## Scope

All New England airports with scheduled commercial service (CT/ME/MA/NH/RI/VT, discovered
live from OurAirports) + the exam's named airports (LAX, SNA, ANC, SFO) + a curated spread of
~35 other major US airports (OEP-35-style). See `ingestion/airport_scope.py`.

## File-by-file detail

### `airports.csv` -- REAL (OurAirports)
One row per in-scope airport: code, name, city, state, region, lat/lon, runway_count,
longest_runway_ft. `region` is derived from state (New England / West Coast / Alaska /
Southeast / etc.) via a hardcoded state->region map, used for regional filtering queries
like "airports in New England."

### `operations.csv` -- SYNTHETIC (FAA ATADS fallback)
Monthly `operations_total` / `itinerant_ops` / `local_ops` per airport, June 2024 - May 2026
(24 months, chosen to align with the real On-Time data's vintage and to give the traffic-growth
KPI a meaningful multi-year CAGR to compute). Base volume is tiered by airport size (large hub /
medium / small), with a shared seasonal curve (summer peak) and a per-airport random-but-fixed
annual growth/decline trend (-3% to +6%/yr) layered on top, plus small month-to-month noise.

### `t100_routes.csv` -- SYNTHETIC (BTS T-100 fallback)
Route-level origin-dest-carrier-month rows, June 2024 - May 2026. `distance_miles` is REAL
(great-circle distance computed from real airport lat/lon in `airports.csv`) -- only the
traffic volumes (seats/passengers/departures) and route selection are synthetic. Each in-scope
airport is connected to 2-4 major hubs plus 1-2 short regional hops to nearby in-scope
airports, with aircraft-size (seat count) tiered by route distance and load factors in a
realistic 55-97% range (mean ~82%) so `passengers <= seats` always holds.

### `ontime_delays.csv` -- REAL (BTS On-Time Performance)
Monthly delay/cancellation stats per **origin** airport, aggregated from BTS's real flight-level
Reporting Carrier On-Time Performance extracts (`transtats.bts.gov/PREZIP`, one download per
month). Pulled for **April-May 2026** (2 months) -- deliberately bounded, not the full available
history, because each monthly file is BTS's complete national extract (~500-600k flight rows,
~25-30MB compressed) that must be downloaded in full and filtered client-side (BTS does not
expose this table through any filterable query API -- checked their Socrata/
data.transportation.gov catalog, which only lists 3 unrelated datasets). Since this ingestion
step runs once, offline, and never at chat/query time, the runtime tradeoff only affects how
long `run_all.py` takes to (re-)run, not the live app. `pct_delay_*` columns are each cause's
share of total delay-minutes (Carrier + Weather + NAS + LateAircraft) for that airport-month;
cancelled flights count toward `flights_total` but not the cause-share denominator (BTS doesn't
attribute delay-cause minutes to cancelled flights). To pull more months, edit
`MONTHS_TO_FETCH` in `ingestion/fetch_bts_ontime.py`.

### `capacity_profiles.csv` -- HARDCODED (FAA Capacity Profiles, approximate)
VMC/IMC hourly runway capacity for ~20 major airports (LAX, SNA, ANC, SFO, BOS required by
spec, plus a spread of other major hubs). FAA Airport Capacity Profiles are published as
individual PDFs with no bulk export or API, so per `docs/contracts.md` this file is manually
transcribed. Values are **representative/approximate**, sourced from public knowledge of these
airports' well-known runway configurations rather than verified line-by-line against each
airport's current official PDF -- `source` column is `"faa_profile_approx"` to flag this
honestly (not claiming a fully-verified `"faa_profile"` figure). Airports outside this table
fall back to a runway-count-based capacity proxy at scoring time (per `docs/contracts.md`),
which is `scoring/`'s responsibility, not this file's.

## Regenerating

```
pip install -r requirements.txt
python ingestion/run_all.py
```

Expect the on-time step to take several minutes (real network download of BTS's monthly
extracts); everything else is fast (OurAirports pull + local synthetic generation).
