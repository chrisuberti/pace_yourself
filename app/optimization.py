"""
Course Optimization Module

This module provides optimization algorithms for cycling course pacing strategies.
Integrated from notebooks/StartCourseEstimation.ipynb as part of Phase 1 consolidation.
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import Tuple, Dict, Any, Optional
import os
import sys

# Add the app directory to the Python path for imports
sys.path.append(os.path.dirname(__file__))

from cycling_physics import calculate_speed_and_plot


class CourseOptimizer:
    """
    Course optimization engine for cycling performance analysis.
    
    This class provides methods to simulate course performance and optimize
    pacing strategies based on rider physiology and course characteristics.
    """
    
    def __init__(self, critical_power: float, w_prime: float):
        """
        Initialize course optimizer with rider parameters.
        
        Args:
            critical_power: Rider's critical power (W)
            w_prime: Rider's anaerobic capacity (J)
        """
        self.critical_power = critical_power
        self.w_prime = w_prime
    
    def _normalize_segments(self, course_segments: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize segment DataFrame to use standard column names.
        
        This allows the optimizer to work with both:
        - Aggregated segments (gradient_mean, distance_sum, altitude_mean)
        - Optimization-ready segments (gradient, distance, altitude)
        
        Args:
            course_segments: DataFrame with either naming convention
        
        Returns:
            DataFrame with standardized column names
        """
        df = course_segments.copy()
        
        # Map aggregated column names to optimization column names
        column_mappings = {
            'gradient_mean': 'gradient',
            'distance_sum': 'distance',
            'altitude_mean': 'altitude',
        }
        
        for old_col, new_col in column_mappings.items():
            if old_col in df.columns and new_col not in df.columns:
                df[new_col] = df[old_col]
        
        # Handle gradient conversion: if stored as percentage (values > 1), convert to decimal
        if 'gradient' in df.columns:
            # Check if gradients look like percentages (typical range -20 to +20 for %)
            sample_gradient = df['gradient'].abs().max()
            if sample_gradient > 1:  # Likely stored as percentage
                df['gradient'] = df['gradient'] / 100
        
        # Handle distance conversion: if small values, likely in km - convert to meters
        if 'distance' in df.columns:
            if df['distance'].max() < 100:  # Likely in km
                df['distance'] = df['distance'] * 1000
        
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
                speed_calc = calculate_speed_and_plot(
                    power, 
                    gradient=gradient, 
                    v_wind=wind, 
                    altitude=altitude
                )
                speed = speed_calc['speed_mps']
            except Exception as e:
                # Fallback speed calculation if physics model fails
                print(f"Warning: Physics calculation failed for segment {segment.name}: {e}")
                # Simple fallback: assume reasonable speed based on power
                speed = max(5.0, min(20.0, power / 200.0))  # Basic speed estimate
            
            # Calculate time for this segment
            time = length / speed
            total_time += time
            
            # Track W' usage and recovery
            if power > self.critical_power:
                # Using anaerobic energy above critical power
                w_used = (power - self.critical_power) * time
                w_remaining -= w_used
                
                # Check if rider "blows up" (W' depleted)
                if w_remaining < 0:
                    return pd.DataFrame(results), float('inf'), w_remaining, total_energy_used
            else:
                # Recovery below critical power
                w_recovery = (self.critical_power - power) * time
                w_remaining = min(w_remaining + w_recovery, self.w_prime)
            
            # Track total energy expenditure
            total_energy_used += power * time
            
            # Store results for this segment
            results.append({
                'segment': segment.name if hasattr(segment, 'name') else len(results),
                'gradient': gradient,
                'length': length,
                'wind': wind,
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
                w_penalty = abs(w_utilization - target_w_utilization) * total_time * 0.1
                
                # Heavily penalize finishing with too much W' remaining (inefficient)
                if w_utilization < target_w_utilization * 0.7:  # Less than 70% of target
                    w_penalty *= 5  # Strong penalty for conservative pacing
                
                # Return time plus W' utilization penalty
                return total_time + w_penalty
                
            except Exception as e:
                print(f"Warning: Optimization objective failed at power {power}: {e}")
                return 1e6 + (power - self.critical_power) ** 2        
        # Set more conservative optimization bounds to avoid numerical issues
        lower_bound = max(self.critical_power * 0.9, 150)  # More conservative lower bound
        upper_bound = min(self.critical_power * 2.0, 500)  # More conservative upper bound
        bounds = [(lower_bound, upper_bound)]
        
        # Start optimization from a reasonable power level
        initial_power = min(self.critical_power * 1.2, upper_bound)
        
        try:
            # Run optimization with multiple starting points to avoid local minima
            best_result = None
            best_objective = float('inf')
            
            # Try multiple starting points within reasonable range
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
                                target_w_utilization: float = 0.85,
                                aggressive_factor: float = 1.2) -> Tuple[pd.DataFrame, float, Dict[str, Any]]:
        """
        Optimize variable power pacing across course segments for minimal time.
        
        This method uses terrain-based heuristics to allocate power across segments,
        utilizing W' for climbs and recovering on flats/descents for optimal performance.
        
        Args:
            course_segments: DataFrame containing segment data (either aggregated or optimization-ready)
            target_w_utilization: Target W' utilization (0.0-1.0, default 0.85)
            aggressive_factor: How aggressive to be on climbs (1.0=CP, 1.5=very aggressive)
        
        Returns:
            Tuple containing:
            - DataFrame with segment-by-segment power strategy and results
            - Total course time (seconds)
            - Dictionary with strategy analysis and comparison to constant power
        """
        print(f"Optimizing variable pacing strategy (target W': {target_w_utilization*100:.0f}%)")
        
        # Normalize column names to handle both aggregated and optimization-ready formats
        course_segments = self._normalize_segments(course_segments)
        
        # Step 1: Analyze course characteristics
        course_analysis = self._analyze_course_terrain(course_segments)
        
        # Step 2: Generate initial heuristic power allocation
        initial_power_strategy = self._generate_heuristic_power_strategy(
            course_segments, course_analysis, target_w_utilization, aggressive_factor
        )
        
        # Step 3: Simulate initial strategy to check feasibility
        strategy_results = self._simulate_variable_pacing(course_segments, initial_power_strategy)
        
        # Step 4: Local optimization to refine strategy
        if strategy_results['feasible']:
            optimized_strategy = self._refine_power_strategy(
                course_segments, initial_power_strategy, target_w_utilization
            )
            final_results = self._simulate_variable_pacing(course_segments, optimized_strategy)
        else:
            # Fallback to more conservative strategy
            print("Initial strategy infeasible, using conservative fallback")
            conservative_strategy = self._generate_conservative_strategy(course_segments)
            optimized_strategy = conservative_strategy
            final_results = self._simulate_variable_pacing(course_segments, optimized_strategy)
        
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
                                         aggressive_factor: float) -> np.ndarray:
        """Generate initial power strategy based on terrain heuristics."""
        num_segments = len(course_segments)
        power_strategy = np.zeros(num_segments)
        
        # Calculate target W' to use
        target_w_to_use = self.w_prime * target_w_utilization
        
        # Get climbing segments for W' allocation
        climbing_segments = course_analysis['climbing_segments']
        climb_distance = course_analysis['climb_distance']
        
        if climb_distance > 0:
            # More conservative W' allocation approach
            # Reserve some W' for unexpected needs (only use 80% of target)
            available_w_budget = target_w_to_use * 0.8
            
            # Calculate total climb time to distribute W' more realistically
            total_climb_time = 0
            climb_segments_info = []
            
            for i, (_, segment) in enumerate(course_segments.iterrows()):
                gradient = segment['gradient']
                distance = segment['distance']
                
                if gradient > 0.03:  # Climbing segment
                    # Estimate realistic climbing time
                    estimated_speed = max(3.0, 12.0 - gradient * 60)  # More conservative speed estimate
                    estimated_time = distance / estimated_speed
                    total_climb_time += estimated_time
                    climb_segments_info.append((i, distance, estimated_time, gradient))
            
            # Distribute W' budget based on time rather than distance
            w_rate = available_w_budget / max(total_climb_time, 1)  # W'/second budget
        
        # Allocate power based on terrain type
        for i, (_, segment) in enumerate(course_segments.iterrows()):
            gradient = segment['gradient']
            distance = segment['distance']
            
            if gradient > 0.03:  # Climbing segments
                # Find this segment in climb info
                segment_time = distance / max(3.0, 12.0 - gradient * 60)
                segment_w_budget = w_rate * segment_time if climb_distance > 0 else 0
                
                # Calculate sustainable power with W' budget
                if segment_time > 0 and segment_w_budget > 0:
                    w_power_contribution = segment_w_budget / segment_time
                    base_power = self.critical_power + w_power_contribution
                    
                    # Apply conservative limits
                    max_power = self.critical_power * min(1.5, 1.1 + aggressive_factor * 0.2)  # Much more conservative
                    power_strategy[i] = min(base_power, max_power)
                else:
                    power_strategy[i] = self.critical_power * 1.05  # Very conservative fallback
                
            elif gradient < -0.02:  # Descent segments
                # Recovery power for descents
                power_strategy[i] = self.critical_power * 0.7  # Easy recovery
                
            else:  # Flat segments
                # Steady power for flats
                power_strategy[i] = self.critical_power * 1.02  # Just above CP for sustainability
        
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
                speed_calc = calculate_speed_and_plot(
                    power, gradient=gradient, v_wind=wind, altitude=altitude
                )
                speed = speed_calc['speed_mps']
            except Exception:
                # Fallback speed calculation
                speed = max(3.0, min(20.0, power / 200.0 + (1 - gradient) * 10))
            
            # Calculate time for this segment
            time = length / speed
            total_time += time
            
            # Track W' usage and recovery
            if power > self.critical_power:
                w_used = (power - self.critical_power) * time
                w_remaining -= w_used
                if w_remaining < 0:
                    feasible = False
                    # Continue simulation for analysis but mark as infeasible
            else:
                w_recovery = (self.critical_power - power) * time
                w_remaining = min(w_remaining + w_recovery, self.w_prime)
            
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
                             target_w_utilization: float) -> np.ndarray:
        """Refine power strategy using local optimization."""
        current_strategy = initial_strategy.copy()
        
        # Simulate current strategy
        sim_results = self._simulate_variable_pacing(course_segments, current_strategy)
        current_w_utilization = sim_results['w_utilization']
        
        print(f"Optimization converged to {np.mean(current_strategy):.0f}W (target W' utilization: {target_w_utilization*100:.0f}%)")
        print(f"Achieved W' utilization: {current_w_utilization*100:.1f}% (target: {target_w_utilization*100:.0f}%)")
        
        # Adjust strategy if W' utilization is off target
        utilization_error = target_w_utilization - current_w_utilization
        
        if abs(utilization_error) > 0.05:  # 5% tolerance
            # Find climbing segments to adjust
            climbing_indices = []
            for i, (_, segment) in enumerate(course_segments.iterrows()):
                if segment['gradient'] > 0.03:
                    climbing_indices.append(i)
            
            if climbing_indices:
                # If we're using too much W' (current > target), reduce power
                # If we're using too little W' (current < target), increase power
                if current_w_utilization > target_w_utilization:                    # Reduce power on climbing segments
                    reduction_factor = 0.9  # Reduce by 10%
                    for idx in climbing_indices:
                        current_strategy[idx] *= reduction_factor
                        # Keep above minimum threshold
                        current_strategy[idx] = max(self.critical_power * 1.01, float(current_strategy[idx]))
                else:
                    # Increase power on climbing segments (but be careful)
                    increase_factor = min(1.1, 1.0 + (utilization_error * 0.5))
                    for idx in climbing_indices:
                        current_strategy[idx] *= increase_factor
                        # Keep within reasonable bounds
                        current_strategy[idx] = min(float(current_strategy[idx]), self.critical_power * 1.5)
                
                # Re-simulate to check if we improved
                new_sim_results = self._simulate_variable_pacing(course_segments, current_strategy)
                new_w_utilization = new_sim_results['w_utilization']
                
                # If the adjustment made things worse or infeasible, revert to original
                if not new_sim_results['feasible'] or abs(new_w_utilization - target_w_utilization) > abs(current_w_utilization - target_w_utilization):
                    current_strategy = initial_strategy.copy()
                    print(f"Refinement made results worse, reverting to initial strategy")
                else:
                    print(f"Refined W' utilization: {new_w_utilization*100:.1f}%")
        
        return current_strategy
    
    def _generate_conservative_strategy(self, course_segments: pd.DataFrame) -> np.ndarray:
        """Generate conservative power strategy as fallback."""
        num_segments = len(course_segments)
        conservative_strategy = np.full(num_segments, self.critical_power * 1.02)
        
        # Slightly reduce power on steep climbs to ensure sustainability
        for i, (_, segment) in enumerate(course_segments.iterrows()):
            if segment['gradient'] > 0.05:  # Steep climbs
                conservative_strategy[i] = self.critical_power * 0.98
            elif segment['gradient'] < -0.02:  # Descents
                conservative_strategy[i] = self.critical_power * 0.8  # Recovery
        
        return conservative_strategy
    
    def _create_variable_pacing_results(self, course_segments: pd.DataFrame,
                                      power_strategy: np.ndarray,
                                      sim_results: Dict[str, Any]) -> pd.DataFrame:
        """Create detailed results DataFrame for variable pacing strategy."""
        results_data = []
        
        for i, segment_result in enumerate(sim_results['segment_results']):
            segment_info = course_segments.iloc[i]
            
            results_data.append({
                'segment': i,
                'distance': segment_info['distance'],
                'gradient': segment_info['gradient'],
                'altitude': segment_info.get('altitude', 0),
                'wind': segment_info.get('wind', 0),
                'target_power': segment_result['power'],
                'speed': segment_result['speed'],
                'time': segment_result['time'],
                'w_remaining': segment_result['w_remaining'],
                'w_used_segment': segment_result['w_used_segment'],
                'energy_segment': segment_result['power'] * segment_result['time'],
                'terrain_type': self._classify_terrain(segment_info['gradient']),
                'power_zone': self._classify_power_zone(segment_result['power'])
            })
        
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
        Perform high-resolution simulation with acceleration modeling.
        
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
        
        # Step 4: Simulate with acceleration modeling
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
        
        if total_points <= target_resolution:
            # No downsampling needed
            print(f"Course has {total_points} points, using all points (target: {target_resolution})")
            return df.reset_index(drop=True)
        
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
        
        print(f"Downsampled from {total_points} to {len(smoothed_df)} points ({len(smoothed_df)/total_points*100:.1f}%)")
        
        return smoothed_df
    
    def _assign_points_to_segments(self, high_res_points: pd.DataFrame, 
                                 course_segments: pd.DataFrame) -> np.ndarray:
        """
        Assign each high-resolution point to the appropriate course segment.
        
        Args:
            high_res_points: High-resolution course points
            course_segments: Course segments with distance ranges
            
        Returns:
            Array mapping each point to segment index
        """
        # Ensure cumulative_distance exists
        if 'cumulative_distance' not in high_res_points.columns:
            if 'distance' in high_res_points.columns:
                high_res_points = high_res_points.copy()
                high_res_points['cumulative_distance'] = high_res_points['distance'].cumsum()
            else:
                # Fallback: evenly distribute points across segments
                num_points = len(high_res_points)
                num_segments = len(course_segments)
                return np.repeat(np.arange(num_segments), num_points // num_segments + 1)[:num_points]
        
        point_distances = high_res_points['cumulative_distance'] / 1000  # Convert to km
        segment_mapping = np.zeros(len(high_res_points), dtype=int)
        
        # Check if enhanced segmentation format is available
        if 'start_distance' in course_segments.columns and 'end_distance' in course_segments.columns:
            # Use precise distance mapping from enhanced format
            for i, distance in enumerate(point_distances):
                # Find which segment this distance falls into
                for seg_idx, segment in course_segments.iterrows():
                    start_dist = segment['start_distance'] / 1000  # Convert to km
                    end_dist = segment['end_distance'] / 1000      # Convert to km
                    
                    if start_dist <= distance <= end_dist:
                        segment_mapping[i] = seg_idx
                        break
                else:
                    # Fallback to closest segment if no exact match
                    segment_centers = (course_segments.get('start_distance', 0) + course_segments.get('end_distance', 0)) / 2000  # km
                    closest_seg = (segment_centers - distance).abs().idxmin()
                    segment_mapping[i] = closest_seg
        else:
            # Traditional approach - distribute points evenly across segments
            total_distance = point_distances.iloc[-1]
            cumulative_segment_distance = 0
            
            for seg_idx, segment in course_segments.iterrows():
                segment_distance = segment['distance'] / 1000  # Convert to km
                segment_end = cumulative_segment_distance + segment_distance
                
                # Assign points that fall within this segment's distance range
                mask = (point_distances >= cumulative_segment_distance) & (point_distances < segment_end)
                segment_mapping[mask] = seg_idx
                
                cumulative_segment_distance = segment_end
            
            # Handle last segment edge case
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
        Simulate course with realistic acceleration modeling between points.
        
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
        
        # Calculate initial average speed for starting condition
        avg_power = np.mean(point_powers)
        try:
            initial_speed_calc = calculate_speed_and_plot(
                avg_power, 
                gradient=high_res_points['gradient'].iloc[0] / 100,  # Convert to decimal
                v_wind=0, 
                altitude=high_res_points['altitude'].iloc[0]
            )
            initial_speed = initial_speed_calc['speed_mps']
        except Exception:
            initial_speed = max(5.0, min(15.0, avg_power / 200.0))  # Fallback estimate
        
        current_speed = initial_speed
        
        for i in range(num_points):
            power = point_powers[i]
            gradient = high_res_points['gradient'].iloc[i] / 100  # Convert to decimal
            altitude = high_res_points['altitude'].iloc[i]
            
            if i == 0:
                distance_step = high_res_points['distance'].iloc[i]
            else:
                distance_step = high_res_points['distance'].iloc[i]
            
            # Calculate target speed using physics
            try:
                target_speed_calc = calculate_speed_and_plot(
                    power, gradient=gradient, v_wind=0, altitude=altitude
                )
                target_speed = target_speed_calc['speed_mps']
            except Exception:
                # Fallback speed calculation
                target_speed = max(3.0, min(20.0, power / 200.0 + (0.05 - gradient) * 10))
            
            if i == 0:
                current_speed = target_speed  # Initial condition
                acceleration = 0
            else:
                # Calculate realistic acceleration
                speed_diff = target_speed - current_speed
                
                if distance_step > 0:
                    # Estimate time step for acceleration calculation
                    avg_speed = (current_speed + target_speed) / 2
                    time_step = distance_step / max(avg_speed, 1.0)  # Avoid division by zero
                    
                    # Calculate required acceleration
                    if time_step > 0:
                        acceleration = speed_diff / time_step
                    else:
                        acceleration = 0
                    
                    # Apply realistic acceleration limits
                    max_accel = 3.0  # m/s² - realistic cycling acceleration limit
                    acceleration = np.clip(acceleration, -max_accel, max_accel)
                    
                    # Update speed with limited acceleration
                    current_speed = current_speed + acceleration * time_step
                    
                    # Ensure speed stays within reasonable bounds
                    current_speed = max(2.0, min(current_speed, 25.0))  # 2-25 m/s limits
                else:
                    acceleration = 0
            
            # Calculate time for this segment
            if current_speed > 0 and distance_step > 0:
                segment_time = distance_step / current_speed
            else:
                segment_time = 0
            
            total_time += segment_time
            
            # Track W' usage and recovery
            if power > self.critical_power:
                w_used = (power - self.critical_power) * segment_time
                w_remaining -= w_used
            else:
                w_recovery = (self.critical_power - power) * segment_time
                w_remaining = min(w_remaining + w_recovery, self.w_prime)
            
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
            'max_acceleration': np.max(accelerations),
            'min_acceleration': np.min(accelerations)
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
            'simulation_type': 'High-Resolution with Acceleration Modeling',
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
        
        # Create optimization-ready DataFrame maintaining sequence order
        optimization_segments = pd.DataFrame({
            'distance': segments['distance_sum'] * 1000,  # Convert km to meters
            'gradient': segments['gradient_mean'] / 100,  # Convert percentage to decimal
            'altitude': segments.get('altitude_mean', 0),  # Use mean altitude if available
            'wind': 0,  # Default to no wind - can be enhanced later
            # Enhanced format specific columns
            'segment_id': segments['segment_id'],              # Terrain type (1, 2, 3, 4)
            'segment_occurrence': segments['segment_occurrence'], # Nth occurrence of this type
            'segment_sequence': segments['segment_sequence'],     # Position in course
            'start_distance': segments.get('start_distance', 0) * 1000,  # Convert to meters
            'end_distance': segments.get('end_distance', 0) * 1000       # Convert to meters
        })
        
        # Sort by sequence to ensure proper order
        optimization_segments = optimization_segments.sort_values('segment_sequence').reset_index(drop=True)
        
    else:
        # Traditional aggregated format - backward compatibility
        print(f"Using traditional aggregated segmentation format with {len(segments)} segments")
        
        # Debug: Check gradient values to determine if they're already decimals or percentages
        sample_gradient = segments['gradient_mean'].iloc[0] if len(segments) > 0 else 0
        gradient_is_percentage = abs(sample_gradient) > 1.0  # If >1, likely stored as percentage
        
        # Ensure required columns exist with proper names
        optimization_segments = pd.DataFrame({
            'distance': segments['distance_sum'] * 1000,  # Convert km to meters
            'gradient': segments['gradient_mean'] / 100,  # Always convert percentage to decimal for physics calculations
            'altitude': segments.get('altitude_mean', 0),  # Use mean altitude if available
            'wind': 0  # Default to no wind - can be enhanced later
        })
    
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
