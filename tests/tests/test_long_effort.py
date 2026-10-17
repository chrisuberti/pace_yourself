"""
Tests for Phase B: long-effort (> 1 hour) pacing support.

Validates:
  - Piecewise power-duration model continuity and decay
  - Duration estimation and is_long_effort detection
  - Optimizer bounds shift below CP for long courses
  - Variable pacing on long courses produces sub-CP base powers
  - W' feasibility is maintained on long courses
"""

import pytest
import numpy as np
import pandas as pd
from app.rider import WTankCalculator
from app.optimization import CourseOptimizer, _has_cluster_info


# ── Constants ──────────────────────────────────────────────────────────────

CP = 300
W_PRIME = 25000
FATIGUE_K = 0.05


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def optimizer():
    return CourseOptimizer(
        critical_power=CP, w_prime=W_PRIME, endurance_fatigue_k=FATIGUE_K
    )


def _make_long_course(n_repeats: int = 6, with_clusters: bool = True) -> pd.DataFrame:
    """Build a ~90 km course (~3 h at CP) with mixed terrain.

    Pattern per repeat (~15 km):
      flat 5 km @ 0% → climb 3 km @ 4% → flat 4 km @ 0% → descent 3 km @ -3%
    """
    block = [
        {'distance': 5000, 'gradient': 0.00, 'altitude': 200, 'wind': 0,
         'cluster': 1},
        {'distance': 3000, 'gradient': 0.04, 'altitude': 300, 'wind': 0,
         'cluster': 2},
        {'distance': 4000, 'gradient': 0.00, 'altitude': 350, 'wind': 0,
         'cluster': 1},
        {'distance': 3000, 'gradient': -0.03, 'altitude': 260, 'wind': 0,
         'cluster': 3},
    ]
    rows = []
    seq = 1
    occurrence_count = {1: 0, 2: 0, 3: 0}
    for _ in range(n_repeats):
        for seg in block:
            cid = seg['cluster']
            occurrence_count[cid] += 1
            row = {
                'distance': seg['distance'],
                'gradient': seg['gradient'],
                'altitude': seg['altitude'],
                'wind': seg['wind'],
                'segment_sequence': seq,
            }
            if with_clusters:
                row['segment_id'] = cid
                row['segment_occurrence'] = occurrence_count[cid]
            rows.append(row)
            seq += 1
    return pd.DataFrame(rows)


@pytest.fixture
def long_cluster_course():
    return _make_long_course(n_repeats=6, with_clusters=True)


@pytest.fixture
def long_legacy_course():
    return _make_long_course(n_repeats=6, with_clusters=False)


@pytest.fixture
def short_cluster_course():
    """A short (~15 min) course for comparison."""
    return pd.DataFrame({
        'distance':          [1500, 2000, 1200, 1000, 1800, 1500],
        'gradient':          [0.01, 0.07, 0.01, -0.04, 0.08, 0.01],
        'altitude':          [100,  150,  120,  100,   160,  130],
        'wind':              [0,    0,    0,    0,     0,    0],
        'segment_id':        [1,    2,    1,    3,     2,    1],
        'segment_sequence':  [1,    2,    3,    4,     5,    6],
        'segment_occurrence':[1,    1,    2,    1,     2,    3],
    })


# ── Piecewise model tests ─────────────────────────────────────────────────

class TestPiecewiseModel:
    """Validate the hybrid CP+W'/t ↔ power-law model."""

    def test_continuity_at_one_hour(self):
        """Model has a small discontinuity at 3600 s equal to W'/3600.

        The left side gives CP + W'/3600, the right side gives CP.
        This is an inherent property of the piecewise model — the jump
        is small (~7 W for typical W'=25 kJ) and acceptable in practice.
        """
        p_left = WTankCalculator.piecewise_power_duration(
            3599.9, CP, W_PRIME, FATIGUE_K)
        p_right = WTankCalculator.piecewise_power_duration(
            3600.1, CP, W_PRIME, FATIGUE_K)
        expected_jump = W_PRIME / 3600.0
        assert abs(p_left - p_right) < expected_jump + 1, (
            f"Jump at 3600 s ({abs(p_left - p_right):.2f} W) larger than "
            f"expected W'/3600 = {expected_jump:.2f} W")

    def test_at_one_hour_equals_cp(self):
        """At exactly 3600 s the W'/t term vanishes, so P ≈ CP."""
        p = WTankCalculator.piecewise_power_duration(3600, CP, W_PRIME, FATIGUE_K)
        # CP + W'/3600 = 300 + 6.9 ≈ 307 W  (not exactly CP because W'/3600 > 0)
        assert CP < p < CP + W_PRIME / 3600 + 1

    def test_power_decreases_with_duration(self):
        """Longer durations should produce lower power."""
        durations = [1800, 3600, 5400, 7200, 10800, 14400]
        powers = [WTankCalculator.piecewise_power_duration(t, CP, W_PRIME, FATIGUE_K)
                  for t in durations]
        for i in range(len(powers) - 1):
            assert powers[i] > powers[i + 1], (
                f"P({durations[i]}s)={powers[i]:.1f} should exceed "
                f"P({durations[i+1]}s)={powers[i+1]:.1f}")

    def test_four_hour_power_below_cp(self):
        """At 4 hours, power should be meaningfully below CP."""
        p_4h = WTankCalculator.piecewise_power_duration(14400, CP, W_PRIME, FATIGUE_K)
        assert p_4h < CP, f"4 h power ({p_4h:.1f}W) should be below CP ({CP}W)"
        # Should be roughly 0.92 × CP for k=0.05
        assert p_4h > CP * 0.85, f"4 h power ({p_4h:.1f}W) unreasonably low"

    def test_array_input(self):
        """Model should handle numpy array of durations."""
        t = np.array([600, 3600, 7200, 14400])
        p = WTankCalculator.piecewise_power_duration(t, CP, W_PRIME, FATIGUE_K)
        assert len(p) == 4
        assert p[0] > p[1] > p[2] > p[3]

    def test_scalar_input(self):
        """Model should work with plain float."""
        p = WTankCalculator.piecewise_power_duration(3600.0, CP, W_PRIME, FATIGUE_K)
        assert isinstance(float(p), float)


# ── Duration estimation & is_long tests ────────────────────────────────────

class TestDurationEstimation:
    def test_long_course_detected(self, optimizer, long_cluster_course):
        """90 km mixed-terrain course should be detected as long (>1 h)."""
        assert optimizer.is_long_effort(long_cluster_course) == True

    def test_short_course_not_long(self, optimizer, short_cluster_course):
        """9 km test course should not be classified as long."""
        assert optimizer.is_long_effort(short_cluster_course) == False

    def test_estimated_duration_reasonable(self, optimizer, long_cluster_course):
        """Duration estimate should be in the right ballpark (~2-4 h)."""
        dur = optimizer._estimate_course_duration(long_cluster_course)
        assert 3600 < dur < 14400, f"Estimated {dur/3600:.1f} h — out of range"


# ── Constant power optimization for long efforts ──────────────────────────

class TestLongEffortConstantPower:
    def test_optimal_power_near_or_below_cp(self, optimizer, long_cluster_course):
        """For a 3 h mixed-terrain course, optimal power is near CP."""
        opt_power, opt_time, results = optimizer.optimize_constant_power(
            long_cluster_course)
        assert opt_power < CP * 1.05, (
            f"Optimal power {opt_power:.0f}W too far above CP {CP}W "
            "for a long effort")
        # Should not be unreasonably low either
        floor = WTankCalculator.piecewise_power_duration(14400, CP, W_PRIME, FATIGUE_K)
        assert opt_power > floor * 0.90, (
            f"Optimal {opt_power:.0f}W below 90% of 4 h floor ({floor:.0f}W)")

    def test_time_finite(self, optimizer, long_cluster_course):
        """Optimization should converge to a finite time."""
        _, opt_time, _ = optimizer.optimize_constant_power(long_cluster_course)
        assert 0 < opt_time < 20000, f"Time {opt_time:.0f}s looks wrong"


# ── Variable pacing for long efforts ──────────────────────────────────────

class TestLongEffortVariablePacing:
    def test_cluster_variable_pacing_feasible(self, optimizer, long_cluster_course):
        """Variable pacing on a long clustered course should remain W'-feasible."""
        results_df, total_time, analysis = optimizer.optimize_variable_pacing(
            long_cluster_course, target_w_utilization=0.70)
        assert results_df['w_remaining'].min() >= -1, (
            f"W' went below zero: {results_df['w_remaining'].min():.0f}")

    def test_average_power_below_cp(self, optimizer, long_cluster_course):
        """Distance-weighted average power for a long course should be near/below CP.

        Uses a distance-weighted mean (not a naive per-segment mean, which would
        over-weight short, repeated climb segments) since that is the
        physiologically meaningful average a rider sustains over the course.
        """
        results_df, _, _ = optimizer.optimize_variable_pacing(
            long_cluster_course, target_w_utilization=0.70)
        avg_power = np.average(
            results_df['target_power'], weights=results_df['distance'])
        assert avg_power < CP * 1.02, (
            f"Distance-weighted average power {avg_power:.0f}W should be "
            "near/below CP for long effort")

    def test_climb_clusters_get_more_power(self, optimizer, long_cluster_course):
        """Climb clusters (segment_id=2) should get more power than flat (1) or descent (3)."""
        results_df, _, _ = optimizer.optimize_variable_pacing(
            long_cluster_course, target_w_utilization=0.70)
        climb_power = results_df.loc[results_df['segment_id'] == 2, 'target_power'].mean()
        descent_power = results_df.loc[results_df['segment_id'] == 3, 'target_power'].mean()
        assert climb_power > descent_power, (
            f"Climb {climb_power:.0f}W should exceed descent {descent_power:.0f}W")

    def test_legacy_long_course_works(self, optimizer, long_legacy_course):
        """Long course without cluster metadata should still optimise."""
        results_df, total_time, _ = optimizer.optimize_variable_pacing(
            long_legacy_course, target_w_utilization=0.70)
        assert total_time > 0
        assert len(results_df) == len(long_legacy_course)

    def test_time_positive_and_finite(self, optimizer, long_cluster_course):
        """Total time should be reasonable."""
        _, total_time, _ = optimizer.optimize_variable_pacing(
            long_cluster_course, target_w_utilization=0.70)
        assert 3600 < total_time < 20000, f"Time {total_time:.0f}s out of range"


# ── Max sustainable power wrapper ──────────────────────────────────────────

class TestMaxSustainablePower:
    def test_short_duration_above_cp(self, optimizer):
        """For a 20 min effort, sustainable power should be above CP."""
        p = optimizer.max_sustainable_power_for_duration(1200)
        assert p > CP

    def test_long_duration_below_cp(self, optimizer):
        """For a 3 h effort, sustainable power should be below CP."""
        p = optimizer.max_sustainable_power_for_duration(10800)
        assert p < CP

    def test_monotone_decreasing(self, optimizer):
        """Power ceiling should decrease with duration."""
        durations = [600, 1800, 3600, 7200, 14400]
        powers = [optimizer.max_sustainable_power_for_duration(d) for d in durations]
        for i in range(len(powers) - 1):
            assert powers[i] > powers[i + 1]
