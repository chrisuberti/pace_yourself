"""
Course Optimization Module

This module provides optimization algorithms for cycling course pacing strategies.
Integrated from notebooks/StartCourseEstimation.ipynb as part of Phase 1 consolidation.
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import Tuple, Dict, Any, Optional
import itertools
import os
import sys

# Add the app directory to the Python path for imports
sys.path.append(os.path.dirname(__file__))

from cycling_physics import calculate_speed_and_plot
from rider import calculate_w_prime_recovery, WTankCalculator

# W' budget ceiling — fraction of W' the optimizer is allowed to spend.
# Applied to both constant and variable pacing. Not a UI control.
W_PRIME_BUDGET_CEILING = 0.90


def _has_cluster_info(course_segments: pd.DataFrame) -> bool:
    """Check whether segments carry cluster/segment_id metadata."""
    return 'segment_id' in course_segments.columns


def _expand_cluster_powers(cluster_power_map: Dict[int, float],
                           segment_ids: pd.Series) -> np.ndarray:
    """Convert a {cluster_id: power} map to a per-segment power array.
    
    Every segment with the *same* segment_id gets the *same* power value.
    This is the core mechanic that gives riders a simple instruction set:
    "uphills: 330 W, flats: 290 W, descents: 250 W".
    
    Args:
        cluster_power_map: Dict mapping cluster/segment_id → power (watts).
        segment_ids: Series of segment_id values (one per spatial segment).
    
    Returns:
        np.ndarray of power values aligned to segment order.
    """
    return np.array([cluster_power_map[sid] for sid in segment_ids])


def _cluster_power_map_from_array(power_array: np.ndarray,
                                  segment_ids: pd.Series) -> Dict[int, float]:
    """Inverse of _expand_cluster_powers — take per-segment array, pick
    the first power value for each cluster_id (they should all be the same
    within a cluster, but just in case we take the mean).
    """
    mapping: Dict[int, float] = {}
    for sid in segment_ids.unique():
        mask = segment_ids == sid
        mapping[sid] = float(np.mean(power_array[mask]))
    return mapping


class CourseOptimizer:
    """
    Course optimization engine for cycling performance analysis.
    
    This class provides methods to simulate course performance and optimize
    pacing strategies based on rider physiology and course characteristics.
    
    Supports efforts from short (< 1 hour, W'-driven) to long (up to 4 hours,
    endurance-decay-driven) via the piecewise power-duration model.
    """
    
    def __init__(self, critical_power: float, w_prime: float,
                 endurance_fatigue_k: float = 0.05,
                 mass: float = 75.0, cda: float = 0.3,
                 crr: float = 0.005):
        """
        Initialize course optimizer with rider parameters.
        
        Args:
            critical_power: Rider's critical power (W)
            w_prime: Rider's anaerobic capacity (J)
            endurance_fatigue_k: Endurance fatigue exponent for efforts > 1 hour.
                Typical values: 0.04 (endurance specialist) to 0.07 (sprinter).
                Default 0.05 (all-rounder).
            mass: Rider/system mass used by the cycling physics model (kg).
            cda: Aerodynamic drag area used by the cycling physics model (m²).
            crr: Rolling resistance coefficient used by the physics model.
        """
        self.critical_power = critical_power
        self.w_prime = w_prime
        self.endurance_k = endurance_fatigue_k
        self.mass = mass
        self.cda = cda
        self.crr = crr

    def _speed_for_power(self, power: float, gradient: float,
                         wind: float = 0, altitude: float = 0) -> float:
        """Calculate steady-state speed with the configured rider physics."""
        try:
            speed_calc = calculate_speed_and_plot(
                power, gradient=gradient, v_wind=wind, altitude=altitude,
                mass=self.mass, CdA=self.cda, Crr=self.crr,
            )
            return speed_calc['speed_mps']
        except Exception:
            return max(
                3.0,
                min(20.0, power / 200.0 + (0.05 - gradient) * 10),
            )

    def _update_w_prime(self, w_remaining: float, power: float,
                        duration: float) -> float:
        """Apply the canonical W' depletion/recovery transition."""
        if power > self.critical_power:
            return w_remaining - (power - self.critical_power) * duration
        return calculate_w_prime_recovery(
            W_prime_max=self.w_prime,
            W_prime_current=w_remaining,
            CP=self.critical_power,
            P_recovery=power,
            recovery_time=duration,
        )

    def max_sustainable_power_for_duration(self, duration_seconds: float) -> float:
        """Return the maximum sustainable average power for a given duration.
        
        Uses the piecewise model:
          t ≤ 3600s: P = CP + W'/t
          t > 3600s: P = CP × (3600/t)^k
        
        This is the power ceiling — the rider cannot average more than this
        over the given duration without exhausting physiological reserves.
        """
        return float(WTankCalculator.piecewise_power_duration(
            duration_seconds, self.critical_power, self.w_prime, self.endurance_k))

    def _estimate_course_duration(self, course_segments: pd.DataFrame,
                                   power_guess: float = None) -> float:
        """Rough estimate of total course duration at a reference power.
        
        Used to determine whether this is a short (< 1h) or long (> 1h) effort,
        which changes the optimization strategy.
        
        Args:
            course_segments: Normalized segments DataFrame.
            power_guess: Power to estimate at. If None, uses CP.
        
        Returns:
            Estimated duration in seconds.
        """
        if power_guess is None:
            power_guess = self.critical_power
        
        total_time = 0
        for _, seg in course_segments.iterrows():
            gradient = seg['gradient']
            distance = seg['distance']
            wind = seg.get('wind', 0)
            altitude = seg.get('altitude', 0)
            try:
                speed = self._speed_for_power(
                    power_guess, gradient, wind, altitude)
            except Exception:
                speed = max(3.0, min(20.0, power_guess / 200.0))
            total_time += distance / max(speed, 1.0)
        return total_time

    def is_long_effort(self, course_segments: pd.DataFrame) -> bool:
        """Return True if estimated duration at CP exceeds 1 hour."""
        segments = self._normalize_segments(course_segments)
        est = self._estimate_course_duration(segments)
        return est > 3600
    
    def _normalize_segments(self, course_segments: pd.DataFrame) -> pd.DataFrame:
        """
        Single ingest boundary — normalize any accepted segment DataFrame
        into the canonical optimization schema.

        Canonical post-normalization schema (downstream code reads only these):
            distance  : float, meters    (required)
            gradient  : float, decimal   (required; e.g. 0.05 == 5%)
            altitude  : float, meters    (optional; defaults to 0 via .get)
            wind      : float, m/s       (auto-added as 0 if missing)

        Accepted input naming conventions (auto-mapped if canonical absent):
            gradient_mean  -> gradient
            distance_sum   -> distance
            altitude_mean  -> altitude

        Accepted input units (converted by schema, not value magnitude):
            gradient_mean: percentage -> decimal
            distance_sum: kilometers -> meters
            gradient and distance: already canonical decimal and meters

        Idempotent: passing an already-canonical DataFrame returns an
        unchanged copy (no double-conversion).

        Args:
            course_segments: DataFrame with either naming convention / units

        Returns:
            DataFrame with canonical column names + units. Original is untouched.
        """
        df = course_segments.copy()
        
        # Map aggregated column names to optimization column names. These
        # aggregate names also identify their units: km and percent.
        column_mappings = {
            'gradient_mean': 'gradient',
            'distance_sum': 'distance',
            'altitude_mean': 'altitude',
        }

        gradient_is_percent = 'gradient' not in df.columns and 'gradient_mean' in df.columns
        distance_is_kilometers = 'distance' not in df.columns and 'distance_sum' in df.columns

        for old_col, new_col in column_mappings.items():
            if old_col in df.columns and new_col not in df.columns:
                df[new_col] = df[old_col]

        if gradient_is_percent:
            df['gradient'] = df['gradient'] / 100
        if distance_is_kilometers:
            df['distance'] = df['distance'] * 1000
        
        # Keep legacy aliases in sync for callers that still expect the
        # aggregated schema. The optimizer reads the canonical columns above;
        # these fields are compatibility mirrors only.
        if 'distance' in df.columns:
            df['distance_sum'] = df['distance'] / 1000
        if 'gradient' in df.columns:
            df['gradient_mean'] = df['gradient'] * 100
        if 'altitude' in df.columns:
            df['altitude_mean'] = df['altitude']
        
        # Ensure wind column exists
        if 'wind' not in df.columns:
            df['wind'] = 0
            
        return df
    
    def _get_segment_value(self, segment, primary_col: str, fallback_col: str = None, default=0):
        """
        Get value from segment, supporting multiple column naming conventions.
        
        This allows the optimizer to work with both:
        - Aggregated segments (gradient_mean, distance_sum, altitude_mean)
        - Optimization-ready segments (gradient, distance, altitude)
        
        Args:
            segment: DataFrame row
            primary_col: Primary column name to try (e.g., 'gradient')
            fallback_col: Fallback column name (e.g., 'gradient_mean')
            default: Default value if neither column exists
        
        Returns:
            Value from the segment
        """
        if primary_col in segment.index:
            return segment[primary_col]
        if fallback_col and fallback_col in segment.index:
            value = segment[fallback_col]
            # Handle gradient conversion: if stored as percentage (>1), convert to decimal
            if 'gradient' in primary_col and abs(value) > 1:
                return value / 100
            return value
        return default
    
    def simulate_course_time(self, power: float, course_segments: pd.DataFrame) -> Tuple[pd.DataFrame, float, float, float]:
        """
        Simulate course time and W' usage for a given constant power.
        
        This function calculates the time to complete each segment at a constant power,
        tracking W' depletion and recovery throughout the course.
        
        Args:
            power: Constant power output (W)
            course_segments: DataFrame containing segment data with columns:
                - gradient/gradient_mean: Segment gradient (decimal or percentage)
                - distance/distance_sum: Segment distance (meters or km)
                - wind: Wind speed (m/s, positive = tailwind)
                - altitude/altitude_mean: Segment altitude (meters)
        
        Returns:
            Tuple containing:
            - DataFrame with segment-by-segment results
            - Total course time (seconds)
            - Remaining W' at finish (J)
            - Total energy used (J)
        """
        # Normalize column names to handle both aggregated and optimization-ready formats
        segments = self._normalize_segments(course_segments)
        
        total_time = 0
        w_remaining = self.w_prime
        total_energy_used = 0
        results = []
        
        for _, segment in segments.iterrows():
            gradient = segment['gradient']
            length = segment['distance']
            wind = segment.get('wind', 0)
            altitude = segment.get('altitude', 0)
            
            # Calculate speed for the given power using physics model
            try:
                speed = self._speed_for_power(power, gradient, wind, altitude)
            except Exception as e:
                # Fallback speed calculation if physics model fails
                print(f"Warning: Physics calculation failed for segment {segment.name}: {e}")
                # Simple fallback: assume reasonable speed based on power
                speed = max(5.0, min(20.0, power / 200.0))  # Basic speed estimate
            
            # Calculate time for this segment
            time = length / speed
            total_time += time
            
            # Track W' usage and recovery
            w_remaining = self._update_w_prime(w_remaining, power, time)
            if w_remaining < 0:
                return pd.DataFrame(results), float('inf'), w_remaining, total_energy_used
            
            # Track total energy expenditure
            total_energy_used += power * time
            
            # Store results for this segment
            results.append({
                'segment': segment.name if hasattr(segment, 'name') else len(results),
                'gradient': gradient,
                'gradient_mean': gradient * 100,
                'length': length,
                'distance': length,
                'distance_sum': length / 1000,
                'wind': wind,
                'altitude': altitude,
                'altitude_mean': altitude,
                'speed': speed,
                'time': time,
                'power': power,
                'w_remaining': w_remaining,                'total_energy_used': total_energy_used
            })
        
        return pd.DataFrame(results), total_time, w_remaining, total_energy_used
    
    def optimize_constant_power(self, course_segments: pd.DataFrame, target_w_utilization: float = 0.85) -> Tuple[float, float, pd.DataFrame]:
        """
        Find the optimal constant power that strategically depletes the W' tank.
        
        This optimization finds a power level that minimizes time while targeting
        a specific W' utilization level (default 85% depletion for aggressive pacing).
        
        Args:
            course_segments: DataFrame containing course segment data
            target_w_utilization: Target W' utilization (0.0-1.0, default 0.85 = 85% depletion)
        
        Returns:
            Tuple containing:
            - Optimal power (W)
            - Total course time at optimal power (seconds)
            - DataFrame with segment-by-segment results at optimal power
        """
        
        def objective(power: float) -> float:
            """Objective function: minimize time while targeting W' utilization"""
            try:
                _, total_time, w_remaining, _ = self.simulate_course_time(power, course_segments)
                
                # If simulation failed (W' depleted), return very high penalty based on power level
                if total_time == float('inf') or total_time > 1e6:
                    # Penalty increases with power level to guide optimization away from impossible powers
                    power_penalty = (power - self.critical_power) ** 2
                    return 1e6 + power_penalty
                
                # Ensure we have valid numbers
                if not np.isfinite(total_time) or not np.isfinite(w_remaining):
                    return 1e6 + (power - self.critical_power) ** 2
                
                # Calculate W' utilization
                w_used = self.w_prime - w_remaining
                w_utilization = w_used / self.w_prime
                
                # Strong penalty for not using enough W' (undertrained) or using too much (unsustainable)
                w_penalty = abs(w_utilization - target_w_utilization) * total_time * w_penalty_weight
                
                # Heavily penalize finishing with too much W' remaining (inefficient)
                if w_utilization < target_w_utilization * 0.7:  # Less than 70% of target
                    w_penalty *= 5  # Strong penalty for conservative pacing
                
                # Return time plus W' utilization penalty
                return total_time + w_penalty
                
            except Exception as e:
                print(f"Warning: Optimization objective failed at power {power}: {e}")
                return 1e6 + (power - self.critical_power) ** 2        
        # Set optimization bounds based on estimated effort duration.
        # For short efforts (<1h), power is above CP.
        # For long efforts (>1h), optimal constant power may be below CP.
        segments_norm = self._normalize_segments(course_segments)
        est_duration = self._estimate_course_duration(segments_norm)
        power_ceiling = self.max_sustainable_power_for_duration(est_duration)
        
        if est_duration > 3600:
            # Long effort: allow sub-CP power down to the 4-hour ceiling
            floor_power = self.max_sustainable_power_for_duration(14400)  # 4h floor
            lower_bound = max(floor_power * 0.95, 100)
            upper_bound = min(self.critical_power * 1.5, 600)
            # For long efforts, reduce W' penalty weight (W' less relevant)
            w_penalty_weight = max(0.02, 0.1 * (3600 / est_duration))
            print(f"Long effort detected: est. {est_duration/60:.0f} min, "
                  f"power ceiling {power_ceiling:.0f}W, bounds [{lower_bound:.0f}, {upper_bound:.0f}]")
        else:
            lower_bound = max(self.critical_power * 0.9, 150)
            upper_bound = min(self.critical_power * 2.0, 500)
            w_penalty_weight = 0.1
        
        bounds = [(lower_bound, upper_bound)]
        
        # Start optimization from a reasonable power level
        initial_power = min(power_ceiling * 1.02, upper_bound)
        
        try:
            # Run optimization with multiple starting points to avoid local minima
            best_result = None
            best_objective = float('inf')
            
            # Try multiple starting points within reasonable range
            if est_duration > 3600:
                # Long effort: search around and below CP
                start_powers = [
                    max(power_ceiling * 0.98, lower_bound),      # Just below ceiling
                    max(self.critical_power * 0.95, lower_bound), # Sub-CP
                    min(self.critical_power * 1.05, upper_bound), # Just above CP
                ]
            else:
                start_powers = [
                    max(self.critical_power * 1.05, lower_bound),  # Just above CP
                    min(self.critical_power * 1.2, upper_bound),   # Moderate
                    min(self.critical_power * 1.4, upper_bound),   # Aggressive
                ]
            
            for start_power in start_powers:
                if lower_bound <= start_power <= upper_bound:
                    result = minimize(
                        lambda p: objective(p[0]), 
                        x0=[start_power], 
                        bounds=bounds, 
                        method='L-BFGS-B',
                        options={'ftol': 1e-6, 'gtol': 1e-6, 'maxiter': 100}
                    )
                    
                    if result.success and result.fun < best_objective and np.isfinite(result.fun):
                        best_result = result
                        best_objective = result.fun            
            if best_result and best_result.success and np.isfinite(best_result.fun):
                optimal_power = best_result.x[0]
                print(f"Optimization converged to {optimal_power:.0f}W (target W' utilization: {target_w_utilization*100:.0f}%)")
            else:
                print(f"Optimization failed, using intelligent fallback strategy")
                # Intelligent fallback: find highest sustainable power
                test_powers = np.linspace(lower_bound, upper_bound, 20)
                best_power = lower_bound
                best_score = float('inf')
                
                for test_power in test_powers:
                    score = objective(test_power)
                    if score < best_score and np.isfinite(score):
                        best_power = test_power
                        best_score = score
                
                optimal_power = best_power
                print(f"Fallback found power: {optimal_power:.0f}W")                
        except Exception as e:
            print(f"Optimization error: {e}")
            # Conservative fallback
            optimal_power = min(self.critical_power * 1.1, upper_bound)
        
        # Ensure optimal_power is within reasonable bounds
        optimal_power = max(lower_bound, min(optimal_power, upper_bound))
        
        # Get detailed results at optimal power
        df_results, optimal_time, w_remaining, total_energy = self.simulate_course_time(
            optimal_power, course_segments
        )
        
        # Handle infinite time case
        if optimal_time == float('inf') or not np.isfinite(optimal_time):
            print(f"Warning: Optimal power {optimal_power:.0f}W results in course failure")
            # Try a more conservative power
            conservative_power = self.critical_power * 1.05
            df_results, optimal_time, w_remaining, total_energy = self.simulate_course_time(
                conservative_power, course_segments
            )
            if optimal_time != float('inf') and np.isfinite(optimal_time):
                optimal_power = conservative_power
                print(f"Using conservative fallback: {optimal_power:.0f}W")
        
        # Report W' utilization achieved
        w_used = self.w_prime - w_remaining
        w_utilization_achieved = w_used / self.w_prime
        print(f"Achieved W' utilization: {w_utilization_achieved*100:.1f}% (target: {target_w_utilization*100:.0f}%)")
        
        return optimal_power, optimal_time, df_results
    
    def optimize_variable_pacing(self, course_segments: pd.DataFrame,
                                target_w_utilization: float = W_PRIME_BUDGET_CEILING,
                                aggressive_factor: float = 1.2,
                                baseline_power: float = None) -> Tuple[pd.DataFrame, float, Dict[str, Any]]:
        """
        Optimize variable power pacing across course segments for minimal time.

        Args:
            course_segments: DataFrame containing segment data (either aggregated or optimization-ready)
            target_w_utilization: W' budget ceiling (0.0-1.0); variable may use UP TO this much.
                                  Defaults to W_PRIME_BUDGET_CEILING (0.90). Not an exact target.
            aggressive_factor: How aggressive to be on climbs (1.0=CP, 1.5=very aggressive)
            baseline_power: Optimal constant power for this course (watts). Used to anchor the
                            heuristic and as a guaranteed-feasible fallback. Defaults to CP.

        Returns:
            Tuple containing:
            - DataFrame with segment-by-segment power strategy and results
            - Total course time (seconds)
            - Dictionary with strategy analysis and comparison to constant power
        """
        print(f"Optimizing variable pacing strategy (W' ceiling: {target_w_utilization*100:.0f}%)")

        # Normalize column names to handle both aggregated and optimization-ready formats
        course_segments = self._normalize_segments(course_segments)

        # Default baseline to CP when not provided (e.g. called directly in tests)
        if baseline_power is None:
            baseline_power = self.critical_power

        # Step 1: Analyze course characteristics
        course_analysis = self._analyze_course_terrain(course_segments)

        # Step 2: Generate initial heuristic power allocation anchored to baseline_power
        initial_power_strategy = self._generate_heuristic_power_strategy(
            course_segments, course_analysis, target_w_utilization, aggressive_factor,
            baseline_power=baseline_power
        )

        # Step 3: Simulate initial strategy to check feasibility
        strategy_results = self._simulate_variable_pacing(course_segments, initial_power_strategy)

        # Step 4: Local optimization to refine strategy.
        #
        # Always refine FROM the gradient-shaped heuristic, even when it is
        # infeasible. The refiner (`_refine_cluster_strategy`) enforces
        # feasibility internally (infeasible points get a large penalty) and
        # always includes a guaranteed-feasible uniform-baseline seed, so it can
        # never return something worse than constant power. Critically, the
        # heuristic's per-segment gradient SHAPE is what L-BFGS-B polishes into
        # the optimal redistribution — discarding it for a flat "conservative"
        # seed (the old behaviour) collapsed many-segment TERRAIN courses back to
        # constant power even when a faster varied strategy existed.
        if not strategy_results['feasible']:
            print("Initial heuristic over-spends W' — refining from its gradient "
                  "shape anyway (refiner enforces feasibility)")
        optimized_strategy = self._refine_power_strategy(
            course_segments, initial_power_strategy, target_w_utilization,
            baseline_power=baseline_power
        )
        final_results = self._simulate_variable_pacing(course_segments, optimized_strategy)
        if not final_results['feasible']:
            # Last-resort clamp to the guaranteed-feasible flat baseline.
            optimized_strategy = np.full(len(course_segments), baseline_power)
            final_results = self._simulate_variable_pacing(course_segments, optimized_strategy)

        # Safety net: if variable is slower than uniform baseline, use baseline.
        # This guarantees variable pacing is never worse than constant power.
        uniform = np.full(len(course_segments), baseline_power)
        uniform_sim = self._simulate_variable_pacing(course_segments, uniform)
        if uniform_sim['feasible'] and uniform_sim['total_time'] < final_results['total_time']:
            print(f"Safety net: uniform {baseline_power:.0f}W "
                  f"({uniform_sim['total_time']/60:.1f} min) faster than variable "
                  f"({final_results['total_time']/60:.1f} min); using uniform.")
            optimized_strategy = uniform
            final_results = uniform_sim
        
        # Step 5: Create detailed results DataFrame
        results_df = self._create_variable_pacing_results(
            course_segments, optimized_strategy, final_results
        )
        
        # Step 6: Generate strategy analysis and comparison
        strategy_analysis = self._analyze_variable_pacing_strategy(
            course_segments, results_df, final_results
        )
        
        total_time = final_results['total_time']
        
        print(f"Variable pacing complete: {total_time/60:.1f} min "
              f"(W' utilization: {final_results['w_utilization']*100:.1f}%)")
        
        return results_df, total_time, strategy_analysis
    
    def _analyze_course_terrain(self, course_segments: pd.DataFrame) -> Dict[str, Any]:
        """Analyze course terrain characteristics for power allocation strategy."""
        total_distance = course_segments['distance'].sum()
        total_elevation_gain = course_segments[course_segments['gradient'] > 0]['distance'].multiply(
            course_segments[course_segments['gradient'] > 0]['gradient']
        ).sum()
        
        # Categorize segments by terrain type
        climb_threshold = 0.03  # 3% gradient
        descent_threshold = -0.02  # -2% gradient
        
        climbing_segments = course_segments['gradient'] > climb_threshold
        flat_segments = (course_segments['gradient'] >= descent_threshold) & (course_segments['gradient'] <= climb_threshold)
        descent_segments = course_segments['gradient'] < descent_threshold
        
        climb_distance = course_segments[climbing_segments]['distance'].sum()
        flat_distance = course_segments[flat_segments]['distance'].sum()
        descent_distance = course_segments[descent_segments]['distance'].sum()
        
        return {
            'total_distance': total_distance,
            'total_elevation_gain': total_elevation_gain,
            'climb_distance': climb_distance,
            'flat_distance': flat_distance,
            'descent_distance': descent_distance,
            'climbing_segments': climbing_segments,
            'flat_segments': flat_segments,            'descent_segments': descent_segments,
            'climb_percentage': climb_distance / total_distance * 100,
            'difficulty_score': total_elevation_gain / (total_distance / 1000)  # m gain per km
        }
    
    def _generate_heuristic_power_strategy(self, course_segments: pd.DataFrame,
                                         course_analysis: Dict[str, Any],
                                         target_w_utilization: float,
                                         aggressive_factor: float,
                                         baseline_power: float = None) -> np.ndarray:
        """
        Generate initial power strategy using per-cluster-type power assignment.

        When segments carry a segment_id (from clustering or terrain segmentation),
        every segment of the same type gets the *same* power value.  This makes the
        rider's instructions simple: "Cluster 1 (uphills): 330 W, Cluster 2 (flats):
        290 W, …".

        For legacy (equal) segmentation without segment_id the old continuous
        gradient-based approach is used as a fallback.
        """
        # Target W' budget
        target_w_to_use = self.w_prime * target_w_utilization

        if baseline_power is None:
            baseline_power = self.critical_power

        # ---------- Cluster-aware path ----------
        if _has_cluster_info(course_segments):
            return self._generate_cluster_heuristic(
                course_segments, target_w_to_use, aggressive_factor,
                baseline_power=baseline_power)

        # ---------- Legacy per-segment fallback (equal segmentation) ----------
        return self._generate_per_segment_heuristic(
            course_segments, target_w_to_use, aggressive_factor)

    # ------------------------------------------------------------------ #
    #  Cluster-aware heuristic (NEW)                                       #
    # ------------------------------------------------------------------ #
    def _generate_cluster_heuristic(self, course_segments: pd.DataFrame,
                                    target_w_to_use: float,
                                    aggressive_factor: float,
                                    baseline_power: float = None) -> np.ndarray:
        """Per-cluster-type power assignment.

        Duration-aware: for long efforts (>1h), scales base power below CP
        using the piecewise power-duration ceiling.  W' budget is only spent
        on steep climb clusters where the time savings are greatest.

        For short efforts, anchors base/recovery to `baseline_power` (the optimal
        constant power) so recovery clusters ride near the constant benchmark rather
        than an arbitrary CP×0.85 that may be well below optimal.
        """
        segment_ids = course_segments['segment_id']
        gradients = course_segments['gradient'].values
        distances = course_segments['distance'].values

        if baseline_power is None:
            baseline_power = self.critical_power

        # Estimate effort duration to determine short vs long regime
        est_duration = self._estimate_course_duration(course_segments)
        is_long = est_duration > 3600
        # For long efforts, base_power drops below CP via piecewise model.
        # For short efforts, anchor to the optimal constant power so recovery
        # clusters don't ride below the constant benchmark.
        if is_long:
            base_power = self.max_sustainable_power_for_duration(est_duration)
        else:
            base_power = baseline_power

        if is_long:
            print(f"Long-effort heuristic: est. {est_duration/60:.0f} min, "
                  f"base power {base_power:.0f} W (CP={self.critical_power:.0f})")

        # Per-cluster stats
        cluster_stats: Dict[int, Dict[str, float]] = {}
        for cid in segment_ids.unique():
            mask = segment_ids == cid
            c_grads = gradients[mask]
            c_dists = distances[mask]
            mean_grad = float(np.mean(c_grads))
            total_dist = float(np.sum(c_dists))
            # Rough time estimate at base power
            est_speed = max(3.0, 12.0 - mean_grad * 80)
            est_time = total_dist / est_speed
            cluster_stats[cid] = {
                'mean_gradient': mean_grad,
                'total_distance': total_dist,
                'est_time': est_time,
            }

        # ---------- RELATIVE gradient classification ----------
        # The key constraint: W' recovery requires power *meaningfully* below
        # CP (Skiba model: tau = 2287 * DCP^-0.69, so DCP < 15 W → tau > 300 s
        # → negligible recovery).  We therefore need enough course distance in
        # recovery clusters, with power far enough below CP, for the depletion/
        # recovery cycle to actually work.  Target: ≥ 35-40 % of clusters as
        # recovery.
        cluster_grads = np.array([v['mean_gradient'] for v in cluster_stats.values()])
        cluster_ids_sorted = sorted(cluster_stats, key=lambda k: cluster_stats[k]['mean_gradient'])
        grad_range = float(cluster_grads.max() - cluster_grads.min())

        # Always use a relative (median-based) threshold to guarantee a
        # meaningful effort/recovery split regardless of absolute gradients.
        # On truly flat courses grad_range ≈ 0, but the median still splits
        # clusters into halves which is the best we can do.
        if len(cluster_grads) >= 2:
            median_grad = float(np.median(cluster_grads))
            # For long efforts, bias effort threshold slightly above median
            # so only the steepest clusters get W' budget
            if is_long:
                effort_threshold = max(median_grad + 0.005, 0.02)
            else:
                effort_threshold = median_grad
        else:
            effort_threshold = 0.0 if not is_long else 0.02

        effort_clusters = {k: v for k, v in cluster_stats.items()
                          if v['mean_gradient'] > effort_threshold}
        recovery_clusters = {k: v for k, v in cluster_stats.items()
                            if v['mean_gradient'] <= effort_threshold}

        # Guarantee minimum representation of each type (≥ 35 % of clusters)
        min_recovery_count = max(1, len(cluster_ids_sorted) * 35 // 100)
        if len(recovery_clusters) < min_recovery_count and len(cluster_stats) > 1:
            # Promote the gentlest clusters until we hit the minimum
            for cid in cluster_ids_sorted:
                if len(recovery_clusters) >= min_recovery_count:
                    break
                if cid not in recovery_clusters:
                    recovery_clusters[cid] = cluster_stats[cid]
                    effort_clusters.pop(cid, None)
        if not effort_clusters and len(cluster_stats) > 1:
            steepest = cluster_ids_sorted[-1]
            effort_clusters[steepest] = cluster_stats[steepest]
            recovery_clusters.pop(steepest, None)

        # Scale W' budget by terrain variation — when all clusters have similar
        # gradients, variable pacing offers diminishing returns over constant.
        # grad_range ~0 ⇒ factor ~0.3, grad_range ≥ 0.06 ⇒ factor = 1.0
        terrain_variation_factor = min(1.0, 0.3 + 0.7 * (grad_range / 0.06))
        adjusted_w_to_use = target_w_to_use * terrain_variation_factor

        # --- Distribute W' across effort clusters weighted by gradient × time ---
        effort_weights = {}
        for cid, stats in effort_clusters.items():
            resistance = stats['mean_gradient'] + 0.01
            effort_weights[cid] = max(resistance, 0.001) * stats['est_time']
        weight_sum = sum(effort_weights.values()) or 1.0

        # Power limits — tighter for long efforts
        if is_long:
            max_power = self.critical_power * min(1.4, 1.0 + aggressive_factor * 0.2)
            min_recovery = base_power * 0.70
        else:
            max_power = self.critical_power * min(1.8, 1.0 + aggressive_factor * 0.35)
            # Recovery floor: far enough below base_power for Skiba W' recovery to work.
            # base_power = baseline_power (optimal constant) for short efforts.
            min_recovery = base_power * 0.65

        cluster_power_map: Dict[int, float] = {}

        for cid, stats in effort_clusters.items():
            frac = effort_weights[cid] / weight_sum
            w_budget = adjusted_w_to_use * frac
            w_contribution = w_budget / max(stats['est_time'], 1.0)
            power = base_power + w_contribution
            cluster_power_map[cid] = min(power, max_power)

        for cid, stats in recovery_clusters.items():
            mean_grad = stats['mean_gradient']
            if mean_grad > 0.01:
                # Uphill recovery: ride near baseline to limit time cost.
                if is_long:
                    power = base_power * 0.92
                else:
                    power = base_power * 0.92
            elif mean_grad < -0.02:
                # Downhill: speed is high anyway, deep recovery is cheap in time.
                depth = min(abs(mean_grad) / 0.08, 1.0)
                if is_long:
                    power = base_power * (0.88 - depth * 0.18)
                else:
                    power = base_power * (0.88 - depth * 0.18)
            else:
                # Flat / false-flat: moderate recovery below baseline.
                if is_long:
                    power = base_power * 0.90
                else:
                    power = base_power * 0.88
            cluster_power_map[cid] = max(power, min_recovery)

        print(f"Cluster heuristic — {len(effort_clusters)} effort / "
              f"{len(recovery_clusters)} recovery clusters "
              f"(terrain variation: {terrain_variation_factor:.0%}, "
              f"W' budget: {adjusted_w_to_use:.0f}J of {target_w_to_use:.0f}J)")
        for cid in sorted(cluster_power_map):
            g = cluster_stats[cid]['mean_gradient']
            p = cluster_power_map[cid]
            label = "effort" if cid in effort_clusters else "recovery"
            print(f"  Cluster {cid} ({label}, grad={g*100:.1f}%): {p:.0f} W")

        return _expand_cluster_powers(cluster_power_map, segment_ids)

    # ------------------------------------------------------------------ #
    #  Legacy per-segment heuristic (unchanged logic, extracted)            #
    # ------------------------------------------------------------------ #
    def _generate_per_segment_heuristic(self, course_segments: pd.DataFrame,
                                        target_w_to_use: float,
                                        aggressive_factor: float) -> np.ndarray:
        """Gradient-based continuous power mapping for equal-segment mode.

        Duration-aware: for long efforts (> 1 h), base power drops below CP
        following the piecewise power-duration model and W' budget is allocated
        more conservatively (only steep climbs warrant above-CP surges).
        """
        num_segments = len(course_segments)
        power_strategy = np.zeros(num_segments)
        gradients = course_segments['gradient'].values
        distances = course_segments['distance'].values

        # --- Duration awareness ---
        est_duration = self._estimate_course_duration(course_segments)
        is_long = est_duration > 3600
        base_power = (self.max_sustainable_power_for_duration(est_duration)
                      if is_long else self.critical_power)

        resistance_scores = gradients + 0.01
        # Long efforts: only truly steep segments get W' budget
        effort_threshold = 0.02 if is_long else 0.0
        above_cp_mask = resistance_scores > effort_threshold
        
        segment_estimated_times = np.zeros(num_segments)
        for i in range(num_segments):
            est_speed = max(3.0, 12.0 - gradients[i] * 80)
            segment_estimated_times[i] = distances[i] / est_speed

        total_above_cp_time = segment_estimated_times[above_cp_mask].sum()

        if is_long:
            max_power = self.critical_power * min(1.4, 1.0 + aggressive_factor * 0.20)
        else:
            max_power = self.critical_power * min(1.5, 1.0 + aggressive_factor * 0.25)

        if total_above_cp_time > 0:
            above_cp_weights = np.where(
                above_cp_mask,
                resistance_scores * segment_estimated_times, 0.0)
            weight_sum = above_cp_weights.sum()
            if weight_sum > 0:
                above_cp_weights /= weight_sum

            for i in range(num_segments):
                if above_cp_mask[i]:
                    seg_w_budget = target_w_to_use * above_cp_weights[i]
                    seg_time = segment_estimated_times[i]
                    w_contribution = seg_w_budget / max(seg_time, 1.0)
                    seg_power = base_power + w_contribution
                    power_strategy[i] = min(seg_power, max_power)
                else:
                    depth = min(abs(gradients[i]) / 0.08, 1.0)
                    if is_long:
                        # Long effort: recover near base_power
                        power_strategy[i] = base_power * (0.97 - depth * 0.15)
                    else:
                        # Keep recovery near CP (0.88-0.98×CP) for per-segment mode
                        power_strategy[i] = self.critical_power * (0.98 - depth * 0.10)
        else:
            power_strategy[:] = base_power * 1.02

        return power_strategy
    
    def _calculate_max_sustainable_power(self, distance: float, gradient: float, 
                                       w_budget: float) -> float:
        """Calculate maximum sustainable power for a segment given W' budget."""
        # Estimate time for segment at critical power
        estimated_speed = 8.0 + (0.05 - gradient) * 20  # Rough speed estimate
        estimated_time = distance / max(estimated_speed, 2.0)  # Minimum 2 m/s
        
        # Calculate max power based on W' budget
        if estimated_time > 0:
            max_power = self.critical_power + (w_budget / estimated_time)
            return min(max_power, self.critical_power * 2.0)  # Reasonable upper limit
        else:
            return self.critical_power
    
    def _simulate_variable_pacing(self, course_segments: pd.DataFrame, 
                                power_strategy: np.ndarray) -> Dict[str, Any]:
        """Simulate variable pacing strategy and return detailed results."""
        total_time = 0
        w_remaining = self.w_prime
        total_energy_used = 0
        segment_results = []
        feasible = True
        
        for i, (_, segment) in enumerate(course_segments.iterrows()):
            power = power_strategy[i]
            gradient = segment['gradient']
            length = segment['distance']
            wind = segment.get('wind', 0)
            altitude = segment.get('altitude', 0)
            
            # Calculate speed using physics model
            try:
                speed = self._speed_for_power(power, gradient, wind, altitude)
            except Exception:
                # Fallback speed calculation
                speed = max(3.0, min(20.0, power / 200.0 + (1 - gradient) * 10))
            
            # Calculate time for this segment
            time = length / speed
            total_time += time
            
            # Track W' usage and recovery
            w_remaining = self._update_w_prime(w_remaining, power, time)
            if w_remaining < 0:
                feasible = False
            
            total_energy_used += power * time
            
            segment_results.append({
                'segment_index': i,
                'power': power,
                'speed': speed,
                'time': time,
                'w_remaining': w_remaining,
                'w_used_segment': max(0, (power - self.critical_power) * time),
                'gradient': gradient,
                'distance': length            })
        
        # Calculate final utilization
        w_utilization = (self.w_prime - w_remaining) / self.w_prime
        
        return {
            'total_time': total_time,            'final_w_remaining': w_remaining,
            'w_utilization': w_utilization,
            'total_energy_used': total_energy_used,
            'segment_results': segment_results,
            'feasible': feasible
        }
    
    def _refine_power_strategy(self, course_segments: pd.DataFrame,
                             initial_strategy: np.ndarray,
                             target_w_utilization: float,
                             baseline_power: float = None) -> np.ndarray:
        """Refine power strategy — cluster-aware or per-segment fallback.

        Cluster-aware: uses scipy.optimize.minimize over N_cluster variables.
        Legacy: iterative scaling with wider bounds than before.
        """
        if _has_cluster_info(course_segments):
            return self._refine_cluster_strategy(
                course_segments, initial_strategy, target_w_utilization,
                baseline_power=baseline_power)
        return self._refine_per_segment_strategy(
            course_segments, initial_strategy, target_w_utilization)

    # ------------------------------------------------------------------ #
    #  Cluster-aware refinement (NEW — scipy minimizer)                    #
    # ------------------------------------------------------------------ #
    def _refine_cluster_strategy(self, course_segments: pd.DataFrame,
                                 initial_strategy: np.ndarray,
                                 target_w_utilization: float,
                                 baseline_power: float = None) -> np.ndarray:
        """Optimise N_cluster power values to minimise total course time.

        Objective: minimise time subject to:
          - W' never goes negative mid-course (feasibility)
          - Final W' >= (1 - target_w_utilization) * W' (budget ceiling)

        Seeds include a uniform-baseline_power candidate, which guarantees the
        optimizer always has a feasible starting point that matches constant power.
        """
        segment_ids = course_segments['segment_id']
        unique_ids = sorted(segment_ids.unique())
        n_clusters = len(unique_ids)
        id_to_idx = {cid: i for i, cid in enumerate(unique_ids)}

        if baseline_power is None:
            baseline_power = self.critical_power

        # Initial cluster powers from heuristic
        initial_map = _cluster_power_map_from_array(initial_strategy, segment_ids)
        x0 = np.array([initial_map[cid] for cid in unique_ids])

        # Bounds per cluster: duration-aware range
        est_duration = self._estimate_course_duration(course_segments)
        is_long = est_duration > 3600
        if is_long:
            base_power = self.max_sustainable_power_for_duration(est_duration)
            max_power = self.critical_power * 1.4
            min_power = base_power * 0.70
        else:
            max_power = self.critical_power * 1.8
            min_power = self.critical_power * 0.55
        bounds = [(min_power, max_power)] * n_clusters

        # W' remaining must be at least this much at finish (budget ceiling)
        floor_w = self.w_prime * (1.0 - target_w_utilization)

        best_result = {'time': float('inf'), 'strategy': initial_strategy.copy()}

        def objective(x):
            cmap = {cid: x[id_to_idx[cid]] for cid in unique_ids}
            power_array = _expand_cluster_powers(cmap, segment_ids)
            sim = self._simulate_variable_pacing(course_segments, power_array)

            # Penalise infeasibility (W' went negative mid-course)
            if not sim['feasible']:
                deficit = abs(sim['final_w_remaining'])
                score = 1e6 + deficit * 100
                return score

            score = sim['total_time']

            # Penalise over-spending W' beyond the budget ceiling
            if sim['final_w_remaining'] < floor_w:
                over = floor_w - sim['final_w_remaining']
                score += over * 0.5  # gentle penalty per joule over budget

            if score < best_result['time']:
                best_result['time'] = score
                best_result['strategy'] = power_array.copy()

            return score

        from scipy.optimize import minimize as sp_minimize
        rng = np.random.default_rng(42)

        # --- Build seed starting points ---
        # 1. Heuristic vector
        starts = [x0]

        # 2. Uniform baseline_power — guaranteed feasible, matches constant pacing.
        #    Provides a provably-good floor the optimizer must beat.
        starts.append(np.full(n_clusters, baseline_power))

        # 3. Spread: exaggerate heuristic differences to help escape flat local minimum
        if n_clusters >= 2:
            mean_x0 = np.mean(x0)
            spread = mean_x0 + (x0 - mean_x0) * 1.5
            starts.append(np.clip(spread, min_power, max_power))

        # 4. Three jittered variants around the heuristic
        for _ in range(3):
            jitter = x0 + rng.normal(0, self.critical_power * 0.05, n_clusters)
            starts.append(np.clip(jitter, min_power, max_power))

        # 5. Push-climbs: steep clusters at max_power, others at baseline_power.
        #    Explores the extreme end of the W'-expenditure spectrum.
        if n_clusters >= 2:
            cluster_grads = {}
            for cid in unique_ids:
                mask = segment_ids == cid
                cluster_grads[cid] = float(course_segments.loc[mask, 'gradient'].mean())
            push = np.array([
                max_power if cluster_grads[cid] > 0.0 else baseline_power
                for cid in unique_ids
            ])
            starts.append(np.clip(push, min_power, max_power))

        # 6. Coarse grid pre-search (only viable for a handful of clusters).
        #    L-BFGS-B is a LOCAL optimizer; with a flat/adverse gradient near the
        #    uniform solution it can miss a much faster varied strategy entirely
        #    (e.g. push the one steep wall hard, ease on the gentle remainder).
        #    An exhaustive coarse sweep guarantees we discover that basin, then we
        #    polish the best grid point with L-BFGS-B below. objective() captures
        #    the best feasible point via side effect, so simply evaluating each
        #    grid node already protects against missing it.
        if n_clusters <= 3:
            grid = np.linspace(min_power, max_power, 11)
            grid_best = {'score': float('inf'), 'x': None}
            for combo in itertools.product(grid, repeat=n_clusters):
                x = np.array(combo)
                score = objective(x)  # side effect updates best_result
                if score < grid_best['score']:
                    grid_best['score'] = score
                    grid_best['x'] = x
            if grid_best['x'] is not None:
                starts.append(grid_best['x'])  # polish the grid optimum

        # 7. Coordinated gradient-tilt line search for MANY segments (terrain mode).
        #    Terrain segmentation gives each contiguous segment a unique
        #    segment_id, so n_clusters can be 10-20+ and the full Cartesian grid
        #    in (6) is impossible (grid^N). Pure coordinate descent ALSO fails
        #    here: at the W' budget ceiling there is no headroom, so changing one
        #    segment at a time is always rejected (raise -> infeasible, lower ->
        #    slower). The winning move is SIMULTANEOUS — push the climbs and ease
        #    the descents/flats so the redistribution is roughly W'-neutral. We
        #    parametrise that single coordinated move by a scalar `alpha` and line
        #    search it: x(alpha) = baseline + alpha * tilt, where tilt pushes
        #    steep segments up and shallow/▼ segments down (zero-mean by distance
        #    so total work stays comparable). objective() captures the best
        #    feasible point via side effect; we also append the best alpha and a
        #    coordinate-descent polish of it.
        if n_clusters > 3:
            grads = np.array([
                float(course_segments.loc[segment_ids == cid, 'gradient'].mean())
                for cid in unique_ids
            ])
            dists = np.array([
                float(course_segments.loc[segment_ids == cid, 'distance'].sum())
                for cid in unique_ids
            ])
            w = dists / dists.sum() if dists.sum() > 0 else np.ones(n_clusters) / n_clusters
            tilt = grads - np.average(grads, weights=w)   # distance-weighted zero-mean
            scale = np.abs(tilt).max()
            if scale > 1e-9:
                tilt = tilt / scale                       # unit-scaled climb/descent signal
                power_span = max_power - baseline_power
                best_tilt = {'score': float('inf'), 'x': None}
                for alpha in np.linspace(0.0, power_span, 25):
                    x = np.clip(baseline_power + alpha * tilt, min_power, max_power)
                    s = objective(x)                      # side effect updates best_result
                    if s < best_tilt['score']:
                        best_tilt['score'], best_tilt['x'] = s, x.copy()

                # Coordinate-descent polish around the best coordinated move.
                if best_tilt['x'] is not None:
                    x_cd = best_tilt['x'].copy()
                    best_cd_score = best_tilt['score']
                    cd_grid = np.linspace(min_power, max_power, 13)
                    for _pass in range(2):
                        improved = False
                        for j in range(n_clusters):
                            saved, local_best_score = x_cd[j], best_cd_score
                            for p in cd_grid:
                                x_cd[j] = p
                                if objective(x_cd) < local_best_score:
                                    local_best_score, saved = objective(x_cd), p
                            x_cd[j] = saved
                            if local_best_score < best_cd_score - 1e-6:
                                best_cd_score, improved = local_best_score, True
                        if not improved:
                            break
                    starts.append(x_cd.copy())

        for start in starts:
            try:
                sp_minimize(objective, start, method='L-BFGS-B',
                            bounds=bounds, options={'maxiter': 80, 'ftol': 0.05})
            except Exception:
                pass  # best_result updated via side effect in objective

        # Log final cluster powers
        final_map = _cluster_power_map_from_array(best_result['strategy'], segment_ids)
        sim = self._simulate_variable_pacing(course_segments, best_result['strategy'])
        print(f"Cluster refinement → {sim['total_time']/60:.1f} min, "
              f"W' util: {sim['w_utilization']*100:.1f}%")
        for cid in unique_ids:
            print(f"  Cluster {cid}: {final_map[cid]:.0f} W")

        return best_result['strategy']

    # ------------------------------------------------------------------ #
    #  Legacy per-segment refinement (kept for equal-segment mode)          #
    # ------------------------------------------------------------------ #
    def _refine_per_segment_strategy(self, course_segments: pd.DataFrame,
                                     initial_strategy: np.ndarray,
                                     target_w_utilization: float) -> np.ndarray:
        """Iterative per-segment refinement with wider dynamic range.

        Duration-aware: long efforts use sub-CP base power, tighter bounds,
        and recovery targets near the piecewise-model ceiling rather than CP.
        """
        current_strategy = initial_strategy.copy()
        best_strategy = current_strategy.copy()
        gradients = course_segments['gradient'].values

        est_duration = self._estimate_course_duration(course_segments)
        is_long = est_duration > 3600

        if is_long:
            base_power = self.max_sustainable_power_for_duration(est_duration)
            max_power = self.critical_power * 1.4
            min_recovery = base_power * 0.70
        else:
            base_power = self.critical_power
            max_power = self.critical_power * 1.5
            min_recovery = self.critical_power * 0.85
        
        sim_results = self._simulate_variable_pacing(course_segments, current_strategy)
        current_w_utilization = sim_results['w_utilization']
        best_time = sim_results['total_time'] if sim_results['feasible'] else float('inf')
        best_w_error = abs(target_w_utilization - current_w_utilization)
        
        print(f"Initial heuristic: avg {np.mean(current_strategy):.0f}W, "
              f"W' utilization: {current_w_utilization*100:.1f}% (target: {target_w_utilization*100:.0f}%)")
        
        max_iterations = 40
        for iteration in range(max_iterations):
            utilization_error = target_w_utilization - current_w_utilization
            
            if abs(utilization_error) <= 0.03:
                break

            # For long efforts, "above base" replaces "above CP"
            above_threshold = base_power if is_long else self.critical_power
            above_cp_indices = [i for i in range(len(current_strategy)) 
                               if current_strategy[i] > above_threshold]
            below_cp_indices = [i for i in range(len(current_strategy)) 
                               if current_strategy[i] <= above_threshold]
            
            if not above_cp_indices:
                sorted_indices = np.argsort(gradients)[::-1]
                above_cp_indices = sorted_indices[:max(1, len(sorted_indices) // 2)].tolist()
            
            if current_w_utilization < target_w_utilization:
                # Smaller step size to avoid overshooting into infeasible
                scale = min(1.06, 1.0 + utilization_error * 0.15)
                for idx in above_cp_indices:
                    current_strategy[idx] *= scale
                    current_strategy[idx] = min(float(current_strategy[idx]), max_power)
                # Also reduce recovery (less W' recovered → higher net utilization)
                if below_cp_indices:
                    recovery_ceiling = (base_power * 0.99 if is_long
                                        else self.critical_power * 0.99)
                    for idx in below_cp_indices:
                        gap = recovery_ceiling - current_strategy[idx]
                        if gap > 0:
                            current_strategy[idx] += gap * 0.15
                            current_strategy[idx] = min(float(current_strategy[idx]),
                                                        recovery_ceiling)
            else:
                scale = max(0.94, 1.0 - abs(utilization_error) * 0.15)
                for idx in above_cp_indices:
                    current_strategy[idx] *= scale
                    floor = above_threshold * 1.01
                    current_strategy[idx] = max(floor,
                                                float(current_strategy[idx]))
            
            new_sim = self._simulate_variable_pacing(course_segments, current_strategy)
            new_w_util = new_sim['w_utilization']
            new_error = abs(target_w_utilization - new_w_util)
            
            if new_sim['feasible'] and new_error < best_w_error:
                best_strategy = current_strategy.copy()
                best_w_error = new_error
                best_time = new_sim['total_time']
                current_w_utilization = new_w_util
            elif new_sim['feasible']:
                # Didn't improve error, but still feasible — keep going
                current_w_utilization = new_w_util
            else:
                # Went infeasible — back off partially instead of giving up
                current_strategy = (current_strategy + best_strategy) / 2.0
                new_sim2 = self._simulate_variable_pacing(course_segments, current_strategy)
                if new_sim2['feasible']:
                    current_w_utilization = new_sim2['w_utilization']
                else:
                    current_strategy = best_strategy.copy()
                    sim_best = self._simulate_variable_pacing(course_segments, best_strategy)
                    current_w_utilization = sim_best['w_utilization']
        
        final_sim = self._simulate_variable_pacing(course_segments, best_strategy)
        print(f"Refined in {iteration+1} iterations: avg {np.mean(best_strategy):.0f}W, "
              f"W' utilization: {final_sim['w_utilization']*100:.1f}% (target: {target_w_utilization*100:.0f}%)")
        
        return best_strategy
    
    def _generate_conservative_strategy(self, course_segments: pd.DataFrame) -> np.ndarray:
        """Generate conservative power strategy as fallback."""
        num_segments = len(course_segments)
        conservative_strategy = np.full(num_segments, self.critical_power)
        
        # Conservative = at or slightly below CP for all segments.
        # On uphills, stay at CP (no W' depletion). On descents, slightly below.
        for i, (_, segment) in enumerate(course_segments.iterrows()):
            g = segment['gradient']
            if g > 0.02:
                # Uphill: ride at CP — conservative means no W' spend
                conservative_strategy[i] = self.critical_power * 1.0
            elif g > 0:
                # Gentle uphill: at CP
                conservative_strategy[i] = self.critical_power * 0.99
            elif g < -0.01:
                recovery_depth = min(abs(g) / 0.05, 1.0)
                conservative_strategy[i] = self.critical_power * (0.95 - recovery_depth * 0.10)

        # If cluster info present, enforce per-cluster-type consistency
        if _has_cluster_info(course_segments):
            cmap = _cluster_power_map_from_array(conservative_strategy,
                                                  course_segments['segment_id'])
            conservative_strategy = _expand_cluster_powers(
                cmap, course_segments['segment_id'])
        
        return conservative_strategy
    
    def _create_variable_pacing_results(self, course_segments: pd.DataFrame,
                                      power_strategy: np.ndarray,
                                      sim_results: Dict[str, Any]) -> pd.DataFrame:
        """Create detailed results DataFrame for variable pacing strategy."""
        has_clusters = _has_cluster_info(course_segments)
        results_data = []
        
        for i, segment_result in enumerate(sim_results['segment_results']):
            segment_info = course_segments.iloc[i]
            
            row = {
                'segment': i,
                'distance': segment_info['distance'],
                'distance_sum': segment_info['distance'] / 1000,
                'gradient': segment_info['gradient'],
                'gradient_mean': segment_info['gradient'] * 100,
                'altitude': segment_info.get('altitude', 0),
                'altitude_mean': segment_info.get('altitude', 0),
                'wind': segment_info.get('wind', 0),
                'target_power': segment_result['power'],
                'speed': segment_result['speed'],
                'time': segment_result['time'],
                'w_remaining': segment_result['w_remaining'],
                'w_used_segment': segment_result['w_used_segment'],
                'energy_segment': segment_result['power'] * segment_result['time'],
                'terrain_type': self._classify_terrain(segment_info['gradient']),
                'power_zone': self._classify_power_zone(segment_result['power'])
            }
            
            # Carry cluster metadata so the UI can group by cluster type
            if has_clusters:
                row['segment_id'] = int(segment_info['segment_id'])
                row['segment_sequence'] = int(segment_info.get('segment_sequence', i))
            
            results_data.append(row)
        
        return pd.DataFrame(results_data)
    
    def _classify_terrain(self, gradient: float) -> str:
        """Classify terrain type based on gradient."""
        if gradient > 0.05:
            return 'Steep Climb'
        elif gradient > 0.02:
            return 'Moderate Climb'
        elif gradient > -0.02:
            return 'Flat'
        elif gradient > -0.05:
            return 'Moderate Descent'
        else:
            return 'Steep Descent'
    
    def _classify_power_zone(self, power: float) -> str:
        """Classify power zone relative to critical power."""
        ratio = power / self.critical_power
        if ratio < 0.7:
            return 'Recovery'
        elif ratio < 0.85:
            return 'Endurance'
        elif ratio < 1.0:
            return 'Tempo'
        elif ratio < 1.15:
            return 'Threshold'
        elif ratio < 1.5:
            return 'VO2 Max'
        else:
            return 'Neuromuscular'
    
    def _analyze_variable_pacing_strategy(self, course_segments: pd.DataFrame,
                                        results_df: pd.DataFrame,
                                        sim_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive analysis of variable pacing strategy."""
        
        # Compare with constant power strategy
        constant_power, constant_time, constant_results = self.optimize_constant_power(course_segments)
        
        # Calculate performance metrics
        total_distance = course_segments['distance'].sum() / 1000  # km
        avg_speed = (total_distance * 1000) / sim_results['total_time'] * 3.6  # km/h
        constant_avg_speed = (total_distance * 1000) / constant_time * 3.6  # km/h
        
        # Time savings
        time_savings = constant_time - sim_results['total_time']
        time_savings_percent = (time_savings / constant_time) * 100
        
        # Power distribution analysis
        power_stats = {
            'mean_power': results_df['target_power'].mean(),
            'max_power': results_df['target_power'].max(),
            'min_power': results_df['target_power'].min(),
            'power_variability': results_df['target_power'].std() / results_df['target_power'].mean(),
            'time_above_cp': results_df[results_df['target_power'] > self.critical_power]['time'].sum(),
            'time_below_cp': results_df[results_df['target_power'] < self.critical_power]['time'].sum()
        }
        
        # Segment-specific insights
        climb_segments = results_df[results_df['terrain_type'].str.contains('Climb')]
        descent_segments = results_df[results_df['terrain_type'].str.contains('Descent')]
        flat_segments = results_df[results_df['terrain_type'] == 'Flat']
        
        return {
            'strategy_type': 'Variable Pacing',
            'total_time_minutes': sim_results['total_time'] / 60,
            'total_distance_km': total_distance,
            'average_speed_kmh': avg_speed,
            'w_prime_utilization_percent': sim_results['w_utilization'] * 100,
            'final_w_remaining': sim_results['final_w_remaining'],
            'comparison_to_constant_power': {
                'constant_power_watts': constant_power,
                'constant_time_minutes': constant_time / 60,
                'constant_avg_speed_kmh': constant_avg_speed,
                'time_savings_seconds': time_savings,
                'time_savings_percent': time_savings_percent,
                'speed_improvement_kmh': avg_speed - constant_avg_speed
            },
            'power_distribution': power_stats,
            'terrain_analysis': {
                'climb_avg_power': climb_segments['target_power'].mean() if len(climb_segments) > 0 else 0,
                'flat_avg_power': flat_segments['target_power'].mean() if len(flat_segments) > 0 else 0,
                'descent_avg_power': descent_segments['target_power'].mean() if len(descent_segments) > 0 else 0,
                'climb_time_percent': climb_segments['time'].sum() / sim_results['total_time'] * 100 if len(climb_segments) > 0 else 0
            },
            'segment_breakdown': results_df,
            'performance_metrics': {
                'normalized_power': self._calculate_normalized_power(results_df['target_power'], results_df['time']),
                'intensity_factor': power_stats['mean_power'] / self.critical_power,
                'variability_index': power_stats['power_variability'],
                'tss_estimate': self._estimate_tss(results_df['target_power'], results_df['time'])
            }
        }
    
    def _calculate_normalized_power(self, power_values: pd.Series, time_values: pd.Series) -> float:
        """Calculate Normalized Power for variable power strategy."""
        # Simplified NP calculation (30-second rolling average would be more accurate)
        weighted_power = np.sum(np.power(power_values, 4) * time_values) / np.sum(time_values)
        return np.power(weighted_power, 0.25)
    
    def _estimate_tss(self, power_values: pd.Series, time_values: pd.Series) -> float:
        """Estimate Training Stress Score for variable power strategy."""
        np_power = self._calculate_normalized_power(power_values, time_values)
        intensity_factor = np_power / self.critical_power
        duration_hours = time_values.sum() / 3600
        return duration_hours * (intensity_factor ** 2) * 100

    def simulate_course_detailed(self, course, course_segments: pd.DataFrame, 
                               power_strategy, target_resolution: int = 5000) -> Tuple[pd.DataFrame, float, Dict[str, Any]]:
        """
        Perform a granular simulation with the canonical physics and W' models.
        
        This function provides the final detailed simulation after optimization,
        using up to 5000 calculation points with realistic acceleration between points.
        
        Args:
            course: Raw course object with full GPS data
            course_segments: Optimized segments with power assignments
            power_strategy: Either constant power (float) or variable power mapping (dict)
            target_resolution: Target number of calculation points (default 5000)
        
        Returns:
            Tuple containing:
            - DataFrame with high-resolution point-by-point results
            - Total course time (seconds)
            - Dictionary with detailed analysis and metrics
        """
        print(f"Starting high-resolution simulation with {target_resolution} points...")
        
        # Step 1: Smooth course to target resolution
        high_res_points = self._smooth_course_to_resolution(course, target_resolution)
        
        # Step 2: Assign each point to appropriate segment
        point_segment_mapping = self._assign_points_to_segments(high_res_points, course_segments)
        
        # Step 3: Assign power based on strategy
        point_powers = self._assign_powers_to_points(point_segment_mapping, course_segments, power_strategy)
        
        # Step 4: Simulate with the same kernels used by optimization
        simulation_results = self._simulate_with_acceleration(high_res_points, point_powers)
        
        # Step 5: Create detailed results and analysis
        results_df = self._create_detailed_results_dataframe(
            high_res_points, point_powers, simulation_results, point_segment_mapping
        )
        
        total_time = simulation_results['total_time']
        analysis = self._analyze_detailed_simulation(results_df, simulation_results, course_segments)
        
        print(f"High-resolution simulation complete: {total_time/60:.1f} min with {len(results_df)} points")
        
        return results_df, total_time, analysis
    
    def _smooth_course_to_resolution(self, course, target_resolution: int) -> pd.DataFrame:
        """
        Intelligently downsample course to target resolution while preserving key features.
        
        Args:
            course: Course object with raw GPS data
            target_resolution: Target number of points
            
        Returns:
            DataFrame with downsampled course points
        """
        df = course.df.copy()
        total_points = len(df)
        
        # Ensure cumulative_distance exists
        if 'cumulative_distance' not in df.columns:
            if 'distance' in df.columns:
                df['cumulative_distance'] = df['distance'].cumsum()
            else:
                # Create distance from index as fallback
                df['cumulative_distance'] = np.arange(len(df))
                print("Warning: No distance data, using index-based sampling")
        
        gradient_unit = (
            'percent' if {'lat', 'lon'}.issubset(df.columns) else 'decimal'
        )

        if total_points <= target_resolution:
            # No downsampling needed
            print(f"Course has {total_points} points, using all points (target: {target_resolution})")
            result_df = df.reset_index(drop=True)
            # Still need to normalize gradients even without downsampling
            result_df = self._normalize_gradients(
                result_df, gradient_unit=gradient_unit)
            return result_df
        
        # Calculate basic sampling ratio
        base_ratio = total_points / target_resolution
        
        # Create adaptive sampling based on gradient changes
        df['gradient_change'] = df['gradient'].diff().abs()
        df['gradient_change_score'] = df['gradient_change'] / (df['gradient_change'].std() + 1e-6)
        
        # Create importance score (higher = more important to keep)
        df['importance'] = (
            df['gradient_change_score'] * 0.4 +  # Gradient changes
            (df['gradient'].abs() * 0.3) +       # Steep sections
            (df['distance'] > 0).astype(float) * 0.3  # Valid data points
        )
        
        # Distance-based sampling with importance weighting
        total_distance = df['cumulative_distance'].iloc[-1]
        target_distances = np.linspace(0, total_distance, target_resolution)
        
        sampled_indices = []
        for target_dist in target_distances:
            # Find closest point to target distance
            dist_diff = (df['cumulative_distance'] - target_dist).abs()
            
            # Within a small window, prefer points with higher importance
            window_size = base_ratio * 2
            window_mask = dist_diff <= window_size
            
            if window_mask.sum() > 0:
                window_df = df[window_mask]
                # Choose point with highest importance in window
                best_idx = window_df['importance'].idxmax()
                sampled_indices.append(best_idx)
            else:
                # Fallback to closest point
                best_idx = dist_diff.idxmin()
                sampled_indices.append(best_idx)
        
        # Remove duplicates and sort, ensuring all indices are valid
        sampled_indices = sorted(list(set(sampled_indices)))
        sampled_indices = [idx for idx in sampled_indices if 0 <= idx < len(df)]
        
        # Ensure we have start and end points
        if 0 not in sampled_indices:
            sampled_indices.insert(0, 0)
        if len(df) - 1 not in sampled_indices:
            sampled_indices.append(len(df) - 1)
        
        # Final validation of indices
        sampled_indices = [idx for idx in sampled_indices if 0 <= idx < len(df)]
        
        if not sampled_indices:
            # Fallback: use evenly spaced indices
            sampled_indices = np.linspace(0, len(df) - 1, min(target_resolution, len(df))).astype(int).tolist()
        
        # Create smoothed course
        smoothed_df = df.iloc[sampled_indices].copy().reset_index(drop=True)
        
        # Recalculate cumulative distance and other derived metrics
        smoothed_df['distance'] = smoothed_df['cumulative_distance'].diff().fillna(0)
        
        # Normalize gradients
        smoothed_df = self._normalize_gradients(
            smoothed_df, gradient_unit=gradient_unit)
        
        print(f"Downsampled from {total_points} to {len(smoothed_df)} points ({len(smoothed_df)/total_points*100:.1f}%)")
        
        return smoothed_df
    
    def _normalize_gradients(self, df: pd.DataFrame,
                             gradient_unit: str = 'decimal') -> pd.DataFrame:
        """
        Normalize gradients using the declared source unit and clip outliers.

        Course point data uses percentage grades; optimization-ready point data
        uses decimal grades. If available, gradient_smoothed is preferred for
        the canonical gradient and normalized using the same source unit.
        
        Args:
            df: DataFrame with 'gradient' column
            gradient_unit: 'percent' for Course points or 'decimal' for
                optimization-ready points.
            
        Returns:
            DataFrame with normalized gradient column
        """
        if 'gradient' not in df.columns:
            return df
        if gradient_unit not in {'percent', 'decimal'}:
            raise ValueError("gradient_unit must be 'percent' or 'decimal'")

        df = df.copy()

        scale = 100 if gradient_unit == 'percent' else 1
        source_col = 'gradient_smoothed' if 'gradient_smoothed' in df.columns else 'gradient'
        for col in ('gradient', 'gradient_smoothed'):
            if col in df.columns:
                df[col] = (df[col] / scale).clip(-0.5, 0.5)
        if source_col == 'gradient_smoothed':
            df['gradient'] = df['gradient_smoothed']

        return df
    
    def _assign_points_to_segments(self, high_res_points: pd.DataFrame, 
                                 course_segments: pd.DataFrame) -> np.ndarray:
        """
        Assign each high-resolution point to the appropriate course segment.
        
        Uses the original segment labels from the course data when available,
        since segments from clustering/auto_segmentation are non-contiguous
        (points with similar gradients are grouped together regardless of position).
        
        Args:
            high_res_points: High-resolution course points (from _smooth_course_to_resolution)
            course_segments: Course segments with distance ranges
            
        Returns:
            Array mapping each point to segment index
        """
        # Preferred approach: use original segment column from course data
        # This correctly handles non-contiguous segments from clustering/auto_segmentation
        if 'segment' in high_res_points.columns:
            segment_values = high_res_points['segment'].values

            # Enhanced-format segments (clustering / terrain) carry segment_id.
            # 'segment' in high_res_points contains CLUSTER LABELS (e.g. 0,1,2),
            # but course_segments rows are indexed by SEQUENCE position (0..N-1).
            # Build a cluster_label → first_row_index mapping so each high-res
            # point resolves to the correct row in course_segments.
            # Since _expand_cluster_powers guarantees one power per cluster label,
            # using the first-occurrence row gives the right target_power.
            if 'segment_id' in course_segments.columns:
                cluster_to_row: dict = {}
                for row_idx, seg_id in enumerate(course_segments['segment_id'].values):
                    key = int(seg_id)
                    if key not in cluster_to_row:
                        cluster_to_row[key] = row_idx
                mapped = np.array(
                    [cluster_to_row.get(int(sv), 0) for sv in segment_values],
                    dtype=int
                )
                print(f"Mapped {len(cluster_to_row)} cluster labels to sequence row indices")
                return mapped

            # Legacy path: segment labels are already row indices
            valid_seg_ids = set(course_segments.index)
            if set(np.unique(segment_values[~np.isnan(segment_values)])).issubset(valid_seg_ids) or \
               set(np.unique(segment_values[~np.isnan(segment_values)])) == valid_seg_ids:
                print(f"Using original segment labels from course data ({len(valid_seg_ids)} segments)")
                return segment_values.astype(int)
            else:
                print(f"Warning: segment column IDs {set(np.unique(segment_values))} don't match "
                      f"course_segments index {valid_seg_ids}, falling back to distance-based mapping")
        
        # Fallback: distance-based mapping for contiguous segments
        # (e.g., equal segmentation where segments ARE contiguous)
        if 'cumulative_distance' not in high_res_points.columns:
            if 'distance' in high_res_points.columns:
                high_res_points = high_res_points.copy()
                high_res_points['cumulative_distance'] = high_res_points['distance'].cumsum()
            else:
                num_points = len(high_res_points)
                num_segments = len(course_segments)
                return np.repeat(np.arange(num_segments), num_points // num_segments + 1)[:num_points]
        
        point_distances = high_res_points['cumulative_distance'] / 1000  # Convert to km
        segment_mapping = np.zeros(len(high_res_points), dtype=int)
        
        if 'start_distance' in course_segments.columns and 'end_distance' in course_segments.columns:
            for i, distance in enumerate(point_distances):
                for seg_idx, segment in course_segments.iterrows():
                    start_dist = segment['start_distance'] / 1000
                    end_dist = segment['end_distance'] / 1000
                    if start_dist <= distance <= end_dist:
                        segment_mapping[i] = seg_idx
                        break
                else:
                    segment_centers = (course_segments.get('start_distance', 0) + course_segments.get('end_distance', 0)) / 2000
                    closest_seg = (segment_centers - distance).abs().idxmin()
                    segment_mapping[i] = closest_seg
        else:
            total_distance = point_distances.iloc[-1]
            cumulative_segment_distance = 0
            dist_col = 'distance' if 'distance' in course_segments.columns else 'distance_sum'
            
            for seg_idx, segment in course_segments.iterrows():
                segment_distance = segment[dist_col]
                if dist_col == 'distance':
                    segment_distance = segment_distance / 1000
                segment_end = cumulative_segment_distance + segment_distance
                mask = (point_distances >= cumulative_segment_distance) & (point_distances < segment_end)
                segment_mapping[mask] = seg_idx
                cumulative_segment_distance = segment_end
            
            segment_mapping[point_distances >= cumulative_segment_distance] = len(course_segments) - 1
        
        return segment_mapping
    
    def _assign_powers_to_points(self, point_segment_mapping: np.ndarray, 
                               course_segments: pd.DataFrame, power_strategy) -> np.ndarray:
        """
        Assign power values to each high-resolution point based on strategy.
        
        Args:
            point_segment_mapping: Array mapping points to segments
            course_segments: Course segments data
            power_strategy: Power specification in various formats:
                - float: Constant power for all points
                - dict with 'segment_breakdown': Strategy analysis from variable pacing
                - dict with int keys: Power per segment index
                - np.ndarray: Power array per segment
                - pd.DataFrame with 'target_power': Per-segment power results
            
        Returns:
            Array of power values for each point
        """
        num_points = len(point_segment_mapping)
        point_powers = np.zeros(num_points)
        
        if isinstance(power_strategy, (int, float)):
            # Constant power strategy
            point_powers.fill(power_strategy)
            print(f"Assigned constant power: {power_strategy:.0f}W to all {num_points} points")
            
        elif isinstance(power_strategy, pd.DataFrame):
            # DataFrame with target_power column (from optimize_variable_pacing results_df)
            if 'target_power' in power_strategy.columns:
                power_array = power_strategy['target_power'].values
                for i, seg_idx in enumerate(point_segment_mapping):
                    if seg_idx < len(power_array):
                        point_powers[i] = power_array[seg_idx]
                    else:
                        point_powers[i] = self.critical_power
                print(f"Assigned power from DataFrame to {num_points} points")
            else:
                point_powers.fill(self.critical_power)
                print(f"DataFrame missing 'target_power', using critical power fallback")
            
        elif isinstance(power_strategy, dict):
            # Check if this is a strategy_analysis dict with segment_breakdown
            if 'segment_breakdown' in power_strategy:
                segment_df = power_strategy['segment_breakdown']
                if isinstance(segment_df, pd.DataFrame) and 'target_power' in segment_df.columns:
                    power_array = segment_df['target_power'].values
                    for i, seg_idx in enumerate(point_segment_mapping):
                        if seg_idx < len(power_array):
                            point_powers[i] = power_array[seg_idx]
                        else:
                            point_powers[i] = self.critical_power
                    print(f"Assigned power from strategy analysis to {num_points} points")
                else:
                    point_powers.fill(self.critical_power)
                    print(f"Strategy analysis missing power data, using critical power fallback")
            else:
                # Variable power strategy - power per segment_id or index
                has_segment_ids = 'segment_id' in course_segments.columns
                
                if has_segment_ids:
                    # Enhanced format - use segment_id mapping
                    for i, seg_idx in enumerate(point_segment_mapping):
                        if seg_idx < len(course_segments):
                            segment_id = course_segments.iloc[seg_idx]['segment_id']
                            point_powers[i] = power_strategy.get(segment_id, self.critical_power)
                        else:
                            point_powers[i] = self.critical_power
                else:
                    # Traditional format - use segment index directly
                    for i, seg_idx in enumerate(point_segment_mapping):
                        point_powers[i] = power_strategy.get(seg_idx, self.critical_power)
                    
                print(f"Assigned variable power strategy to {num_points} points")
            
        elif isinstance(power_strategy, np.ndarray):
            # Power array per segment - map to points
            for i, seg_idx in enumerate(point_segment_mapping):
                if seg_idx < len(power_strategy):
                    point_powers[i] = power_strategy[seg_idx]
                else:
                    point_powers[i] = self.critical_power
                    
            print(f"Assigned power array strategy to {num_points} points")
            
        else:
            # Fallback to critical power
            point_powers.fill(self.critical_power)
            print(f"Using fallback critical power: {self.critical_power:.0f}W for all points")
        
        return point_powers
    
    def _simulate_with_acceleration(self, high_res_points: pd.DataFrame, 
                                  point_powers: np.ndarray) -> Dict[str, Any]:
        """
        Simulate granular course points with the canonical physics and W' kernels.
        
        Args:
            high_res_points: High-resolution course points
            point_powers: Power for each point
            
        Returns:
            Dictionary with simulation results including speeds, times, and acceleration
        """
        num_points = len(high_res_points)
        speeds = np.zeros(num_points)
        times = np.zeros(num_points)
        accelerations = np.zeros(num_points)
        w_remaining_track = np.zeros(num_points)
        
        total_time = 0
        w_remaining = self.w_prime
        total_energy = 0
        
        for i in range(num_points):
            power = point_powers[i]
            gradient = high_res_points['gradient'].iloc[i]  # Already in decimal form from smoothing
            altitude = high_res_points['altitude'].iloc[i]
            wind = high_res_points['wind'].iloc[i] if 'wind' in high_res_points else 0
            distance_step = high_res_points['distance'].iloc[i]
            
            # Calculate target speed using physics
            try:
                target_speed = self._speed_for_power(
                    power, gradient, wind, altitude)
            except Exception:
                # Fallback speed calculation
                target_speed = max(3.0, min(20.0, power / 200.0 + (0.05 - gradient) * 10))
            current_speed = target_speed
            acceleration = 0
            
            # Calculate time for this segment
            if current_speed > 0 and distance_step > 0:
                segment_time = distance_step / current_speed
            else:
                segment_time = 0
            
            total_time += segment_time
            
            # Track W' usage and recovery
            w_remaining = self._update_w_prime(
                w_remaining, power, segment_time)
            
            total_energy += power * segment_time
            
            # Store results
            speeds[i] = current_speed
            times[i] = segment_time
            accelerations[i] = acceleration
            w_remaining_track[i] = w_remaining
        
        return {
            'total_time': total_time,
            'speeds': speeds,
            'times': times,
            'accelerations': accelerations,
            'w_remaining_track': w_remaining_track,
            'final_w_remaining': w_remaining,
            'total_energy': total_energy,
            'average_speed': np.mean(speeds),
            'max_speed': np.max(speeds),
            'min_speed': np.min(speeds),
            'max_acceleration': 0.0,
            'min_acceleration': 0.0,
        }
    
    def _create_detailed_results_dataframe(self, high_res_points: pd.DataFrame, 
                                         point_powers: np.ndarray, 
                                         simulation_results: Dict[str, Any],
                                         point_segment_mapping: np.ndarray) -> pd.DataFrame:
        """Create comprehensive DataFrame with detailed simulation results."""
        results_df = high_res_points.copy()
        
        # Ensure cumulative_distance exists
        if 'cumulative_distance' not in results_df.columns:
            if 'distance' in results_df.columns:
                results_df['cumulative_distance'] = results_df['distance'].cumsum()
            else:
                results_df['cumulative_distance'] = np.arange(len(results_df))
        
        # Add simulation results
        results_df['power'] = point_powers
        results_df['speed_mps'] = simulation_results['speeds']
        results_df['speed_kmh'] = simulation_results['speeds'] * 3.6
        results_df['time'] = simulation_results['times']
        results_df['acceleration'] = simulation_results['accelerations']
        results_df['w_remaining'] = simulation_results['w_remaining_track']
        results_df['segment_index'] = point_segment_mapping
        
        # Add derived metrics
        results_df['cumulative_time'] = results_df['time'].cumsum()
        results_df['energy_used'] = results_df['power'] * results_df['time']
        results_df['cumulative_energy'] = results_df['energy_used'].cumsum()
        
        # Power zones relative to critical power
        results_df['power_ratio'] = results_df['power'] / self.critical_power
        results_df['above_cp'] = results_df['power'] > self.critical_power
        
        return results_df
    
    def _analyze_detailed_simulation(self, results_df: pd.DataFrame, 
                                   simulation_results: Dict[str, Any],
                                   course_segments: pd.DataFrame) -> Dict[str, Any]:
        """Generate comprehensive analysis of detailed simulation."""
        total_distance = results_df['cumulative_distance'].iloc[-1] / 1000  # km
        total_time = simulation_results['total_time']
        avg_speed_kmh = (total_distance / (total_time / 3600))  # km/h
        
        # W' utilization
        w_utilization = (self.w_prime - simulation_results['final_w_remaining']) / self.w_prime
        
        # Power analysis
        power_stats = {
            'average': results_df['power'].mean(),
            'max': results_df['power'].max(),
            'min': results_df['power'].min(),
            'std': results_df['power'].std(),
            'time_above_cp': results_df[results_df['above_cp']]['time'].sum(),
            'time_below_cp': results_df[~results_df['above_cp']]['time'].sum()
        }
        
        # Speed and acceleration analysis
        speed_stats = {
            'average_mps': simulation_results['average_speed'],
            'average_kmh': simulation_results['average_speed'] * 3.6,
            'max_mps': simulation_results['max_speed'],
            'max_kmh': simulation_results['max_speed'] * 3.6,
            'min_mps': simulation_results['min_speed'],
            'min_kmh': simulation_results['min_speed'] * 3.6,
            'speed_variability': results_df['speed_mps'].std()
        }
        
        acceleration_stats = {
            'max_accel': simulation_results['max_acceleration'],
            'max_decel': simulation_results['min_acceleration'],
            'avg_accel_magnitude': results_df['acceleration'].abs().mean(),
            'time_accelerating': (results_df['acceleration'] > 0.1).sum() * results_df['time'].mean(),
            'time_decelerating': (results_df['acceleration'] < -0.1).sum() * results_df['time'].mean()
        }
        
        return {
            'simulation_type': 'Granular canonical simulation',
            'total_points': len(results_df),
            'total_distance_km': total_distance,
            'total_time_minutes': total_time / 60,
            'average_speed_kmh': avg_speed_kmh,
            'w_prime_utilization_percent': w_utilization * 100,
            'final_w_remaining': simulation_results['final_w_remaining'],
            'total_energy_kj': simulation_results['total_energy'] / 1000,
            'power_analysis': power_stats,
            'speed_analysis': speed_stats,
            'acceleration_analysis': acceleration_stats,
            'segment_count': len(course_segments),
            'resolution_improvement': f"{len(results_df)}x more detailed than {len(course_segments)} segments"
        }

    # ...existing code...
def create_course_segments_from_course(course) -> pd.DataFrame:
    """
    Convert Course object segments to optimization-ready DataFrame.
    Supports both traditional aggregated segments and new sequence-preserving segments.
    
    Args:
        course: Course object with aggregated segments
    
    Returns:
        DataFrame formatted for optimization functions
    """
    if not hasattr(course, 'course_segments'):
        raise ValueError("Course must have aggregated segments. Run segmentation first.")
    
    segments = course.course_segments.copy()
    
    # Check if this is the new enhanced segmentation format
    has_enhanced_format = 'segment_id' in segments.columns and 'segment_sequence' in segments.columns
    
    if has_enhanced_format:
        # New enhanced format - preserve sequence order
        print(f"Using enhanced segmentation format with {len(segments)} sequence segments")
        
        # Resolve distance column
        if 'distance_sum' in segments.columns:
            dist_values = segments['distance_sum']
        elif 'distance' in segments.columns:
            dist_values = segments['distance']
        else:
            raise ValueError(f"No distance column found. Available columns: {list(segments.columns)}")
        
        # Resolve gradient column
        if 'gradient_mean' in segments.columns:
            grad_values = segments['gradient_mean']
        elif 'gradient' in segments.columns:
            grad_values = segments['gradient']
        else:
            raise ValueError(f"No gradient column found. Available columns: {list(segments.columns)}")
        
        # Create optimization-ready DataFrame maintaining sequence order
        optimization_segments = pd.DataFrame({
            'distance': dist_values * 1000,  # Convert km to meters
            'gradient': grad_values / 100,  # Convert percentage to decimal
            'altitude': segments.get('altitude_mean', segments.get('altitude', 0)),
            'wind': 0,
            'segment_id': segments['segment_id'],
            'segment_occurrence': segments['segment_occurrence'],
            'segment_sequence': segments['segment_sequence'],
            'start_distance': segments.get('start_distance', 0) * 1000,
            'end_distance': segments.get('end_distance', 0) * 1000
        })

        optimization_segments['distance_sum'] = optimization_segments['distance'] / 1000
        optimization_segments['gradient_mean'] = optimization_segments['gradient'] * 100
        optimization_segments['altitude_mean'] = optimization_segments['altitude']
        
        # Sort by sequence to ensure proper order
        optimization_segments = optimization_segments.sort_values('segment_sequence').reset_index(drop=True)
        
    else:
        # Traditional aggregated format - backward compatibility
        print(f"Using traditional aggregated segmentation format with {len(segments)} segments")
        
        # Resolve distance column — handle both naming conventions
        if 'distance_sum' in segments.columns:
            dist_values = segments['distance_sum']
        elif 'distance' in segments.columns:
            dist_values = segments['distance']
        else:
            raise ValueError(
                f"No distance column found in course_segments. "
                f"Available columns: {list(segments.columns)}"
            )
        
        # Resolve gradient column
        if 'gradient_mean' in segments.columns:
            grad_values = segments['gradient_mean']
        elif 'gradient' in segments.columns:
            grad_values = segments['gradient']
        else:
            raise ValueError(
                f"No gradient column found in course_segments. "
                f"Available columns: {list(segments.columns)}"
            )
        
        # Debug: Check gradient values to determine if they're already decimals or percentages
        sample_gradient = grad_values.iloc[0] if len(grad_values) > 0 else 0
        gradient_is_percentage = abs(sample_gradient) > 1.0
        
        # Ensure required columns exist with proper names
        optimization_segments = pd.DataFrame({
            'distance': dist_values * 1000,  # Convert km to meters
            'gradient': grad_values / 100,  # Always convert percentage to decimal
            'altitude': segments.get('altitude_mean', segments.get('altitude', 0)),
            'wind': 0
        })

        optimization_segments['distance_sum'] = optimization_segments['distance'] / 1000
        optimization_segments['gradient_mean'] = optimization_segments['gradient'] * 100
        optimization_segments['altitude_mean'] = optimization_segments['altitude']
    
    # Validate gradients are reasonable (between -0.3 and 0.3 for -30% to 30%)
    invalid_gradients = optimization_segments[(optimization_segments['gradient'].abs() > 0.5)]
    if len(invalid_gradients) > 0:
        import warnings
        warnings.warn(
            f"Found {len(invalid_gradients)} segments with extreme gradients. "
            f"Max gradient: {optimization_segments['gradient'].max():.3f} "
            f"({optimization_segments['gradient'].max()*100:.1f}%)"
        )
    
    return optimization_segments


# Legacy functions for backward compatibility
def simulate_course_time(power: float, course_segments: pd.DataFrame, 
                        critical_power: float, w_prime: float) -> Tuple[pd.DataFrame, float, float, float]:
    """
    Legacy function wrapper for backward compatibility.
    
    Args:
        power: Constant power (W)
        course_segments: Course segment data
        critical_power: Critical power (W) 
        w_prime: Anaerobic capacity (J)
    
    Returns:
        Same as CourseOptimizer.simulate_course_time()
    """
    optimizer = CourseOptimizer(critical_power, w_prime)
    return optimizer.simulate_course_time(power, course_segments)


def optimize_constant_power(course_segments: pd.DataFrame, 
                           critical_power: float, w_prime: float) -> Tuple[float, float, pd.DataFrame]:
    """
    Legacy function wrapper for backward compatibility.
    
    Args:
        course_segments: Course segment data
        critical_power: Critical power (W)
        w_prime: Anaerobic capacity (J)
    
    Returns:
        Same as CourseOptimizer.optimize_constant_power()
    """
    optimizer = CourseOptimizer(critical_power, w_prime)
    return optimizer.optimize_constant_power(course_segments)


if __name__ == "__main__":
    # Example usage and testing
    print("Course Optimization Module")
    print("=" * 40)
    
    # Create example course segments
    example_segments = pd.DataFrame({
        'distance': [1000, 1500, 800, 1200, 900],  # meters
        'gradient': [0.02, 0.06, -0.03, 0.01, 0.04],  # decimal
        'altitude': [100, 120, 115, 110, 125],  # meters
        'wind': [0, 0, 2, -1, 0]  # m/s
    })
    
    # Test optimization
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    
    print("Testing course simulation...")
    results, time, w_rem, energy = optimizer.simulate_course_time(350, example_segments)
    print(f"Time: {time/60:.1f} min, W' remaining: {w_rem:.0f} J")
    
    print("\nTesting power optimization...")
    opt_power, opt_time, opt_results = optimizer.optimize_constant_power(example_segments)
    print(f"Optimal power: {opt_power:.0f} W, Time: {opt_time/60:.1f} min")
    
    print("\nTesting variable pacing optimization...")
    var_results_df, var_time, var_analysis = optimizer.optimize_variable_pacing(example_segments)
    print(f"Variable pacing complete: {var_time/60:.1f} min")
    print(f"Average speed: {var_analysis['average_speed_kmh']:.1f} km/h")
    print(f"W' utilization: {var_analysis['w_prime_utilization_percent']:.1f}%")
