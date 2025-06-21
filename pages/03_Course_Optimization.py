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
from app.visualizations import create_map, plot_cumulative_distance_vs_altitude


def plot_power_comparison(power_results):
    """Create visualization comparing different power outputs."""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Speed Profile', 'W\' Depletion', 'Time per Segment', 'Power Demand'),
        specs=[[{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": True}]]
    )
    
    colors = ['blue', 'green', 'orange', 'red', 'purple']
    
    for i, (power, data) in enumerate(power_results.items()):
        if data['time'] != float('inf'):
            results_df = data['results']
            color = colors[i % len(colors)]
            
            # Speed profile
            fig.add_trace(
                go.Scatter(x=results_df['segment'], y=results_df['speed']*3.6, 
                          name=f'{power}W Speed', line=dict(color=color)),
                row=1, col=1
            )
            
            # W' depletion
            fig.add_trace(
                go.Scatter(x=results_df['segment'], y=results_df['w_remaining']/1000,
                          name=f'{power}W W\' Remaining', line=dict(color=color)),
                row=1, col=2
            )
            
            # Time per segment
            fig.add_trace(
                go.Scatter(x=results_df['segment'], y=results_df['time'],
                          name=f'{power}W Time', line=dict(color=color)),
                row=2, col=1
            )
    
    # Add gradient profile on secondary y-axis
    if power_results:
        first_result = next(iter(power_results.values()))
        if first_result['time'] != float('inf'):
            results_df = first_result['results']
            fig.add_trace(
                go.Scatter(x=results_df['segment'], y=results_df['gradient']*100,
                          name='Gradient %', line=dict(color='black', dash='dash')),
                row=2, col=2
            )
    
    fig.update_xaxes(title_text="Segment", row=1, col=1)
    fig.update_xaxes(title_text="Segment", row=1, col=2)
    fig.update_xaxes(title_text="Segment", row=2, col=1)
    fig.update_xaxes(title_text="Segment", row=2, col=2)
    
    fig.update_yaxes(title_text="Speed (km/h)", row=1, col=1)
    fig.update_yaxes(title_text="W' Remaining (kJ)", row=1, col=2)
    fig.update_yaxes(title_text="Time (s)", row=2, col=1)
    fig.update_yaxes(title_text="Gradient (%)", row=2, col=2)
    
    fig.update_layout(height=600, title_text="Power Strategy Comparison")
    return fig


def plot_optimization_results(analysis):
    """Create comprehensive visualization of optimization results."""
    segment_data = analysis['segment_breakdown']
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Speed & Gradient Profile', 'W\' Usage Over Time', 
                       'Segment Time Distribution', 'Power Demand Analysis'),
        specs=[[{"secondary_y": True}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    # Speed and gradient profile
    fig.add_trace(
        go.Scatter(x=segment_data['segment'], y=segment_data['speed']*3.6,
                  name='Speed (km/h)', line=dict(color='blue')),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=segment_data['segment'], y=segment_data['gradient']*100,
                  name='Gradient (%)', line=dict(color='red')),
        row=1, col=1, secondary_y=True
    )
    
    # W' usage over time
    cumulative_time = np.cumsum([0] + segment_data['time'].tolist())
    w_remaining_points = [25000] + segment_data['w_remaining'].tolist()
    
    fig.add_trace(
        go.Scatter(x=cumulative_time[:-1]/60, y=np.array(w_remaining_points[:-1])/1000,
                  name='W\' Remaining', fill='tonexty', line=dict(color='green')),
        row=1, col=2
    )
    
    # Segment time distribution
    fig.add_trace(
        go.Bar(x=segment_data['segment'], y=segment_data['time'],
               name='Segment Time', marker_color='orange'),
        row=2, col=1
    )
    
    # Power demand analysis (gradient * distance as proxy)
    power_demand = segment_data['gradient'] * segment_data['length']
    fig.add_trace(
        go.Bar(x=segment_data['segment'], y=power_demand,
               name='Power Demand', marker_color='purple'),
        row=2, col=2
    )
    
    # Update axes
    fig.update_xaxes(title_text="Segment", row=1, col=1)
    fig.update_xaxes(title_text="Time (min)", row=1, col=2)
    fig.update_xaxes(title_text="Segment", row=2, col=1)
    fig.update_xaxes(title_text="Segment", row=2, col=2)
    
    fig.update_yaxes(title_text="Speed (km/h)", row=1, col=1)
    fig.update_yaxes(title_text="Gradient (%)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="W' Remaining (kJ)", row=1, col=2)
    fig.update_yaxes(title_text="Time (s)", row=2, col=1)
    fig.update_yaxes(title_text="Power Demand", row=2, col=2)
    
    fig.update_layout(height=600, title_text="Optimization Analysis Results")
    return fig


# Page title and description
st.title("🚴‍♂️ Course Optimization & Pacing Strategy")
st.write("""
This page demonstrates the new optimization capabilities integrated from research notebooks.
Analyze optimal pacing strategies, compare power outputs, and optimize race performance.
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
    col1, col2 = st.columns(2)
    
    with col1:
        total_distance = course.course_segments['distance_sum'].sum()
        total_elevation = course.course_segments['height_gain_sum'].sum()
        avg_gradient = course.course_segments['gradient_mean'].mean()
        
        st.metric("Total Distance", f"{total_distance:.1f} km")
        st.metric("Total Elevation Gain", f"{total_elevation:.0f} m")
        st.metric("Average Gradient", f"{avg_gradient:.1f}%")
    
    with col2:
        # Course map
        if 'lat_mean' in course.course_segments.columns:
            st.write("Course Segments Map")
            map_deck = create_map(course.df, color='segment')
            st.pydeck_chart(map_deck)
    
    # Prepare optimization data
    optimization_segments = create_course_segments_from_course(course)
    optimizer = CourseOptimizer(critical_power, w_prime)
    
    # Optimization analysis
    st.header("Power Strategy Analysis")
    
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
                        'Power (W)': power,
                        'Time (min)': data['time'] / 60,
                        'Avg Speed (km/h)': avg_speed,
                        'W\' Remaining (kJ)': data['w_remaining'] / 1000,
                        'Energy Used (kJ)': data['energy_used'] / 1000
                    })
                else:
                    comparison_data.append({
                        'Power (W)': power,
                        'Time (min)': '∞ (Failed)',
                        'Avg Speed (km/h)': 'N/A',
                        'W\' Remaining (kJ)': 'Depleted',
                        'Energy Used (kJ)': 'N/A'
                    })
            
            st.dataframe(pd.DataFrame(comparison_data))
            
            # Plot comparison
            if any(data['time'] != float('inf') for data in power_results.values()):
                fig = plot_power_comparison(power_results)
                st.plotly_chart(fig, use_container_width=True)
    
    # Optimization
    st.subheader("Optimal Power Strategy")
    
    if st.button("Find Optimal Power"):
        with st.spinner("Optimizing power strategy..."):
            try:
                analysis = optimizer.analyze_pacing_strategy(optimization_segments)
                st.session_state.optimization_results = analysis
                
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
                st.subheader("Critical Segments")
                critical_df = pd.DataFrame(analysis['critical_segments'])
                critical_df['gradient_percent'] = critical_df['gradient'] * 100
                critical_df = critical_df[['segment', 'gradient_percent', 'time']]
                critical_df.columns = ['Segment', 'Gradient (%)', 'Time (s)']
                st.dataframe(critical_df)
                
                # Detailed visualization
                fig = plot_optimization_results(analysis)
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Optimization failed: {e}")
    
    # Display optimization results if available
    if st.session_state.optimization_results:
        st.subheader("Segment Breakdown")
        segment_breakdown = st.session_state.optimization_results['segment_breakdown']
        
        # Format segment data for display
        display_segments = segment_breakdown.copy()
        display_segments['speed_kmh'] = display_segments['speed'] * 3.6
        display_segments['gradient_percent'] = display_segments['gradient'] * 100
        display_segments['distance_km'] = display_segments['length'] / 1000
        
        display_cols = ['segment', 'distance_km', 'gradient_percent', 'speed_kmh', 'time', 'w_remaining']
        display_segments = display_segments[display_cols]
        display_segments.columns = ['Segment', 'Distance (km)', 'Gradient (%)', 'Speed (km/h)', 'Time (s)', 'W\' Remaining (J)']
        
        st.dataframe(display_segments)

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
