#!/usr/bin/env python3
"""
Test gradient fix for Course Optimization page
"""

import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course

def test_course_optimization_gradients():
    """Test that Course Optimization displays correct gradients and times."""
    
    print("=== Testing Course Optimization Gradient Fix ===")
    
    # Create realistic test course (5% average gradient)
    test_data = pd.DataFrame({
        'lat': [47.6 + i*0.001 for i in range(20)],
        'lon': [-122.3 - i*0.0005 for i in range(20)],
        'altitude': [100 + i*5 for i in range(20)]  # 5m rise per point for 5% grade
    })
    
    # Process course
    course = Course(test_data)
    course.equal_segmentation(5)
    
    print("1. Course segment gradients:")
    gradients = course.course_segments['gradient_mean'].values
    print(f"   Values: {gradients}")
    print(f"   Range: {gradients.min():.1f}% to {gradients.max():.1f}%")
    print(f"   ✅ Should show reasonable percentages (2-8%)")
    
    # Test optimization
    optimization_segments = create_course_segments_from_course(course)
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    
    print("\n2. Optimization segment gradients:")
    opt_gradients = optimization_segments['gradient'].values
    print(f"   Values: {opt_gradients}")
    print(f"   Range: {opt_gradients.min():.3f} to {opt_gradients.max():.3f} (decimal)")
    print(f"   Percentage: {opt_gradients.min()*100:.1f}% to {opt_gradients.max()*100:.1f}%")
    
    # Test simulation time
    print("\n3. Course simulation at 300W:")
    results, time, w_remaining, energy = optimizer.simulate_course_time(300, optimization_segments)
    
    print(f"   Total time: {time/60:.1f} minutes")
    print(f"   Distance: {optimization_segments['distance'].sum()/1000:.2f} km")
    print(f"   Average speed: {(optimization_segments['distance'].sum()/time)*3.6:.1f} km/h")
    
    if 10 <= time/60 <= 40:
        print("   ✅ REALISTIC: Time is reasonable for cycling")
    else:
        print("   ❌ UNREALISTIC: Time seems too fast or slow")
    
    print("\n4. Segment analysis:")
    for i, (_, segment) in enumerate(optimization_segments.iterrows()):
        segment_result = results.iloc[i] if i < len(results) else None
        if segment_result is not None:
            speed_kmh = segment_result['speed'] * 3.6
            print(f"   Segment {i+1}: {segment['gradient']*100:.1f}% grade, {speed_kmh:.1f} km/h")

if __name__ == "__main__":
    test_course_optimization_gradients()
