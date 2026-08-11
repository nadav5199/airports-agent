# scoring/

Deterministic scoring engine for the Airport Investment Intelligence Agent.
Implements the KPI formulas and weights from the "Scoring Methodology" section
of the root `CLAUDE.md`, per the interface in `docs/contracts.md`. Pure
functions over the processed CSVs in `data/processed/` -- no network calls, no
LLM calls, no database. `backend/` (built by the next agent) is expected to
import these functions directly and expose them as LLM tool calls, not
reimplement the logic.

## Module layout

- **`schemas.py`** -- pydantic models: `KPIResult`, `ScoreBreakdown`,
  `LongHaulShare`. Matches `docs/contracts.md` field-for-field.
- **`data_loader.py`** -- loads the five `data/processed/*.csv` files once
  (module-level `lru_cache`) and exposes small helpers (`get_airport_row`,
  `year_month_str`). Everything else in this package reads data through here,
  never via a raw `pd.read_csv` scattered elsewhere.
- **`kpis.py`** -- one function per KPI, each airport-scoped:
  - `compute_capacity_utilization(airport_code)`
  - `compute_traffic_growth(airport_code)`
  - `compute_delay_burden(airport_code)`
  - `compute_load_factor(airport_code)`
  - `compute_long_haul_share(airport_code, threshold_miles=2400)` -- standalone
    descriptive stat, not part of the composite score.
- **`composite.py`** -- `compute_composite_score(airport_codes)`: percentile-
  rank normalizes each KPI **within the given airport_codes set**, applies the
  0.35 / 0.25 / 0.25 / 0.15 weights, and reweights across only the
  non-`unavailable` KPIs per airport.
- **`tests/`** -- pytest, run against the real merged `data/processed/*.csv`
  (no mocks/fixtures standing in for the data).

## Key design decisions (read before changing formulas)

- **`confidence` vs data honesty.** `confidence` (`actual` / `estimated` /
  `unavailable`) describes the *method*: did we use the primary formula, a
  documented fallback/proxy, or nothing at all. Separately, every `source`
  string discloses whether the underlying `data/processed/*.csv` content
  itself is real, synthetic-fallback, or hand-transcribed-approximate, per
  `data/processed/README.md`. A KPI can be `confidence="actual"` (full
  primary-formula computation) while its `source` honestly notes the input
  file is synthetic -- these are two different axes of "how much should you
  trust this number," both surfaced, neither hidden.
- **Capacity Utilization peak-hour estimate.** `operations.csv` only has
  monthly totals (FAA ATADS has no free hourly-granularity product), so peak
  hourly ops are estimated as `(monthly_total / days_in_month) * 8%`, an
  explicit documented planning-style assumption (see `PEAK_HOUR_SHARE_OF_DAY`
  in `kpis.py`), not a measured figure.
- **Capacity Utilization proxy fallback.** Airports missing from
  `capacity_profiles.csv` (only ~20 major airports have one) get an hourly
  capacity estimate from `runway_count` / `longest_runway_ft` in
  `airports.csv`, tiered by runway length with diminishing returns for
  additional runways. Always `confidence="estimated"`.
- **Traffic Growth CAGR.** With the full 24-month dataset (true for all 62
  airports as shipped), this is a trailing-12 vs leading-12 month sum ratio
  (`confidence="actual"`). The function also handles shorter histories
  gracefully (12-23 months, or 2-11 months) by annualizing a first-vs-last-
  month comparison and downgrading to `confidence="estimated"` with a note
  that the window is short/noisy -- and returns `unavailable` (not a crash or
  a fabricated 0) for fewer than 2 months of history.
- **Delay Burden.** `flights_delayed_15 / flights_total`, scaled toward the
  flights-weighted NAS/volume-attributed delay-minute share (`pct_delay_nas`)
  per CLAUDE.md's "weighted toward volume/NAS-attributed causes" instruction --
  see `_NAS_FLOOR` in `kpis.py` for the exact blend. Real BTS data only covers
  Apr-May 2026 for 50 of 62 in-scope airports; the other 12 (small New England
  fields with no reporting-carrier service in that window) come back
  `confidence="unavailable"`, never a fabricated 0. Very thin samples (<20
  flights total) are downgraded to `confidence="estimated"`.
- **Load Factor.** Seat-weighted `passengers / seats` over the trailing up-to-
  12 months of `t100_routes.csv` rows with this airport as origin (smooths
  single-month/single-route noise). `seats`/`passengers` are synthetic
  fallback data; `distance_miles` (used only by long-haul share, not this KPI)
  is real.
- **Long-haul share.** Computed directly from `distance_miles` in
  `t100_routes.csv`, which is real (great-circle distance from real airport
  lat/lon) even though other columns on that file are synthetic. "Flights" is
  approximated by `departures_performed` (T-100 is route/segment-level, not
  individual-flight-level). Raises `ValueError` for an airport with zero
  T-100 rows rather than returning a fabricated 0% -- every field on
  `LongHaulShare` is non-optional per `docs/contracts.md`, so there's no
  "unavailable" state to return; the caller is expected to catch this for an
  unknown airport code.
- **Composite reweighting.** For each airport, `composite_score` is the
  weight-normalized average of only the KPIs with `confidence != "unavailable"`
  and a non-`None` normalized score:
  `sum(normalized_i * weight_i) / sum(weight_i)` over available `i`. It's
  `None` only when every KPI is unavailable for that airport -- never silently
  defaulted to 0 or computed with a missing KPI treated as 0.
- **Percentile rank is set-relative, by design.** `compute_composite_score`
  normalizes each KPI via `pandas.Series.rank(pct=True)` computed only across
  the `airport_codes` passed in that call -- not a fixed global population.
  Calling it with a 2-airport comparison set vs. a whole-region set will (and
  should) produce different `normalized_0_100` values for the same airport.

## Running the tests

```
pip install -r requirements.txt
python -m pytest scoring/tests -v
```

Tests run against the real merged `data/processed/*.csv` files (no mocking),
using airports known ahead of time to exercise specific paths, e.g.:
- SFO (has an FAA Capacity Profile, known-congested major hub) vs. ACK
  (small New England regional airport, no capacity profile -> proxy fallback)
  for the "congested hub scores higher" capacity-utilization check.
- HYA (zero rows in `ontime_delays.csv`) for the missing-data /
  `unavailable`-confidence / reweighting-without-crashing checks.
- ANC for the long-haul share sanity check (`CLAUDE.md`'s example query).
- MVY (short-hop-only route set) for a 0% long-haul share check.
- `ZZZ` (not a real airport code) across every function, to confirm unknown
  airports come back `unavailable`/raise cleanly instead of crashing.

As of this writing: 19 tests, all passing.
