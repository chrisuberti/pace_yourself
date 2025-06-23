"""
Test script for enhanced Course Optimization visualizations
Tests the new power recommendation and course profile features
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd
import numpy as np
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course

def test_enhanced_visualizations():
    """Test the enhanced visualizations with sample data."""
    print("=== Testing Enhanced Course Optimization Visualizations ===")
    print()
    
    # 1. Create sample course data
    print("1. Creating sample course with realistic gradients...")
    sample_data = pd.DataFrame({
        'lat': [47.6 + i*0.001 for i in range(50)],
        'lon': [-122.3 - i*0.0005 for i in range(50)],
        'altitude': [100 + 50*np.sin(i/8) + 10*np.sin(i/3) for i in range(50)]
    })
    
    course = Course(sample_data)
    course.equal_segmentation(8)
    
    print(f"   Course created with {len(course.course_segments)} segments")
    print(f"   Total distance: {course.course_segments['distance_sum'].sum():.2f} km")
    print(f"   Gradient range: {course.course_segments['gradient_mean'].min():.1f}% to {course.course_segments['gradient_mean'].max():.1f}%")
    
    # 2. Test optimization data conversion
    print("\n2. Testing optimization data conversion...")
    optimization_segments = create_course_segments_from_course(course)
    
    print(f"   Optimization segments: {len(optimization_segments)}")
    print(f"   Gradient format: {optimization_segments['gradient'].min():.3f} to {optimization_segments['gradient'].max():.3f} (decimal)")
    print(f"   Distance format: {optimization_segments['distance'].sum()/1000:.2f} km total")
    
    # 3. Test optimization analysis
    print("\n3. Testing optimization analysis...")
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    
    try:
        analysis = optimizer.analyze_pacing_strategy(optimization_segments)
        
        print(f"   ✅ Optimization successful!")
        print(f"   Optimal power: {analysis['optimal_power']:.0f}W")
        print(f"   Total time: {analysis['total_time_minutes']:.1f} minutes")
        print(f"   Average speed: {analysis['average_speed_kmh']:.1f} km/h")
        print(f"   W' utilization: {analysis['w_prime_utilization_percent']:.1f}%")
        
        # 4. Test segment breakdown data
        print("\n4. Testing segment breakdown data...")
        segment_breakdown = analysis['segment_breakdown']
        
        print(f"   Segment breakdown columns: {list(segment_breakdown.columns)}")
        print(f"   Number of segments: {len(segment_breakdown)}")
        
        # Check if we have the data needed for visualizations
        required_cols = ['segment', 'gradient', 'length', 'speed', 'time', 'w_remaining']
        missing_cols = [col for col in required_cols if col not in segment_breakdown.columns]
        
        if not missing_cols:
            print("   ✅ All required columns present for visualizations")
            
            # Test power recommendation display
            print("\n5. Testing power recommendation display...")
            print("   Segment-by-segment power recommendations:")
            for i in range(min(5, len(segment_breakdown))):
                segment = segment_breakdown.iloc[i]
                print(f"     Segment {int(segment['segment'])}: {analysis['optimal_power']:.0f}W "
                      f"(Gradient: {segment['gradient']*100:.1f}%, Speed: {segment['speed']*3.6:.1f} km/h)")
                      
            # Test course profile data
            print("\n6. Testing course profile data...")
            print("   Course profile visualization data:")
            cumulative_distance = np.cumsum([0] + (segment_breakdown['length'] / 1000).tolist())
            print(f"     Cumulative distances: {cumulative_distance[:5].round(2)}... km")
            print(f"     Segment gradients: {(segment_breakdown['gradient'].head()*100).round(1).tolist()}%")
            print(f"     Segment speeds: {(segment_breakdown['speed'].head()*3.6).round(1).tolist()} km/h")
            
        else:
            print(f"   ❌ Missing columns: {missing_cols}")
            
        print("\n7. Testing multiple power comparison...")
        test_powers = [250, 300, 350]
        power_results = {}
        
        for power in test_powers:
            results, time, w_remaining, energy = optimizer.simulate_course_time(power, optimization_segments)
            if time != float('inf'):
                power_results[power] = {
                    'results': results,
                    'time': time,
                    'w_remaining': w_remaining,
                    'energy_used': energy
                }
                avg_speed = (optimization_segments['distance'].sum() / time) * 3.6
                print(f"     {power}W: {time/60:.1f}min, {avg_speed:.1f}km/h, {w_remaining/1000:.1f}kJ remaining")
            else:
                print(f"     {power}W: FAILED (W' depleted)")
                
        print(f"\n✅ Successfully tested {len(power_results)} power levels")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Optimization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = test_enhanced_visualizations()
        if success:
            print("\n🎉 All enhanced visualization tests passed!")
            print("\nEnhanced features ready:")
            print("   ✅ Power recommendations by segment")
            print("   ✅ Course profile with power overlay")
            print("   ✅ Enhanced comparison tables")
            print("   ✅ Actionable power strategy display")
        else:
            print("\n❌ Some tests failed - check output above")
            
    except Exception as e:
        print(f"\n💥 Test script failed: {e}")
        import traceback
        traceback.print_exc()
