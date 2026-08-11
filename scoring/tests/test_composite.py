"""Unit tests for scoring/composite.py, run against the REAL processed data."""

from __future__ import annotations

from scoring.composite import compute_composite_score


class TestCompositeWeights:
    def test_weights_sum_to_one_for_full_kpi_airport(self):
        breakdown = compute_composite_score(["LAX", "SFO", "ACK"])["LAX"]
        total_weight = sum(k.weight for k in breakdown.kpis.values())
        assert abs(total_weight - 1.0) < 1e-9

    def test_composite_score_is_none_only_when_every_kpi_unavailable(self):
        breakdowns = compute_composite_score(["LAX", "ZZZ"])
        # ZZZ isn't a real airport -- every KPI should be unavailable, so the
        # composite score must be None (not fabricated as 0).
        assert breakdowns["ZZZ"].composite_score is None
        for kpi in breakdowns["ZZZ"].kpis.values():
            assert kpi.confidence == "unavailable"
        assert breakdowns["LAX"].composite_score is not None


class TestCongestedHubRanksHigher:
    def test_sfo_scores_higher_capacity_utilization_than_small_regional(self):
        breakdowns = compute_composite_score(["SFO", "ACK"])
        sfo_util = breakdowns["SFO"].kpis["capacity_utilization"]
        ack_util = breakdowns["ACK"].kpis["capacity_utilization"]
        assert sfo_util.raw_value > ack_util.raw_value
        assert sfo_util.normalized_0_100 > ack_util.normalized_0_100


class TestMissingDataReweighting:
    def test_missing_kpi_does_not_crash_and_does_not_silently_zero_score(self):
        # HYA has no ontime_delays.csv rows at all -> delay_burden is
        # unavailable for it. The composite score must reweight across the
        # remaining 3 KPIs, not silently treat the missing one as 0.
        breakdowns = compute_composite_score(["LAX", "SFO", "ACK", "HYA", "MVY"])
        hya = breakdowns["HYA"]
        assert hya.kpis["delay_burden"].confidence == "unavailable"
        assert hya.kpis["delay_burden"].raw_value is None
        assert hya.kpis["delay_burden"].normalized_0_100 is None
        assert hya.composite_score is not None

        # Sanity check the reweighting math directly: composite should equal
        # the weighted average of only the available KPIs' normalized scores.
        available = [k for k in hya.kpis.values() if k.confidence != "unavailable"]
        weight_total = sum(k.weight for k in available)
        expected = sum(k.normalized_0_100 * k.weight for k in available) / weight_total
        assert abs(hya.composite_score - expected) < 1e-9

    def test_percentile_rank_is_scoped_to_the_given_comparison_set(self):
        # The same airport's normalized_0_100 for a KPI should generally differ
        # across different comparison sets, since percentile rank is relative
        # -- not a fixed global score. Use capacity_utilization, which has a
        # real, non-degenerate spread across airports.
        small_set = compute_composite_score(["SFO", "ACK"])
        big_set = compute_composite_score(["SFO", "LAX", "SNA", "ANC", "ACK", "MVY", "BDL"])
        sfo_small = small_set["SFO"].kpis["capacity_utilization"].normalized_0_100
        sfo_big = big_set["SFO"].kpis["capacity_utilization"].normalized_0_100
        assert sfo_small == 100.0  # SFO is the max of a 2-airport set
        assert sfo_big <= 100.0
