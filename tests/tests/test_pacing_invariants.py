"""Invariant-enforcing tests for pacing optimization and gradient smoothing.

These tests pin down the *desired outcomes* that previously regressed silently:

  1. Gradient smoothing must be robust to near-zero GPS steps (no ±hundreds-%
     spikes, output bounded, correct slope on a known ramp).
  2. On terrain with genuine redistribution opportunity (rolling climbs +
     descents and W' headroom), variable pacing must be MEASURABLY faster than
     constant power AND show visible per-cluster power spread.
  3. On a steady, uniform climb, the optimizer must NOT fabricate variation —
     variable pacing should collapse to ~constant (this is physically correct).
  4. Same-cluster segments always receive identical power (rider-actionable).
  5. The heuristic+refinement optimizer must stay close to a brute-force optimum
     on a small course (no large optimality gap masked by the safety net).
"""

import itertools
import os

import numpy as np
import pandas as pd
import pytest

from app.course import Course
from app.optimization import (
    CourseOptimizer,
    create_course_segments_from_course,
    W_PRIME_BUDGET_CEILING,
)
from app.course import (
    classify_gradient_band,
    BAND_RANK,
    BAND_LABELS,
)

_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
PTYP_FIXTURE = os.path.join(_FIXTURE_DIR, "pedal_till_ya_puke.csv")
NF4832_FIXTURE = os.path.join(_FIXTURE_DIR, "nf_4832_climb.csv")


# ── Synthetic course builders ──────────────────────────────────────────────

def _segments(distances, gradients, segment_ids):
    """Build a sequence-preserving segment frame with cluster metadata."""
    n = len(distances)
    return pd.DataFrame({
        'distance':           list(distances),
        'gradient':           list(gradients),
        'altitude':           list(np.cumsum([g * d for g, d in zip(gradients, distances)])),
        'wind':               [0] * n,
        'segment_id':         list(segment_ids),
        'segment_sequence':   list(range(1, n + 1)),
        'segment_occurrence': list(range(1, n + 1)),
    })


@pytest.fixture
def rolling_course():
    """Rolling terrain: flat / climb / descent alternating with W' headroom.

    Variation SHOULD help here — push on climbs (slow, time-dense), ease on
    descents (where power barely affects speed), bank W' on the flats.
        cluster 1 = flat (~1%), 2 = climb (~8%), 3 = descent (~-7%)
    """
    dist = [1200, 1500, 1200, 1500, 1200, 1500, 1200]
    grad = [0.01, 0.08, -0.07, 0.08, -0.07, 0.08, 0.01]
    sid  = [1,    2,    3,     2,    3,     2,    1]
    return _segments(dist, grad, sid)


@pytest.fixture
def steady_climb():
    """Uniform climb broken into equal pieces — constant power is optimal.

    Every segment is the same ~6% grade, so there is nothing to redistribute.
    The optimizer must NOT invent spurious variation.
    """
    dist = [1500] * 8
    grad = [0.06] * 8
    sid  = [1] * 8  # single cluster: one steady grade
    return _segments(dist, grad, sid)


# ── 1. Gradient smoothing robustness ───────────────────────────────────────

class TestGradientSmoothing:
    def test_windowed_gradient_known_ramp(self):
        """A constant 5% ramp must yield ~5% gradient everywhere."""
        cum = np.arange(0, 2000, 10.0)
        alt = cum * 0.05  # 5% grade
        g = Course._windowed_gradient(cum, alt, half_window_m=50.0)
        # Interior points (away from the truncated window edges) should be ~5%.
        interior = g[10:-10]
        assert np.allclose(interior, 5.0, atol=0.5), \
            f"Expected ~5% ramp, got range [{interior.min():.2f}, {interior.max():.2f}]"

    def test_tiny_steps_do_not_explode(self):
        """Near-zero-distance GPS steps must not produce huge gradients."""
        # 200 points but many duplicated coords -> several ~0 m steps.
        cum = np.sort(np.concatenate([
            np.arange(0, 1000, 10.0),
            np.arange(0, 1000, 10.0) + 1e-4,  # near-duplicate points
        ]))
        alt = cum * 0.04 + np.random.default_rng(0).normal(0, 0.05, len(cum))
        g = Course._windowed_gradient(cum, alt, half_window_m=50.0)
        assert np.isfinite(g).all(), "Gradient contains non-finite values"
        assert np.abs(g).max() < 25.0, \
            f"Tiny steps produced a spike of {np.abs(g).max():.0f}% (should stay bounded)"

    def test_real_route_gradient_is_clean(self):
        """Processing a real route must not leave the profile saturated at clamp."""
        df = pd.read_csv(NF4832_FIXTURE)
        course = Course(df)
        g = course.df['gradient']
        assert np.isfinite(g).all()
        # Almost nothing should sit pinned at the ±max_gradient clamp.
        pinned = (g.abs() >= course.max_gradient - 0.1).mean()
        assert pinned < 0.05, \
            f"{pinned*100:.1f}% of points pinned at clamp — smoothing too weak"


# ── 2. Variation helps on rolling terrain ──────────────────────────────────

class TestVariationWhenItHelps:
    @pytest.fixture
    def optimizer(self):
        # Generous W' so the rider has headroom to redistribute effort.
        return CourseOptimizer(critical_power=280, w_prime=28000)

    def test_variable_beats_constant_on_rolling(self, optimizer, rolling_course):
        const_p, const_t, _ = optimizer.optimize_constant_power(rolling_course)
        _, var_t, _ = optimizer.optimize_variable_pacing(rolling_course)
        assert var_t <= const_t + 1e-6, \
            f"Variable ({var_t:.1f}s) must not be slower than constant ({const_t:.1f}s)"

    def test_visible_power_spread_on_rolling(self, optimizer, rolling_course):
        results_df, _, _ = optimizer.optimize_variable_pacing(rolling_course)
        cluster_powers = results_df.groupby('segment_id')['target_power'].first()
        spread = cluster_powers.max() - cluster_powers.min()
        assert spread >= 10.0, \
            f"Expected visible per-cluster spread, got {spread:.1f}W ({dict(cluster_powers.round())})"

    def test_climb_gets_more_than_descent(self, optimizer, rolling_course):
        results_df, _, _ = optimizer.optimize_variable_pacing(rolling_course)
        climb = results_df.loc[results_df['segment_id'] == 2, 'target_power'].iloc[0]
        descent = results_df.loc[results_df['segment_id'] == 3, 'target_power'].iloc[0]
        assert climb > descent, f"Climb {climb:.0f}W should exceed descent {descent:.0f}W"


# ── 3. No fabricated variation on a steady climb ───────────────────────────

class TestNoSpuriousVariation:
    @pytest.fixture
    def optimizer(self):
        return CourseOptimizer(critical_power=250, w_prime=20000)

    def test_steady_climb_stays_near_constant(self, optimizer, steady_climb):
        const_p, const_t, _ = optimizer.optimize_constant_power(steady_climb)
        results_df, var_t, _ = optimizer.optimize_variable_pacing(steady_climb)
        # Single cluster -> one power; it must be essentially the constant power.
        powers = results_df['target_power'].values
        assert powers.std() < 1.0, \
            f"Optimizer fabricated variation on a uniform climb: std={powers.std():.1f}W"
        assert abs(var_t - const_t) <= const_t * 0.01, \
            f"Variable ({var_t:.1f}s) diverged from constant ({const_t:.1f}s) on uniform climb"


# ── 4. One power per cluster ───────────────────────────────────────────────

class TestOnePowerPerCluster:
    @pytest.fixture
    def optimizer(self):
        return CourseOptimizer(critical_power=280, w_prime=28000)

    def test_uniform_power_within_each_cluster(self, optimizer, rolling_course):
        results_df, _, _ = optimizer.optimize_variable_pacing(rolling_course)
        for sid in rolling_course['segment_id'].unique():
            powers = results_df.loc[results_df['segment_id'] == sid, 'target_power']
            assert powers.round(2).nunique() == 1, \
                f"Cluster {sid} has non-uniform power: {powers.values}"


# ── 5. Optimizer stays close to brute-force optimum ────────────────────────

class TestBruteForceAgreement:
    @pytest.fixture
    def optimizer(self):
        return CourseOptimizer(critical_power=280, w_prime=28000)

    def test_within_tolerance_of_grid_optimum(self, optimizer, rolling_course):
        """Heuristic+refinement should be within ~1% of an exhaustive grid search."""
        norm = optimizer._normalize_segments(rolling_course)
        clusters = sorted(norm['segment_id'].unique())

        best_time = np.inf
        grid = range(220, 380, 10)
        for combo in itertools.product(grid, repeat=len(clusters)):
            strat = np.zeros(len(norm))
            for cid, p in zip(clusters, combo):
                strat[(norm['segment_id'] == cid).values] = p
            sim = optimizer._simulate_variable_pacing(norm, strat)
            if sim['feasible'] and sim['total_time'] < best_time:
                best_time = sim['total_time']

        _, var_t, _ = optimizer.optimize_variable_pacing(rolling_course)
        assert var_t <= best_time * 1.01, \
            f"Optimizer time {var_t:.1f}s exceeds grid optimum {best_time:.1f}s by >1%"


# ── 6. Real rolling course regression: 'Pedal till ya puke' ────────────────
#
# Mauna Kea is a poor optimizer test: it is a monotonic uphill where constant
# power is provably optimal, so it can NEVER exercise variable pacing. The
# 'Pedal till ya puke' course (~11 km, gentle terrain with one short steep wall)
# is a genuine redistribution opportunity — an exhaustive grid search shows a
# varied strategy beats constant by ~25 s. These tests pin that outcome so the
# refinement can never silently collapse back to uniform power again.

@pytest.mark.skipif(not os.path.exists(PTYP_FIXTURE),
                    reason="PTYP fixture CSV not present")
class TestPedalTillYaPukeRealCourse:
    CP, WPRIME = 250, 20000

    @pytest.fixture(scope="class")
    def optimized(self):
        df = pd.read_csv(PTYP_FIXTURE)  # lat, lon, ele
        course = Course(df)
        course.auto_segmentation(max_clusters=3)
        course.enable_enhanced_segmentation()
        opt_segs = create_course_segments_from_course(course)
        opt = CourseOptimizer(critical_power=self.CP, w_prime=self.WPRIME)
        const_p, const_t, _ = opt.optimize_constant_power(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING)
        var_df, var_t, _ = opt.optimize_variable_pacing(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING,
            baseline_power=const_p)
        return {'const_p': const_p, 'const_t': const_t,
                'var_df': var_df, 'var_t': var_t}

    def test_smoothed_gradient_not_saturated(self):
        """Windowed smoothing must keep the real course off the gradient clamp."""
        course = Course(pd.read_csv(PTYP_FIXTURE))
        g = course.df['gradient']
        assert np.isfinite(g).all()
        pinned = (g.abs() >= course.max_gradient - 0.1).mean()
        assert pinned < 0.02, f"{pinned*100:.1f}% of points pinned at gradient clamp"

    def test_variable_shows_visible_spread(self, optimized):
        """Variable pacing must produce a rider-visible power spread, not uniform."""
        cp = optimized['var_df'].groupby('segment_id')['target_power'].first()
        spread = cp.max() - cp.min()
        assert spread >= 50.0, \
            f"Expected visible per-cluster spread, got {spread:.0f}W ({dict(cp.round())})"

    def test_variable_beats_constant(self, optimized):
        """Variable pacing must be measurably faster than constant on this course."""
        gain = optimized['const_t'] - optimized['var_t']
        assert gain >= 10.0, \
            f"Variable only gained {gain:.1f}s over constant (expected ≥10s)"

    def test_steep_wall_gets_most_power(self, optimized):
        """The short steep wall cluster should receive the highest power."""
        cp = optimized['var_df'].groupby('segment_id')['target_power'].first()
        grads = optimized['var_df'].groupby('segment_id')['gradient'].mean()
        steepest_cluster = grads.idxmax()
        assert cp.idxmax() == steepest_cluster, \
            f"Highest power went to cluster {cp.idxmax()}, not steepest {steepest_cluster}"

    def test_one_power_per_cluster(self, optimized):
        """Each cluster must still resolve to a single actionable power."""
        var_df = optimized['var_df']
        for sid in var_df['segment_id'].unique():
            powers = var_df.loc[var_df['segment_id'] == sid, 'target_power']
            assert powers.round(2).nunique() == 1, \
                f"Cluster {sid} has non-uniform power: {powers.values}"


# ── 7. Terrain (many-segment) must vary, not collapse to constant ──────────
#
# Terrain segmentation gives EACH contiguous segment a unique segment_id, so a
# course can have 10-20+ "clusters". The coarse Cartesian grid pre-search used
# for clustering (<=3 labels) is infeasible there, so terrain courses used to
# collapse straight back to constant power (0.0 s gain, flat line) while the
# SAME course under clustering varied. These tests pin that terrain produces
# real variation AND is consistent with clustering on the identical course.

@pytest.mark.skipif(not os.path.exists(NF4832_FIXTURE),
                    reason="NF 4832 fixture CSV not present")
class TestTerrainManySegmentVariation:
    # CP/W' chosen to leave genuine W' headroom so redistribution helps.
    CP, WPRIME = 260, 30000

    def _optimize(self, method):
        course = Course(pd.read_csv(NF4832_FIXTURE))  # lat, lon, ele
        if method == "terrain":
            course.gradient_bearing_segmentation(
                uphill_threshold=2.0, downhill_threshold=-2.0,
                bearing_change_threshold=60, min_segment_distance=300)
        else:
            course.auto_segmentation(max_clusters=4,
                                     gradient_weight=0.5, bearing_weight=0.5)
        course.enable_enhanced_segmentation()
        opt_segs = create_course_segments_from_course(course)
        opt = CourseOptimizer(critical_power=self.CP, w_prime=self.WPRIME)
        const_p, const_t, _ = opt.optimize_constant_power(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING)
        var_df, var_t, _ = opt.optimize_variable_pacing(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING,
            baseline_power=const_p)
        cp = var_df.groupby('segment_id')['target_power'].first()
        return {'n_seg': cp.shape[0], 'const_t': const_t, 'var_t': var_t,
                'spread': cp.max() - cp.min(), 'cluster_powers': cp,
                'var_df': var_df}

    @pytest.fixture(scope="class")
    def terrain(self):
        return self._optimize("terrain")

    def test_terrain_produces_many_segments(self, terrain):
        """Sanity: terrain really does exceed the grid-search cluster cap (>3)."""
        assert terrain['n_seg'] > 3, \
            f"Expected many terrain segments, got {terrain['n_seg']}"

    def test_terrain_varies_not_constant(self, terrain):
        """Terrain must NOT collapse to constant power when variation helps."""
        assert terrain['spread'] >= 30.0, \
            f"Terrain spread only {terrain['spread']:.0f}W — collapsed to constant"

    def test_terrain_beats_constant(self, terrain):
        """Terrain variable pacing must be measurably faster than constant."""
        gain = terrain['const_t'] - terrain['var_t']
        assert gain >= 5.0, f"Terrain gained only {gain:.1f}s over constant"

    def test_terrain_consistent_with_clustering(self, terrain):
        """The same course under clustering must ALSO gain — not one-method-only.

        Both segmentations should find a faster-than-constant strategy; terrain
        (finer granularity) should gain at least as much as clustering.
        """
        clustering = self._optimize("clustering")
        terrain_gain = terrain['const_t'] - terrain['var_t']
        cluster_gain = clustering['const_t'] - clustering['var_t']
        assert cluster_gain >= 5.0, \
            f"Clustering gained only {cluster_gain:.1f}s (regression in <=3 path)"
        assert terrain_gain >= cluster_gain - 2.0, \
            (f"Terrain ({terrain_gain:.1f}s) much worse than clustering "
             f"({cluster_gain:.1f}s) on the same course")

    def test_terrain_steepest_segment_high_power(self, terrain):
        """The steepest terrain segment should be among the highest-power ones."""
        cp = terrain['cluster_powers']
        grads = terrain['var_df'].groupby('segment_id')['gradient'].mean()
        steepest = grads.idxmax()
        # Steepest segment power should sit in the top third of the spread.
        threshold = cp.min() + 0.66 * (cp.max() - cp.min())
        assert cp[steepest] >= threshold, \
            f"Steepest segment power {cp[steepest]:.0f}W not near the top of spread"


# ── 8. Gradient-band "Pacing Zones" — low dimensionality, digestible rule ───
#
# Terrain gives each block a unique id (high-D, hard to optimize). Pacing Zones
# collapses the course into a few recurring gradient bands so the optimizer
# solves only a handful of power knobs (like clustering) AND the rider gets a
# simple rule. These tests pin the band classifier, the low dimensionality, the
# one-power-per-zone contract, and that variation still beats constant.

class TestGradientBandClassifier:
    def test_band_boundaries(self):
        """Classifier maps gradients to the expected bands at the defaults."""
        assert classify_gradient_band(10.0) == 'steep_climb'
        assert classify_gradient_band(4.0) == 'climb'
        assert classify_gradient_band(0.0) == 'flat'
        assert classify_gradient_band(-4.0) == 'descent'
        assert classify_gradient_band(-10.0) == 'steep_descent'

    def test_thresholds_are_tunable(self):
        """Raising the steep threshold reclassifies a borderline climb."""
        assert classify_gradient_band(7.0, steep_threshold=6.0) == 'steep_climb'
        assert classify_gradient_band(7.0, steep_threshold=8.0) == 'climb'

    def test_flat_band_is_symmetric(self):
        assert classify_gradient_band(1.5) == 'flat'
        assert classify_gradient_band(-1.5) == 'flat'


@pytest.mark.skipif(not os.path.exists(NF4832_FIXTURE),
                    reason="NF 4832 fixture CSV not present")
class TestPacingZonesRealCourse:
    CP, WPRIME = 260, 30000

    @pytest.fixture(scope="class")
    def zoned(self):
        course = Course(pd.read_csv(NF4832_FIXTURE))
        course.gradient_band_segmentation()
        course.enable_enhanced_segmentation()
        opt_segs = create_course_segments_from_course(course)
        opt = CourseOptimizer(critical_power=self.CP, w_prime=self.WPRIME)
        const_p, const_t, _ = opt.optimize_constant_power(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING)
        var_df, var_t, _ = opt.optimize_variable_pacing(
            opt_segs, target_w_utilization=W_PRIME_BUDGET_CEILING,
            baseline_power=const_p)
        return {'segs': opt_segs, 'const_p': const_p, 'const_t': const_t,
                'var_df': var_df, 'var_t': var_t}

    def test_low_dimensionality(self, zoned):
        """The whole point: a course collapses to a FEW power knobs (<=5)."""
        n_zones = zoned['segs']['segment_id'].nunique()
        assert 1 < n_zones <= 5, \
            f"Expected a handful of pacing zones, got {n_zones}"

    def test_zones_are_valid_bands(self, zoned):
        """Every segment_id is a real gradient-band rank (0-4)."""
        ids = set(zoned['segs']['segment_id'].unique())
        assert ids <= set(BAND_RANK.values()), \
            f"Unexpected zone ids {ids}, not band ranks {set(BAND_RANK.values())}"

    def test_one_power_per_zone(self, zoned):
        """Same gradient zone → identical power everywhere it recurs."""
        var_df = zoned['var_df']
        for sid in var_df['segment_id'].unique():
            powers = var_df.loc[var_df['segment_id'] == sid, 'target_power']
            assert powers.round(2).nunique() == 1, \
                f"Zone {sid} has non-uniform power: {powers.values}"

    def test_zone_recurs_along_course(self, zoned):
        """At least one zone should appear at multiple points (recurring ids).

        This is what distinguishes bands from terrain's unique-per-block ids and
        is what keeps the optimizer low-dimensional.
        """
        segs = zoned['segs']
        # More spatial segments than unique zone ids ⇒ at least one zone recurs.
        assert len(segs) > segs['segment_id'].nunique(), \
            "No zone recurs — bands collapsed to one-block-per-id (terrain-like)"

    def test_variation_beats_constant(self, zoned):
        """Even collapsed to a few zones, variation must still help here."""
        gain = zoned['const_t'] - zoned['var_t']
        assert gain >= 5.0, f"Pacing zones gained only {gain:.1f}s over constant"

    def test_climbs_get_more_than_descents(self, zoned):
        """Climb zones should be paced above the descent zones."""
        zp = zoned['var_df'].groupby('segment_id').agg(
            power=('target_power', 'first'), grad=('gradient', 'mean'))
        climb_power = zp.loc[zp['grad'] > 0.02, 'power']
        descent_power = zp.loc[zp['grad'] < -0.02, 'power']
        if not climb_power.empty and not descent_power.empty:
            assert climb_power.min() > descent_power.max(), \
                "A climb zone is paced no higher than a descent zone"


@pytest.mark.skipif(not os.path.exists(NF4832_FIXTURE),
                    reason="NF 4832 fixture CSV not present")
class TestPacingZonesVsTerrain:
    """Bands must be lower-dimensional than raw terrain on the same course."""
    def test_bands_have_fewer_knobs_than_terrain(self):
        df = pd.read_csv(NF4832_FIXTURE)

        terrain = Course(df.copy())
        terrain.gradient_bearing_segmentation(
            uphill_threshold=2.0, downhill_threshold=-2.0,
            bearing_change_threshold=60, min_segment_distance=300)
        terrain.enable_enhanced_segmentation()
        n_terrain = create_course_segments_from_course(terrain)['segment_id'].nunique()

        bands = Course(df.copy())
        bands.gradient_band_segmentation()
        bands.enable_enhanced_segmentation()
        n_bands = create_course_segments_from_course(bands)['segment_id'].nunique()

        assert n_bands < n_terrain, \
            f"Bands ({n_bands}) not lower-dimensional than terrain ({n_terrain})"
        assert n_bands <= 5
