"""
Test for zero distance segments issue
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.course import Course

def test_zero_distance_segments():
    """Test if segmentation creates zero distance segments."""
    
    print("🔧 Testing Zero Distance Segments Issue")
    print("=" * 50)
    
    # Create test course with more realistic data
    mock_data = pd.DataFrame({
        'lat': np.linspace(40.0, 40.1, 200),  # More data points
        'lon': np.linspace(-74.0, -73.9, 200),
        'altitude': 100 + np.sin(np.linspace(0, 4*np.pi, 200)) * 50,
        'cumulative_distance': np.linspace(0, 20000, 200),  # 20km total
        'distance': np.full(200, 100),  # 100m per point
        'gradient': np.sin(np.linspace(0, 4*np.pi, 200)) * 0.05,
        'bearing': np.linspace(0, 360, 200),
        'height_gain': np.random.uniform(0, 5, 200),
        'height_loss': np.random.uniform(0, 5, 200)
    })
    
    course = Course(mock_data)
    
    # Test segmentation with default parameters from 01 page
    print("🔧 Testing segmentation with 01 page defaults...")
    course.auto_segmentation(
        max_clusters=5,
        gradient_weight=0.5,
        bearing_weight=0.5,
        smoothing_window=20
    )
    
    print(f"✅ Segmented into {len(course.course_segments)} segments")
    
    # Check for zero distance segments
    zero_dist_count = (course.course_segments['distance_sum'] == 0).sum()
    print(f"\n📏 Zero distance segments: {zero_dist_count}")
    
    print("\n📊 Segment Details:")
    # Use columns that actually exist in the segmentation output
    available_cols = ['segment', 'distance_sum', 'gradient_mean']
    segment_summary = course.course_segments[[c for c in available_cols if c in course.course_segments.columns]].round(3)
    print(segment_summary)
    
    # Check total distance
    total_dist = course.course_segments['distance_sum'].sum()
    expected_dist = mock_data['distance'].sum() / 1000  # Convert to km
    print(f"\n🎯 Distance Check:")
    print(f"   Total from segments: {total_dist:.2f} km")
    print(f"   Expected total: {expected_dist:.2f} km")
    print(f"   Difference: {abs(total_dist - expected_dist):.2f} km")
    
    # Check if any segments have very small distances (potential issue)
    small_segments = course.course_segments[course.course_segments['distance_sum'] < 0.1]  # Less than 100m
    if len(small_segments) > 0:
        print(f"\n⚠️ Found {len(small_segments)} segments with distance < 100m:")
        print(small_segments[['segment_id', 'distance_sum', 'segment_sequence']])
    else:
        print("\n✅ All segments have reasonable distances (>100m)")

if __name__ == "__main__":
    test_zero_distance_segments()
