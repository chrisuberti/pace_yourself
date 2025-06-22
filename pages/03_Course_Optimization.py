"""
Course Optimization Page

This page demonstrates the new optimization capabilities integrated from 
the notebook functions. Users can analyze pacing strategies and power optimization.
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course
from app.visualizations import (
    create_map, 
    plot_cumulative_distance_vs_altitude, 
    plot_course_profile_with_overlays,
    plot_power_strategy_summary
)


def plot_power_comparison_table(power_results):
    """Create a simple comparison table for different power levels."""
    comparison_data = []
    for power, data in power_results.items():
        if data['time'] != float('inf'):
            avg_speed = (data['total_distance'] / data['time']) * 3.6 if 'total_distance' in data else 'N/A'
            comparison_data.append({
                'Target Power (W)': power,
                'Time (min)': f"{data['time'] / 60:.1f}",
                'Avg Speed (km/h)': f"{avg_speed:.1f}" if avg_speed != 'N/A' else 'N/A',
                'W\' Remaining (kJ)': f"{data['w_remaining'] / 1000:.1f}",
                'Status': '✅ Success'
            })
        else:
            comparison_data.append({
                'Target Power (W)': power,
                'Time (min)': '∞ (Failed)',
                'Avg Speed (km/h)': 'N/A',
                'W\' Remaining (kJ)': 'Depleted',
                'Status': '❌ Failed'
            })
    return pd.DataFrame(comparison_data)


# Page title and description
st.title("🚴‍♂️ Course Optimization & Pacing Strategy")
st.write("""
Enhanced course optimization using your proven visualization methods.
Analyze optimal pacing strategies with intuitive course profile visualizations.
""")

# Initialize session state
if 'optimization_course' not in st.session_state:
    st.session_state.optimization_course = None
if 'optimization_results' not in st.session_state:
    st.session_state.optimization_results = None

# Sidebar for course selection and rider parameters
st.sidebar.header("Course & Rider Setup")

# Course loading options
course_source = st.sidebar.radio(
    "Course Data Source",
    ["Load from Files", "Use Current Session", "Create Sample Course"]
)

course = None

if course_source == "Load from Files":
    route_path = os.getenv('ROUTE_PATH', 'data/sample_routes')
    if os.path.exists(route_path):
        files = [f for f in os.listdir(route_path) if f.endswith('.csv')]
        if files:
            selected_file = st.sidebar.selectbox("Select Course File", files)
            if st.sidebar.button("Load Course"):
                course_data = pd.read_csv(os.path.join(route_path, selected_file))
                course = Course(course_data)
                st.session_state.optimization_course = course
                st.sidebar.success(f"Loaded {selected_file}")

elif course_source == "Use Current Session":
    if 'course' in st.session_state:
        course = st.session_state.course
        st.session_state.optimization_course = course
        st.sidebar.success("Using session course")
    else:
        st.sidebar.warning("No course in current session")

elif course_source == "Create Sample Course":
    if st.sidebar.button("Generate Sample Course"):
        # Create a sample hilly course
        sample_data = pd.DataFrame({
            'lat': [47.6 + i*0.001 for i in range(50)],
            'lon': [-122.3 - i*0.0005 for i in range(50)],
            'altitude': [100 + 50*np.sin(i/5) + 20*np.sin(i/2) for i in range(50)]
        })
        course = Course(sample_data)
        st.session_state.optimization_course = course
        st.sidebar.success("Generated sample course")

# Use course from session state if available
if st.session_state.optimization_course:
    course = st.session_state.optimization_course

# Rider parameters
st.sidebar.subheader("Rider Parameters")
critical_power = st.sidebar.number_input("Critical Power (W)", min_value=100, max_value=500, value=300, step=10)
w_prime = st.sidebar.number_input("W' Anaerobic Capacity (kJ)", min_value=10, max_value=50, value=25, step=1) * 1000

# Segmentation options
if course:
    st.sidebar.subheader("Course Segmentation")
    segmentation_method = st.sidebar.selectbox(
        "Segmentation Method",
        ["Equal Distance", "Auto Clustering", "Use Existing"]
    )
    
    if segmentation_method == "Equal Distance":
        num_segments = st.sidebar.slider("Number of Segments", 3, 15, 8)
        if st.sidebar.button("Apply Segmentation"):
            course.equal_segmentation(num_segments)
            st.sidebar.success(f"Created {num_segments} equal segments")
    
    elif segmentation_method == "Auto Clustering":
        max_clusters = st.sidebar.slider("Max Clusters", 3, 15, 8)
        if st.sidebar.button("Apply Auto Segmentation"):
            course.auto_segmentation(max_clusters=max_clusters)
            st.sidebar.success("Applied auto clustering")

# Main content
if course and hasattr(course, 'course_segments'):
      # Course overview
    st.header("Course Overview")
    c1,c2,c3 = st.columns(3)

    avg_gradient = course.course_segments['gradient_mean'].mean()
    total_distance = course.course_segments['distance_sum'].sum()
    total_elevation = course.course_segments['height_gain_sum'].sum()
    # Auto-detect if gradient is stored as percentage or decimal
    gradient_is_percentage = abs(avg_gradient) > 1.0 if not pd.isna(avg_gradient) else True
    gradient_display = avg_gradient if gradient_is_percentage else avg_gradient * 100
    with c1:
        st.metric("Total Distance", f"{total_distance:.1f} km")
    with c2:
        st.metric("Total Elevation Gain", f"{total_elevation:.0f} m")
    with c3:
        st.metric("Average Gradient", f"{gradient_display:.1f}%")
    
    

    # Course map
    with st.expander("Course Map", expanded=True):
            st.write(course.df)
    if 'lat' in course.course_segments.columns:
        st.write("Course Segments Map")
        map_deck = create_map(course.df, color='segment')
        st.pydeck_chart(map_deck)
    
    # Prepare optimization data
    optimization_segments = create_course_segments_from_course(course)
    optimizer = CourseOptimizer(critical_power, w_prime)


    # Power comparison
    st.subheader("Power Level Comparison")
    
    # Power range selection
    col1, col2, col3 = st.columns(3)
    with col1:
        min_power = st.number_input("Min Power (W)", min_value=100, max_value=critical_power-50, value=critical_power-100)
    with col2:
        max_power = st.number_input("Max Power (W)", min_value=critical_power, max_value=600, value=critical_power+100)
    with col3:
        power_step = st.number_input("Power Step (W)", min_value=10, max_value=50, value=25)
    
    if st.button("Run Power Comparison"):
        with st.spinner("Analyzing different power levels..."):
            power_results = {}
            test_powers = range(min_power, max_power + 1, power_step)
            
            for power in test_powers:
                results, time, w_remaining, energy_used = optimizer.simulate_course_time(
                    power, optimization_segments
                )
                
                power_results[power] = {
                    'results': results,
                    'time': time,
                    'w_remaining': w_remaining,
                    'energy_used': energy_used
                }
            
            st.session_state.power_comparison = power_results
              # Display results table
            comparison_data = []
            for power, data in power_results.items():
                if data['time'] != float('inf'):
                    avg_speed = (optimization_segments['distance'].sum() / data['time']) * 3.6
                    comparison_data.append({
                        'Target Power (W)': power,
                        'Time (min)': data['time'] / 60,
                        'Avg Speed (km/h)': avg_speed,
                        'W\' Remaining (kJ)': data['w_remaining'] / 1000,
                        'Energy Used (kJ)': data['energy_used'] / 1000,
                        'Status': '✅ Success'
                    })
                else:
                    comparison_data.append({
                        'Target Power (W)': power,
                        'Time (min)': '∞ (Failed)',
                        'Avg Speed (km/h)': 'N/A',
                        'W\' Remaining (kJ)': 'Depleted',
                        'Energy Used (kJ)': 'N/A',
                        'Status': '❌ Failed'
                    })
              # Display comparison table
            comparison_df = plot_power_comparison_table(power_results)
            st.dataframe(comparison_df, use_container_width=True)
            
            # Store successful results for visualization
            successful_results = {p: d for p, d in power_results.items() if d['time'] != float('inf')}
            if successful_results:
                st.success(f"✅ {len(successful_results)} power levels completed successfully")
            else:
                st.warning("❌ All power levels failed - try lower power values")
    
    # Optimization
    st.subheader("Optimal Power Strategy")
    
    if st.button("Find Optimal Power"):
        with st.spinner("Optimizing power strategy..."):
            try:
                analysis = optimizer.analyze_pacing_strategy(optimization_segments)
                st.session_state.optimization_results = analysis
                # Add this right after: analysis = optimizer.analyze_pacing_strategy(optimization_segments)

                # Add this right after: analysis = optimizer.analyze_pacing_strategy(optimization_segments)

                # Quick debug inspection
                st.write("### 🔍 Analysis Debug Information")
                st.write("**Segment Breakdown Preview:**")
                if 'segment_breakdown' in analysis:
                    st.dataframe(analysis['segment_breakdown'].head(3))

                with st.expander("📊 Complete Analysis Object", expanded=False):
                    st.json(analysis)
                # Display key results
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Optimal Power", f"{analysis['optimal_power']:.0f} W")
                with col2:
                    st.metric("Total Time", f"{analysis['total_time_minutes']:.1f} min")
                with col3:
                    st.metric("Average Speed", f"{analysis['average_speed_kmh']:.1f} km/h")
                with col4:
                    st.metric("W' Utilization", f"{analysis['w_prime_utilization_percent']:.1f}%")
                
                # Performance metrics
                st.subheader("Performance Metrics")
                metrics_col1, metrics_col2 = st.columns(2)
                
                with metrics_col1:
                    st.write("**Power Analysis**")
                    st.write(f"Power-to-Weight: {analysis['performance_metrics']['power_to_weight']:.1f} W/kg")
                    st.write(f"Intensity Factor: {analysis['performance_metrics']['intensity_factor']:.2f}")
                    st.write(f"Normalized Power: {analysis['performance_metrics']['normalized_power']:.0f} W")
                
                with metrics_col2:
                    st.write("**Training Load**")
                    st.write(f"Estimated TSS: {analysis['performance_metrics']['tss_estimate']:.0f}")
                    st.write(f"Final W' Remaining: {analysis['final_w_remaining']/1000:.1f} kJ")
                    st.write(f"Total Distance: {analysis['total_distance_km']:.2f} km")
                  # Critical segments
                
                # Enhanced Course Profile with Power/Speed Overlays
                st.subheader("Course Profile with Power & Speed Strategy")
                profile_fig = plot_course_profile_with_overlays(
                    course.df, 
                    optimization_results=analysis,
                    color='segment',
                    overlays=['power', 'speed'],
                    title="Course Elevation Profile"
                )
                st.plotly_chart(profile_fig, use_container_width=True)
                
                # Power Strategy Summary
                st.subheader("Power Strategy Analysis")
                strategy_fig = plot_power_strategy_summary(analysis, course.course_segments)
                st.plotly_chart(strategy_fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Optimization failed: {e}")
    
    # Display optimization results if available
    if st.session_state.optimization_results:
        analysis = st.session_state.optimization_results
        
        # Show course profile colored by segments (your existing visualization!)
        st.subheader("Course Segmentation Overview")
        course_profile_fig = plot_cumulative_distance_vs_altitude(course.df, color='segment')
        st.plotly_chart(course_profile_fig, use_container_width=True)
        
        st.subheader("Power Strategy Breakdown")
        segment_breakdown = analysis['segment_breakdown']
        optimal_power = analysis['optimal_power']
        
        # Format segment data for display with RECOMMENDED POWER
        display_segments = segment_breakdown.copy()
        display_segments['speed_kmh'] = display_segments['speed'] * 3.6
        display_segments['gradient_percent'] = display_segments['gradient'] * 100
        display_segments['distance_km'] = display_segments['length'] / 1000
        display_segments['recommended_power'] = optimal_power  # Add recommended power column
        
        display_cols = ['segment', 'distance_km', 'gradient_percent', 'recommended_power', 'speed_kmh', 'time', 'w_remaining']
        display_segments = display_segments[display_cols]
        display_segments.columns = ['Segment', 'Distance (km)', 'Gradient (%)', 'Target Power (W)', 'Speed (km/h)', 'Time (s)', 'W\' Remaining (J)']
        
        st.dataframe(display_segments, use_container_width=True)
        
        # Power strategy summary
        st.info(f"🎯 **Power Strategy**: Maintain {optimal_power:.0f}W throughout the entire course for optimal time while preserving energy reserves.")

else:
    st.info("👆 Please load a course and apply segmentation to begin optimization analysis.")
    
    st.write("### What This Tool Does")
    st.write("""
    - **Power Comparison**: Test different constant power outputs to see their effect on performance
    - **Optimization**: Find the optimal constant power that minimizes time while efficiently using energy
    - **W' Modeling**: Track anaerobic energy depletion and recovery throughout the course
    - **Performance Metrics**: Calculate TSS, IF, power-to-weight, and other training metrics
    - **Critical Segment Analysis**: Identify the most demanding parts of the course
    """)
    
    st.write("### How to Use")
    st.write("""
    1. Load a course using the sidebar options
    2. Set your rider parameters (Critical Power and W')
    3. Choose and apply a segmentation method
    4. Run power comparisons to see different strategies
    5. Find optimal power for the best time/energy balance
    """)

# Footer
st.write("---")
st.caption("Course Optimization powered by physics-based modeling and W' energy dynamics")
