---
name: optimization-debug
description: Diagnose pacing optimization issues — variable strategy diverging from constant, W' going negative, simulate vs optimize time mismatch, gradient/unit confusion. Use when results look wrong or `CourseOptimizer` raises.
---

# Optimization Debug

## Trigger
Use when pacing results look wrong: variable slower than constant, W' goes negative, detailed sim disagrees with segment sim, or optimizer raises a schema/unit error.

## Locked boundary
`app/optimization.py::CourseOptimizer._normalize_segments` is the ingest boundary.

Canonical output schema:
- `distance` in meters
- `gradient` as decimal
- `altitude` in meters
- `wind` in m/s

Accepted aliases:
- `distance_sum` → `distance`
- `gradient_mean` → `gradient`
- `altitude_mean` → `altitude`

Unit conversion rules:
- Canonical `gradient` is decimal and `distance` is meters, including gentle
  grades and short segments.
- Aggregated `gradient_mean` is percent → divide by 100; `distance_sum` is km →
  multiply by 1000.
- Course point grades (including `gradient_smoothed`) are percentages.
- Never infer units from value magnitude.

Regression test: [tests/tests/test_optimization_boundary_contract.py](../../tests/tests/test_optimization_boundary_contract.py).

## Fast debug path
1. Print `_normalize_segments(course_segments).head()` and verify the canonical columns/units.
2. Compare `simulate_course_time(power, segs)` vs `simulate_course_detailed(course, segs, power_strategy=power)`.
3. For variable pacing, inspect `_run_constant` and `_run_variable` in [pages_vibe/tabs/tab_optimization.py](../../pages_vibe/tabs/tab_optimization.py).
4. If the issue is cluster-aware pacing, check `_expand_cluster_powers` and `_cluster_power_map_from_array` in [app/optimization.py](../../app/optimization.py).

## Do not
- Do not bypass `_normalize_segments`.
- Do not use `float('inf')` penalties; use finite penalties.
- Do not treat `app/visualizations*.py` as source of truth.

## Known equal-segmentation fix
Equal segmentation uses the per-segment fallback path. If a consumer still expects legacy aggregate columns, keep the alias fields mirrored in `optimization.py` results.
