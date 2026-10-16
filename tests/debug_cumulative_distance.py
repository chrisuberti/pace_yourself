#!/usr/bin/env python3
"""
Debug script to identify the cumulative_distance error
"""

import pandas as pd
import numpy as np
import sys
import os

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course

def debug_cumulative_distance_error():
    """Debug the cumulative_distance error step by step."""
    
    print("🔍 Debugging cumulative_distance error...")
    print("=" * 50)
    
    # Create test course data similar to what Strava would provide
    print("1. Creating test course data...")
    test_data = pd.DataFrame({
        'lat': np.linspace(47.6, 47.65, 100),
        'lon': np.linspace(-122.3, -122.25, 100),
        'altitude': 100 + np.sin(np.linspace(0, 2*np.pi, 100)) * 50,
    })
    
    print(f"   - Original data shape: {test_data.shape}")
    print(f"   - Original columns: {list(test_data.columns)}")
    
    # Create Course object
    print("\n2. Creating Course object...")
    try:
        course = Course(test_data)
        print("   ✅ Course created successfully")
        print(f"   - After processing columns: {list(course.df.columns)}")
        print(f"   - DataFrame shape: {course.df.shape}")
        
        # Check required columns
        required_cols = ['cumulative_distance', 'gradient', 'distance', 'bearing']
        missing_cols = [col for col in required_cols if col not in course.df.columns]
        if missing_cols:
            print(f"   ❌ Missing columns: {missing_cols}")
        else:
            print(f"   ✅ All required columns present")
            
    except Exception as e:
        print(f"   ❌ Error creating course: {str(e)}")
        return
    
    # Test segmentation
    print("\n3. Testing auto-segmentation...")
    try:
        course.auto_segmentation(max_clusters=5)
        print("   ✅ Auto-segmentation successful")
        
        if hasattr(course, 'course_segments'):
            print(f"   - Segments created: {len(course.course_segments)}")
            print(f"   - Segment columns: {list(course.course_segments.columns)}")
        else:
            print("   ❌ No course_segments attribute")
            
    except Exception as e:
        print(f"   ❌ Error in segmentation: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Test create_course_segments_from_course
    print("\n4. Testing create_course_segments_from_course...")
    try:
        optimization_segments = create_course_segments_from_course(course)
        print("   ✅ Optimization segments created successfully")
        print(f"   - Optimization segments shape: {optimization_segments.shape}")
        print(f"   - Optimization segments columns: {list(optimization_segments.columns)}")
        
    except Exception as e:
        print(f"   ❌ Error creating optimization segments: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Test optimization
    print("\n5. Testing optimization...")
    try:
        optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
        optimal_power, const_time, const_detailed = optimizer.optimize_constant_power(optimization_segments)
        print("   ✅ Constant power optimization successful")
        print(f"   - Optimal power: {optimal_power}W")
        print(f"   - Time: {const_time/60:.1f} minutes")
        
    except Exception as e:
        print(f"   ❌ Error in optimization: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n🎉 All tests passed! The cumulative_distance error is not reproduced with this test data.")
    print("The issue might be with the specific course data loaded in the application.")

if __name__ == "__main__":
    debug_cumulative_distance_error()
