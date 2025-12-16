import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, to_rgba
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

def continuous_colormap(df, column = 'altitude'):
    norm = Normalize(vmin=df[column].min(), vmax=df[column].max())
    cmap = plt.get_cmap("viridis")
    return [to_rgba(cmap(norm(alt))) for alt in df[column]]

def categorical_colormap(df, column='segment'):
    unique_values = df[column].unique()
    cmap = plt.get_cmap("tab20", len(unique_values))  # Use a colormap with enough colors
    color_dict = {val: to_rgba(cmap(i)) for i, val in enumerate(unique_values)}
    return [color_dict[val] for val in df[column]]

def create_color_map(df, color = 'altitude'):
    if color == 'gradient':
        df["color"] = continuous_colormap(df, 'gradient')
    elif color == 'altitude':    
        df["color"] = continuous_colormap(df)
    elif color == 'power':
        df["color"] = continuous_colormap(df, 'power')
    elif color == 'speed':
        df["color"] = continuous_colormap(df, 'speed')
    elif color == 'segment':
        df["color"] = categorical_colormap(df, 'segment')

    # Convert RGBA values to a format that pydeck can understand
    df["color"] = df["color"].apply(lambda x: [int(255 * c) for c in x])

    return df

# Function to create a pydeck map
def create_map(df, color = 'altitude'):
    # Create a color map
    df = create_color_map(df, color)

    # Create a pydeck layer
    layer = pdk.Layer(
        'ScatterplotLayer',
        data=df,
        get_position='[lon, lat]',
        get_color='color',
        get_radius=50,
        pickable=True
    )

    # Set the view state
    view_state = pdk.ViewState(
        latitude=df["lat"].mean(),
        longitude=df["lon"].mean(),
        zoom=12,
        pitch=0
    )

    # Create the pydeck Deck object
    return pdk.Deck(layers=[layer], initial_view_state=view_state)

def plot_cumulative_distance_vs_altitude(df, color='altitude'):
    """
    Plot cumulative distance vs altitude using a scatter plot to avoid connecting discontinuous segments.

    Args:
        df (pd.DataFrame): The DataFrame containing the data.
        color (str): The column to use for coloring the plot.

    Returns:
        plotly.graph_objects.Figure: The generated plot.
    """
    
    df = create_color_map(df, color)

    if color == 'segment':
        # Use discrete color scale for segments
        fig = px.scatter(
            df,
            x='cumulative_distance',
            y='altitude',
            color='segment',
            labels={'cumulative_distance': 'Distance (km)', 'altitude': 'Altitude (m)', 'segment': 'Segment'},
            template='plotly_dark',  # Use the dark theme
            title="Cumulative Distance vs Altitude"
        )
    else:
        # Use continuous color scale for other attributes
        fig = px.scatter(
            df,
            x='cumulative_distance',
            y='altitude',
            color=color,
            labels={'cumulative_distance': 'Distance (km)', 'altitude': 'Altitude (m)'},
            template='plotly_dark',  # Use the dark theme
            title="Cumulative Distance vs Altitude"
        )

    return fig


def plot_course_profile_with_overlays(df, optimization_results=None, color='segment', 
                                    overlays=['power', 'speed'], title="Course Profile"):
    """
    Enhanced course profile plot with multiple overlays.
    
    Args:
        df (pd.DataFrame): Course data with cumulative_distance, altitude, etc.
        optimization_results (dict): Results from optimization analysis (optional)
        color (str): Column to use for coloring the altitude profile
        overlays (list): List of metrics to overlay ['power', 'speed', 'gradient', 'w_remaining']
        title (str): Plot title
    
    Returns:
        plotly.graph_objects.Figure: Multi-panel plot with overlays
    """
    
    # Ensure consistent distance units throughout
    df = df.copy()
    
    # Debug: Check current distance units
    max_distance = df['cumulative_distance'].max()
    print(f"DEBUG: Max cumulative distance = {max_distance}")
    
    # Standardize distance to METERS for all calculations
    if max_distance < 100:  # Likely in km, convert to meters
        df['cumulative_distance_m'] = df['cumulative_distance'] * 1000
        distance_unit = "m"
        print("DEBUG: Converting distance from km to meters")
    else:  # Already in meters
        df['cumulative_distance_m'] = df['cumulative_distance']
        distance_unit = "m"
        print("DEBUG: Distance already in meters")
    
    # Create subplots - main altitude plot plus overlays
    rows = 1 + len(overlays)
    subplot_titles = [title] + [f"{overlay.title()} Profile" for overlay in overlays]
    
    fig = make_subplots(
        rows=rows, cols=1,
        subplot_titles=subplot_titles,
        shared_xaxes=True,
        vertical_spacing=0.08,
        specs=[[{"secondary_y": color == 'segment'}] if i == 0 else [{"secondary_y": False}] 
               for i in range(rows)]
    )
    
    # Main altitude profile with color coding
    if color == 'segment':
        # Create segment-colored altitude profile
        for segment in df['segment'].unique():
            segment_data = df[df['segment'] == segment]
            fig.add_trace(
                go.Scatter(
                    x=segment_data['cumulative_distance_m'],  # Use consistent meters
                    y=segment_data['altitude'],
                    mode='lines+markers',
                    name=f'Segment {int(segment)}',
                    line=dict(width=3),
                    marker=dict(size=4)
                ),
                row=1, col=1
            )
    else:
        # Single colored altitude profile
        fig.add_trace(
            go.Scatter(
                x=df['cumulative_distance_m'],  # Use consistent meters
                y=df['altitude'],
                mode='lines',
                name='Elevation',
                line=dict(width=3)
            ),
            row=1, col=1
        )
    
    # Add optimization results overlays if provided
    if optimization_results and 'segment_breakdown' in optimization_results:
        segment_breakdown = optimization_results['segment_breakdown']
        
        # Create distance mapping for overlay data
        # Convert segment distances to cumulative distances in METERS
        segment_distances = []
        cumulative_dist = 0
        
        for idx, row in segment_breakdown.iterrows():
            segment_length_m = row['length']  # Should be in meters from optimization
            segment_distances.append({
                'segment': row['segment'],
                'start_m': cumulative_dist,
                'end_m': cumulative_dist + segment_length_m,
                'mid_m': cumulative_dist + segment_length_m / 2,
                'power': optimization_results.get('optimal_power', 300),
                'speed_kmh': row['speed'] * 3.6 if 'speed' in row else 25,
                'gradient': row['gradient'] if 'gradient' in row else 0,
                'w_remaining': row['w_remaining'] if 'w_remaining' in row else 20000
            })
            cumulative_dist += segment_length_m
        
        segment_df = pd.DataFrame(segment_distances)
        
        # Add overlays
        for i, overlay in enumerate(overlays):
            row_num = i + 2
            
            if overlay == 'power':
                fig.add_trace(
                    go.Scatter(
                        x=segment_df['mid_m'],  # Use meters consistently
                        y=segment_df['power'],
                        mode='lines+markers',
                        name='Target Power',
                        line=dict(color='red', width=2, dash='dash'),
                        marker=dict(size=6)
                    ),
                    row=row_num, col=1
                )
                fig.update_yaxes(title_text="Power (W)", row=row_num, col=1)
                
            elif overlay == 'speed':
                fig.add_trace(
                    go.Scatter(
                        x=segment_df['mid_m'],  # Use meters consistently
                        y=segment_df['speed_kmh'],
                        mode='lines+markers',
                        name='Speed',
                        line=dict(color='blue', width=2),
                        marker=dict(size=6)
                    ),
                    row=row_num, col=1
                )
                fig.update_yaxes(title_text="Speed (km/h)", row=row_num, col=1)
                
            elif overlay == 'gradient':
                fig.add_trace(
                    go.Scatter(
                        x=segment_df['mid_m'],  # Use meters consistently
                        y=segment_df['gradient'] * 100,  # Convert to percentage
                        mode='lines+markers',
                        name='Gradient',
                        line=dict(color='green', width=2),
                        marker=dict(size=6)
                    ),
                    row=row_num, col=1
                )
                fig.update_yaxes(title_text="Gradient (%)", row=row_num, col=1)
                
            elif overlay == 'w_remaining':
                fig.add_trace(
                    go.Scatter(
                        x=segment_df['mid_m'],  # Use meters consistently
                        y=segment_df['w_remaining'] / 1000,  # Convert to kJ
                        mode='lines+markers',
                        name="W' Remaining",
                        line=dict(color='orange', width=2),
                        marker=dict(size=6)
                    ),
                    row=row_num, col=1
                )
                fig.update_yaxes(title_text="W' Remaining (kJ)", row=row_num, col=1)
    
    # Update layout
    fig.update_layout(
        height=300 + (len(overlays) * 200),
        title_text=title,
        showlegend=True
    )
    
    # Update x-axes - ALL in meters with km labels
    for i in range(rows):
        fig.update_xaxes(
            title_text="Distance (km)" if i == rows - 1 else "",
            tickmode='array',
            tickvals=list(range(0, int(df['cumulative_distance_m'].max()) + 1000, 1000)),
            ticktext=[f"{x/1000:.1f}" for x in range(0, int(df['cumulative_distance_m'].max()) + 1000, 1000)],
            row=i + 1, 
            col=1
        )
    
    # Update y-axis for main altitude plot
    fig.update_yaxes(title_text="Elevation (m)", row=1, col=1)
    
    return fig

def plot_power_strategy_summary(optimization_results, course_segments=None):
    """
    Create a focused power strategy visualization.
    
    Args:
        optimization_results (dict): Results from optimization analysis
        course_segments (pd.DataFrame): Course segment data (optional)
    
    Returns:
        plotly.graph_objects.Figure: Power strategy summary
    """
    segment_data = optimization_results['segment_breakdown']
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Power vs Course Difficulty',
            'Speed Response to Gradient', 
            'W\' Energy Management',
            'Segment Performance Summary'
        ],
        specs=[[{"secondary_y": True}, {"secondary_y": True}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    # 1. Power vs Course Difficulty - This plot really doesn't make any senese, should remove, it's also not really clear what it represents

    segments = segment_data['segment']
    power_line = [optimization_results['optimal_power']] * len(segments)
    gradient_bars = segment_data['gradient'] * 100
    
    fig.add_trace(
        go.Scatter(x=segments, y=power_line, 
                  name=f'Target Power ({optimization_results["optimal_power"]:.0f}W)',
                  line=dict(color='red', width=4)),
        row=1, col=1
    )
    fig.add_trace(
        go.Bar(x=segments, y=gradient_bars, 
               name='Gradient (%)', marker_color='lightgray', opacity=0.7),
        row=1, col=1, secondary_y=True
    )
    
    # 2. Speed Response to Gradient, possibly not useful either, remove
    speeds = segment_data['speed'] * 3.6
    fig.add_trace(
        go.Scatter(x=gradient_bars, y=speeds,
                  mode='markers+lines', name='Speed vs Gradient',
                  marker=dict(size=8, color='blue')),
        row=1, col=2
    )
    
    # 3. W' Energy Management, this is the ONE that's useful, and will be insightful once we change our pacing strategy
    cumulative_time = np.cumsum([0] + segment_data['time'].tolist()) / 60  # Convert to minutes
    w_remaining = [optimization_results.get('w_prime', 25000)/1000] + (segment_data['w_remaining']/1000).tolist()
    fig.add_trace(
        go.Scatter(x=cumulative_time[:-1], y=w_remaining[:-1],
                  name="W' Remaining", fill='tonexty', 
                  line=dict(color='green', width=3)),
        row=2, col=1
    )
    
    # 4. Segment Performance Summary
    segment_times = segment_data['time']
    distances = segment_data['length'] / 1000
    
    fig.add_trace(
        go.Bar(x=segments, y=segment_times, 
               name='Time per Segment', marker_color='purple'),
        row=2, col=2
    )
    
    # Update axes
    fig.update_xaxes(title_text="Segment", row=1, col=1)
    fig.update_xaxes(title_text="Gradient (%)", row=1, col=2)
    fig.update_xaxes(title_text="Time (min)", row=2, col=1)
    fig.update_xaxes(title_text="Segment", row=2, col=2)
    
    fig.update_yaxes(title_text="Power (W)", row=1, col=1)
    fig.update_yaxes(title_text="Gradient (%)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Speed (km/h)", row=1, col=2)
    fig.update_yaxes(title_text="W' Remaining (kJ)", row=2, col=1)
    fig.update_yaxes(title_text="Time (s)", row=2, col=2)
    
    fig.update_layout(
        height=600, 
        title_text="Power Strategy Analysis",
        template='plotly_dark',
        showlegend=True
    )
    
    return fig

def plot_variable_pacing_strategy(variable_pacing_results, course_segments=None, 
                                 show_comparison=True, title="Variable Pacing Strategy"):
    """
    Create comprehensive visualization for variable pacing strategy.
    
    Args:
        variable_pacing_results (dict): Results from optimize_variable_pacing
        course_segments (pd.DataFrame): Course segment data (optional)
        show_comparison (bool): Whether to show constant power comparison
        title (str): Plot title
    
    Returns:
        plotly.graph_objects.Figure: Multi-panel variable pacing visualization
    """
    segment_data = variable_pacing_results['segment_breakdown']
    
    # Create subplots
    rows = 3 if show_comparison else 2
    subplot_titles = [
        'Power Strategy by Terrain',
        'W\' Management Throughout Course'
    ]
    if show_comparison:
        subplot_titles.append('Variable vs Constant Power Comparison')
    
    fig = make_subplots(
        rows=rows, cols=1,
        subplot_titles=subplot_titles,
        shared_xaxes=True,
        vertical_spacing=0.08,
        specs=[[{"secondary_y": True}] for _ in range(rows)]
    )
    
    # Calculate cumulative distance for x-axis
    segment_data = segment_data.copy()
    segment_data['cumulative_distance'] = segment_data['distance'].cumsum() / 1000  # Convert to km
    segment_data['distance_start'] = segment_data['cumulative_distance'] - (segment_data['distance'] / 1000)
    
    # 1. Power Strategy by Terrain (Step function per coding standards)
    # Create step function for power
    x_power = []
    y_power = []
    terrain_colors = []
    
    terrain_color_map = {
        'Steep Climb': 'red',
        'Moderate Climb': 'orange', 
        'Flat': 'blue',
        'Moderate Descent': 'green',
        'Steep Descent': 'darkgreen'
    }
    
    for _, segment in segment_data.iterrows():
        # Add start point
        x_power.extend([segment['distance_start'], segment['cumulative_distance']])
        y_power.extend([segment['target_power'], segment['target_power']])
        terrain_colors.extend([terrain_color_map.get(segment['terrain_type'], 'gray')] * 2)
    
    # Add power strategy line
    fig.add_trace(
        go.Scatter(
            x=x_power, y=y_power,
            mode='lines',
            line=dict(width=3, shape='hv'),  # Step function shape
            name='Target Power',
            hovertemplate='Distance: %{x:.1f} km<br>Power: %{y:.0f} W<extra></extra>'
        ),
        row=1, col=1
    )
    
    # Add gradient bars on secondary y-axis
    fig.add_trace(
        go.Bar(
            x=segment_data['cumulative_distance'] - (segment_data['distance'] / 2000),  # Center bars
            y=segment_data['gradient'] * 100,
            width=segment_data['distance'] / 1000,
            name='Gradient %',
            opacity=0.3,
            marker_color=[terrain_color_map.get(t, 'gray') for t in segment_data['terrain_type']],
            hovertemplate='Distance: %{x:.1f} km<br>Gradient: %{y:.1f}%<extra></extra>'
        ),
        row=1, col=1, secondary_y=True
    )
      # 2. W' Management Throughout Course
    x_w = []
    y_w = []
    
    # Start at full W' (use the optimizer's W' value)
    initial_w_prime = variable_pacing_results.get('final_w_remaining', 0) + \
                     (variable_pacing_results.get('w_prime_utilization_percent', 0) / 100) * 25000  # Estimate
    
    # Better approach: Use the first segment's w_remaining + w_used to get initial W'
    first_segment = segment_data.iloc[0]
    if 'w_remaining' in first_segment and 'w_used_segment' in first_segment:
        # This gives us the W' at the END of the first segment plus what was used in that segment
        initial_w_prime = first_segment['w_remaining'] + first_segment['w_used_segment']
    else:
        initial_w_prime = 25000  # Default assumption
    
    x_w.append(0)
    y_w.append(initial_w_prime)
    
    for _, segment in segment_data.iterrows():
        x_w.append(segment['cumulative_distance'])
        y_w.append(segment['w_remaining'])
    
    fig.add_trace(
        go.Scatter(
            x=x_w, y=np.array(y_w) / 1000,  # Convert to kJ
            mode='lines+markers',
            line=dict(width=3, color='purple'),
            name='W\' Remaining (kJ)',
            hovertemplate='Distance: %{x:.1f} km<br>W\' Remaining: %{y:.1f} kJ<extra></extra>'
        ),
        row=2, col=1
    )
    # Add target W' utilization line
    target_utilization = variable_pacing_results.get('w_prime_utilization_percent', 85) / 100
    target_w_remaining = initial_w_prime * (1 - target_utilization)
    
    # Add horizontal line for target W' level using add_shape
    fig.add_shape(
        type="line",
        x0=0, x1=max(x_w), 
        y0=target_w_remaining / 1000, y1=target_w_remaining / 1000,
        line=dict(color="red", dash="dash"),
        row=2, col=1
    )
    
    # Add annotation for target W' level
    fig.add_annotation(
        x=max(x_w) * 0.7,  # Position annotation at 70% of the x-axis
        y=target_w_remaining / 1000,
        text=f"Target W' Level ({target_utilization*100:.0f}% utilization)",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=2,
        arrowcolor="red",
        row=2, col=1
    )
    
    # 3. Comparison with constant power (if requested)
    if show_comparison:
        comparison = variable_pacing_results.get('comparison_to_constant_power', {})
        
        # Create comparison bar chart
        categories = ['Variable Power', 'Constant Power']
        times = [
            variable_pacing_results['total_time_minutes'],
            comparison.get('constant_time_minutes', 0)
        ]
        speeds = [
            variable_pacing_results['average_speed_kmh'],
            comparison.get('constant_avg_speed_kmh', 0)
        ]
        
        fig.add_trace(
            go.Bar(
                x=categories, y=times,
                name='Time (minutes)',
                text=[f"{t:.1f} min" for t in times],
                textposition='outside',
                marker_color=['green', 'blue']
            ),
            row=3, col=1
        )
        
        # Add speed on secondary y-axis
        fig.add_trace(
            go.Scatter(
                x=categories, y=speeds,
                mode='markers+text',
                text=[f"{s:.1f} km/h" for s in speeds],
                textposition='top center',
                marker=dict(size=12, color=['green', 'blue']),
                name='Avg Speed (km/h)',
                yaxis='y2'
            ),
            row=3, col=1, secondary_y=True
        )
    
    # Update layout
    fig.update_layout(
        title=title,
        height=800 if show_comparison else 600,
        showlegend=True,
        hovermode='x unified'
    )
    
    # Update axes labels
    fig.update_xaxes(title_text="Distance (km)", row=rows, col=1)
    fig.update_yaxes(title_text="Power (W)", row=1, col=1)
    fig.update_yaxes(title_text="Gradient (%)", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="W' Remaining (kJ)", row=2, col=1)
    
    if show_comparison:
        fig.update_yaxes(title_text="Time (minutes)", row=3, col=1)
        fig.update_yaxes(title_text="Speed (km/h)", row=3, col=1, secondary_y=True)
    
    return fig


def plot_pacing_strategy_comparison(constant_results, variable_results, course_segments=None):
    """
    Create side-by-side comparison of constant vs variable pacing strategies.
    
    Args:
        constant_results (dict): Results from constant power optimization
        variable_results (dict): Results from variable pacing optimization
        course_segments (pd.DataFrame): Course segment data (optional)
    
    Returns:
        plotly.graph_objects.Figure: Comparison visualization
    """
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Power Distribution Comparison',
            'Speed Profile Comparison',
            'Performance Metrics',
            'W\' Utilization Strategy'
        ],
        specs=[
            [{"secondary_y": False}, {"secondary_y": False}],
            [{"type": "table"}, {"secondary_y": False}]
        ]
    )
    
    # Extract segment data
    var_segments = variable_results['segment_breakdown']
    var_segments['cumulative_distance'] = var_segments['distance'].cumsum() / 1000
    
    # 1. Power Distribution Comparison
    # Variable power as step function
    x_var = []
    y_var = []
    for _, segment in var_segments.iterrows():
        dist_start = segment['cumulative_distance'] - (segment['distance'] / 1000)
        x_var.extend([dist_start, segment['cumulative_distance']])
        y_var.extend([segment['target_power'], segment['target_power']])
    
    fig.add_trace(
        go.Scatter(
            x=x_var, y=y_var,
            mode='lines',
            line=dict(width=3, shape='hv', color='red'),
            name='Variable Power',
            hovertemplate='Distance: %{x:.1f} km<br>Power: %{y:.0f} W<extra></extra>'
        ),
        row=1, col=1
    )
    
    # Constant power as horizontal line
    const_power = constant_results.get('optimal_power', 0)
    max_distance = var_segments['cumulative_distance'].max()
    
    fig.add_trace(
        go.Scatter(
            x=[0, max_distance], y=[const_power, const_power],
            mode='lines',
            line=dict(width=3, color='blue', dash='dash'),
            name=f'Constant Power ({const_power:.0f}W)',
            hovertemplate='Power: %{y:.0f} W<extra></extra>'
        ),
        row=1, col=1
    )
    
    # 2. Speed Profile Comparison
    fig.add_trace(
        go.Scatter(
            x=var_segments['cumulative_distance'],
            y=var_segments['speed'] * 3.6,  # Convert to km/h
            mode='lines+markers',
            line=dict(color='red'),
            name='Variable Speed',
            hovertemplate='Distance: %{x:.1f} km<br>Speed: %{y:.1f} km/h<extra></extra>'
        ),
        row=1, col=2
    )
    
    # For constant power, we'd need to calculate speed profile
    # For now, show average speed as horizontal line
    const_avg_speed = constant_results.get('average_speed_kmh', 0)
    fig.add_trace(
        go.Scatter(
            x=[0, max_distance], y=[const_avg_speed, const_avg_speed],
            mode='lines',
            line=dict(color='blue', dash='dash'),
            name=f'Constant Avg Speed ({const_avg_speed:.1f} km/h)',
            hovertemplate='Speed: %{y:.1f} km/h<extra></extra>'
        ),
        row=1, col=2
    )
    
    # 3. Performance Metrics Table
    comparison_data = variable_results.get('comparison_to_constant_power', {})
    
    metrics_data = [
        ['Metric', 'Variable Pacing', 'Constant Power', 'Improvement'],
        ['Time (minutes)', f"{variable_results['total_time_minutes']:.1f}", 
         f"{comparison_data.get('constant_time_minutes', 0):.1f}",
         f"{comparison_data.get('time_savings_seconds', 0):.0f}s"],
        ['Avg Speed (km/h)', f"{variable_results['average_speed_kmh']:.1f}",
         f"{comparison_data.get('constant_avg_speed_kmh', 0):.1f}",
         f"+{comparison_data.get('speed_improvement_kmh', 0):.1f}"],
        ['W\' Utilization (%)', f"{variable_results['w_prime_utilization_percent']:.1f}",
         f"{constant_results.get('w_prime_utilization_percent', 0):.1f}",
         f"±{variable_results['w_prime_utilization_percent'] - constant_results.get('w_prime_utilization_percent', 0):.1f}"],
        ['Max Power (W)', f"{variable_results['power_distribution']['max_power']:.0f}",
         f"{const_power:.0f}",
         f"+{variable_results['power_distribution']['max_power'] - const_power:.0f}"]
    ]
    
    fig.add_trace(
        go.Table(
            header=dict(values=metrics_data[0], align='center'),
            cells=dict(values=list(zip(*metrics_data[1:])), align='center')
        ),
        row=2, col=1
    )
      # 4. W' Utilization Strategy
    x_w = []
    y_w = []
    
    # Get initial W' from first segment
    first_segment = var_segments.iloc[0]
    if 'w_remaining' in first_segment and 'w_used_segment' in first_segment:
        initial_w_prime = first_segment['w_remaining'] + first_segment['w_used_segment']
    else:
        initial_w_prime = 25000  # Default assumption
    
    x_w.append(0)
    y_w.append(initial_w_prime / 1000)  # Start with full W' in kJ
    
    for _, segment in var_segments.iterrows():
        x_w.append(segment['cumulative_distance'])
        y_w.append(segment['w_remaining'] / 1000)
    
    fig.add_trace(
        go.Scatter(
            x=x_w, y=y_w,
            mode='lines+markers',
            line=dict(width=3, color='red'),
            name='Variable W\' Profile',
            hovertemplate='Distance: %{x:.1f} km<br>W\' Remaining: %{y:.1f} kJ<extra></extra>'
        ),
        row=2, col=2
    )
    
    # Add constant power W' profile (would need simulation)
    # For now, show final W' remaining as horizontal line
    const_final_w = constant_results.get('final_w_remaining', 0) / 1000
    fig.add_trace(
        go.Scatter(
            x=[0, max_distance], y=[const_final_w, const_final_w],
            mode='lines',
            line=dict(color='blue', dash='dash'),
            name=f'Constant Final W\' ({const_final_w:.1f} kJ)',
            hovertemplate='W\' Remaining: %{y:.1f} kJ<extra></extra>'
        ),
        row=2, col=2
    )
    
    # Update layout
    fig.update_layout(
        title="Pacing Strategy Comparison: Variable vs Constant Power",
        height=800,
        showlegend=True
    )
    
    # Update axes
    fig.update_xaxes(title_text="Distance (km)")
    fig.update_yaxes(title_text="Power (W)", row=1, col=1)
    fig.update_yaxes(title_text="Speed (km/h)", row=1, col=2)
    fig.update_yaxes(title_text="W' Remaining (kJ)", row=2, col=2)
    
    return fig


def plot_terrain_power_analysis(variable_pacing_results):
    """
    Analyze power allocation by terrain type for variable pacing strategy.
    
    Args:
        variable_pacing_results (dict): Results from variable pacing optimization
    
    Returns:
        plotly.graph_objects.Figure: Terrain-based power analysis
    """
    segment_data = variable_pacing_results['segment_breakdown']
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Power by Terrain Type',
            'Time Distribution by Terrain',
            'W\' Usage by Terrain',
            'Efficiency Analysis'
        ],
        specs=[[{"type": "xy"}, {"type": "domain"}],
               [{"type": "xy"}, {"type": "xy"}]]
    )
    
    # Group by terrain type
    terrain_groups = segment_data.groupby('terrain_type').agg({
        'target_power': ['mean', 'std', 'count'],
        'time': 'sum',
        'w_used_segment': 'sum',
        'distance': 'sum',
        'speed': 'mean'
    }).round(2)
    
    terrain_types = terrain_groups.index.tolist()
    
    # 1. Power by Terrain Type (Box plot style)
    fig.add_trace(
        go.Bar(
            x=terrain_types,
            y=terrain_groups[('target_power', 'mean')],
            error_y=dict(type='data', array=terrain_groups[('target_power', 'std')]),
            name='Avg Power (W)',
            text=[f"{p:.0f}W" for p in terrain_groups[('target_power', 'mean')]],
            textposition='outside'
        ),
        row=1, col=1
    )
    
    # 2. Time Distribution by Terrain
    fig.add_trace(
        go.Pie(
            labels=terrain_types,
            values=terrain_groups[('time', 'sum')],
            name='Time Distribution',
            textinfo='label+percent',
            hovertemplate='%{label}<br>Time: %{value:.0f}s<br>Percentage: %{percent}<extra></extra>'
        ),
        row=1, col=2
    )
    
    # 3. W' Usage by Terrain
    fig.add_trace(
        go.Bar(
            x=terrain_types,
            y=terrain_groups[('w_used_segment', 'sum')] / 1000,  # Convert to kJ
            name='W\' Used (kJ)',
            text=[f"{w:.1f}kJ" for w in terrain_groups[('w_used_segment', 'sum')] / 1000],
            textposition='outside',
            marker_color='orange'
        ),
        row=2, col=1
    )
    
    # 4. Efficiency Analysis (Speed vs Power)
    power_means = terrain_groups[('target_power', 'mean')]
    speed_means = terrain_groups[('speed', 'mean')] * 3.6  # Convert to km/h
    
    fig.add_trace(
        go.Scatter(
            x=power_means,
            y=speed_means,
            mode='markers+text',
            text=terrain_types,
            textposition='top center',
            marker=dict(size=15, color='green'),
            name='Power vs Speed Efficiency',
            hovertemplate='Terrain: %{text}<br>Power: %{x:.0f}W<br>Speed: %{y:.1f} km/h<extra></extra>'
        ),
        row=2, col=2
    )
    
    # Update layout
    fig.update_layout(
        title="Terrain-Based Power Analysis",
        height=700,
        showlegend=False
    )
    
    # Update axes
    fig.update_yaxes(title_text="Power (W)", row=1, col=1)
    fig.update_yaxes(title_text="W' Used (kJ)", row=2, col=1)
    fig.update_xaxes(title_text="Power (W)", row=2, col=2)
    fig.update_yaxes(title_text="Speed (km/h)", row=2, col=2)
    
    return fig