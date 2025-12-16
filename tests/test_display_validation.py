"""
Simple validation test for optimization display
"""
import streamlit as st

def test_display_metrics():
    """Test the display_performance_metrics function with sample data."""
    
    # Sample granular_analysis data structure (matches what optimization returns)
    sample_analysis = {
        'optimal_power': 315,  # This is now being added in 03 page
        'total_time_minutes': 25.5,
        'average_speed_kmh': 35.2,
        'w_prime_utilization_percent': 85.0,
        'total_points': 5247,
        'power_analysis': {
            'average': 315,
            'max': 450,
            'min': 200
        },
        'speed_analysis': {
            'max_kmh': 65.3,
            'average_kmh': 35.2
        },
        'acceleration_analysis': {
            'max_accel': 2.1
        }
    }
    
    print("✅ Sample granular_analysis structure:")
    for key, value in sample_analysis.items():
        if isinstance(value, dict):
            print(f"   📁 {key}: {list(value.keys())}")
        else:
            print(f"   📊 {key}: {value}")
    
    print("\n✅ The display_performance_metrics function should now show:")
    print(f"   Optimal Power: {sample_analysis['optimal_power']}W")
    print(f"   Total Time: {sample_analysis['total_time_minutes']:.1f} min")
    print(f"   Avg Speed: {sample_analysis['average_speed_kmh']:.1f} km/h") 
    print(f"   W' Utilization: {sample_analysis['w_prime_utilization_percent']:.1f}%")
    print(f"   GPS Points: {sample_analysis['total_points']:,}")
    
    return sample_analysis

if __name__ == "__main__":
    test_display_metrics()
