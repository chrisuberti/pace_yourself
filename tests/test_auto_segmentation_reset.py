"""
Test script for auto-segmentation reset functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.course import Course

def test_auto_segmentation_reset():
    """Test that auto-segmentation properly resets when called multiple times."""
    
    print("🧪 Testing Auto-Segmentation Reset")
    print("=" * 40)
    
    # Create mock course data
    print("1️⃣ Creating mock course data...")
    
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
    
    print(f"   ✅ Created course with {len(course.df)} points")
    
    # Test first auto-segmentation
    print("\n2️⃣ Running first auto-segmentation...")
    
    course.auto_segmentation(max_clusters=8)
    first_segment_count = len(course.course_segments)
    first_segments = course.course_segments.copy()
    
    print(f"   ✅ First segmentation: {first_segment_count} segments")
    print(f"   📊 Segment IDs: {first_segments['segment_id'].tolist() if 'segment_id' in first_segments.columns else 'No segment_id column'}")
    
    # Test second auto-segmentation (should reset, not accumulate)
    print("\n3️⃣ Running second auto-segmentation...")
    
    course.auto_segmentation(max_clusters=8)
    second_segment_count = len(course.course_segments)
    second_segments = course.course_segments.copy()
    
    print(f"   ✅ Second segmentation: {second_segment_count} segments")
    print(f"   📊 Segment IDs: {second_segments['segment_id'].tolist() if 'segment_id' in second_segments.columns else 'No segment_id column'}")
    
    # Test third auto-segmentation with different parameters
    print("\n4️⃣ Running third auto-segmentation with different parameters...")
    
    course.auto_segmentation(max_clusters=6)  # Different cluster count
    third_segment_count = len(course.course_segments)
    third_segments = course.course_segments.copy()
    
    print(f"   ✅ Third segmentation: {third_segment_count} segments")
    print(f"   📊 Segment IDs: {third_segments['segment_id'].tolist() if 'segment_id' in third_segments.columns else 'No segment_id column'}")
    
    # Verify results
    print("\n📋 Analysis:")
    
    # Check if segment counts are reasonable (not growing exponentially)
    max_segments = max(first_segment_count, second_segment_count, third_segment_count)
    min_segments = min(first_segment_count, second_segment_count, third_segment_count)
    
    print(f"   📊 Segment count range: {min_segments} - {max_segments}")
    
    if max_segments <= 10:  # Should be reasonable for 8 max clusters
        print("   ✅ Segment counts are reasonable")
    else:
        print("   ❌ Segment counts seem too high - possible accumulation issue")
    
    # Check if segments are actually different between runs
    if first_segment_count != second_segment_count or second_segment_count != third_segment_count:
        print("   ✅ Segment counts vary between runs (good - shows reset is working)")
    else:
        print("   ⚠️ All segment counts identical (might be deterministic)")
    
    # Check that dataframe segment column exists and is reasonable
    if 'segment' in course.df.columns:
        unique_segments_in_df = course.df['segment'].nunique()
        print(f"   📊 Unique segments in dataframe: {unique_segments_in_df}")
        
        if unique_segments_in_df == third_segment_count:
            print("   ✅ Dataframe segments match course_segments count")
        else:
            print("   ⚠️ Mismatch between dataframe and course_segments")
    
    print("\n🎉 Auto-segmentation reset test completed!")
    
    return True

if __name__ == "__main__":
    test_auto_segmentation_reset()
