#!/usr/bin/env python3
"""
Test script to verify that the W' optimization is working correctly
and meaningfully depleting the W' tank.
"""

import pandas as pd
import numpy as np
import sys
import os

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'app')))

from app.optimization import CourseOptimizer

def create_test_course():
    """Create a challenging test course with varied terrain."""
    print("Creating test course...")
    
    # Create a challenging hilly course (20km with significant climbs)
    segments = []
    
    # Segment 1: Flat start (2km, 0% grade)
    segments.append({'distance': 2000, 'gradient': 0.0, 'altitude': 100, 'wind': 0})
    
    # Segment 2: Moderate climb (3km, 6% grade)
    segments.append({'distance': 3000, 'gradient': 0.06, 'altitude': 280, 'wind': 0})
    
    # Segment 3: Steep climb (2km, 12% grade)
    segments.append({'distance': 2000, 'gradient': 0.12, 'altitude': 520, 'wind': 0})
    
    # Segment 4: Rolling hills (5km, 3% grade)
    segments.append({'distance': 5000, 'gradient': 0.03, 'altitude': 670, 'wind': 0})
    
    # Segment 5: Steep descent (3km, -8% grade)
    segments.append({'distance': 3000, 'gradient': -0.08, 'altitude': 430, 'wind': 0})
    
    # Segment 6: Final flat (5km, 1% grade)
    segments.append({'distance': 5000, 'gradient': 0.01, 'altitude': 480, 'wind': 0})
    
    return pd.DataFrame(segments)

def test_power_levels(optimizer, course_segments, power_levels):
    """Test different power levels to see W' depletion patterns."""
    print(f"\nTesting power levels: {power_levels}")
    print("Power (W) | Time (min) | W' Used (%) | W' Remaining (kJ) | Status")
    print("-" * 70)
    
    results = {}
    
    for power in power_levels:
        try:
            df_results, total_time, w_remaining, total_energy = optimizer.simulate_course_time(
                power, course_segments
            )
            
            if total_time != float('inf'):
                w_used = optimizer.w_prime - w_remaining
                w_utilization = (w_used / optimizer.w_prime) * 100
                status = "✅ Success"
                time_min = total_time / 60
                w_remaining_kj = w_remaining / 1000
            else:
                w_utilization = 100.0  # W' depleted
                status = "❌ Failed (W' depleted)"
                time_min = float('inf')
                w_remaining_kj = 0.0
            
            results[power] = {
                'time': total_time,
                'w_utilization': w_utilization,
                'w_remaining': w_remaining,
                'status': status
            }
            
            print(f"{power:8d} | {time_min:9.1f} | {w_utilization:10.1f} | {w_remaining_kj:16.1f} | {status}")
            
        except Exception as e:
            print(f"{power:8d} | {'Error':>9} | {'Error':>10} | {'Error':>16} | ❌ Error: {e}")
            results[power] = {'error': str(e)}
    
    return results

def test_optimization(optimizer, course_segments, target_utilizations):
    """Test the optimization function with different W' utilization targets."""
    print(f"\nTesting optimization with different W' utilization targets...")
    print("Target W' (%) | Optimal Power (W) | Achieved W' (%) | Time (min) | Status")
    print("-" * 75)
    
    for target_util in target_utilizations:
        try:
            optimal_power, optimal_time, df_results = optimizer.optimize_constant_power(
                course_segments, target_w_utilization=target_util
            )
            
            w_remaining = df_results['w_remaining'].iloc[-1]
            w_used = optimizer.w_prime - w_remaining
            achieved_util = (w_used / optimizer.w_prime) * 100
            time_min = optimal_time / 60
            
            print(f"{target_util*100:11.0f} | {optimal_power:15.0f} | {achieved_util:13.1f} | {time_min:9.1f} | ✅ Success")
            
        except Exception as e:
            print(f"{target_util*100:11.0f} | {'Error':>15} | {'Error':>13} | {'Error':>9} | ❌ Error: {e}")

def main():
    """Main test function."""
    print("=== W' Tank Optimization Test ===")
    
    # Test rider parameters
    critical_power = 300  # W
    w_prime = 25000  # J (25 kJ)
    
    print(f"Rider: CP = {critical_power}W, W' = {w_prime/1000:.0f}kJ")
    
    # Create test course
    course_segments = create_test_course()
    total_distance = course_segments['distance'].sum() / 1000
    total_elevation = course_segments[course_segments['gradient'] > 0]['distance'].sum() * \
                     course_segments[course_segments['gradient'] > 0]['gradient'].mean()
    avg_gradient = (course_segments['gradient'] * course_segments['distance']).sum() / course_segments['distance'].sum()
    
    print(f"Course: {total_distance:.1f}km, {total_elevation:.0f}m elevation gain, {avg_gradient*100:.1f}% avg gradient")
    
    # Create optimizer
    optimizer = CourseOptimizer(critical_power, w_prime)
    
    # Test 1: Different power levels
    print("\n" + "="*50)
    print("TEST 1: Power Level Analysis")
    print("="*50)
    
    power_levels = [250, 275, 300, 325, 350, 375, 400, 425, 450]
    power_results = test_power_levels(optimizer, course_segments, power_levels)
    
    # Test 2: Optimization with different W' targets
    print("\n" + "="*50)
    print("TEST 2: Optimization Analysis")
    print("="*50)
    
    target_utilizations = [0.5, 0.7, 0.85, 0.95]  # 50%, 70%, 85%, 95%
    test_optimization(optimizer, course_segments, target_utilizations)
    
    # Test 3: Full analysis
    print("\n" + "="*50)
    print("TEST 3: Full Pacing Strategy Analysis")
    print("="*50)
    
    try:
        analysis = optimizer.analyze_pacing_strategy(course_segments)
        
        print(f"Optimal Power: {analysis['optimal_power']:.0f}W")
        print(f"Total Time: {analysis['total_time_minutes']:.1f} minutes")
        print(f"Average Speed: {analysis['average_speed_kmh']:.1f} km/h")
        print(f"W' Utilization: {analysis['w_prime_utilization_percent']:.1f}%")
        print(f"Intensity Factor: {analysis['performance_metrics']['intensity_factor']:.2f}")
        print(f"Estimated TSS: {analysis['performance_metrics']['tss_estimate']:.0f}")
        
        print("\nSegment Breakdown:")
        segment_breakdown = analysis['segment_breakdown']
        for idx, row in segment_breakdown.iterrows():
            w_remaining_kj = row['w_remaining'] / 1000
            gradient_pct = row['gradient'] * 100
            speed_kmh = row['speed'] * 3.6
            print(f"  Segment {idx+1}: {gradient_pct:+5.1f}% grade, {speed_kmh:4.1f} km/h, W' = {w_remaining_kj:4.1f}kJ")
        
        print("\n✅ Full analysis completed successfully!")
        
    except Exception as e:
        print(f"❌ Full analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
