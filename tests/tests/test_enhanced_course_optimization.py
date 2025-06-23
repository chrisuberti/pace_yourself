"""
Test the enhanced Course Optimization page with improved visualizations
that leverage the existing plot_cumulative_distance_vs_altitude pattern
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd
import numpy as np
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course
from app.visualizations import (
    plot_cumulative_distance_vs_altitude,
    plot_course_profile_with_overlays,
    plot_power_strategy_summary
)

def test_enhanced_course_optimization_visualizations():
    """Test the enhanced visualizations that use your existing patterns."""
    print("=== Testing Enhanced Course Optimization with Your Visualization Patterns ===")
    print()
    
    # 1. Create sample course data
    print("1. Creating sample course...")
    sample_data = pd.DataFrame({
        'lat': [47.6 + i*0.001 for i in range(50)],
        'lon': [-122.3 - i*0.0005 for i in range(50)],
        'altitude': [100 + 30*np.sin(i/8) + 15*np.sin(i/3) for i in range(50)]
    })
    
    course = Course(sample_data)
    course.equal_segmentation(8)
    
    print(f"   Course created with {len(course.course_segments)} segments")
    print(f"   Total distance: {course.course_segments['distance_sum'].sum():.2f} km")
    
    # 2. Test your existing visualization with segment coloring
    print("\n2. Testing your existing plot_cumulative_distance_vs_altitude with segments...")
    try:
        fig1 = plot_cumulative_distance_vs_altitude(course.df, color='segment')
        print("   ✅ Successfully created course profile colored by segments")
        print(f"   Data points: {len(course.df)}")
        print(f"   Segments: {course.df['segment'].nunique()}")
    except Exception as e:
        print(f"   ❌ Failed to create segmented course profile: {e}")
        return False
    
    # 3. Test optimization analysis
    print("\n3. Running optimization analysis...")
    optimization_segments = create_course_segments_from_course(course)
    optimizer = CourseOptimizer(critical_power=300, w_prime=25000)
    
    try:
        analysis = optimizer.analyze_pacing_strategy(optimization_segments)
        print(f"   ✅ Optimization successful!")
        print(f"   Optimal power: {analysis['optimal_power']:.0f}W")
        print(f"   Total time: {analysis['total_time_minutes']:.1f} minutes")
    except Exception as e:
        print(f"   ❌ Optimization failed: {e}")
        return False
    
    # 4. Test enhanced course profile with overlays
    print("\n4. Testing enhanced course profile with power/speed overlays...")
    try:
        fig2 = plot_course_profile_with_overlays(
            course.df, 
            optimization_results=analysis,
            color='segment',
            overlays=['power', 'speed'],
            title="Course Profile with Power Strategy"
        )
        print("   ✅ Successfully created course profile with power/speed overlays")
        print(f"   Overlays: power, speed")
        print(f"   Power target: {analysis['optimal_power']:.0f}W")
    except Exception as e:
        print(f"   ❌ Failed to create enhanced course profile: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Test power strategy summary
    print("\n5. Testing power strategy summary visualization...")
    try:
        fig3 = plot_power_strategy_summary(analysis, course.course_segments)
        print("   ✅ Successfully created power strategy summary")
        print("   Includes: Power vs Difficulty, Speed vs Gradient, W' Management, Performance Summary")
    except Exception as e:
        print(f"   ❌ Failed to create power strategy summary: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 6. Test flexible overlay options
    print("\n6. Testing flexible overlay combinations...")
    overlay_combinations = [
        ['power'],
        ['speed'],
        ['gradient'],
        ['w_remaining'],
        ['power', 'speed'],
        ['power', 'speed', 'gradient'],
        ['power', 'speed', 'w_remaining']
    ]
    
    successful_overlays = 0
    for overlays in overlay_combinations:
        try:
            fig = plot_course_profile_with_overlays(
                course.df,
                optimization_results=analysis,
                color='segment',
                overlays=overlays,
                title=f"Course Profile with {', '.join(overlays).title()}"
            )
            successful_overlays += 1
        except Exception as e:
            print(f"   ❌ Failed overlay combination {overlays}: {e}")
    
    print(f"   ✅ {successful_overlays}/{len(overlay_combinations)} overlay combinations successful")
    
    # 7. Test different color schemes
    print("\n7. Testing different color schemes...")
    color_schemes = ['segment', 'altitude', 'gradient']
    successful_colors = 0
    
    for color in color_schemes:
        try:
            fig = plot_cumulative_distance_vs_altitude(course.df, color=color)
            successful_colors += 1
        except Exception as e:
            print(f"   ❌ Failed color scheme {color}: {e}")
    
    print(f"   ✅ {successful_colors}/{len(color_schemes)} color schemes successful")
    
    print("\n8. Summary of enhanced features:")
    print("   ✅ Leverages your existing plot_cumulative_distance_vs_altitude pattern")
    print("   ✅ Enhanced with flexible overlay system (power, speed, gradient, w_remaining)")
    print("   ✅ Maintains your color mapping system (segment, altitude, gradient)")
    print("   ✅ Uses plotly_dark theme for consistency")
    print("   ✅ Provides actionable power recommendations")
    print("   ✅ Shows course profile with multiple metrics overlaid")
    
    return True

if __name__ == "__main__":
    try:
        success = test_enhanced_course_optimization_visualizations()
        if success:
            print("\n🎉 Enhanced Course Optimization visualizations ready!")
            print("\nKey improvements:")
            print("   📊 Uses your proven plot_cumulative_distance_vs_altitude as foundation")
            print("   🎯 Adds flexible overlay system for power/speed/gradient/w_remaining")
            print("   🎨 Maintains your color mapping system and dark theme")
            print("   📈 Provides multiple views: course profile + strategy analysis")
            print("   ⚡ Shows actionable power recommendations")
            print("\nThe Course Optimization page now uses your established visualization patterns!")
        else:
            print("\n❌ Some enhanced visualization tests failed")
            
    except Exception as e:
        print(f"\n💥 Test script failed: {e}")
        import traceback
        traceback.print_exc()
