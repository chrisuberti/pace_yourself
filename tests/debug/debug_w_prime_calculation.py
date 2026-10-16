"""
Debug script to understand W' utilization calculation in variable pacing.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.optimization import CourseOptimizer

def debug_w_prime_calculation():
    """Debug W' utilization calculation step by step."""
    
    print("=== W' Calculation Debug ===")
    
    # Create simple test case
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    print(f"Optimizer CP: {optimizer.critical_power}W, W': {optimizer.w_prime}J")
    
    # Simple course with one climbing segment
    test_segments = pd.DataFrame({
        'distance': [1000, 2000, 1000],  # 1km, 2km, 1km
        'gradient': [0.0, 0.08, 0.0],   # flat, 8% climb, flat
        'altitude': [100, 100, 260],     # realistic elevation
        'wind': [0, 0, 0]
    })
    
    print("\nCourse segments:")
    print(test_segments)
    
    # Test variable pacing
    print("\n=== Variable Pacing Simulation ===")
    results_df, total_time, analysis = optimizer.optimize_variable_pacing(
        test_segments, target_w_utilization=0.85
    )
    
    print(f"\nResults:")
    print(f"Total time: {total_time/60:.2f} minutes")
    print(f"Reported W' utilization: {analysis['w_prime_utilization_percent']:.1f}%")
    print(f"Final W' remaining: {analysis['final_w_remaining']:.0f}J")
    
    # Manual calculation
    w_used_total = optimizer.w_prime - analysis['final_w_remaining']
    w_utilization_manual = (w_used_total / optimizer.w_prime) * 100
    print(f"Manual W' utilization: {w_utilization_manual:.1f}%")
    
    print("\nSegment breakdown:")
    print(results_df[['segment', 'target_power', 'time', 'w_remaining', 'w_used_segment', 'terrain_type']])
    
    # Check W' balance
    print("\n=== W' Balance Check ===")
    print(f"Initial W': {optimizer.w_prime}J")
    total_w_used_segments = results_df['w_used_segment'].sum()
    print(f"Total W' used in segments: {total_w_used_segments:.0f}J")
    print(f"Final W' remaining: {analysis['final_w_remaining']:.0f}J")
    print(f"Balance check: {optimizer.w_prime - total_w_used_segments:.0f}J (should equal final W' remaining)")
    
    # Check each segment manually
    print("\n=== Segment-by-Segment W' Tracking ===")
    w_current = optimizer.w_prime
    for i, row in results_df.iterrows():
        power = row['target_power']
        time = row['time']
        
        if power > optimizer.critical_power:
            w_used = (power - optimizer.critical_power) * time
            w_current -= w_used
            print(f"Segment {i}: Power {power:.0f}W, Time {time:.0f}s, W' used {w_used:.0f}J, W' remaining {w_current:.0f}J")
        else:
            w_recovered = (optimizer.critical_power - power) * time
            w_current = min(w_current + w_recovered, optimizer.w_prime)
            print(f"Segment {i}: Power {power:.0f}W, Time {time:.0f}s, W' recovered {w_recovered:.0f}J, W' remaining {w_current:.0f}J")
    
    print(f"Final manual W' calculation: {w_current:.0f}J")
    
    return results_df, analysis

if __name__ == "__main__":
    debug_w_prime_calculation()
