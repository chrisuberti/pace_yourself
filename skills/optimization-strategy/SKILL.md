---
name: optimization-strategy
description: Theoretical foundation, algorithmic decisions, and tunable parameters of the Pace Yourself pacing optimizer. Use when modifying or reasoning about CourseOptimizer, picking defaults, designing new pacing strategies, or explaining why a particular result is sensible. Complements `optimization-debug` (which focuses on diagnosing wrong results); this pack explains why the algorithm is shaped the way it is.
---

# Optimization Strategy & Decisions

Scope: why `app/optimization.py` is shaped the way it is. For diagnosis, use [optimization-debug](../optimization-debug/SKILL.md).

## Model summary
- CP/W' is the core short-effort model.
- For >1 h, `app/rider.py::WTankCalculator.piecewise_power_duration` adds endurance decay.
- Recovery uses Skiba-style exponential refill in [app/rider.py](../../app/rider.py); recovery must be meaningfully below CP.
- Speed is solved from cycling physics in [app/cycling_physics.py](../../app/cycling_physics.py), with a stable clamp fallback.

## Constant power
- Single-variable `scipy.optimize.minimize`.
- Objective: `total_time + W' penalty`.
- Bounds are duration-aware.
- All penalties are finite; the optimizer should not raise.

## Variable pacing
- Cluster-aware when `segment_id` exists; equal segmentation falls back to per-segment strategy.
- Heuristic seed: compute cluster gradients, split effort vs recovery, enforce enough recovery distance, scale W' by terrain variation, then distribute effort power and clamp recovery power below CP.
- Refinement: optimize cluster powers for minimum time with finite penalties and multi-start seeds.
- Safety rule: variable pacing should not end slower than the uniform-baseline fallback.

## Important constants and thresholds
- `W_PRIME_BUDGET_CEILING = 0.90` is a module constant, not a UI control.
- Recovery needs a noticeable gap below CP; very small gaps are ineffective.
- Terrain variation should damp W' on flat routes.

## What to change carefully
- Any constant in `_generate_cluster_heuristic`, `_refine_cluster_strategy`, or `optimize_variable_pacing`.
- Any new pacing strategy.
- Any change to the matched-W' comparison in [pages_vibe/tabs/tab_optimization.py](../../pages_vibe/tabs/tab_optimization.py).

## Validation
- [tests/tests/test_cluster_pacing.py](../../tests/tests/test_cluster_pacing.py)
- [tests/tests/test_pacing_invariants.py](../../tests/tests/test_pacing_invariants.py)
- [tests/tests/test_optimization_boundary_contract.py](../../tests/tests/test_optimization_boundary_contract.py)

## When to invoke
- Adding/removing a tunable parameter.
- Changing a heuristic or refinement constant.
- Designing a new pacing strategy.
- Explaining to a user why a result looks the way it does.
- Reviewing a PR that touches `app/optimization.py` or `app/rider.py` CP/W' code.
- Before changing the Skiba τ coefficients (don't, unless replacing the model).

---

## Design invariants (enforced as of 2026-06)

### 1. One power per segment/cluster
For clustering and terrain segmentation, every spatial occurrence of the same `segment_id`
must receive the SAME target power. This gives riders a simple instruction set:
"Cluster 0 (flat): 265 W, Cluster 1 (climb): 330 W, Cluster 2 (descent): 230 W".
Enforced by `_expand_cluster_powers(cluster_power_map, segment_ids)` in
`app/optimization.py`. **Do not break this invariant.**

### 2. Variable pacing = min-time subject to W' budget ceiling
Objective: minimise total course time. Constraints:
- W' never goes below 0 mid-course (feasibility).
- Final W' >= (1 - W_PRIME_BUDGET_CEILING) * W'  (budget ceiling, not exact target).
`W_PRIME_BUDGET_CEILING = 0.90` is a module constant in `app/optimization.py`.
It is NOT a UI slider. Applied to BOTH constant and variable strategies.

### 3. Variable pacing is never slower than constant power
After optimisation, `optimize_variable_pacing` simulates a uniform-`baseline_power`
strategy. If it is faster than the variable result, the strategy is replaced with
the uniform baseline. This is the safety net — it makes variable pacing provably
better than or equal to constant pacing.

### 4. Baseline-power anchor for short efforts
For efforts <= 60 min, the heuristic anchors recovery clusters to `baseline_power`
(the optimal constant power from `optimize_constant_power`), NOT to CP × 0.85.
This prevents recovery clusters from riding below the constant benchmark, which
would waste time without providing physiological benefit.
Long efforts (> 60 min) use the piecewise power-duration ceiling (unchanged).
