"""Constant-power simulation and W' optimization contracts."""

import numpy as np
import pandas as pd
import pytest

from app.optimization import CourseOptimizer


@pytest.fixture
def optimizer():
    return CourseOptimizer(critical_power=300, w_prime=25000)


@pytest.fixture
def course_segments():
    return pd.DataFrame({
        "distance": [2000, 3000, 2000, 5000, 3000, 5000],
        "gradient": [0.0, 0.06, 0.12, 0.03, -0.08, 0.01],
        "altitude": [100, 280, 520, 670, 430, 480],
        "wind": [0, 0, 0, 0, 0, 0],
    })


@pytest.mark.parametrize("power", [250, 275, 300, 305])
def test_power_levels(optimizer, course_segments, power):
    results, total_time, w_remaining, energy = optimizer.simulate_course_time(
        power, course_segments
    )

    assert len(results) == len(course_segments)
    assert np.isfinite(total_time) and total_time > 0
    assert energy == pytest.approx(power * total_time)
    expected_w = optimizer.w_prime - max(
        power - optimizer.critical_power, 0
    ) * total_time
    assert w_remaining == pytest.approx(expected_w)
    assert results["w_remaining"].between(0, optimizer.w_prime).all()


@pytest.mark.parametrize("target_utilization", [0.5, 0.7, 0.85, 0.95])
def test_optimization(optimizer, course_segments, target_utilization):
    power, total_time, results = optimizer.optimize_constant_power(
        course_segments, target_w_utilization=target_utilization
    )

    assert np.isfinite(power) and power > 0
    assert np.isfinite(total_time) and total_time > 0
    assert len(results) == len(course_segments)
    assert results["w_remaining"].between(0, optimizer.w_prime).all()
    assert total_time == pytest.approx(results["time"].sum())
    assert results["power"].to_numpy() == pytest.approx(power)
