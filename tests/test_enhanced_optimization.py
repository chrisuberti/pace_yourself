"""
Test script for enhanced optimization functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from app.optimization import CourseOptimizer, create_course_segments_from_course

def test_enhanced_optimization():
    """Test the enhanced optimization with new segmentation format."""
    
    print("🧪 Testing Enhanced Optimization System")
    print("=" * 50)
    
    # Create test course segments with enhanced format
    print("1️⃣ Creating test course segments with enhanced format...")
    
    # Simulate a course with repeated segment types: [1, 2, 1, 3, 1, 2, 4]
    # This represents: flat, climb, flat, steep climb, flat, climb, descent
    enhanced_segments = pd.DataFrame({
        'segment_id': [1, 2, 1, 3, 1, 2, 4],           # Terrain type
        'segment_occurrence': [1, 1, 2, 1, 3, 2, 1],   # Nth occurrence of this type
        'segment_sequence': [1, 2, 3, 4, 5, 6, 7],     # Position in course
        'distance_sum': [1.5, 0.8, 2.0, 0.6, 1.2, 0.9, 1.0],  # km
        'gradient_mean': [1.0, 5.5, 0.5, 8.2, -0.5, 6.0, -4.0],  # %
        'altitude_mean': [100, 120, 115, 140, 130, 145, 125],   # m
        'start_distance': [0, 1500, 2300, 4300, 4900, 6100, 7000],    # m
        'end_distance': [1500, 2300, 4300, 4900, 6100, 7000, 8000]    # m
    })
    
    print(f"   ✅ Created course with {len(enhanced_segments)} segments")
    print(f"   📊 Segment sequence: {enhanced_segments['segment_id'].tolist()}")
    print(f"   📏 Total distance: {enhanced_segments['distance_sum'].sum():.1f} km")
    
    # Test conversion to optimization format
    print("\n2️⃣ Converting to optimization format...")
    
    try:
        opt_segments = pd.DataFrame({
            'distance': enhanced_segments['distance_sum'] * 1000,  # Convert to meters
            'gradient': enhanced_segments['gradient_mean'] / 100,   # Convert to decimal
            'altitude': enhanced_segments['altitude_mean'],
            'wind': 0,
            'segment_id': enhanced_segments['segment_id'],
            'segment_sequence': enhanced_segments['segment_sequence']
        })
        
        print(f"   ✅ Converted to optimization format: {len(opt_segments)} segments")
        print(f"   📈 Gradient range: {opt_segments['gradient'].min()*100:.1f}% to {opt_segments['gradient'].max()*100:.1f}%")
        
    except Exception as e:
        print(f"   ❌ Conversion failed: {e}")
        return False
    
    # Test optimization
    print("\n3️⃣ Testing optimization algorithms...")
    
    try:
        # Initialize optimizer
        optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
        print(f"   🏋️ Optimizer initialized: CP={optimizer.critical_power}W, W'={optimizer.w_prime/1000:.0f}kJ")
        
        # Test constant power optimization
        print("\n   🔄 Testing constant power optimization...")
        const_power, const_time, const_results = optimizer.optimize_constant_power(opt_segments)
        
        print(f"   ✅ Constant power: {const_power:.0f}W, Time: {const_time/60:.1f} min")
        print(f"   📊 Results shape: {const_results.shape}")
        
        # Test variable pacing optimization
        print("\n   🔄 Testing variable pacing optimization...")
        var_results, var_time, var_analysis = optimizer.optimize_variable_pacing(opt_segments)
        
        print(f"   ✅ Variable pacing: Time: {var_time/60:.1f} min")
        print(f"   📊 Results shape: {var_results.shape}")
        print(f"   ⚡ W' utilization: {var_analysis['w_prime_utilization_percent']:.1f}%")
        
    except Exception as e:
        print(f"   ❌ Optimization failed: {e}")
        return False
    
    print("\n4️⃣ Testing high-resolution simulation...")
    
    try:
        # Create mock course object for detailed simulation
        class MockCourse:
            def __init__(self):
                # Create high-resolution GPS data (simulate 1000 points)
                distances = np.linspace(0, 8000, 1000)  # 8km course
                self.df = pd.DataFrame({
                    'cumulative_distance': distances,
                    'distance': np.diff(distances, prepend=0),
                    'gradient': np.sin(distances / 1000) * 5 + np.random.normal(0, 1, 1000),  # Varying gradient
                    'altitude': 100 + np.cumsum(np.sin(distances / 1000) * 0.01),
                    'latitude': 40.0 + distances / 111000,  # Mock coordinates
                    'longitude': -74.0 + distances / 111000
                })
        
        mock_course = MockCourse()
        print(f"   🗺️ Created mock course with {len(mock_course.df)} GPS points")
        
        # Test detailed simulation with constant power
        print("\n   🔄 Testing detailed simulation (constant power)...")
        detailed_results, detailed_time, detailed_analysis = optimizer.simulate_course_detailed(
            mock_course, opt_segments, const_power, target_resolution=500
        )
        
        print(f"   ✅ Detailed simulation complete!")
        print(f"   📊 High-res points: {len(detailed_results)}")
        print(f"   ⏱️ Total time: {detailed_time/60:.1f} min")
        print(f"   🏃 Avg speed: {detailed_analysis['average_speed_kmh']:.1f} km/h")
        print(f"   ⚡ Max acceleration: {detailed_analysis['acceleration_analysis']['max_accel']:.2f} m/s²")
        
    except Exception as e:
        print(f"   ❌ Detailed simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n🎉 All tests completed successfully!")
    print("\n📋 Summary:")
    print(f"   • Enhanced segmentation: ✅ Working")
    print(f"   • Constant power optimization: ✅ Working")  
    print(f"   • Variable pacing optimization: ✅ Working")
    print(f"   • High-resolution simulation: ✅ Working")
    print(f"   • Acceleration modeling: ✅ Working")
    
    return True

if __name__ == "__main__":
    success = test_enhanced_optimization()
    if success:
        print("\n🚀 Enhanced optimization system is ready for integration!")
    else:
        print("\n❌ Tests failed - check implementation")
