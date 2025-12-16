"""
Test script for visualization fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.optimization import CourseOptimizer, create_course_segments_from_course
from app.visualizations_granular import create_segment_summary_table, create_power_step_function

def test_visualization_fixes():
    """Test the fixed visualization functions."""
    
    print("🧪 Testing Visualization Fixes")
    print("=" * 50)
    
    # Create test data similar to real optimization results
    print("1️⃣ Creating test optimization segments and results...")
    
    # Optimization segments (what goes into the optimization)
    optimization_segments = pd.DataFrame({
        'distance': [1500, 800, 2000, 600, 1200, 900, 1000],  # meters
        'gradient': [0.01, 0.055, 0.005, 0.082, -0.005, 0.060, -0.04],  # decimal
        'altitude': [100, 120, 115, 140, 130, 145, 125],   # m
        'wind': [0, 0, 0, 0, 0, 0, 0]
    })
    
    # Segment results (what comes back from optimization)
    segment_results = pd.DataFrame({
        'segment': [0, 1, 2, 3, 4, 5, 6],
        'gradient': [0.01, 0.055, 0.005, 0.082, -0.005, 0.060, -0.04],
        'length': [1500, 800, 2000, 600, 1200, 900, 1000],  # meters
        'wind': [0, 0, 0, 0, 0, 0, 0],
        'speed': [12.5, 8.2, 13.1, 6.8, 14.2, 7.9, 16.5],  # m/s
        'time': [120, 98, 153, 88, 85, 114, 61],  # seconds
        'power': [324, 324, 324, 324, 324, 324, 324],  # watts
        'w_remaining': [25000, 24200, 23800, 22900, 23100, 22200, 22500]  # J
    })
    
    print(f"   ✅ Created {len(optimization_segments)} segments")
    print(f"   📊 Segment distances: {optimization_segments['distance'].tolist()}")
    print(f"   ⚡ Powers: {segment_results['power'].tolist()}")
    
    # Test segment summary table creation
    print("\n2️⃣ Testing segment summary table creation...")
    
    try:
        # Test with segment results (should show real data)
        table_with_results = create_segment_summary_table(
            optimization_segments, 
            granular_analysis=None, 
            segment_results=segment_results
        )
        
        print(f"   ✅ Table created with segment results: {len(table_with_results)} rows")
        print("   📋 Sample data:")
        print(table_with_results.head(3).to_string(index=False))
        
        # Check for N/A values
        na_count = table_with_results.isin(['N/A']).sum().sum()
        print(f"   📊 N/A values found: {na_count}")
        
        if na_count == 0:
            print("   ✅ No N/A values - segment data properly extracted!")
        
    except Exception as e:
        print(f"   ❌ Table creation failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test power step function
    print("\n3️⃣ Testing power step function...")
    
    try:
        # Create mock granular data
        granular_data = pd.DataFrame({
            'cumulative_distance': np.linspace(0, 8000, 100),  # 100 points over 8km
            'speed_kmh': np.random.uniform(25, 45, 100),
            'gradient': np.random.uniform(-0.05, 0.08, 100)
        })
        
        power_array = create_power_step_function(
            granular_data, 
            optimization_segments, 
            segment_results
        )
        
        print(f"   ✅ Power array created: {len(power_array)} points")
        print(f"   📊 Power range: {power_array.min():.0f}W to {power_array.max():.0f}W")
        print(f"   🎯 Unique power values: {len(np.unique(power_array))}")
        
        # Check if we have proper step function (should be constant 324W)
        if len(np.unique(power_array)) == 1 and power_array[0] == 324:
            print("   ✅ Correct constant power step function!")
        else:
            print(f"   ⚠️ Power variation detected: {np.unique(power_array)}")
        
    except Exception as e:
        print(f"   ❌ Power step function failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 Visualization tests completed!")
    
    return True

if __name__ == "__main__":
    test_visualization_fixes()
