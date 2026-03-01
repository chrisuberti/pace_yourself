# ============================================================================
# ARCHIVE — These functions are NOT used by the active Streamlit app.
# Retained for test compatibility. Review and delete as needed.
# ============================================================================
"""
Granular Visualization System for Course Optimization

This module provides visualizations focused on high-resolution simulation results
with a clean, comprehensive single-chart approach showing power, speed, and elevation.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

def create_granular_optimization_chart(granular_results, coarse_segments, course_info, optimization_type="constant_power", segment_results=None):
    """
    Create a comprehensive multi-line chart showing granular optimization results.
    
    Parameters:
    - granular_results: DataFrame with point-by-point simulation data
    - coarse_segments: DataFrame with segment-level strategy data
    - course_info: Dict with course metadata
    - optimization_type: String indicating optimization type
    - segment_results: DataFrame with segment-by-segment optimization results
    
    Returns:
    - Plotly figure object
    """
    
    # Prepare data for visualization
    chart_data = prepare_chart_data(granular_results, coarse_segments, segment_results)
    
    # Create subplot with secondary y-axis
    fig = make_subplots(
        specs=[[{"secondary_y": True}]],
        subplot_titles=[f"Course Optimization Results - {course_info.get('name', 'Course')}"]
    )
    
    # Distance array in km for x-axis
    distance_km = chart_data['distance'] / 1000
    
    # Add elevation profile (filled area)
    fig.add_trace(
        go.Scatter(
            x=distance_km,
            y=chart_data['elevation'],
            fill='tonexty',
            fillcolor='rgba(46, 204, 113, 0.2)',
            line=dict(color='#2ECC71', width=1),
            name='Elevation',
            hovertemplate='<b>Elevation</b><br>Distance: %{x:.1f} km<br>Elevation: %{y:.0f} m<extra></extra>',
            yaxis='y2'
        ),
        secondary_y=True,
    )
    
    # Add power strategy (step function)
    fig.add_trace(
        go.Scatter(
            x=distance_km,
            y=chart_data['power'],
            line=dict(color='#E74C3C', width=3, shape='hv'),
            name='Power',
            hovertemplate='<b>Power</b><br>Distance: %{x:.1f} km<br>Power: %{y:.0f} W<extra></extra>',
        ),
        secondary_y=False,
    )
    
    # Add speed curve (smooth line with markers)
    fig.add_trace(
        go.Scatter(
            x=distance_km,
            y=chart_data['speed_kmh'],
            line=dict(color='#3498DB', width=2),
            mode='lines+markers',
            marker=dict(size=2, color='#3498DB'),
            name='Speed',
            hovertemplate='<b>Speed</b><br>Distance: %{x:.1f} km<br>Speed: %{y:.1f} km/h<extra></extra>',
        ),
        secondary_y=False,
    )
    
    # Add segment boundaries as vertical lines
    segment_boundaries = get_segment_boundaries(coarse_segments, segment_results)
    for i, boundary in enumerate(segment_boundaries[1:-1], 1):  # Skip start and end
        fig.add_vline(
            x=boundary/1000,
            line_dash="dash",
            line_color="gray",
            opacity=0.5,
            annotation_text=f"Seg {i+1}",
            annotation_position="top"
        )
    
    # Add gradient zones as background colors
    add_gradient_zones(fig, chart_data, distance_km)
    
    # Update layout
    fig.update_layout(
        title={
            'text': f"Course Optimization: {optimization_type.replace('_', ' ').title()}",
            'x': 0.5,
            'font': {'size': 16}
        },
        xaxis_title="Distance (km)",
        template="plotly_white",
        hovermode="x unified",
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Set y-axes titles
    fig.update_yaxes(title_text="Power (W) & Speed (km/h)", secondary_y=False)
    fig.update_yaxes(title_text="Elevation (m)", secondary_y=True)
    
    return fig

def prepare_chart_data(granular_results, coarse_segments, segment_results=None):
    """
    Prepare and resample data for smooth chart display.
    
    Returns dictionary with aligned data arrays for visualization.
    """
    
    # Intelligent sampling for performance (max 1000 points)
    target_points = min(1000, len(granular_results))
    
    if len(granular_results) > target_points:
        # Sample preserving important features (peaks, gradient changes)
        sample_indices = np.linspace(0, len(granular_results)-1, target_points, dtype=int)
        sampled_data = granular_results.iloc[sample_indices].copy()
    else:
        sampled_data = granular_results.copy()
    
    # Create power step function from coarse segments
    power_array = create_power_step_function(sampled_data, coarse_segments, segment_results)
    
    return {
        'distance': sampled_data['cumulative_distance'].values,
        'elevation': sampled_data.get('altitude', sampled_data.get('elevation', np.zeros(len(sampled_data)))),
        'power': power_array,
        'speed_kmh': sampled_data['speed_kmh'].values,
        'gradient': sampled_data['gradient'].values
    }

def create_power_step_function(granular_data, coarse_segments, segment_results=None):
    """
    Create step function power array aligned with granular data points.
    Uses segment_results from optimization for accurate power mapping.
    """
    
    power_array = np.zeros(len(granular_data))
    distances = granular_data['cumulative_distance'].values
    
    # If we have segment results from optimization, use those for power values
    if segment_results is not None and len(segment_results) == len(coarse_segments):
        cumulative_distance = 0
        
        for i, (segment, result) in enumerate(zip(coarse_segments.iterrows(), segment_results.iterrows())):
            _, segment_data = segment
            _, result_data = result
            
            # Get segment distance - try both column names
            segment_distance = result_data.get('distance', result_data.get('length', segment_data.get('distance', 0)))
            
            # Get segment power - handle both 'target_power' (variable pacing) and 'power' (constant power)
            segment_power = result_data.get('target_power', result_data.get('power', segment_data.get('target_power', segment_data.get('power', 300))))
            
            # Find points within this segment
            segment_start = cumulative_distance
            segment_end = cumulative_distance + segment_distance
            
            mask = (distances >= segment_start) & (distances < segment_end)
            power_array[mask] = segment_power
            
            cumulative_distance += segment_distance
    else:
        # Fallback to coarse segments with distance-based mapping
        cumulative_distance = 0
        
        for _, segment in coarse_segments.iterrows():
            # Get segment distance and power
            segment_distance = segment.get('distance', segment.get('length', 0))
            segment_power = segment.get('target_power', segment.get('power', 300))
            
            # Find points within this segment
            segment_start = cumulative_distance
            segment_end = cumulative_distance + segment_distance
            
            mask = (distances >= segment_start) & (distances < segment_end)
            power_array[mask] = segment_power
            
            cumulative_distance += segment_distance
    
    # Fill any remaining zeros with a default power (shouldn't happen with proper data)
    if np.any(power_array == 0):
        default_power = 300  # Default to 300W
        power_array[power_array == 0] = default_power
    
    return power_array

def get_segment_boundaries(coarse_segments, segment_results=None):
    """
    Extract segment boundary distances for vertical lines.
    Uses segment_results if available for accurate distances.
    """
    
    boundaries = [0]  # Start
    cumulative_distance = 0
    
    if segment_results is not None and len(segment_results) == len(coarse_segments):
        # Use optimization results for accurate distances
        for _, result in segment_results.iterrows():
            segment_distance = result.get('length', result.get('distance', 0))
            cumulative_distance += segment_distance
            boundaries.append(cumulative_distance)
    else:
        # Fallback to coarse segments
        for _, segment in coarse_segments.iterrows():
            segment_distance = segment.get('distance', segment.get('length', 0))
            cumulative_distance += segment_distance
            boundaries.append(cumulative_distance)
    
    return boundaries

def add_gradient_zones(fig, chart_data, distance_km):
    """
    Add colored background zones based on gradient ranges.
    """
    
    gradients = chart_data['gradient']
    
    # Define gradient categories
    flat_mask = np.abs(gradients) < 0.02  # < 2%
    moderate_climb_mask = (gradients >= 0.02) & (gradients < 0.05)  # 2-5%
    steep_climb_mask = gradients >= 0.05  # > 5%
    descent_mask = gradients < -0.02  # < -2%
    
    # Add background color shapes (simplified approach)
    # Note: This is a basic implementation - could be enhanced with continuous zones
    
    return fig

def display_performance_metrics(analysis_data):
    """
    Display performance summary metrics in Streamlit columns.
    """
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Handle both direct optimal_power and nested power_analysis.average
        optimal_power = analysis_data.get('optimal_power', 0)
        if optimal_power == 0 and 'power_analysis' in analysis_data:
            optimal_power = analysis_data['power_analysis'].get('average', 0)
        st.metric("Optimal Power", f"{optimal_power:.0f}W")
    
    with col2:
        # Handle both total_time_seconds and total_time_minutes
        total_time_sec = analysis_data.get('total_time_seconds', 0)
        if total_time_sec == 0:
            total_time_minutes = analysis_data.get('total_time_minutes', 0)
            total_time_sec = total_time_minutes * 60
        st.metric("Total Time", f"{total_time_sec/60:.1f} min")
    
    with col3:
        avg_speed = analysis_data.get('average_speed_kmh', 0)
        st.metric("Avg Speed", f"{avg_speed:.1f} km/h")
    
    with col4:
        w_util = analysis_data.get('w_prime_utilization_percent', 0)
        st.metric("W' Utilization", f"{w_util:.1f}%")
    
    # Second row of metrics
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        # Handle nested speed analysis
        max_speed = 0
        if 'speed_analysis' in analysis_data:
            max_speed = analysis_data['speed_analysis'].get('max_kmh', 0)
        else:
            max_speed = analysis_data.get('max_speed_kmh', 0)
        st.metric("Max Speed", f"{max_speed:.1f} km/h")
    
    with col6:
        # Handle nested acceleration analysis
        max_accel = 0
        if 'acceleration_analysis' in analysis_data:
            max_accel = analysis_data['acceleration_analysis'].get('max_accel', 0)
        else:
            max_accel = analysis_data.get('max_acceleration', 0)
        st.metric("Max Accel", f"{max_accel:.2f} m/s²")
    
    with col7:
        elevation_gain = analysis_data.get('elevation_gain_m', 0)
        st.metric("Elevation", f"+{elevation_gain:.0f}m")
    
    with col8:
        # Handle different names for simulation points
        gps_points = analysis_data.get('simulation_points', analysis_data.get('total_points', 0))
        st.metric("GPS Points", f"{gps_points:,}")

def create_segment_summary_table(coarse_segments, granular_analysis=None, segment_results=None):
    """
    Create a formatted segment summary table for display.
    Uses segment_results from optimization if available.
    """
    
    summary_data = []
    
    # If we have segment results from optimization, use those for accurate data
    if segment_results is not None and len(segment_results) == len(coarse_segments):
        for i, (segment, result) in enumerate(zip(coarse_segments.iterrows(), segment_results.iterrows())):
            _, segment_data = segment
            _, result_data = result
            
            # Calculate W' used from remaining values
            if i == 0:
                w_used = 25000 - result_data.get('w_remaining', 0)  # First segment
            else:
                prev_w = segment_results.iloc[i-1].get('w_remaining', 0)
                curr_w = result_data.get('w_remaining', 0)
                w_used = prev_w - curr_w
            
            # Get terrain type - try multiple sources
            terrain_type = result_data.get('terrain_type', None)
            if not terrain_type:
                # Determine terrain type from gradient
                gradient = result_data.get('gradient', 0) * 100
                if gradient > 4:
                    terrain_type = 'Climb'
                elif gradient < -2:
                    terrain_type = 'Descent'
                else:
                    terrain_type = 'Flat'
            
            # Get power - handle both 'power' and 'target_power' columns
            power_value = result_data.get('target_power', result_data.get('power', 0))
            
            # Get distance - handle both 'distance' and 'length' columns  
            distance_value = result_data.get('distance', result_data.get('length', 0))
            
            summary_data.append({
                'Segment': i + 1,
                'Type': terrain_type,
                'Distance': f"{distance_value/1000:.1f} km",
                'Avg Power': f"{power_value:.0f}W",
                'Avg Speed': f"{result_data.get('speed', 0)*3.6:.1f} km/h",
                'Time': f"{result_data.get('time', 0)/60:.1f} min",
                'W\' Used': f"{w_used/1000:.1f} kJ" if w_used > 0 else "0.0 kJ"
            })
    else:
        # Fallback to coarse segments data
        for i, segment in coarse_segments.iterrows():
            # Try different column names that might exist
            distance_col = segment.get('distance', segment.get('length', 0))
            power_col = segment.get('target_power', segment.get('power', 0))
            speed_col = segment.get('speed', 0)
            time_col = segment.get('time', 0)
            
            # Determine terrain type from gradient
            gradient = segment.get('gradient', 0) * 100
            if gradient > 4:
                terrain_type = 'Climb'
            elif gradient < -2:
                terrain_type = 'Descent'
            else:
                terrain_type = 'Flat'
            
            summary_data.append({
                'Segment': i + 1,
                'Type': terrain_type,
                'Distance': f"{distance_col/1000:.1f} km",
                'Avg Power': f"{power_col:.0f}W" if power_col > 0 else "N/A",
                'Avg Speed': f"{speed_col*3.6:.1f} km/h" if speed_col > 0 else "N/A",
                'Time': f"{time_col/60:.1f} min" if time_col > 0 else "N/A",
                'W\' Used': "N/A"  # Can't calculate without proper data
            })
    
    return pd.DataFrame(summary_data)
