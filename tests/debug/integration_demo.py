"""
Integration example demonstrating how to use the new optimization module
with existing Course functionality.

This example shows the complete workflow from course segmentation to optimization.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd
from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course


def demonstration_workflow():
    """Demonstrate the complete course analysis and optimization workflow."""
    
    print("=== Pace Yourself - Optimization Integration Demo ===")
    print()
      # 1. Load a sample course (using one of the existing files)
    route_path = os.getenv('ROUTE_PATH', 'data/sample_routes')
    
    # Check if the route path exists and get sample files
    if os.path.exists(route_path):
        sample_files = [f for f in os.listdir(route_path) if f.endswith('.csv')]
    else:
        sample_files = []
    
    if not sample_files:
        print("No sample route files found. Creating synthetic data...")
        # Create synthetic course data
        synthetic_data = pd.DataFrame({
            'lat': [47.6 + i*0.001 for i in range(100)],
            'lon': [-122.3 - i*0.001 for i in range(100)],
            'altitude': [100 + 20*abs((i-50)/10) for i in range(100)]
        })
        course_file = "synthetic_course.csv"
    else:
        course_file = os.path.join(route_path, sample_files[0])
        print(f"Loading course data from: {course_file}")
        synthetic_data = pd.read_csv(course_file)
    
    # 2. Create Course object and perform segmentation
    print("Creating Course object and processing segments...")
    course = Course(synthetic_data)
    
    # Use equal segmentation for consistency
    course.equal_segmentation(8)  # Create 8 equal segments
    print(f"Course segmented into {len(course.course_segments)} segments")
    
    # 3. Prepare optimization data
    print("Converting course segments for optimization...")
    optimization_segments = create_course_segments_from_course(course)
    print(f"Optimization segments prepared:")
    print(optimization_segments.head())
    print()
    
    # 4. Set up rider parameters
    print("Setting up rider parameters...")
    critical_power = 300  # watts
    w_prime = 25000  # joules
    print(f"Critical Power: {critical_power}W, W': {w_prime/1000:.0f}kJ")
    print()
    
    # 5. Create optimizer and run analysis
    print("Running optimization analysis...")
    optimizer = CourseOptimizer(critical_power, w_prime)
    
    # Test different power levels
    print("\n--- Power Level Comparison ---")
    test_powers = [250, 300, 350, 400]
    
    for power in test_powers:
        results, time, w_remaining, energy_used = optimizer.simulate_course_time(
            power, optimization_segments
        )
        
        if time == float('inf'):
            print(f"{power}W: FAILED - Rider depleted W' reserves")
        else:
            avg_speed = (optimization_segments['distance'].sum() / time) * 3.6  # km/h
            print(f"{power}W: {time/60:.1f}min, {avg_speed:.1f}km/h, W' remaining: {w_remaining/1000:.1f}kJ")
    
    # 6. Find optimal power
    print("\n--- Optimization Results ---")
    try:
        optimal_power, optimal_time, detailed_results = optimizer.optimize_constant_power(
            optimization_segments
        )
        
        total_distance = optimization_segments['distance'].sum() / 1000  # km
        avg_speed = (total_distance / optimal_time) * 3600  # km/h
        
        print(f"Optimal Power: {optimal_power:.0f}W")
        print(f"Total Time: {optimal_time/60:.1f} minutes")
        print(f"Average Speed: {avg_speed:.1f} km/h")
        print(f"Total Distance: {total_distance:.2f} km")
        
        # 7. Comprehensive analysis
        print("\n--- Comprehensive Analysis ---")
        analysis = optimizer.analyze_pacing_strategy(optimization_segments)
        
        print(f"Power-to-Weight Ratio: {analysis['performance_metrics']['power_to_weight']:.1f} W/kg")
        print(f"Intensity Factor: {analysis['performance_metrics']['intensity_factor']:.2f}")
        print(f"W' Utilization: {analysis['w_prime_utilization_percent']:.1f}%")
        print(f"Estimated TSS: {analysis['performance_metrics']['tss_estimate']:.0f}")
        
        # 8. Show segment breakdown
        print("\n--- Critical Segments ---")
        for i, segment in enumerate(analysis['critical_segments']):
            print(f"Segment {segment['segment']}: {segment['gradient']*100:.1f}% grade, {segment['time']:.0f}s")
            
    except Exception as e:
        print(f"Optimization failed: {e}")
        return
    
    print("\n--- Integration Demo Complete ---")
    print("✅ Course loading and processing: SUCCESS")
    print("✅ Segmentation conversion: SUCCESS") 
    print("✅ Power simulation: SUCCESS")
    print("✅ Optimization: SUCCESS")
    print("✅ Comprehensive analysis: SUCCESS")
    
    return {
        'course': course,
        'optimizer': optimizer,
        'analysis': analysis,
        'optimal_power': optimal_power,
        'optimal_time': optimal_time
    }


if __name__ == "__main__":
    # Run the demonstration
    try:
        results = demonstration_workflow()
        print(f"\nDemo completed successfully!")
        print(f"Key result: {results['optimal_power']:.0f}W for {results['optimal_time']/60:.1f} minutes")
        
    except Exception as e:
        print(f"Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
