#!/usr/bin/env python3
"""
Test the gradient conversion fix
"""

import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from app.course import Course
from app.optimization import create_course_segments_from_course

def test_gradient_conversion():
    """Test that gradient conversion works correctly."""
    
    print("=== Testing Gradient Conversion Fix ===")
    
    # Create test course with known gradients (2% grade)
    test_data = pd.DataFrame({
        'lat': [47.6 + i*0.001 for i in range(20)],
        'lon': [-122.3 - i*0.0005 for i in range(20)],
        'altitude': [100 + i*2 for i in range(20)]  # 2m rise per point
    })
    
    course = Course(test_data)
    course.equal_segmentation(5)
    
    print("\n1. Raw course gradients (after processing):")
    print(f"   Sample values: {course.df['gradient'].head(5).values}")
    print(f"   Should be around 200% because stored as percentage")
    
    print("\n2. Aggregated segment gradients:")
    print(f"   Values: {course.course_segments['gradient_mean'].values}")
    print(f"   Should still be around 200% (percentage format)")
    
    print("\n3. Optimization-ready gradients:")
    opt_segments = create_course_segments_from_course(course)
    print(f"   Values: {opt_segments['gradient'].values}")
    print(f"   Should be around 2.0 (converted from 200% to decimal)")
    
    print("\n4. Validation:")
    avg_gradient = opt_segments['gradient'].mean()
    if 1.5 <= avg_gradient <= 2.5:
        print(f"   ✅ SUCCESS: Average gradient {avg_gradient:.2f} is reasonable for 2% grade")
    else:
        print(f"   ❌ PROBLEM: Average gradient {avg_gradient:.2f} is not reasonable")
        
    print(f"\n5. Gradient range check:")
    max_gradient = opt_segments['gradient'].max()
    if max_gradient > 0.5:
        print(f"   ⚠️  WARNING: Max gradient {max_gradient:.3f} ({max_gradient*100:.1f}%) seems very high")
    else:
        print(f"   ✅ OK: Max gradient {max_gradient:.3f} ({max_gradient*100:.1f}%) is reasonable")

if __name__ == "__main__":
    test_gradient_conversion()
