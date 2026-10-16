"""
Test cluster-aware variable pacing optimization.

Validates that when segments carry segment_id metadata (from terrain/clustering
segmentation), the optimizer assigns the SAME power to all segments of the same
cluster type, producing a rider-actionable pacing instruction set.
"""

import pytest
import pandas as pd
import numpy as np
from app.optimization import (
    CourseOptimizer,
    _has_cluster_info,
    _expand_cluster_powers,
    _cluster_power_map_from_array,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def optimizer():
    return CourseOptimizer(critical_power=300, w_prime=25000)


@pytest.fixture
def cluster_segments():
    """Simulated sequence-preserving segments: flat→climb→flat→descent→climb→flat.
    
    Three cluster types:
      segment_id=1: flat  (gradient ~1%)
      segment_id=2: climb (gradient ~7%)
      segment_id=3: descent (gradient ~-4%)
    """
    return pd.DataFrame({
        'distance':          [1500, 2000, 1200, 1000, 1800, 1500],
        'gradient':          [0.01, 0.07, 0.01, -0.04, 0.08, 0.01],
        'altitude':          [100,  150,  120,  100,   160,  130],
        'wind':              [0,    0,    0,    0,     0,    0],
        'segment_id':        [1,    2,    1,    3,     2,    1],
        'segment_sequence':  [1,    2,    3,    4,     5,    6],
        'segment_occurrence':[1,    1,    2,    1,     2,    3],
    })


@pytest.fixture
def legacy_segments():
    """Same course without cluster metadata — legacy equal segmentation."""
    return pd.DataFrame({
        'distance':  [1500, 2000, 1200, 1000, 1800, 1500],
        'gradient':  [0.01, 0.07, 0.01, -0.04, 0.08, 0.01],
        'altitude':  [100,  150,  120,  100,   160,  130],
        'wind':      [0,    0,    0,    0,     0,    0],
    })


# ── Helper function tests ─────────────────────────────────────────────────

class TestHelpers:
    def test_has_cluster_info_true(self, cluster_segments):
        assert _has_cluster_info(cluster_segments) is True

    def test_has_cluster_info_false(self, legacy_segments):
        assert _has_cluster_info(legacy_segments) is False

    def test_expand_cluster_powers(self, cluster_segments):
        cmap = {1: 290.0, 2: 340.0, 3: 250.0}
        result = _expand_cluster_powers(cmap, cluster_segments['segment_id'])
        expected = np.array([290.0, 340.0, 290.0, 250.0, 340.0, 290.0])
        np.testing.assert_array_almost_equal(result, expected)

    def test_cluster_power_map_roundtrip(self, cluster_segments):
        cmap = {1: 290.0, 2: 340.0, 3: 250.0}
        expanded = _expand_cluster_powers(cmap, cluster_segments['segment_id'])
        recovered = _cluster_power_map_from_array(expanded, cluster_segments['segment_id'])
        for cid in cmap:
            assert abs(recovered[cid] - cmap[cid]) < 0.01


# ── Core behavior tests ───────────────────────────────────────────────────

class TestClusterPacing:
    def test_same_cluster_gets_same_power(self, optimizer, cluster_segments):
        """All segments of the same cluster_id must be assigned identical power."""
        results_df, total_time, analysis = optimizer.optimize_variable_pacing(
            cluster_segments, target_w_utilization=0.85, aggressive_factor=1.2
        )

        # Group by segment_id and check power is uniform within each group
        for sid in cluster_segments['segment_id'].unique():
            mask = results_df['segment_id'] == sid
            powers = results_df.loc[mask, 'target_power'].values
            assert len(set(np.round(powers, 2))) == 1, \
                f"Cluster {sid} has varying powers: {powers}"

    def test_variable_pacing_produces_distinct_powers(self, optimizer, cluster_segments):
        """Different cluster types should get different power values."""
        results_df, _, _ = optimizer.optimize_variable_pacing(
            cluster_segments, target_w_utilization=0.85
        )

        cluster_powers = {}
        for sid in cluster_segments['segment_id'].unique():
            mask = results_df['segment_id'] == sid
            cluster_powers[sid] = results_df.loc[mask, 'target_power'].iloc[0]

        unique_powers = set(round(p) for p in cluster_powers.values())
        assert len(unique_powers) >= 2, \
            f"Expected at least 2 distinct power levels, got {cluster_powers}"

    def test_climbs_get_more_power_than_descents(self, optimizer, cluster_segments):
        """Climb clusters should receive higher power than descent clusters."""
        results_df, _, _ = optimizer.optimize_variable_pacing(
            cluster_segments, target_w_utilization=0.85
        )

        climb_power = results_df.loc[results_df['segment_id'] == 2, 'target_power'].iloc[0]
        descent_power = results_df.loc[results_df['segment_id'] == 3, 'target_power'].iloc[0]

        assert climb_power > descent_power, \
            f"Climb power ({climb_power:.0f}W) should exceed descent ({descent_power:.0f}W)"

    def test_results_carry_segment_id(self, optimizer, cluster_segments):
        """Results DataFrame should include segment_id for UI grouping."""
        results_df, _, _ = optimizer.optimize_variable_pacing(cluster_segments)
        assert 'segment_id' in results_df.columns
        assert 'segment_sequence' in results_df.columns

    def test_w_prime_stays_positive(self, optimizer, cluster_segments):
        """W' should never go below zero in a feasible strategy."""
        results_df, _, analysis = optimizer.optimize_variable_pacing(
            cluster_segments, target_w_utilization=0.85
        )
        assert results_df['w_remaining'].min() >= -1, \
            f"W' went below zero: {results_df['w_remaining'].min():.0f}"

    def test_total_time_is_faster_than_constant(self, optimizer, cluster_segments):
        """Variable pacing should be at least as fast as constant power."""
        _, var_time, analysis = optimizer.optimize_variable_pacing(
            cluster_segments, target_w_utilization=0.85
        )
        const_time = analysis['comparison_to_constant_power']['constant_time_minutes'] * 60
        # Variable pacing should be ≤ constant power time (or very close)
        assert var_time <= const_time * 1.01, \
            f"Variable ({var_time:.1f}s) slower than constant ({const_time:.1f}s)"


class TestLegacyFallback:
    def test_legacy_segments_still_work(self, optimizer, legacy_segments):
        """Without segment_id, optimizer should fall back to per-segment mode."""
        results_df, total_time, analysis = optimizer.optimize_variable_pacing(
            legacy_segments, target_w_utilization=0.85
        )
        assert total_time > 0
        assert len(results_df) == len(legacy_segments)
        # Should NOT have segment_id in results
        assert 'segment_id' not in results_df.columns

    def test_legacy_produces_variable_power(self, optimizer, legacy_segments):
        """Legacy mode should still produce varying power across segments."""
        results_df, _, _ = optimizer.optimize_variable_pacing(
            legacy_segments, target_w_utilization=0.85
        )
        powers = results_df['target_power'].values
        assert np.std(powers) > 1.0, \
            f"Expected variable power, got std={np.std(powers):.1f}"
