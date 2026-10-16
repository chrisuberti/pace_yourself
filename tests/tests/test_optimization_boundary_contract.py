"""
Boundary contract tests for app.optimization._normalize_segments and
create_course_segments_from_course.

Locks the canonical post-normalization schema:
    distance (meters), gradient (decimal), altitude (meters), wind (m/s)

These are MVP-blocking contracts — downstream simulate / optimize functions
assume canonical names + units.
"""
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.optimization import CourseOptimizer


@pytest.fixture
def optimizer():
    return CourseOptimizer(critical_power=250, w_prime=20000)


@pytest.fixture
def aggregated_input():
    """Aggregated-style input: *_sum / *_mean column names, gradient as %, distance as km."""
    return pd.DataFrame({
        'distance_sum': [1.0, 1.5, 0.8, 1.2],   # km
        'gradient_mean': [2.0, 6.0, -3.0, 1.0],  # percent
        'altitude_mean': [100, 120, 115, 110],
    })


@pytest.fixture
def canonical_input():
    """Already-canonical input: distance (m), gradient (decimal), altitude (m), wind."""
    return pd.DataFrame({
        'distance': [1000.0, 1500.0, 800.0, 1200.0],
        'gradient': [0.02, 0.06, -0.03, 0.01],
        'altitude': [100, 120, 115, 110],
        'wind': [0.0, 0.0, 0.0, 0.0],
    })


class TestNormalizeSegmentsContract:
    def test_aggregated_input_produces_canonical_columns(self, optimizer, aggregated_input):
        out = optimizer._normalize_segments(aggregated_input)
        for col in ('distance', 'gradient', 'altitude', 'wind'):
            assert col in out.columns, f"missing canonical column: {col}"

    def test_aggregated_input_converts_units(self, optimizer, aggregated_input):
        out = optimizer._normalize_segments(aggregated_input)
        # km -> m
        np.testing.assert_allclose(out['distance'].values, [1000, 1500, 800, 1200])
        # percent -> decimal
        np.testing.assert_allclose(out['gradient'].values, [0.02, 0.06, -0.03, 0.01])

    def test_canonical_input_is_idempotent(self, optimizer, canonical_input):
        out = optimizer._normalize_segments(canonical_input)
        np.testing.assert_allclose(out['distance'].values, canonical_input['distance'].values)
        np.testing.assert_allclose(out['gradient'].values, canonical_input['gradient'].values)

    def test_double_normalization_is_stable(self, optimizer, aggregated_input):
        once = optimizer._normalize_segments(aggregated_input)
        twice = optimizer._normalize_segments(once)
        np.testing.assert_allclose(once['distance'].values, twice['distance'].values)
        np.testing.assert_allclose(once['gradient'].values, twice['gradient'].values)

    def test_wind_default_added_when_missing(self, optimizer, aggregated_input):
        out = optimizer._normalize_segments(aggregated_input)
        assert 'wind' in out.columns
        assert (out['wind'] == 0).all()

    def test_original_dataframe_untouched(self, optimizer, aggregated_input):
        before_cols = set(aggregated_input.columns)
        before_grad = aggregated_input['gradient_mean'].copy()
        _ = optimizer._normalize_segments(aggregated_input)
        assert set(aggregated_input.columns) == before_cols
        np.testing.assert_allclose(aggregated_input['gradient_mean'].values, before_grad.values)


class TestOptimizerAcceptsBothShapes:
    """End-to-end: simulate_course_time must produce equivalent results for
    aggregated vs canonical input shapes (same underlying course)."""

    def test_simulate_matches_for_both_shapes(self, optimizer, aggregated_input, canonical_input):
        _, t_agg, w_agg, _ = optimizer.simulate_course_time(220.0, aggregated_input)
        _, t_can, w_can, _ = optimizer.simulate_course_time(220.0, canonical_input)
        # Same course, same power -> times within numerical tolerance
        assert abs(t_agg - t_can) < 0.5, f"time mismatch: {t_agg} vs {t_can}"
        assert abs(w_agg - w_can) < 1.0, f"W' mismatch: {w_agg} vs {w_can}"

    def test_short_canonical_distance_matches_explicit_kilometer_schema(self, optimizer):
        canonical = pd.DataFrame({
            'distance': [35.0],
            'gradient': [0.005],
            'altitude': [100.0],
        })
        aggregated = pd.DataFrame({
            'distance_sum': [0.035],
            'gradient_mean': [0.5],
            'altitude_mean': [100.0],
        })

        normalized = optimizer._normalize_segments(canonical)
        np.testing.assert_allclose(normalized['distance'], [35.0])

        _, canonical_time, _, _ = optimizer.simulate_course_time(220, canonical)
        _, aggregated_time, _, _ = optimizer.simulate_course_time(220, aggregated)
        assert canonical_time == pytest.approx(aggregated_time)


class TestCanonicalSimulationKernels:
    def test_rider_physics_change_simulated_time(self, canonical_input):
        aero_rider = CourseOptimizer(
            critical_power=250, w_prime=20000,
            mass=70, cda=0.22, crr=0.003,
        )
        upright_rider = CourseOptimizer(
            critical_power=250, w_prime=20000,
            mass=90, cda=0.40, crr=0.006,
        )

        _, aero_time, _, _ = aero_rider.simulate_course_time(220, canonical_input)
        _, upright_time, _, _ = upright_rider.simulate_course_time(220, canonical_input)

        assert aero_time < upright_time

    def test_granular_w_prime_uses_canonical_transition(self, optimizer):
        points = pd.DataFrame({
            'distance': [200.0, 250.0, 180.0, 300.0],
            'gradient': [0.04, -0.02, 0.06, -0.03],
            'altitude': [100.0, 108.0, 103.0, 114.0],
            'wind': [0.0, 0.0, 0.0, 0.0],
        })
        powers = np.array([300.0, 180.0, 290.0, 190.0])

        simulation = optimizer._simulate_with_acceleration(points, powers)
        expected_w = optimizer.w_prime
        for power, duration in zip(powers, simulation['times']):
            expected_w = optimizer._update_w_prime(expected_w, power, duration)

        assert simulation['final_w_remaining'] == pytest.approx(expected_w)
        np.testing.assert_allclose(simulation['accelerations'], 0.0)

    def test_equivalent_granular_and_segment_inputs_match(self, optimizer,
                                                           canonical_input):
        point_data = canonical_input.copy()
        point_data['cumulative_distance'] = point_data['distance'].cumsum()
        point_data['segment'] = np.arange(len(point_data))
        course = SimpleNamespace(df=point_data)

        coarse, coarse_time, coarse_w, coarse_energy = (
            optimizer.simulate_course_time(220.0, canonical_input)
        )
        granular, granular_time, analysis = optimizer.simulate_course_detailed(
            course=course,
            course_segments=coarse,
            power_strategy=220.0,
        )

        assert granular_time == pytest.approx(coarse_time)
        assert granular['w_remaining'].iloc[-1] == pytest.approx(coarse_w)
        assert granular['cumulative_energy'].iloc[-1] == pytest.approx(
            coarse_energy)
        assert analysis['simulation_type'] == 'Granular canonical simulation'

    def test_detailed_simulation_converts_gentle_course_grade_consistently(
            self, optimizer):
        course_points = pd.DataFrame({
            'lat': [45.0, 45.001],
            'lon': [-122.0, -122.001],
            'distance': [0.0, 1000.0],
            'cumulative_distance': [0.0, 1000.0],
            'gradient': [0.5, 0.5],  # Course point grades are percentages.
            'gradient_smoothed': [0.5, 0.5],
            'altitude': [100.0, 100.0],
            'segment': [0, 0],
        })
        segments = pd.DataFrame({
            'distance': [1000.0],
            'gradient': [0.005],
            'altitude': [100.0],
            'wind': [0.0],
        })
        course = SimpleNamespace(df=course_points)

        _, segment_time, _, _ = optimizer.simulate_course_time(250.0, segments)
        detailed, detailed_time, _ = optimizer.simulate_course_detailed(
            course=course,
            course_segments=segments,
            power_strategy=250.0,
        )

        assert detailed['gradient'].iloc[-1] == pytest.approx(0.005)
        assert detailed['gradient_smoothed'].iloc[-1] == pytest.approx(0.005)
        assert detailed_time == pytest.approx(segment_time)
