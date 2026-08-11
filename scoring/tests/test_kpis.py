"""Unit tests for scoring/kpis.py, run against the REAL processed data in
data/processed/ -- not mocks. Run with: pytest scoring/tests -v
"""

from __future__ import annotations

from scoring.kpis import (
    compute_capacity_utilization,
    compute_delay_burden,
    compute_load_factor,
    compute_long_haul_share,
    compute_traffic_growth,
)


class TestCapacityUtilization:
    def test_congested_hub_scores_higher_than_small_regional_airport(self):
        # SFO has a real FAA Capacity Profile row and is a well-known congested
        # major hub; ACK is a tiny New England regional airport with no
        # capacity profile (falls back to the runway-count proxy).
        sfo = compute_capacity_utilization("SFO")
        ack = compute_capacity_utilization("ACK")
        assert sfo.raw_value is not None
        assert ack.raw_value is not None
        assert sfo.raw_value > ack.raw_value
        assert sfo.confidence == "actual"
        assert ack.confidence == "estimated"

    def test_airport_with_capacity_profile_is_actual_confidence(self):
        result = compute_capacity_utilization("LAX")
        assert result.confidence == "actual"
        assert "Capacity Profile" in result.source

    def test_airport_without_capacity_profile_falls_back_to_proxy(self):
        # MVY (Martha's Vineyard) has no row in capacity_profiles.csv.
        result = compute_capacity_utilization("MVY")
        assert result.confidence == "estimated"
        assert "proxy" in result.source
        assert result.raw_value is not None

    def test_unknown_airport_is_unavailable_not_crash(self):
        result = compute_capacity_utilization("ZZZ")
        assert result.confidence == "unavailable"
        assert result.raw_value is None


class TestTrafficGrowth:
    def test_full_history_airport_is_actual_confidence(self):
        result = compute_traffic_growth("LAX")
        assert result.confidence == "actual"
        assert result.raw_value is not None
        assert isinstance(result.raw_value, float)

    def test_unknown_airport_is_unavailable_not_crash(self):
        result = compute_traffic_growth("ZZZ")
        assert result.confidence == "unavailable"
        assert result.raw_value is None


class TestDelayBurden:
    def test_airport_with_real_delay_data_is_computable(self):
        result = compute_delay_burden("LAX")
        assert result.raw_value is not None
        assert result.confidence in ("actual", "estimated")
        assert 0.0 <= result.raw_value <= 1.0

    def test_airport_with_no_ontime_rows_is_unavailable_not_crash(self):
        # HYA has zero rows in ontime_delays.csv (real BTS extract only covers
        # 50 of the 62 in-scope airports for Apr-May 2026).
        result = compute_delay_burden("HYA")
        assert result.confidence == "unavailable"
        assert result.raw_value is None

    def test_unknown_airport_does_not_crash(self):
        result = compute_delay_burden("ZZZ")
        assert result.confidence == "unavailable"


class TestLoadFactor:
    def test_load_factor_is_a_plausible_fraction(self):
        result = compute_load_factor("LAX")
        assert result.raw_value is not None
        assert 0.0 < result.raw_value <= 1.0

    def test_unknown_airport_does_not_crash(self):
        result = compute_load_factor("ZZZ")
        assert result.confidence == "unavailable"
        assert result.raw_value is None


class TestLongHaulShare:
    def test_anc_long_haul_share_is_sane_percentage(self):
        result = compute_long_haul_share("ANC")
        assert result.airport_code == "ANC"
        assert 0.0 <= result.pct_long_haul_flights <= 1.0
        assert 0.0 <= result.pct_long_haul_seats <= 1.0
        print(
            f"ANC long-haul share: {result.pct_long_haul_flights:.1%} of flights, "
            f"{result.pct_long_haul_seats:.1%} of seats (threshold "
            f"{result.threshold_miles} mi, as of {result.as_of})"
        )

    def test_short_hop_only_airport_has_zero_long_haul_share(self):
        # MVY (Martha's Vineyard) only connects to nearby New England
        # airports/islands in the generated route set, so nothing clears a
        # 2400-mile threshold.
        result = compute_long_haul_share("MVY")
        assert result.pct_long_haul_flights == 0.0
        assert result.pct_long_haul_seats == 0.0

    def test_unknown_airport_raises_instead_of_returning_fabricated_data(self):
        import pytest

        with pytest.raises(ValueError):
            compute_long_haul_share("ZZZ")
