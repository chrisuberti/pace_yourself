"""
Debug script to check optimization data structure and display_performance_metrics
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course
from app.rider import Rider

def debug_optimization_data():
    """Debug the optimization results structure."""
    
    print("🔍 Debug: Optimization Data Structure")
    print("=" * 50)
    
    # Create mock course data
    print("1️⃣ Creating mock course...")
    
    mock_data = pd.DataFrame({
        'lat': np.linspace(40.0, 40.1, 100),
        'lon': np.linspace(-74.0, -73.9, 100),
        'altitude': 100 + np.sin(np.linspace(0, 4*np.pi, 100)) * 50,
        'cumulative_distance': np.linspace(0, 10000, 100),
        'distance': np.full(100, 100),
        'gradient': np.sin(np.linspace(0, 4*np.pi, 100)) * 0.05,
        'bearing': np.linspace(0, 360, 100),
        'height_gain': np.random.uniform(0, 5, 100),
        'height_loss': np.random.uniform(0, 5, 100)
    })
    
    course = Course(mock_data)
    
    # Segment the course with same parameters as 01 page
    print("2️⃣ Segmenting course...")
    course.auto_segmentation(
        max_clusters=5,
        gradient_weight=0.5,
        bearing_weight=0.5,
        smoothing_window=20
    )
    
    print(f"   ✅ Course segmented into {len(course.course_segments)} segments")
    
    # Create course segments for optimization
    print("3️⃣ Preparing optimization...")
    course_segments = create_course_segments_from_course(course)
    
    # Create rider
    rider = Rider(
        height=1.75,
        weight=75,
        critical_power=300
    )
    
    # Create optimizer and run constant power optimization
    print("4️⃣ Running constant power optimization...")
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    results = optimizer.optimize_constant_power(course_segments)
    
    print(f"   ✅ Optimization completed")
    
    # Analyze results structure
    print("\n📊 Results Structure Analysis:")
    print(f"   Results keys: {list(results.keys())}")
    
    for key, value in results.items():
        if isinstance(value, dict):
            print(f"   📁 {key}: {type(value)} with keys: {list(value.keys())}")
        elif isinstance(value, pd.DataFrame):
            print(f"   📊 {key}: DataFrame with {len(value)} rows, columns: {list(value.columns)}")
        else:
            print(f"   📄 {key}: {type(value)} = {value}")
    
    # Check granular_analysis specifically
    if 'granular_analysis' in results:
        print(f"\n🔍 Granular Analysis Details:")
        granular = results['granular_analysis']
        
        if isinstance(granular, dict):
            for key, value in granular.items():
                print(f"   📊 {key}: {value}")
        else:
            print(f"   ⚠️ granular_analysis is not a dict: {type(granular)}")
    else:
        print("   ❌ No 'granular_analysis' key found")
    
    # Check course_segments distance values
    print(f"\n📏 Course Segments Distance Analysis:")
    if hasattr(course, 'course_segments'):
        segments = course.course_segments
        print(f"   📊 Segments DataFrame shape: {segments.shape}")
        print(f"   📊 Columns: {list(segments.columns)}")
        
        if 'distance_sum' in segments.columns:
            distances = segments['distance_sum']
            print(f"   📏 Distance values: {distances.tolist()}")
            print(f"   📏 Zero distances: {(distances == 0).sum()}")
            print(f"   📏 Total distance: {distances.sum():.2f} km")
        else:
            print("   ❌ No 'distance_sum' column found")
    
    return results

if __name__ == "__main__":
    debug_optimization_data()
