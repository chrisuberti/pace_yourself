#!/usr/bin/env python3
"""
Debug distance calculation
"""

import pandas as pd
import numpy as np
from app.course import Course

def debug_distance_calculation():
    """Debug why distances are too small."""
    
    print("=== Debugging Distance Calculation ===")
    
    # Create test course with known distance
    # 20 points, each 0.001 degree apart in latitude = ~111m each = ~2.22km total
    test_data = pd.DataFrame({
        'lat': [47.6 + i*0.001 for i in range(20)],
        'lon': [-122.3 - i*0.0005 for i in range(20)],
        'altitude': [100 + i*5 for i in range(20)]
    })
    
    print("1. Input data:")
    print(f"   Lat range: {test_data['lat'].min():.3f} to {test_data['lat'].max():.3f}")
    print(f"   Lon range: {test_data['lon'].min():.3f} to {test_data['lon'].max():.3f}")
    print(f"   Expected total distance: ~2.2 km")
    
    # Manual distance calculation
    lat_diff = test_data['lat'].max() - test_data['lat'].min()
    lon_diff = test_data['lon'].max() - test_data['lon'].min()
    manual_distance = np.sqrt((lat_diff * 111139)**2 + (lon_diff * 111139 * np.cos(np.radians(47.6)))**2)
    print(f"   Manual calculation: {manual_distance/1000:.2f} km")
    
    # Process with Course
    course = Course(test_data)
    
    print("\n2. Course processing results:")
    print(f"   Individual distances: {course.df['distance'].head(5).values}")
    print(f"   Total distance: {course.df['distance'].sum()/1000:.2f} km")
    print(f"   Max cumulative: {course.df['cumulative_distance'].max()/1000:.2f} km")
    
    # Segment results
    course.equal_segmentation(5)
    print(f"\n3. Segment distances:")
    print(f"   Segment distances: {course.course_segments['distance_sum'].values}")
    print(f"   Total segmented: {course.course_segments['distance_sum'].sum():.2f} km")

if __name__ == "__main__":
    debug_distance_calculation()
