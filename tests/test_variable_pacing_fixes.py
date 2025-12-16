"""
Test script for variable pacing visualization fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.visualizations_granular import create_segment_summary_table, create_power_step_function

def test_variable_pacing_fixes():
    """Test the visualization fixes for variable pacing."""
    
    print("🧪 Testing Variable Pacing Visualization Fixes")
    print("=" * 55)
    
    # Create test data similar to variable pacing optimization results
    print("1️⃣ Creating test variable pacing segments and results...")
    
    # Optimization segments (what goes into the optimization)
    optimization_segments = pd.DataFrame({
        'distance': [1500, 800, 2000, 600, 1200, 900, 1000],  # meters
        'gradient': [0.01, 0.055, 0.005, 0.082, -0.005, 0.060, -0.04],  # decimal
        'altitude': [100, 120, 115, 140, 130, 145, 125],   # m
        'wind': [0, 0, 0, 0, 0, 0, 0]
    })
    
    # Variable pacing results (what comes back from optimize_variable_pacing)
    var_results_df = pd.DataFrame({
        'segment': [0, 1, 2, 3, 4, 5, 6],
        'distance': [1500, 800, 2000, 600, 1200, 900, 1000],  # meters
        'gradient': [0.01, 0.055, 0.005, 0.082, -0.005, 0.060, -0.04],
        'altitude': [100, 120, 115, 140, 130, 145, 125],
        'wind': [0, 0, 0, 0, 0, 0, 0],
        'target_power': [310, 380, 305, 420, 280, 375, 250],  # Variable power strategy
        'speed': [12.8, 7.9, 13.2, 6.2, 14.8, 8.1, 18.2],  # m/s
        'time': [117, 101, 152, 97, 81, 111, 55],  # seconds
        'w_remaining': [25000, 23800, 24100, 22200, 22900, 21800, 22300],  # J
        'w_used_segment': [0, 1200, -300, 900, -700, 1100, -500],
        'energy_segment': [36270, 38380, 46360, 40740, 22680, 41625, 13750],
        'terrain_type': ['Flat', 'Moderate Climb', 'Flat', 'Steep Climb', 'Flat', 'Moderate Climb', 'Moderate Descent'],
        'power_zone': ['Threshold', 'VO2 Max', 'Threshold', 'Neuromuscular', 'Tempo', 'VO2 Max', 'Endurance']
    })
    
    print(f"   ✅ Created {len(optimization_segments)} segments")
    print(f"   📊 Segment distances: {optimization_segments['distance'].tolist()}")
    print(f"   ⚡ Variable powers: {var_results_df['target_power'].tolist()}")
    print(f"   🏔️ Terrain types: {var_results_df['terrain_type'].tolist()}")
    
    # Test segment summary table creation with variable pacing
    print("\n2️⃣ Testing segment summary table with variable pacing...")
    
    try:
        table_with_var_results = create_segment_summary_table(
            optimization_segments, 
            granular_analysis=None, 
            segment_results=var_results_df
        )
        
        print(f"   ✅ Table created with variable pacing results: {len(table_with_var_results)} rows")
        print("   📋 Sample data:")
        print(table_with_var_results.head(4).to_string(index=False))
        
        # Check for N/A values
        na_count = table_with_var_results.isin(['N/A']).sum().sum()
        print(f"   📊 N/A values found: {na_count}")
        
        if na_count == 0:
            print("   ✅ No N/A values - variable pacing data properly extracted!")
        
        # Check if power values are variable (not constant)
        power_values = table_with_var_results['Avg Power'].str.replace('W', '').astype(int)
        unique_powers = len(power_values.unique())
        print(f"   🎯 Unique power values: {unique_powers} (should be >1 for variable pacing)")
        
        if unique_powers > 1:
            print("   ✅ Variable power strategy correctly displayed!")
        else:
            print("   ⚠️ Power values appear constant - check power extraction")
        
    except Exception as e:
        print(f"   ❌ Variable pacing table creation failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test power step function with variable pacing
    print("\n3️⃣ Testing power step function with variable pacing...")
    
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
            var_results_df
        )
        
        print(f"   ✅ Power array created: {len(power_array)} points")
        print(f"   📊 Power range: {power_array.min():.0f}W to {power_array.max():.0f}W")
        unique_power_count = len(np.unique(power_array))
        print(f"   🎯 Unique power values: {unique_power_count}")
        print(f"   📈 Power values: {np.unique(power_array)}")
        
        # Check if we have proper variable power step function
        expected_powers = var_results_df['target_power'].unique()
        if unique_power_count >= len(expected_powers):
            print("   ✅ Correct variable power step function!")
        else:
            print(f"   ⚠️ Expected {len(expected_powers)} unique powers, got {unique_power_count}")
        
    except Exception as e:
        print(f"   ❌ Variable power step function failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 Variable pacing visualization tests completed!")
    
    return True

if __name__ == "__main__":
    test_variable_pacing_fixes()
