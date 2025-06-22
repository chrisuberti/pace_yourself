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