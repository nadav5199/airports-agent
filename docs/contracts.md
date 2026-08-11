# Contracts

Authoritative interface spec for the four implementation layers. Each layer is built by a
separate agent, sequentially (ingestion → scoring → backend → frontend), each merging real work
into `main` before the next starts. See [../CLAUDE.md](../CLAUDE.md) for the full requirements,
data source rationale, scoring methodology, and explainability design this spec implements.

## 1. Processed data schema (`data/processed/*.csv`)

Produced by `ingestion/`, consumed by `scoring/`. All files CSV, UTF-8, header row required.

### `airports.csv`
One row per airport in the demo dataset (scope: all New England airports + LAX, SNA, ANC, SFO +
enough other major US airports for meaningful percentile-rank comparisons — e.g. the FAA OEP-35
set is a reasonable superset).

| column | type | notes |
|---|---|---|
| airport_code | str | IATA code, primary key used across all other files |
| name | str | |
| city | str | |
| state | str | 2-letter |
| region | str | e.g. "New England", "West Coast" — used for regional filtering queries |
| lat | float | |
| lon | float | |
| runway_count | int | from OurAirports |
| longest_runway_ft | float | from OurAirports — used for the capacity-estimate fallback |

### `operations.csv`
Monthly airport operations (FAA ATADS). One row per airport per year-month.

| column | type | notes |
|---|---|---|
| airport_code | str | FK → airports.csv |
| year | int | |
| month | int | 1-12 |
| operations_total | int | takeoffs + landings |
| itinerant_ops | int | |
| local_ops | int | |

### `t100_routes.csv`
Route-level segment data (BTS T-100). One row per origin-dest-carrier-year-month.

| column | type | notes |
|---|---|---|
| origin | str | airport_code |
| dest | str | airport_code |
| year | int | |
| month | int | |
| carrier | str | |
| passengers | int | |
| seats | int | |
| departures_performed | int | |
| distance_miles | float | great-circle distance, used for long-haul bucketing |

### `ontime_delays.csv`
Monthly delay/cancellation stats (BTS On-Time Performance / ASQP). One row per airport per
year-month.

| column | type | notes |
|---|---|---|
| airport_code | str | FK → airports.csv |
| year | int | |
| month | int | |
| flights_total | int | |
| flights_delayed_15 | int | flights delayed 15+ min |
| avg_delay_min | float | |
| pct_delay_nas | float | 0-1, share of delay-minutes attributed to NAS/volume causes |
| pct_delay_weather | float | 0-1 |
| pct_delay_carrier | float | 0-1 |
| pct_delay_late_aircraft | float | 0-1 |

### `capacity_profiles.csv`
Hourly runway throughput capacity. **Not API-sourced** — FAA Capacity Profiles are PDF-only
documents; this file is manually transcribed for ~15-20 major airports. This is a deliberate,
explicitly-flagged deviation from "use public APIs" (see `CLAUDE.md` Data Sources section) — call
it out in the design doc.

| column | type | notes |
|---|---|---|
| airport_code | str | FK → airports.csv |
| vmc_hourly_capacity | int | operations/hour under visual conditions |
| imc_hourly_capacity | int | operations/hour under instrument conditions |
| source | str | `"faa_profile_approx"` (representative/approximate figures, hand-transcribed from public knowledge rather than verified line-by-line against each airport's current official PDF — see `data/processed/README.md`). Airports missing from this file entirely get the runway-count proxy at scoring time (see below); that proxy's confidence label is `"estimated"`, set by the scoring engine, not this file. |

## 2. Scoring engine (`scoring/`)

Implements the methodology in `CLAUDE.md`'s "Scoring Methodology" section. Pure functions/classes
over the processed CSVs — no I/O side effects beyond reading `data/processed/`.

### Models (`scoring/schemas.py`, pydantic)

```python
class KPIResult(BaseModel):
    name: str                       # "capacity_utilization" | "traffic_growth" | "delay_burden" | "load_factor"
    raw_value: float | None         # the underlying metric, e.g. 0.92 for 92% utilization; None if unavailable
    normalized_0_100: float | None  # percentile rank within the comparison set; None if unavailable
    weight: float                   # 0.35 / 0.25 / 0.25 / 0.15 respectively
    confidence: Literal["actual", "estimated", "unavailable"]
    source: str                     # e.g. "FAA ATADS + FAA Capacity Profile", or "estimated via runway count proxy"
    as_of: str                      # data vintage, e.g. "2025-12" or the max year-month covered

class ScoreBreakdown(BaseModel):
    airport_code: str
    composite_score: float | None   # None only if every KPI is unavailable
    kpis: dict[str, KPIResult]      # keyed by KPIResult.name

class LongHaulShare(BaseModel):
    airport_code: str
    threshold_miles: float          # default 2400
    pct_long_haul_flights: float
    pct_long_haul_seats: float
    as_of: str
```

### Functions (`scoring/kpis.py`, `scoring/composite.py`)

- `compute_capacity_utilization(airport_code: str) -> KPIResult`
- `compute_traffic_growth(airport_code: str) -> KPIResult`
- `compute_delay_burden(airport_code: str) -> KPIResult`
- `compute_load_factor(airport_code: str) -> KPIResult`
- `compute_composite_score(airport_codes: list[str]) -> dict[str, ScoreBreakdown]` — normalizes
  each KPI via percentile rank **within this specific airport_codes set**, applies the 0.35 /
  0.25 / 0.25 / 0.15 weights, reweights across only the available (non-`unavailable`) KPIs per
  airport per the missing-data policy in `CLAUDE.md`.
- `compute_long_haul_share(airport_code: str, threshold_miles: float = 2400) -> LongHaulShare`

Capacity Utilization fallback: if `airport_code` has no row in `capacity_profiles.csv`, compute a
proxy from `runway_count`/`longest_runway_ft` in `airports.csv`, and set `confidence="estimated"`,
`source="estimated via runway count proxy"`.

## 3. Backend API (`backend/`)

FastAPI app. Tools wrap the `scoring/` functions exactly (not reimplement them) — the LLM must
call these tools to get any number, per the grounding rule in `CLAUDE.md`.

### `POST /api/chat`
Request:
```json
{"message": "string", "conversation_id": "string | null"}
```
Response:
```json
{
  "reply": "string",
  "conversation_id": "string",
  "breakdown": [ /* ScoreBreakdown or LongHaulShare objects relevant to this answer, or [] */ ]
}
```

### `GET /api/airports`
Response: array of `airports.csv` rows as JSON (for the frontend's airport picker/autocomplete).

## 4. Frontend (`frontend/`)

React app calling the two endpoints above. Chat thread renders `reply`; whenever `breakdown` is
non-empty, render a collapsible panel per airport showing each KPI's `raw_value`, `weight`,
`normalized_0_100`, and a visual badge distinguishing `confidence: "actual"` vs `"estimated"` vs
`"unavailable"`, plus the `composite_score` and `as_of` date.
