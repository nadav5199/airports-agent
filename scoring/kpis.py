"""Per-airport KPI computations. See CLAUDE.md "Scoring Methodology" for the
formulas/weights and docs/contracts.md for the function signatures this module
implements.

Every function here is a pure read of data/processed/*.csv (via scoring.data_loader)
-- no LLM calls, no side effects. Each returns a scoring.schemas.KPIResult with:
  - raw_value: the underlying metric, or None if it truly can't be computed
  - confidence: "actual" (computed from the primary formula/data), "estimated"
    (a documented fallback/proxy was used, or the input window is short/noisy),
    or "unavailable" (no usable data at all -- never silently defaulted to 0)
  - source: cites which processed file(s) fed the number AND discloses whether the
    underlying data/processed/*.csv content is real, synthetic-fallback, or
    hand-transcribed-approximate, per data/processed/README.md. This is separate
    from `confidence`, which is about the *method*, not the underlying data's
    real/synthetic status -- see scoring/README.md for the distinction.

`normalized_0_100` is intentionally left None here -- percentile-rank normalization
only makes sense across a comparison set, so it's filled in by
scoring.composite.compute_composite_score, not by these single-airport functions.
"""

from __future__ import annotations

import calendar

from scoring import data_loader as dl
from scoring.schemas import KPIResult, LongHaulShare

# ---------------------------------------------------------------------------
# Capacity Utilization (weight 0.35)
# ---------------------------------------------------------------------------
# CLAUDE.md formula: "peak-period operations / FAA hourly runway capacity".
# operations.csv only has *monthly* totals (no hourly breakdown -- FAA ATADS
# doesn't expose intraday granularity in the free bulk product), so we estimate
# a representative peak hour from the monthly total:
#   avg_daily_ops   = operations_total / days_in_month
#   peak_hour_ops   = avg_daily_ops * PEAK_HOUR_SHARE_OF_DAY
# PEAK_HOUR_SHARE_OF_DAY (8%) is a documented planning-style rule of thumb: a
# single busy hour typically carries a disproportionate share of a day's
# operations at a scheduled-service airport (FAA planning literature commonly
# cites peak hour shares in the 7-10% range). This is an explicit modeling
# assumption, not a measured figure -- flagged in the docstring/README, not
# hidden.
PEAK_HOUR_SHARE_OF_DAY = 0.08

# Runway-count/length proxy for airports missing from capacity_profiles.csv.
# Tiered by longest_runway_ft (longer runway -> can host larger/faster aircraft
# -> higher per-runway hourly throughput), with diminishing returns per extra
# runway (parallel/crossing runways are rarely fully independent).
_RUNWAY_CAPACITY_TIERS = (
    (10000.0, 45),  # long-haul capable (large hub) runways
    (7000.0, 30),  # mid-size jet runways
    (5000.0, 18),  # regional jet / small commercial runways
    (0.0, 10),  # short/general-aviation-grade runways
)
_EXTRA_RUNWAY_EFFICIENCY = 0.6  # each additional runway adds 60% of one runway's capacity


def _proxy_hourly_capacity(runway_count: int, longest_runway_ft: float) -> float:
    per_runway = _RUNWAY_CAPACITY_TIERS[-1][1]
    for min_ft, cap in _RUNWAY_CAPACITY_TIERS:
        if longest_runway_ft >= min_ft:
            per_runway = cap
            break
    runway_count = max(1, int(runway_count or 1))
    effective_runways = 1 + _EXTRA_RUNWAY_EFFICIENCY * (runway_count - 1)
    return per_runway * effective_runways


def compute_capacity_utilization(airport_code: str) -> KPIResult:
    name = "capacity_utilization"
    weight = 0.35
    ops = dl.load_operations()
    airport_ops = ops[ops["airport_code"] == airport_code]
    if airport_ops.empty:
        return KPIResult(
            name=name,
            raw_value=None,
            normalized_0_100=None,
            weight=weight,
            confidence="unavailable",
            source="No FAA ATADS operations rows for this airport in operations.csv",
            as_of="n/a",
        )

    latest = airport_ops.sort_values(["year", "month"]).iloc[-1]
    year, month = int(latest["year"]), int(latest["month"])
    days_in_month = calendar.monthrange(year, month)[1]
    avg_daily_ops = latest["operations_total"] / days_in_month
    peak_hour_ops = avg_daily_ops * PEAK_HOUR_SHARE_OF_DAY
    as_of = dl.year_month_str(year, month)

    cap_profiles = dl.load_capacity_profiles()
    profile = cap_profiles[cap_profiles["airport_code"] == airport_code]

    if not profile.empty:
        vmc_capacity = float(profile.iloc[0]["vmc_hourly_capacity"])
        raw_value = peak_hour_ops / vmc_capacity if vmc_capacity else None
        return KPIResult(
            name=name,
            raw_value=raw_value,
            normalized_0_100=None,
            weight=weight,
            confidence="actual",
            source=(
                "FAA ATADS operations (synthetic fallback data, monthly total "
                f"scaled by an assumed {PEAK_HOUR_SHARE_OF_DAY:.0%} peak-hour share of "
                "daily traffic) / FAA Capacity Profile VMC hourly capacity "
                "(hand-transcribed, approximate -- source='faa_profile_approx' "
                "in capacity_profiles.csv). See data/processed/README.md."
            ),
            as_of=as_of,
        )

    # Fallback proxy: no FAA capacity profile for this airport.
    airport_row = dl.get_airport_row(airport_code)
    if airport_row is None:
        return KPIResult(
            name=name,
            raw_value=None,
            normalized_0_100=None,
            weight=weight,
            confidence="unavailable",
            source="Airport not found in airports.csv; cannot build runway-count proxy",
            as_of=as_of,
        )
    proxy_capacity = _proxy_hourly_capacity(
        int(airport_row["runway_count"]), float(airport_row["longest_runway_ft"])
    )
    raw_value = peak_hour_ops / proxy_capacity if proxy_capacity else None
    return KPIResult(
        name=name,
        raw_value=raw_value,
        normalized_0_100=None,
        weight=weight,
        confidence="estimated",
        source=(
            "estimated via runway count proxy: FAA ATADS operations (synthetic "
            f"fallback data, scaled by assumed {PEAK_HOUR_SHARE_OF_DAY:.0%} peak-hour "
            "share) / a runway-count and runway-length based hourly capacity estimate "
            "(no FAA Capacity Profile exists for this airport)."
        ),
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Traffic Growth Rate (weight 0.25)
# ---------------------------------------------------------------------------
# CLAUDE.md formula: "multi-year CAGR of operations and/or passengers". The
# processed dataset covers 24 months (2024-06 .. 2026-05) for every airport, so
# in practice every airport hits the >=24-month branch below. The shorter-window
# branches exist so the function degrades gracefully (never crashes) if the
# dataset is ever regenerated with less history.


def compute_traffic_growth(airport_code: str) -> KPIResult:
    name = "traffic_growth"
    weight = 0.25
    ops = dl.load_operations()
    airport_ops = ops[ops["airport_code"] == airport_code].sort_values(["year", "month"])
    n = len(airport_ops)
    source_base = "FAA ATADS operations (synthetic fallback data, see data/processed/README.md)"

    if n < 2:
        return KPIResult(
            name=name,
            raw_value=None,
            normalized_0_100=None,
            weight=weight,
            confidence="unavailable",
            source=f"{source_base}; fewer than 2 months of history, cannot compute growth",
            as_of="n/a",
        )

    latest = airport_ops.iloc[-1]
    as_of = dl.year_month_str(int(latest["year"]), int(latest["month"]))

    if n >= 24:
        # Non-overlapping trailing-12 vs leading-12 month windows -- centers are
        # ~1 year apart, so the ratio is directly a 1-year CAGR.
        first12 = airport_ops.iloc[:12]["operations_total"].sum()
        last12 = airport_ops.iloc[-12:]["operations_total"].sum()
        if first12 <= 0:
            growth_rate = None
        else:
            growth_rate = (last12 / first12) - 1.0
        confidence = "actual"
        note = "12-month trailing window vs 12-month leading window, annualized"
    elif n >= 12:
        first_val = airport_ops.iloc[0]["operations_total"]
        last_val = airport_ops.iloc[-1]["operations_total"]
        months_span = n - 1
        growth_rate = None
        if first_val > 0 and months_span > 0:
            growth_rate = (last_val / first_val) ** (12.0 / months_span) - 1.0
        confidence = "estimated"
        note = (
            f"only {n} months of history available (< 24-month full window); "
            "annualized first-vs-last-month comparison, treat as noisy"
        )
    else:  # 2 <= n < 12
        first_val = airport_ops.iloc[0]["operations_total"]
        last_val = airport_ops.iloc[-1]["operations_total"]
        months_span = n - 1
        growth_rate = None
        if first_val > 0 and months_span > 0:
            growth_rate = (last_val / first_val) ** (12.0 / months_span) - 1.0
        confidence = "estimated"
        note = (
            f"only {n} months of history available -- CAGR over a window this short "
            "is unreliable, treat as a rough directional signal only"
        )

    return KPIResult(
        name=name,
        raw_value=growth_rate,
        normalized_0_100=None,
        weight=weight,
        confidence=confidence if growth_rate is not None else "unavailable",
        source=f"{source_base}; {note}",
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Delay Burden (weight 0.25)
# ---------------------------------------------------------------------------
# CLAUDE.md: "% flights delayed 15+ min and/or avg delay minutes, weighted
# toward volume/NAS-attributed causes". We compute the flights-delayed-15 rate
# and scale it toward NAS-attributed causes, since NAS delay is the closest BTS
# proxy for capacity/volume-driven congestion (vs weather or carrier-caused
# delay, which don't indicate an airport is capacity-constrained):
#   raw_value = pct_delayed_15 * (NAS_FLOOR + (1 - NAS_FLOOR) * pct_delay_nas)
# NAS_FLOOR (0.3) keeps the metric from going to ~0 for airports whose delays
# are real but mostly attributed to other causes -- it's a delay-*burden*
# metric, not purely a volume-attribution metric, so NAS share modulates rather
# than gates it.
_NAS_FLOOR = 0.3
_THIN_SAMPLE_FLIGHTS = 20  # below this many flights, the rate is statistically noisy


def compute_delay_burden(airport_code: str) -> KPIResult:
    name = "delay_burden"
    weight = 0.25
    delays = dl.load_ontime_delays()
    airport_delays = delays[delays["airport_code"] == airport_code].sort_values(
        ["year", "month"]
    )

    if airport_delays.empty:
        return KPIResult(
            name=name,
            raw_value=None,
            normalized_0_100=None,
            weight=weight,
            confidence="unavailable",
            source=(
                "No BTS On-Time Performance rows for this airport (real data covers "
                "only Apr-May 2026, 50 of 62 in-scope airports -- see "
                "data/processed/README.md); likely a small airport with no "
                "reporting-carrier service in that window"
            ),
            as_of="n/a",
        )

    total_flights = airport_delays["flights_total"].sum()
    total_delayed15 = airport_delays["flights_delayed_15"].sum()
    # flights_total-weighted average of pct_delay_nas across available months
    weighted_nas = (
        airport_delays["pct_delay_nas"] * airport_delays["flights_total"]
    ).sum() / total_flights if total_flights else 0.0

    pct_delayed15 = total_delayed15 / total_flights if total_flights else None
    raw_value = None
    if pct_delayed15 is not None:
        raw_value = pct_delayed15 * (_NAS_FLOOR + (1 - _NAS_FLOOR) * weighted_nas)

    months = sorted(
        {
            dl.year_month_str(int(r.year), int(r.month))
            for r in airport_delays.itertuples()
        }
    )
    as_of = months[-1] if months else "n/a"

    confidence = "actual"
    sample_note = ""
    if total_flights < _THIN_SAMPLE_FLIGHTS:
        confidence = "estimated"
        sample_note = f"; thin sample ({int(total_flights)} flights), treat as approximate"

    return KPIResult(
        name=name,
        raw_value=raw_value,
        normalized_0_100=None,
        weight=weight,
        confidence=confidence,
        source=(
            "BTS On-Time Performance real extract, months="
            f"{months}{sample_note} (see data/processed/README.md); rate of flights "
            "delayed 15+ min, scaled toward the flights_total-weighted NAS/volume-"
            "attributed delay-minute share"
        ),
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Long-haul share (standalone descriptive stat, not part of the composite score)
# ---------------------------------------------------------------------------
# CLAUDE.md: "% of flights or seats with great-circle distance over the
# industry-standard long-haul threshold (~2,100+ nm / ~2,400+ statute miles)".
# distance_miles in t100_routes.csv is REAL (computed from real airport lat/lon)
# even though seats/passengers/departures on that file are synthetic -- see
# data/processed/README.md. "Flights" is approximated by departures_performed
# (t100 is route/segment-level, not individual-flight-level).


def compute_long_haul_share(
    airport_code: str, threshold_miles: float = 2400.0
) -> LongHaulShare:
    t100 = dl.load_t100_routes()
    airport_routes = t100[t100["origin"] == airport_code]
    if airport_routes.empty:
        raise ValueError(
            f"No T-100 route rows with origin={airport_code!r}; cannot compute "
            "long-haul share for this airport"
        )

    is_long_haul = airport_routes["distance_miles"] >= threshold_miles
    total_departures = airport_routes["departures_performed"].sum()
    total_seats = airport_routes["seats"].sum()
    long_haul_departures = airport_routes.loc[is_long_haul, "departures_performed"].sum()
    long_haul_seats = airport_routes.loc[is_long_haul, "seats"].sum()

    pct_long_haul_flights = (
        long_haul_departures / total_departures if total_departures else 0.0
    )
    pct_long_haul_seats = long_haul_seats / total_seats if total_seats else 0.0

    year_months = airport_routes[["year", "month"]].drop_duplicates()
    latest = year_months.sort_values(["year", "month"]).iloc[-1]
    as_of = dl.year_month_str(int(latest["year"]), int(latest["month"]))

    return LongHaulShare(
        airport_code=airport_code,
        threshold_miles=threshold_miles,
        pct_long_haul_flights=float(pct_long_haul_flights),
        pct_long_haul_seats=float(pct_long_haul_seats),
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Passenger/Seat Load Factor (weight 0.15)
# ---------------------------------------------------------------------------
# CLAUDE.md formula: "passengers / seats". Aggregated over the most recent up-
# to-12 months of t100_routes.csv for this airport as origin, weighted by seats
# (i.e. total passengers / total seats across those months+routes), to smooth
# out single-month/single-route noise.


def compute_load_factor(airport_code: str) -> KPIResult:
    name = "load_factor"
    weight = 0.15
    t100 = dl.load_t100_routes()
    airport_routes = t100[t100["origin"] == airport_code]

    if airport_routes.empty:
        return KPIResult(
            name=name,
            raw_value=None,
            normalized_0_100=None,
            weight=weight,
            confidence="unavailable",
            source="No T-100 route rows with this airport as origin in t100_routes.csv",
            as_of="n/a",
        )

    year_months = sorted(
        airport_routes[["year", "month"]].drop_duplicates().itertuples(index=False),
        key=lambda ym: (ym.year, ym.month),
    )
    recent_year_months = set(year_months[-12:])
    ym_pairs = list(zip(airport_routes["year"], airport_routes["month"]))
    recent = airport_routes[[ym in recent_year_months for ym in ym_pairs]]

    total_seats = recent["seats"].sum()
    total_passengers = recent["passengers"].sum()
    raw_value = total_passengers / total_seats if total_seats else None
    last_ym = year_months[-1]
    as_of = dl.year_month_str(last_ym.year, last_ym.month)
    window_note = f"trailing {len(recent_year_months)} month(s)"

    return KPIResult(
        name=name,
        raw_value=raw_value,
        normalized_0_100=None,
        weight=weight,
        confidence="actual" if raw_value is not None else "unavailable",
        source=(
            "BTS T-100 (synthetic fallback passengers/seats volumes; distance_miles "
            f"is real -- see data/processed/README.md), {window_note}, seat-weighted "
            "passengers / seats across routes originating at this airport"
        ),
        as_of=as_of,
    )
