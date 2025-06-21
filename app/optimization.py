"""
Course Optimization Module

This module provides optimization algorithms for cycling course pacing strategies.
Integrated from notebooks/StartCourseEstimation.ipynb as part of Phase 1 consolidation.
"""

import pandas as pd
import numpy as np
from scipy.optimize import minimize
from typing import Tuple, Dict, Any, Optional
from app.cycling_physics import calculate_speed_and_plot


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
    
    def simulate_course_time(self, power: float, course_segments: pd.DataFrame) -> Tuple[pd.DataFrame, float, float, float]:
        """
        Simulate course time and W' usage for a given constant power.
        
        This function calculates the time to complete each segment at a constant power,
        tracking W' depletion and recovery throughout the course.
        
        Args:
            power: Constant power output (W)
            course_segments: DataFrame containing segment data with columns:
                - gradient: Segment gradient (decimal, e.g., 0.05 for 5%)
                - distance: Segment distance (meters)
                - wind: Wind speed (m/s, positive = tailwind)
                - altitude: Segment altitude (meters)
        
        Returns:
            Tuple containing:
            - DataFrame with segment-by-segment results
            - Total course time (seconds)
            - Remaining W' at finish (J)
            - Total energy used (J)
        """
        total_time = 0
        w_remaining = self.w_prime
        total_energy_used = 0
        results = []
        
        for _, segment in course_segments.iterrows():
            gradient = segment['gradient']
            length = segment['distance']
            wind = segment.get('wind', 0)  # Default to no wind if not specified
            altitude = segment.get('altitude', 0)  # Default to sea level
            
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
                'w_remaining': w_remaining,
                'total_energy_used': total_energy_used
            })
        
        return pd.DataFrame(results), total_time, w_remaining, total_energy_used
    
    def optimize_constant_power(self, course_segments: pd.DataFrame) -> Tuple[float, float, pd.DataFrame]:
        """
        Find the optimal constant power to efficiently use the rider's energy budget.
        
        This optimization seeks to find the power that minimizes total time while
        efficiently utilizing the rider's available energy (CP × time + W').
        
        Args:
            course_segments: DataFrame containing course segment data
        
        Returns:
            Tuple containing:
            - Optimal power (W)
            - Total course time at optimal power (seconds)
            - DataFrame with segment-by-segment results at optimal power
        """
        def objective(power: float) -> float:
            """Objective function to minimize: time + penalty for inefficient energy use"""
            try:
                _, total_time, _, total_energy_used = self.simulate_course_time(power, course_segments)
                
                # Calculate theoretical energy budget
                energy_budget = self.critical_power * total_time + self.w_prime
                
                # Penalize deviation from efficient energy use
                energy_penalty = abs(energy_budget - total_energy_used) * 0.001  # Scale penalty
                
                # Return total time plus penalty (minimize time while using energy efficiently)
                return total_time + energy_penalty
                
            except Exception as e:
                print(f"Warning: Optimization objective failed at power {power}: {e}")
                return float('inf')  # Return high penalty for failed calculations
        
        # Set optimization bounds around critical power
        lower_bound = max(50, self.critical_power - 100)  # Don't go too low
        upper_bound = self.critical_power * 3  # Allow significant overpowering
        bounds = [(lower_bound, upper_bound)]
        
        try:
            # Run optimization
            result = minimize(
                lambda p: objective(p[0]), 
                x0=[self.critical_power], 
                bounds=bounds, 
                method='L-BFGS-B'
            )
            
            if result.success:
                optimal_power = result.x[0]
            else:
                print(f"Optimization failed: {result.message}")
                optimal_power = self.critical_power  # Fallback to critical power
                
        except Exception as e:
            print(f"Optimization error: {e}")
            optimal_power = self.critical_power  # Fallback to critical power
        
        # Get detailed results at optimal power
        df_results, optimal_time, w_remaining, total_energy = self.simulate_course_time(
            optimal_power, course_segments
        )
        
        return optimal_power, optimal_time, df_results
    
    def analyze_pacing_strategy(self, course_segments: pd.DataFrame) -> Dict[str, Any]:
        """
        Comprehensive analysis of pacing strategy for a given course.
        
        Args:
            course_segments: DataFrame containing course segment data
        
        Returns:
            Dictionary containing analysis results including optimal power,
            segment breakdown, energy utilization, and performance metrics
        """
        # Get optimal constant power strategy
        optimal_power, total_time, segment_results = self.optimize_constant_power(course_segments)
        
        # Calculate course statistics
        total_distance = course_segments['distance'].sum() / 1000  # Convert to km
        average_speed = (total_distance * 1000) / total_time * 3.6  # km/h
        elevation_gain = course_segments[course_segments['gradient'] > 0]['distance'].sum() * \
                        course_segments[course_segments['gradient'] > 0]['gradient'].mean()
        
        # Calculate energy utilization
        final_w_remaining = segment_results['w_remaining'].iloc[-1]
        w_utilization = (self.w_prime - final_w_remaining) / self.w_prime * 100
        
        # Identify critical segments (highest power demand)
        segment_results['power_demand'] = segment_results['gradient'] * segment_results['length']
        critical_segments = segment_results.nlargest(3, 'power_demand')[['segment', 'gradient', 'time']]
        
        return {
            'optimal_power': optimal_power,
            'total_time_minutes': total_time / 60,
            'total_distance_km': total_distance,
            'average_speed_kmh': average_speed,
            'elevation_gain_m': elevation_gain,
            'w_prime_utilization_percent': w_utilization,
            'final_w_remaining': final_w_remaining,
            'critical_segments': critical_segments.to_dict('records'),
            'segment_breakdown': segment_results,
            'performance_metrics': {
                'power_to_weight': optimal_power / 75,  # Assume 75kg rider
                'normalized_power': optimal_power,  # For constant power, NP = power
                'intensity_factor': optimal_power / self.critical_power,
                'tss_estimate': (total_time / 3600) * (optimal_power / self.critical_power) ** 2 * 100
            }
        }


def create_course_segments_from_course(course) -> pd.DataFrame:
    """
    Convert Course object segments to optimization-ready DataFrame.
    
    Args:
        course: Course object with aggregated segments
    
    Returns:
        DataFrame formatted for optimization functions
    """
    if not hasattr(course, 'course_segments'):
        raise ValueError("Course must have aggregated segments. Run segmentation first.")
    
    segments = course.course_segments.copy()
    
    # Ensure required columns exist with proper names
    optimization_segments = pd.DataFrame({
        'distance': segments['distance_sum'] * 1000,  # Convert km to meters
        'gradient': segments['gradient_mean'] / 100,  # Convert percentage to decimal
        'altitude': segments.get('altitude_mean', 0),  # Use mean altitude if available
        'wind': 0  # Default to no wind - can be enhanced later
    })
    
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
    
    print("\nTesting comprehensive analysis...")
    analysis = optimizer.analyze_pacing_strategy(example_segments)
    print(f"Analysis complete - Average speed: {analysis['average_speed_kmh']:.1f} km/h")
