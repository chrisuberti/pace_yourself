import pandas as pd
import numpy as np
from scipy.signal import savgol_filter
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import AgglomerativeClustering
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from dotenv import load_dotenv
import os
load_dotenv()
route_path = os.getenv('ROUTE_PATH')


# ============================================================================
# TERRAIN COLOR SCHEMES
# ============================================================================

TERRAIN_COLORS = {
    'uphill': '#2ecc71',      # green
    'flat': '#95a5a6',        # gray
    'downhill': '#e74c3c'     # red
}

SEGMENT_COLORSCALE = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
    '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
    '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5'
]


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert hex color to rgba string for Plotly."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    elif len(hex_color) == 3:
        r, g, b = int(hex_color[0]*2, 16), int(hex_color[1]*2, 16), int(hex_color[2]*2, 16)
    else:
        return f'rgba(100, 100, 100, {alpha})'  # fallback gray
    return f'rgba({r}, {g}, {b}, {alpha})'


# ============================================================================
# SMOOTHING VISUALIZATION UTILITIES
# ============================================================================

def plot_smoothing_comparison(df, title_prefix="", 
                               gradient_raw_col='raw_gradient', gradient_smooth_col='gradient',
                               bearing_change_raw_col='bearing_change', bearing_change_smooth_col='bearing_change_smoothed',
                               max_gradient=30.0):
    """
    Create a comprehensive 2x2 comparison plot showing raw vs smoothed data
    for both gradient and bearing changes.
    
    Args:
        df: DataFrame with gradient and bearing data
        title_prefix: Optional prefix for plot titles (e.g., course name)
        gradient_raw_col: Column name for raw gradient data
        gradient_smooth_col: Column name for smoothed gradient data
        bearing_change_raw_col: Column name for raw bearing change data
        bearing_change_smooth_col: Column name for smoothed bearing change data
        max_gradient: Maximum gradient threshold for reference lines
    
    Returns:
        plotly Figure object
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("Plotly is required for this visualization. Install with: pip install plotly")
        return None
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Raw Gradient', 'Raw Bearing Changes',
            'Smoothed Gradient', 'Smoothed Bearing Changes'
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.08
    )
    
    # Row 1: Raw data
    if gradient_raw_col in df.columns:
        fig.add_trace(
            go.Scatter(y=df[gradient_raw_col], mode='lines', name='Raw Gradient', 
                      line=dict(color='red', width=0.5)),
            row=1, col=1
        )
    
    if bearing_change_raw_col in df.columns:
        fig.add_trace(
            go.Scatter(y=df[bearing_change_raw_col], mode='lines', name='Raw Bearing', 
                      line=dict(color='red', width=0.5)),
            row=1, col=2
        )
    
    # Row 2: Smoothed data
    if gradient_smooth_col in df.columns:
        fig.add_trace(
            go.Scatter(y=df[gradient_smooth_col], mode='lines', name='Smoothed Gradient', 
                      line=dict(color='blue')),
            row=2, col=1
        )
    
    if bearing_change_smooth_col in df.columns:
        fig.add_trace(
            go.Scatter(y=df[bearing_change_smooth_col], mode='lines', name='Smoothed Bearing', 
                      line=dict(color='blue')),
            row=2, col=2
        )
    
    # Add threshold lines for gradient
    for row in [1, 2]:
        fig.add_hline(y=max_gradient, line_dash='dash', line_color='orange', row=row, col=1)
        fig.add_hline(y=-max_gradient, line_dash='dash', line_color='orange', row=row, col=1)
    
    # Add threshold lines for bearing changes
    for row in [1, 2]:
        fig.add_hline(y=90, line_dash='dash', line_color='orange', row=row, col=2)
        fig.add_hline(y=-90, line_dash='dash', line_color='orange', row=row, col=2)
        fig.add_hline(y=120, line_dash='dash', line_color='red', row=row, col=2)
        fig.add_hline(y=-120, line_dash='dash', line_color='red', row=row, col=2)
    
    # Update axes labels
    fig.update_xaxes(title_text='Point Index', row=2, col=1)
    fig.update_xaxes(title_text='Point Index', row=2, col=2)
    fig.update_yaxes(title_text='Gradient (%)', row=1, col=1)
    fig.update_yaxes(title_text='Gradient (%)', row=2, col=1)
    fig.update_yaxes(title_text='Bearing Change (°)', row=1, col=2)
    fig.update_yaxes(title_text='Bearing Change (°)', row=2, col=2)
    
    title = f'{title_prefix} Raw vs Smoothed: Gradient & Bearing' if title_prefix else 'Raw vs Smoothed: Gradient & Bearing'
    fig.update_layout(
        height=700,
        width=1200,
        title_text=title,
        showlegend=False
    )
    
    return fig


def plot_smoothing_histograms(df, title_prefix="",
                              gradient_raw_col='raw_gradient', gradient_smooth_col='gradient',
                              bearing_change_raw_col='bearing_change', bearing_change_smooth_col='bearing_change_smoothed'):
    """
    Create histogram comparison plots for gradient and bearing changes.
    
    Args:
        df: DataFrame with gradient and bearing data
        title_prefix: Optional prefix for plot titles
        gradient_raw_col: Column name for raw gradient data
        gradient_smooth_col: Column name for smoothed gradient data
        bearing_change_raw_col: Column name for raw bearing change data
        bearing_change_smooth_col: Column name for smoothed bearing change data
    
    Returns:
        plotly Figure object
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("Plotly is required for this visualization. Install with: pip install plotly")
        return None
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=['Gradient Distribution', 'Bearing Change Distribution'],
        horizontal_spacing=0.1
    )
    
    if gradient_raw_col in df.columns:
        fig.add_trace(
            go.Histogram(x=df[gradient_raw_col].dropna(), name='Raw Gradient', 
                        opacity=0.5, nbinsx=50, marker_color='red'),
            row=1, col=1
        )
    if gradient_smooth_col in df.columns:
        fig.add_trace(
            go.Histogram(x=df[gradient_smooth_col].dropna(), name='Smoothed Gradient', 
                        opacity=0.5, nbinsx=50, marker_color='blue'),
            row=1, col=1
        )
    
    if bearing_change_raw_col in df.columns:
        fig.add_trace(
            go.Histogram(x=df[bearing_change_raw_col].dropna(), name='Raw Bearing', 
                        opacity=0.5, nbinsx=100, marker_color='red'),
            row=1, col=2
        )
    if bearing_change_smooth_col in df.columns:
        fig.add_trace(
            go.Histogram(x=df[bearing_change_smooth_col].dropna(), name='Smoothed Bearing', 
                        opacity=0.5, nbinsx=100, marker_color='blue'),
            row=1, col=2
        )
    
    fig.add_vline(x=90, line_dash='dash', line_color='red', row=1, col=2)
    fig.add_vline(x=-90, line_dash='dash', line_color='red', row=1, col=2)
    
    fig.update_layout(
        barmode='overlay',
        height=400,
        width=1200,
        title_text=f'{title_prefix} Distribution Comparison' if title_prefix else 'Distribution Comparison',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5)
    )
    fig.update_xaxes(title_text='Gradient (%)', row=1, col=1)
    fig.update_xaxes(title_text='Bearing Change (°)', row=1, col=2)
    fig.update_yaxes(title_text='Count', row=1, col=1)
    fig.update_yaxes(title_text='Count', row=1, col=2)
    
    return fig


def print_smoothing_stats(df, 
                          gradient_raw_col='raw_gradient', gradient_smooth_col='gradient',
                          bearing_change_raw_col='bearing_change', bearing_change_smooth_col='bearing_change_smoothed',
                          max_gradient=30.0):
    """
    Print summary statistics comparing raw vs smoothed data for gradient and bearing.
    """
    print("=" * 70)
    print("SMOOTHING STATISTICS COMPARISON")
    print("=" * 70)
    
    print("\n--- GRADIENT ---")
    print(f"{'Metric':<25} {'Raw':>15} {'Smoothed':>15}")
    print("-" * 55)
    
    if gradient_raw_col in df.columns and gradient_smooth_col in df.columns:
        raw_g = df[gradient_raw_col]
        smooth_g = df[gradient_smooth_col]
        print(f"{'Min':<25} {raw_g.min():>15.1f}% {smooth_g.min():>15.1f}%")
        print(f"{'Max':<25} {raw_g.max():>15.1f}% {smooth_g.max():>15.1f}%")
        print(f"{'Mean':<25} {raw_g.mean():>15.2f}% {smooth_g.mean():>15.2f}%")
        print(f"{'Std Dev':<25} {raw_g.std():>15.2f}% {smooth_g.std():>15.2f}%")
        print(f"{'Points > {0}%'.format(max_gradient):<25} {(raw_g.abs() > max_gradient).sum():>15} {(smooth_g.abs() > max_gradient).sum():>15}")
    
    print("\n--- BEARING CHANGES ---")
    print(f"{'Metric':<25} {'Raw':>15} {'Smoothed':>15}")
    print("-" * 55)
    
    if bearing_change_raw_col in df.columns and bearing_change_smooth_col in df.columns:
        raw_b = df[bearing_change_raw_col]
        smooth_b = df[bearing_change_smooth_col]
        print(f"{'Min':<25} {raw_b.min():>15.1f}° {smooth_b.min():>15.1f}°")
        print(f"{'Max':<25} {raw_b.max():>15.1f}° {smooth_b.max():>15.1f}°")
        print(f"{'Mean':<25} {raw_b.mean():>15.2f}° {smooth_b.mean():>15.2f}°")
        print(f"{'Std Dev':<25} {raw_b.std():>15.2f}° {smooth_b.std():>15.2f}°")
        print(f"{'Sharp turns (>90°)':<25} {(raw_b.abs() > 90).sum():>15} {(smooth_b.abs() > 90).sum():>15}")
        print(f"{'Extreme turns (>120°)':<25} {(raw_b.abs() > 120).sum():>15} {(smooth_b.abs() > 120).sum():>15}")
    
    print("=" * 70)

class Course:
    def __init__(self, df, skip_processing: bool = False,
                 smoothing_target_distance: float = 100.0,
                 smoothing_min_window: int = 51,
                 smoothing_max_window: int = 101,
                 smoothing_polyorder: int = 2,
                 max_gradient: float = 25.0):
        """
        Initialize a Course object.
        
        Args:
            df: DataFrame with GPS data (lat, lon, altitude at minimum)
            skip_processing: If True, assume df is already processed (has gradient, 
                           cumulative_distance, etc.). Used when loading from database.
            smoothing_target_distance: Target distance in meters for smoothing window (default: 100m)
            smoothing_min_window: Minimum number of points for smoothing window (default: 51)
            smoothing_max_window: Maximum number of points for smoothing window (default: 101)
            smoothing_polyorder: Polynomial order for Savitzky-Golay filter (default: 2)
            max_gradient: Maximum allowed gradient in percent, values beyond are clamped (default: 25%)
        """
        self.df = df.copy()
        
        # Store smoothing parameters as instance variables
        self.smoothing_target_distance = smoothing_target_distance
        self.smoothing_min_window = smoothing_min_window
        self.smoothing_max_window = smoothing_max_window
        self.smoothing_polyorder = smoothing_polyorder
        self.max_gradient = max_gradient
        
        if skip_processing:
            # Data already processed - just validate required columns exist
            required_cols = ['lat', 'lon', 'altitude', 'gradient', 'cumulative_distance']
            missing = [c for c in required_cols if c not in self.df.columns]
            if missing:
                print(f"Warning: Pre-processed data missing columns: {missing}")
            return
            
        try:
            self.process_segment()
            self.calculate_bearing()
            #self.bearing_to_cardinal()
        except Exception as e:
            print(f"Error in Course initialization: {e}")
            # Ensure we at least have basic columns for debugging
            if 'cumulative_distance' not in self.df.columns:
                print("WARNING: cumulative_distance column missing after processing")
            raise

    def process_segment(self):
        print('running process segment')
        self.df["lat"] = self.df["lat"].astype(float)
        self.df["lon"] = self.df["lon"].astype(float)
        
        # Normalize altitude column name - GPX uses 'ele', we standardize to 'altitude'
        if 'ele' in self.df.columns and 'altitude' not in self.df.columns:
            self.df['altitude'] = self.df['ele']
        elif 'altitude' not in self.df.columns:
            raise ValueError("DataFrame must contain 'altitude' or 'ele' column")
        
        self.df["altitude"] = self.df["altitude"].astype(float)
        
        # Calculate the net distance between a pair of lat/lon points FIRST
        # (needed to determine appropriate smoothing window)
        self.df["delta_lat"] = self.df["lat"].diff()
        self.df["delta_lon"] = self.df["lon"].diff()
        self.df["distance"] = (self.df["delta_lat"]**2 + self.df["delta_lon"]**2)**0.5
        self.df["distance"] = self.df["distance"].fillna(0)
        # Convert the lat/lon distance to meters
        self.df["distance"] = self.df["distance"] * 111139
        # Calculate the cumulative distance
        self.df["cumulative_distance"] = self.df["distance"].cumsum()
        
        # Smooth altitude data to reduce GPS noise before gradient calculation
        # Use adaptive window based on point density
        avg_point_spacing = self.df["distance"].median()
        if avg_point_spacing > 0:
            target_points = max(
                self.smoothing_min_window, 
                min(self.smoothing_max_window, int(self.smoothing_target_distance / avg_point_spacing))
            )
            # Window must be odd
            window_length = target_points if target_points % 2 == 1 else target_points + 1
        else:
            window_length = self.smoothing_min_window * 2 + 1  # Default odd window
        
        # Store calculated window for reference
        self.calculated_window_length = window_length
        
        # Apply Savitzky-Golay filter for smooth altitude
        if window_length >= 5 and len(self.df) >= window_length:
            self.df["altitude_smoothed"] = savgol_filter(
                self.df["altitude"].ffill().bfill(), 
                window_length=window_length, 
                polyorder=self.smoothing_polyorder
            )
        else:
            self.df["altitude_smoothed"] = self.df["altitude"]
        
        # Calculate gradient using smoothed altitude
        self.df["delta_altitude"] = self.df["altitude_smoothed"].diff()
        self.df["height_gain"] = self.df["altitude"].diff().clip(lower=0)  # Use raw for actual gain
        self.df["height_loss"] = -self.df["altitude"].diff().clip(upper=0)
        
        # Handle inf values in the gradient and set them to zero
        self.df["gradient"] = (self.df["delta_altitude"] / self.df["distance"]) * 100
        self.df["gradient"] = self.df["gradient"].fillna(0)
        self.df['gradient'] = self.df['gradient'].replace([np.inf, -np.inf], 0)
        
        # Clamp gradient to realistic values
        self.df['gradient'] = self.df['gradient'].clip(lower=-self.max_gradient, upper=self.max_gradient)


    def calculate_bearing(self):
        """
        Calculate the compass bearing between consecutive points in the DataFrame.
        Also calculates bearing changes and smoothed bearings.
        """
        lat1 = np.radians(self.df["lat"].shift(0))
        lat2 = np.radians(self.df["lat"].shift(-1))
        diff_long = np.radians(self.df["lon"].shift(-1) - self.df["lon"])

        x = np.sin(diff_long) * np.cos(lat2)
        y = np.cos(lat1) * np.sin(lat2) - (np.sin(lat1) * np.cos(lat2) * np.cos(diff_long))

        initial_bearing = np.arctan2(x, y)
        initial_bearing = np.degrees(initial_bearing)
        compass_bearing = (initial_bearing + 360) % 360

        self.df["bearing"] = compass_bearing
        self.df["bearing"] = self.df["bearing"].fillna(0)  # Handle NaN for the last row
        
        # Calculate bearing changes (handling wrap-around at 0/360)
        bearing_diff = self.df["bearing"].diff()
        # Normalize to -180 to 180
        bearing_diff = np.where(bearing_diff > 180, bearing_diff - 360, bearing_diff)
        bearing_diff = np.where(bearing_diff < -180, bearing_diff + 360, bearing_diff)
        self.df["bearing_change"] = bearing_diff
        
        # Calculate raw gradient for comparison (before smoothing was applied)
        self.df["raw_gradient"] = (self.df["altitude"].diff() / self.df["distance"]) * 100
        self.df["raw_gradient"] = self.df["raw_gradient"].replace([np.inf, -np.inf], np.nan)
        
        # Smooth bearings using unit vector approach (handles circular nature)
        bearing_x = np.cos(np.radians(self.df["bearing"]))
        bearing_y = np.sin(np.radians(self.df["bearing"]))
        
        # Use same adaptive window as altitude smoothing (reuse calculated value if available)
        if hasattr(self, 'calculated_window_length'):
            window_length = self.calculated_window_length
        else:
            avg_point_spacing = self.df["distance"].median()
            if avg_point_spacing > 0:
                target_points = max(
                    self.smoothing_min_window,
                    min(self.smoothing_max_window, int(self.smoothing_target_distance / avg_point_spacing))
                )
                window_length = target_points if target_points % 2 == 1 else target_points + 1
            else:
                window_length = self.smoothing_min_window * 2 + 1
        
        if window_length >= 5 and len(self.df) >= window_length:
            bearing_x_smooth = savgol_filter(
                pd.Series(bearing_x).ffill().bfill(),
                window_length=window_length,
                polyorder=self.smoothing_polyorder
            )
            bearing_y_smooth = savgol_filter(
                pd.Series(bearing_y).ffill().bfill(),
                window_length=window_length,
                polyorder=self.smoothing_polyorder
            )
        else:
            bearing_x_smooth = bearing_x
            bearing_y_smooth = bearing_y
        
        self.df["bearing_smoothed"] = np.degrees(np.arctan2(bearing_y_smooth, bearing_x_smooth)) % 360
        
        # Calculate smoothed bearing changes
        bearing_diff_smooth = self.df["bearing_smoothed"].diff()
        bearing_diff_smooth = np.where(bearing_diff_smooth > 180, bearing_diff_smooth - 360, bearing_diff_smooth)
        bearing_diff_smooth = np.where(bearing_diff_smooth < -180, bearing_diff_smooth + 360, bearing_diff_smooth)
        self.df["bearing_change_smoothed"] = bearing_diff_smooth

    def plot_smoothing_comparison(self, title_prefix=""):
        """
        Create comparison plots showing raw vs smoothed gradient and bearing data.
        Returns a plotly Figure object.
        """
        return plot_smoothing_comparison(
            self.df, 
            title_prefix=title_prefix,
            gradient_raw_col='raw_gradient',
            gradient_smooth_col='gradient',
            bearing_change_raw_col='bearing_change',
            bearing_change_smooth_col='bearing_change_smoothed'
        )
    
    def plot_smoothing_histograms(self, title_prefix=""):
        """
        Create histogram comparison plots for gradient and bearing changes.
        Returns a plotly Figure object.
        """
        return plot_smoothing_histograms(
            self.df,
            title_prefix=title_prefix,
            gradient_raw_col='raw_gradient',
            gradient_smooth_col='gradient',
            bearing_change_raw_col='bearing_change',
            bearing_change_smooth_col='bearing_change_smoothed'
        )
    
    def print_smoothing_stats(self):
        """Print summary statistics comparing raw vs smoothed data."""
        print_smoothing_stats(
            self.df,
            gradient_raw_col='raw_gradient',
            gradient_smooth_col='gradient',
            bearing_change_raw_col='bearing_change',
            bearing_change_smooth_col='bearing_change_smoothed'
        )

    def bearing_to_cardinal(self):
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = ((self.df["bearing"] + 11.25) / 22.5).astype(int)
        self.df["cardinal"] = idx.apply(lambda x: directions[x % 16])

    def equal_segmentation(self, n):
        """Divide the course into equal segments based on distance."""
        # Clear stale segmentation metadata from other methods
        if 'segment_terrain' in self.df.columns:
            self.df.drop(columns=['segment_terrain'], inplace=True)
        self.df['segment'] = pd.cut(self.df['cumulative_distance'], bins=n, labels=False)+1
        self.df['segment_terrain'] = 'equal'
        self.aggregate_segments()  # Call the aggregation method

    def slider_segmentation(self, slider_values):
        """Segment the course based on slider values."""
        self.df['segment'] = len(slider_values)
        for i in range(1, len(slider_values)):
            course_length = self.df.distance.sum()
            min_seg_dist = slider_values[i - 1] / 100 * course_length
            max_seg_dist = slider_values[i] / 100 * course_length
            self.df.loc[
                (self.df['cumulative_distance'] >= min_seg_dist) &
                (self.df['cumulative_distance'] < max_seg_dist),
                'segment'
            ] = i
        self.aggregate_segments()  # Call the aggregation method

    def manual_segmentation(self, num_sliders, distance=100):
        """
        Perform manual segmentation using slider values.

        Args:
            num_sliders (int): Number of sliders for segmentation.
            distance (float): Total distance of the course.

        Returns:
            list: Slider values representing segment boundaries.
        """
        slider_values = [0]
        equal_distance = distance / num_sliders

        for i in range(1, num_sliders):
            min_value = slider_values[i - 1]
            initial_value = min_value + equal_distance
            slider_values.append(initial_value)

        slider_values.append(distance)  # Ensure the last segment ends at the total distance

        # Apply segmentation based on slider values
        self.df['segment'] = len(slider_values) - 1
        for i in range(1, len(slider_values)):
            min_seg_dist = slider_values[i - 1]
            max_seg_dist = slider_values[i]
            self.df.loc[
                (self.df['cumulative_distance'] >= min_seg_dist) &
                (self.df['cumulative_distance'] < max_seg_dist),
                'segment'
            ] = i
        self.aggregate_segments()  # Call the aggregation method

        return slider_values

    def aggregate_segments(self):
        """Aggregate segment data while preserving sequence order."""
        # First, create the traditional aggregated segments for backward compatibility
        self.course_segments_aggregated = self.df.groupby('segment').agg({
            'lat': 'mean',
            'lon': 'mean',
            'bearing': 'mean',
            'altitude': ['mean', 'min', 'max'],
            'gradient': 'mean',
            'height_gain': 'sum',
            'height_loss': 'sum',
            'distance': 'sum'
        }).reset_index()
        
        # Flatten multiindex columns for aggregated segments
        self.course_segments_aggregated.columns = ['_'.join(col).strip() for col in self.course_segments_aggregated.columns.values]
        self.course_segments_aggregated.rename(columns={'segment_': 'segment'}, inplace=True)
        self.course_segments_aggregated['distance_sum'] = self.course_segments_aggregated['distance_sum'] / 1000
        self.course_segments_aggregated['gradient_mean'] = self.course_segments_aggregated['gradient_mean'].round(2)
        self.course_segments_aggregated.drop(columns=['lat_mean', 'lon_mean'], inplace=True)
        self.course_segments_aggregated.dropna(inplace=True)
        
        # NEW: Create sequence-preserving segments that maintain order
        self.course_segments = self._create_sequence_preserving_segments()
        
        # Keep backward compatibility - if code expects old format, it still works
        if not hasattr(self, 'use_enhanced_segmentation') or not self.use_enhanced_segmentation:
            # For backward compatibility, keep old behavior as default
            self.course_segments = self.course_segments_aggregated.copy()
    
    def _create_sequence_preserving_segments(self):
        """Create segment sequence that preserves order while tracking segment types."""
        # Group consecutive segments of the same type
        segment_changes = self.df['segment'].diff().fillna(1) != 0
        segment_groups = segment_changes.cumsum()
        
        # Create sequence-preserving segments
        sequence_segments = []
        segment_occurrence = {}
        
        for group_id in segment_groups.unique():
            group_data = self.df[segment_groups == group_id]
            segment_id = group_data['segment'].iloc[0]
            
            # Track occurrences of each segment type
            if segment_id not in segment_occurrence:
                segment_occurrence[segment_id] = 0
            segment_occurrence[segment_id] += 1
            
            # Calculate aggregated metrics for this segment occurrence
            segment_info = {
                'segment_id': segment_id,                              # Original terrain type (1, 2, 3, 4)
                'segment_occurrence': segment_occurrence[segment_id],   # Nth occurrence of this type
                'segment_sequence': len(sequence_segments) + 1,        # Position in course
                'distance_sum': group_data['distance'].sum() / 1000,   # km
                'gradient_mean': group_data['gradient'].mean(),        # percentage
                'altitude_mean': group_data['altitude'].mean(),        # meters
                'altitude_min': group_data['altitude'].min(),
                'altitude_max': group_data['altitude'].max(),
                'bearing_mean': group_data['bearing'].mean(),
                'height_gain_sum': group_data['height_gain'].sum(),
                'height_loss_sum': group_data['height_loss'].sum(),
                'start_distance': group_data['cumulative_distance'].iloc[0] / 1000,  # km
                'end_distance': group_data['cumulative_distance'].iloc[-1] / 1000,    # km
                'start_index': group_data.index[0],                    # Original dataframe index
                'end_index': group_data.index[-1]                     # Original dataframe index
            }
            
            sequence_segments.append(segment_info)
        
        # Convert to DataFrame with proper formatting
        segments_df = pd.DataFrame(sequence_segments)
        segments_df['gradient_mean'] = segments_df['gradient_mean'].round(2)
        segments_df.dropna(inplace=True)
        
        return segments_df
    
    def enable_enhanced_segmentation(self):
        """Enable the new sequence-preserving segmentation format."""
        self.use_enhanced_segmentation = True
        # Re-aggregate to use enhanced format
        if hasattr(self, 'df') and 'segment' in self.df.columns:
            self.aggregate_segments()

    def smooth_data(self, df_col, window_size=5):
        return (
            df_col
            .rolling(window=window_size, center=True)
            .mean()
            .bfill()  # Fill the start of the DataFrame
            .ffill()  # Fill the end of the DataFrame
        )

    def auto_segmentation(self, max_clusters=10, gradient_weight=1.0, bearing_weight=1.0, smoothing_window=5):
        """
        Automatically segment the course into clusters based on gradient and bearing.

        Args:
            max_clusters (int): Maximum number of clusters to create.
            gradient_weight (float): Weight for the gradient feature.
            bearing_weight (float): Weight for the bearing feature.
            smoothing_window (int): Window size for smoothing gradient and bearing data.
        """
        # Clear existing segmentation data to prevent accumulation
        if 'segment' in self.df.columns:
            self.df.drop(columns=['segment'], inplace=True)
        if 'segment_terrain' in self.df.columns:
            self.df.drop(columns=['segment_terrain'], inplace=True)
        if hasattr(self, 'course_segments'):
            delattr(self, 'course_segments')
        if hasattr(self, 'course_segments_aggregated'):
            delattr(self, 'course_segments_aggregated')
        
        def normalize_bearing(bearing):
            return np.radians(bearing)

        def compute_custom_distance(point_a, point_b):
            """
            Custom distance metric that considers gradient and bearing.
            Args:
                point_a: Tuple (gradient, bearing).
                point_b: Tuple (gradient, bearing).
            Returns:
                float: Weighted distance between the two points.
            """
            grad_a, bear_a = point_a
            grad_b, bear_b = point_b

            # Normalize gradient difference
            grad_diff = abs(grad_a - grad_b)

            # Normalize bearing difference (handle circularity)
            bear_diff = abs(np.arctan2(np.sin(bear_a - bear_b), np.cos(bear_a - bear_b)))

            # Adjust weights based on gradient
            if abs(grad_a) > 2 or abs(grad_b) > 2:  # High gradient scenario
                grad_weight = gradient_weight * 1.5
                bear_weight = bearing_weight * 0.5
            else:  # Flat scenario
                grad_weight = gradient_weight * 0.5
                bear_weight = bearing_weight * 1.5

            return grad_weight * grad_diff + bear_weight * bear_diff

        # Smooth gradient and bearing columns (clear any existing smoothed columns first)
        for col in ['gradient_smoothed', 'bearing_smoothed', 'bearing_normalized']:
            if col in self.df.columns:
                self.df.drop(columns=[col], inplace=True)
                
        self.df["gradient_smoothed"] = self.smooth_data(self.df["gradient"], window_size=smoothing_window)
        self.df["bearing_smoothed"] = self.smooth_data(self.df["bearing"], window_size=smoothing_window)

        # Normalize bearing for clustering
        self.df["bearing_normalized"] = normalize_bearing(self.df["bearing_smoothed"])
        features = self.df[["gradient_smoothed", "bearing_normalized"]].to_numpy()

        # Compute custom distance matrix
        dist_matrix = squareform(pdist(features, metric=compute_custom_distance))

        # Perform hierarchical clustering
        clusterer = AgglomerativeClustering(
            linkage="average",
            n_clusters=None,
            distance_threshold=None
        )
        clusterer.set_params(n_clusters=min(max_clusters, len(self.df)))
        self.df["segment"] = clusterer.fit_predict(dist_matrix)
        self.df['segment_terrain'] = 'cluster'

        # Aggregate segments
        self.aggregate_segments()

    def gradient_bearing_segmentation(self, 
                                       uphill_threshold: float = 2.0,
                                       downhill_threshold: float = -2.0,
                                       bearing_change_threshold: float = 45.0,
                                       min_segment_distance: float = 200.0,
                                       smoothing_window: int = 21):
        """
        Segment the course based on gradient classification and bearing changes.
        Creates CONTIGUOUS segments where each segment has consistent terrain character.
        
        Segment boundaries are created when:
        1. Gradient classification changes (uphill → flat → downhill)
        2. Large cumulative bearing change detected (e.g., hairpin turn, out-and-back)
        
        Args:
            uphill_threshold: Gradient (%) above which terrain is classified as uphill (default: 2.0)
            downhill_threshold: Gradient (%) below which terrain is classified as downhill (default: -2.0)
            bearing_change_threshold: Cumulative bearing change (degrees) over smoothing window 
                                     that triggers a segment boundary (default: 45.0)
            min_segment_distance: Minimum segment length in meters to avoid micro-segments (default: 200)
            smoothing_window: Window size for smoothing gradient before classification (default: 21)
        
        Returns:
            DataFrame with segment assignments and terrain classifications
        """
        # Clear existing segmentation
        if 'segment' in self.df.columns:
            self.df.drop(columns=['segment'], inplace=True)
        if hasattr(self, 'course_segments'):
            delattr(self, 'course_segments')
        if hasattr(self, 'course_segments_aggregated'):
            delattr(self, 'course_segments_aggregated')
        
        # Work with sorted data
        df = self.df.sort_values('cumulative_distance').reset_index(drop=True)
        
        # Smooth gradient for classification (reduce noise-triggered boundaries)
        gradient_smooth = df['gradient'].rolling(
            window=smoothing_window, center=True, min_periods=1
        ).mean()
        
        # Classify each point by gradient
        def classify_gradient(g):
            if g > uphill_threshold:
                return 'uphill'
            elif g < downhill_threshold:
                return 'downhill'
            else:
                return 'flat'
        
        df['terrain_class'] = gradient_smooth.apply(classify_gradient)
        
        # Calculate cumulative bearing change over rolling window
        # This detects sharp turns, hairpins, and direction reversals
        bearing_change_abs = df['bearing_change'].abs().fillna(0)
        cumulative_bearing_change = bearing_change_abs.rolling(
            window=smoothing_window, center=True, min_periods=1
        ).sum()
        
        # Detect significant bearing change points
        df['bearing_change_significant'] = cumulative_bearing_change > bearing_change_threshold
        
        # Create segment boundaries
        # Boundary when: terrain class changes OR significant bearing change
        terrain_changed = df['terrain_class'] != df['terrain_class'].shift(1)
        bearing_boundary = df['bearing_change_significant'] & ~df['bearing_change_significant'].shift(1).fillna(False)
        
        # Combine boundary conditions
        is_boundary = terrain_changed | bearing_boundary
        is_boundary.iloc[0] = True  # First point is always a boundary
        
        # Assign preliminary segments
        df['segment'] = is_boundary.cumsum() - 1
        
        # Merge small segments into neighbors
        # Calculate segment distances
        segment_distances = df.groupby('segment')['distance'].sum()
        small_segments = segment_distances[segment_distances < min_segment_distance].index.tolist()
        
        # Merge small segments with the previous segment (or next if first)
        for seg_id in small_segments:
            if seg_id == 0:
                # Merge with next segment
                df.loc[df['segment'] == seg_id, 'segment'] = 1
            else:
                # Merge with previous segment
                df.loc[df['segment'] == seg_id, 'segment'] = seg_id - 1
        
        # Renumber segments sequentially
        unique_segs = sorted(df['segment'].unique())
        seg_mapping = {old: new for new, old in enumerate(unique_segs)}
        df['segment'] = df['segment'].map(seg_mapping)
        
        # Store terrain class for each segment (majority vote)
        segment_terrain = df.groupby('segment')['terrain_class'].agg(
            lambda x: x.value_counts().index[0]
        )
        df['segment_terrain'] = df['segment'].map(segment_terrain)
        
        # Update the main dataframe
        self.df = df
        
        # Aggregate segments
        self.aggregate_segments()
        
        # Add terrain classification to aggregated segments
        if hasattr(self, 'course_segments'):
            terrain_map = df.groupby('segment')['segment_terrain'].first().to_dict()
            self.course_segments['terrain'] = self.course_segments['segment'].map(terrain_map)
        
        # Print summary
        print(f"Created {df['segment'].nunique()} contiguous segments:")
        for seg_id in sorted(df['segment'].unique()):
            seg_data = df[df['segment'] == seg_id]
            dist_km = seg_data['distance'].sum() / 1000
            avg_grad = seg_data['gradient'].mean()
            terrain = seg_data['segment_terrain'].iloc[0]
            bearing_total = seg_data['bearing_change'].abs().sum()
            print(f"  Seg {seg_id}: {dist_km:.2f}km, {avg_grad:+.1f}%, {terrain}, Σ|bearing|={bearing_total:.0f}°")
        
        return df

    # ========================================================================
    # PREVIEW SEGMENTATION METHODS (Non-destructive for interactive tuning)
    # ========================================================================
    
    def preview_equal_segmentation(self, n_segments: int) -> pd.DataFrame:
        """
        Preview equal segmentation without modifying self.df.
        
        Args:
            n_segments: Number of equal-distance segments
        
        Returns:
            DataFrame with segment assignments
        """
        df = self.df.copy()
        total_distance = df['cumulative_distance'].iloc[-1]
        segment_distance = total_distance / n_segments
        df['segment'] = (df['cumulative_distance'] / segment_distance).astype(int)
        df['segment'] = df['segment'].clip(upper=n_segments - 1)
        df['segment_terrain'] = 'equal'  # Placeholder for consistency
        return df
    
    def preview_terrain_segmentation(self,
                                      uphill_threshold: float = 2.0,
                                      downhill_threshold: float = -2.0,
                                      bearing_change_threshold: float = 45.0,
                                      min_segment_distance: float = 200.0,
                                      smoothing_window: int = 21) -> pd.DataFrame:
        """
        Preview terrain-based segmentation without modifying self.df.
        
        Args:
            uphill_threshold: Gradient (%) above which terrain is classified as uphill
            downhill_threshold: Gradient (%) below which terrain is classified as downhill
            bearing_change_threshold: Cumulative bearing change threshold for segment boundary
            min_segment_distance: Minimum segment length in meters
            smoothing_window: Window size for gradient smoothing
        
        Returns:
            DataFrame with segment assignments and terrain classifications
        """
        df = self.df.copy().sort_values('cumulative_distance').reset_index(drop=True)
        
        # Ensure bearing_change column exists (may be missing from pre-processed data)
        if 'bearing_change' not in df.columns:
            if 'bearing' in df.columns:
                bearing_diff = df['bearing'].diff()
                # Normalize to -180 to 180
                bearing_diff = np.where(bearing_diff > 180, bearing_diff - 360, bearing_diff)
                bearing_diff = np.where(bearing_diff < -180, bearing_diff + 360, bearing_diff)
                df['bearing_change'] = bearing_diff
            else:
                # No bearing data available - create zero column
                df['bearing_change'] = 0
        
        # Smooth gradient for classification
        gradient_smooth = df['gradient'].rolling(
            window=smoothing_window, center=True, min_periods=1
        ).mean()
        
        # Classify each point by gradient
        def classify_gradient(g):
            if g > uphill_threshold:
                return 'uphill'
            elif g < downhill_threshold:
                return 'downhill'
            else:
                return 'flat'
        
        df['terrain_class'] = gradient_smooth.apply(classify_gradient)
        
        # Calculate cumulative bearing change over rolling window
        bearing_change_abs = df['bearing_change'].abs().fillna(0)
        cumulative_bearing_change = bearing_change_abs.rolling(
            window=smoothing_window, center=True, min_periods=1
        ).sum()
        
        # Detect significant bearing change points
        df['bearing_change_significant'] = cumulative_bearing_change > bearing_change_threshold
        
        # Create segment boundaries
        terrain_changed = df['terrain_class'] != df['terrain_class'].shift(1)
        bearing_boundary = df['bearing_change_significant'] & ~df['bearing_change_significant'].shift(1).fillna(False)
        is_boundary = terrain_changed | bearing_boundary
        is_boundary.iloc[0] = True
        
        df['segment'] = is_boundary.cumsum() - 1
        
        # Merge small segments
        segment_distances = df.groupby('segment')['distance'].sum()
        small_segments = segment_distances[segment_distances < min_segment_distance].index.tolist()
        
        for seg_id in small_segments:
            if seg_id == 0:
                df.loc[df['segment'] == seg_id, 'segment'] = 1
            else:
                df.loc[df['segment'] == seg_id, 'segment'] = seg_id - 1
        
        # Renumber segments sequentially
        unique_segs = sorted(df['segment'].unique())
        seg_mapping = {old: new for new, old in enumerate(unique_segs)}
        df['segment'] = df['segment'].map(seg_mapping)
        
        # Store terrain class for each segment
        segment_terrain = df.groupby('segment')['terrain_class'].agg(
            lambda x: x.value_counts().index[0]
        )
        df['segment_terrain'] = df['segment'].map(segment_terrain)
        
        return df
    
    def preview_clustering_segmentation(self,
                                         max_clusters: int = 10,
                                         gradient_weight: float = 1.0,
                                         bearing_weight: float = 1.0,
                                         smoothing_window: int = 5) -> pd.DataFrame:
        """
        Preview clustering-based segmentation without modifying self.df.
        
        Args:
            max_clusters: Maximum number of clusters
            gradient_weight: Weight for gradient feature
            bearing_weight: Weight for bearing feature
            smoothing_window: Window size for smoothing
        
        Returns:
            DataFrame with segment assignments
        """
        df = self.df.copy()
        
        def normalize_bearing(bearing):
            return np.radians(bearing)
        
        def compute_custom_distance(point_a, point_b):
            grad_a, bear_a = point_a
            grad_b, bear_b = point_b
            grad_diff = abs(grad_a - grad_b)
            bear_diff = abs(np.arctan2(np.sin(bear_a - bear_b), np.cos(bear_a - bear_b)))
            
            if abs(grad_a) > 2 or abs(grad_b) > 2:
                grad_w = gradient_weight * 1.5
                bear_w = bearing_weight * 0.5
            else:
                grad_w = gradient_weight * 0.5
                bear_w = bearing_weight * 1.5
            
            return grad_w * grad_diff + bear_w * bear_diff
        
        # Smooth data
        df["gradient_smoothed"] = df["gradient"].rolling(
            window=smoothing_window, center=True, min_periods=1
        ).mean()
        df["bearing_smoothed"] = df["bearing"].rolling(
            window=smoothing_window, center=True, min_periods=1
        ).mean()
        df["bearing_normalized"] = normalize_bearing(df["bearing_smoothed"])
        
        features = df[["gradient_smoothed", "bearing_normalized"]].to_numpy()
        dist_matrix = squareform(pdist(features, metric=compute_custom_distance))
        
        clusterer = AgglomerativeClustering(
            linkage="average",
            n_clusters=min(max_clusters, len(df))
        )
        df["segment"] = clusterer.fit_predict(dist_matrix)
        df['segment_terrain'] = 'cluster'  # Placeholder
        
        return df

    # ========================================================================
    # PLOTLY VISUALIZATION METHODS
    # ========================================================================
    
    def plot_segmentation_profile(self, 
                                   df: pd.DataFrame = None,
                                   method: str = 'terrain',
                                   title: str = None,
                                   show_segment_bar: bool = True,
                                   height: int = 600) -> go.Figure:
        """
        Create Plotly elevation profile colored by segment.
        
        For contiguous methods (terrain, equal): plots each segment as a continuous block.
        For clustering: plots each contiguous RUN of the same segment separately,
        since the same segment ID can appear at multiple points along the course.
        
        Args:
            df: DataFrame with segment assignments (uses self.df if None)
            method: 'terrain', 'equal', or 'clustering' - affects coloring and plotting strategy
            title: Plot title (auto-generated if None)
            show_segment_bar: Whether to show segment bar below profile
            height: Figure height in pixels
        
        Returns:
            Plotly Figure object
        """
        if df is None:
            df = self.df.copy()
        
        df_sorted = df.sort_values('cumulative_distance').reset_index(drop=True)
        cum_dist_km = df_sorted['cumulative_distance'] / 1000
        altitude = df_sorted['altitude']
        
        unique_segments = sorted(df_sorted['segment'].unique())
        n_segments = len(unique_segments)
        
        # Determine color scheme based on method
        if method == 'terrain' and 'segment_terrain' in df_sorted.columns:
            use_terrain_colors = True
        else:
            use_terrain_colors = False
        
        # Build color map
        segment_colors = {}
        for i, seg_id in enumerate(unique_segments):
            if use_terrain_colors:
                terrain = df_sorted[df_sorted['segment'] == seg_id]['segment_terrain'].iloc[0]
                segment_colors[seg_id] = TERRAIN_COLORS.get(terrain, SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)])
            else:
                segment_colors[seg_id] = SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)]
        
        # Create subplots
        if show_segment_bar:
            fig = make_subplots(
                rows=2, cols=1,
                row_heights=[0.85, 0.15],
                shared_xaxes=True,
                vertical_spacing=0.02
            )
        else:
            fig = make_subplots(rows=1, cols=1)
        
        # Track which segments we've already added to legend
        legend_added = set()
        
        # For clustering, we need to plot each CONTIGUOUS RUN separately
        # since the same segment ID can appear at multiple positions
        if method == 'clustering':
            # For clustering, we'll only show legend entries for unique segment types (clusters)
            # not for every contiguous run
            legend_added = set()
            
            # Iterate through data and find contiguous runs
            prev_seg = None
            run_start_idx = 0
            
            for i in range(len(df_sorted)):
                seg_id = df_sorted['segment'].iloc[i]
                
                if seg_id != prev_seg:
                    # Plot the previous run if it exists
                    if prev_seg is not None and i > run_start_idx:
                        # Get data for this contiguous run (exclusive end - don't include transition point)
                        run_dist = cum_dist_km.iloc[run_start_idx:i]
                        run_alt = altitude.iloc[run_start_idx:i]
                        
                        color = segment_colors[prev_seg]
                        fill_color = hex_to_rgba(color, 0.4) if color.startswith('#') else color
                        
                        # Calculate stats for this run
                        run_mask = (df_sorted.index >= run_start_idx) & (df_sorted.index < i)
                        avg_grad = df_sorted.loc[run_mask, 'gradient'].mean()
                        run_distance = df_sorted.loc[run_mask, 'distance'].sum() / 1000
                        
                        # Only show in legend once per cluster type
                        show_legend = prev_seg not in legend_added
                        if show_legend:
                            legend_added.add(prev_seg)
                        
                        # Simplified legend name for clustering - just show "Cluster X"
                        legend_name = f'Cluster {prev_seg}'
                        
                        fig.add_trace(
                            go.Scatter(
                                x=run_dist,
                                y=run_alt,
                                mode='lines',
                                fill='tozeroy',
                                fillcolor=fill_color,
                                line=dict(color=color, width=2),
                                name=legend_name,
                                legendgroup=f'cluster_{prev_seg}',
                                showlegend=show_legend,
                                hovertemplate=(
                                    f'<b>Cluster {prev_seg}</b><br>'
                                    f'Distance: %{{x:.2f}} km<br>'
                                    f'Altitude: %{{y:.0f}} m<br>'
                                    f'Avg Gradient: {avg_grad:+.1f}%<extra></extra>'
                                )
                            ),
                            row=1, col=1
                        )
                    
                    # Start new run
                    run_start_idx = i
                    prev_seg = seg_id
            
            # Plot the last run
            if prev_seg is not None and len(df_sorted) > run_start_idx:
                run_dist = cum_dist_km.iloc[run_start_idx:]
                run_alt = altitude.iloc[run_start_idx:]
                
                color = segment_colors[prev_seg]
                fill_color = hex_to_rgba(color, 0.4) if color.startswith('#') else color
                
                run_mask = df_sorted.index >= run_start_idx
                avg_grad = df_sorted.loc[run_mask, 'gradient'].mean()
                
                show_legend = prev_seg not in legend_added
                if show_legend:
                    legend_added.add(prev_seg)
                
                legend_name = f'Cluster {prev_seg}'
                
                fig.add_trace(
                    go.Scatter(
                        x=run_dist,
                        y=run_alt,
                        mode='lines',
                        fill='tozeroy',
                        fillcolor=fill_color,
                        line=dict(color=color, width=2),
                        name=legend_name,
                        legendgroup=f'cluster_{prev_seg}',
                        showlegend=show_legend,
                        hovertemplate=(
                            f'<b>Cluster {prev_seg}</b><br>'
                            f'Distance: %{{x:.2f}} km<br>'
                            f'Altitude: %{{y:.0f}} m<br>'
                            f'Avg Gradient: {avg_grad:+.1f}%<extra></extra>'
                        )
                    ),
                    row=1, col=1
                )
        else:
            # For contiguous methods (terrain, equal), use simple approach
            # Track which terrain types or segment colors we've shown in legend
            terrain_legend_added = set()
            
            for i, seg_id in enumerate(unique_segments):
                seg_mask = df_sorted['segment'] == seg_id
                seg_indices = df_sorted.index[seg_mask]
                
                if len(seg_indices) == 0:
                    continue
                
                start_idx = seg_indices[0]
                end_idx = seg_indices[-1] + 1
                
                seg_dist = cum_dist_km.iloc[start_idx:end_idx]
                seg_alt = altitude.iloc[start_idx:end_idx]
                
                color = segment_colors[seg_id]
                fill_color = hex_to_rgba(color, 0.4) if color.startswith('#') else color
                
                # Calculate segment stats
                avg_grad = df_sorted.loc[seg_mask, 'gradient'].mean()
                seg_distance = df_sorted.loc[seg_mask, 'distance'].sum() / 1000
                
                if use_terrain_colors:
                    # For terrain-based: group legend by terrain type, not segment ID
                    terrain = df_sorted.loc[seg_mask, 'segment_terrain'].iloc[0]
                    legend_name = terrain.capitalize()
                    legend_group = f'terrain_{terrain}'
                    show_legend = terrain not in terrain_legend_added
                    if show_legend:
                        terrain_legend_added.add(terrain)
                else:
                    # For equal segments: show each segment in legend
                    legend_name = f'Segment {seg_id}'
                    legend_group = f'seg_{seg_id}'
                    show_legend = True
                
                fig.add_trace(
                    go.Scatter(
                        x=seg_dist,
                        y=seg_alt,
                        mode='lines',
                        fill='tozeroy',
                        fillcolor=fill_color,
                        line=dict(color=color, width=2),
                        name=legend_name,
                        legendgroup=legend_group,
                        showlegend=show_legend,
                        hovertemplate=(
                            f'<b>Segment {seg_id}</b><br>'
                            f'Distance: %{{x:.2f}} km<br>'
                            f'Altitude: %{{y:.0f}} m<br>'
                            f'Avg Gradient: {avg_grad:+.1f}%<br>'
                            f'Segment Length: {seg_distance:.2f} km<extra></extra>'
                        )
                    ),
                    row=1, col=1
                )
                
                # Add segment boundary line (except for first segment)
                if seg_id > 0 and len(seg_dist) > 0:
                    fig.add_vline(
                        x=seg_dist.iloc[0],
                        line=dict(color='black', width=1, dash='dash'),
                        opacity=0.3,
                        row=1, col=1
                    )
        
        # Add segment bar if requested
        if show_segment_bar:
            if method == 'clustering':
                # For clustering, show each contiguous run as a separate bar
                prev_seg = None
                run_start_idx = 0
                
                for i in range(len(df_sorted)):
                    seg_id = df_sorted['segment'].iloc[i]
                    
                    if seg_id != prev_seg:
                        if prev_seg is not None and i > run_start_idx:
                            # Add bar for the previous run
                            run_start = cum_dist_km.iloc[run_start_idx]
                            run_end = cum_dist_km.iloc[i - 1]
                            color = segment_colors[prev_seg]
                            
                            run_mask = (df_sorted.index >= run_start_idx) & (df_sorted.index < i)
                            avg_grad = df_sorted.loc[run_mask, 'gradient'].mean()
                            
                            fig.add_trace(
                                go.Bar(
                                    x=[(run_start + run_end) / 2],
                                    y=[1],
                                    width=[max(run_end - run_start, 0.05)],
                                    marker_color=color,
                                    opacity=0.8,
                                    showlegend=False,
                                    hovertemplate=(
                                        f'<b>Seg {prev_seg}</b><br>'
                                        f'{avg_grad:+.1f}%<extra></extra>'
                                    ),
                                    text=str(prev_seg),
                                    textposition='inside',
                                    textfont=dict(size=8, color='white')
                                ),
                                row=2, col=1
                            )
                        run_start_idx = i
                        prev_seg = seg_id
                
                # Add bar for the last run
                if prev_seg is not None and len(df_sorted) > run_start_idx:
                    run_start = cum_dist_km.iloc[run_start_idx]
                    run_end = cum_dist_km.iloc[-1]
                    color = segment_colors[prev_seg]
                    
                    run_mask = df_sorted.index >= run_start_idx
                    avg_grad = df_sorted.loc[run_mask, 'gradient'].mean()
                    
                    fig.add_trace(
                        go.Bar(
                            x=[(run_start + run_end) / 2],
                            y=[1],
                            width=[max(run_end - run_start, 0.05)],
                            marker_color=color,
                            opacity=0.8,
                            showlegend=False,
                            hovertemplate=(
                                f'<b>Seg {prev_seg}</b><br>'
                                f'{avg_grad:+.1f}%<extra></extra>'
                            ),
                            text=str(prev_seg),
                            textposition='inside',
                            textfont=dict(size=8, color='white')
                        ),
                        row=2, col=1
                    )
            else:
                # For contiguous methods, use simple approach
                for i, seg_id in enumerate(unique_segments):
                    seg_mask = df_sorted['segment'] == seg_id
                    seg_indices = df_sorted.index[seg_mask]
                    
                    if len(seg_indices) == 0:
                        continue
                    
                    seg_start = cum_dist_km.iloc[seg_indices[0]]
                    seg_end = cum_dist_km.iloc[seg_indices[-1]]
                    
                    color = segment_colors[seg_id]
                    avg_grad = df_sorted.loc[seg_mask, 'gradient'].mean()
                    
                    fig.add_trace(
                        go.Bar(
                            x=[(seg_start + seg_end) / 2],
                            y=[1],
                            width=[seg_end - seg_start],
                            marker_color=color,
                            opacity=0.8,
                            showlegend=False,
                            hovertemplate=(
                                f'<b>Seg {seg_id}</b><br>'
                                f'{avg_grad:+.1f}%<extra></extra>'
                            ),
                            text=f'{seg_id}<br>{avg_grad:+.1f}%',
                            textposition='inside',
                            textfont=dict(size=10, color='white')
                        ),
                        row=2, col=1
                    )
        
        # Update layout
        title = title or f'Course Segmentation ({method.title()} Method) - {n_segments} Segments'
        
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center'),
            height=height,
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='center',
                x=0.5
            ),
            hovermode='x unified'
        )
        
        fig.update_xaxes(title_text='Distance (km)', row=2 if show_segment_bar else 1, col=1)
        fig.update_yaxes(title_text='Altitude (m)', row=1, col=1)
        
        if show_segment_bar:
            fig.update_yaxes(visible=False, row=2, col=1)
            fig.update_xaxes(matches='x', row=2, col=1)
        
        return fig
    
    def plot_segmentation_map(self,
                               df: pd.DataFrame = None,
                               method: str = 'terrain',
                               title: str = None,
                               height: int = 500) -> go.Figure:
        """
        Create Plotly map view of course colored by segment.
        
        Args:
            df: DataFrame with segment assignments (uses self.df if None)
            method: 'terrain', 'equal', or 'clustering' - affects coloring and display mode
            title: Plot title (auto-generated if None)
            height: Figure height in pixels
        
        Returns:
            Plotly Figure object
        """
        if df is None:
            df = self.df.copy()
        
        df_sorted = df.sort_values('cumulative_distance').reset_index(drop=True)
        unique_segments = sorted(df_sorted['segment'].unique())
        n_segments = len(unique_segments)
        
        # Determine color scheme
        if method == 'terrain' and 'segment_terrain' in df_sorted.columns:
            use_terrain_colors = True
        else:
            use_terrain_colors = False
        
        # For clustering method, segments are non-contiguous so we use markers only
        # For terrain/equal, segments are contiguous so we can use lines
        use_lines = method != 'clustering'
        
        fig = go.Figure()
        
        # Add base route line first (gray, thin) to show full course path
        fig.add_trace(
            go.Scattermapbox(
                lat=df_sorted['lat'],
                lon=df_sorted['lon'],
                mode='lines',
                line=dict(color='gray', width=2),
                name='Route',
                hoverinfo='skip',
                showlegend=False
            )
        )
        
        # Plot each segment
        for i, seg_id in enumerate(unique_segments):
            seg_mask = df_sorted['segment'] == seg_id
            seg_data = df_sorted[seg_mask]
            
            if len(seg_data) == 0:
                continue
            
            # Determine color
            if use_terrain_colors:
                terrain = seg_data['segment_terrain'].iloc[0]
                color = TERRAIN_COLORS.get(terrain, SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)])
                legend_name = f'Seg {seg_id} ({terrain})'
            else:
                color = SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)]
                legend_name = f'Segment {seg_id}'
            
            avg_grad = seg_data['gradient'].mean()
            seg_distance = seg_data['distance'].sum() / 1000
            
            if use_lines:
                # For contiguous segments (terrain/equal), draw lines connecting points
                # Need to plot each contiguous run separately
                seg_indices = seg_data.index.tolist()
                
                # Find contiguous runs within this segment
                runs = []
                current_run = [seg_indices[0]]
                for j in range(1, len(seg_indices)):
                    if seg_indices[j] == seg_indices[j-1] + 1:
                        current_run.append(seg_indices[j])
                    else:
                        runs.append(current_run)
                        current_run = [seg_indices[j]]
                runs.append(current_run)
                
                # Plot each contiguous run
                for run_idx, run in enumerate(runs):
                    run_data = df_sorted.loc[run]
                    fig.add_trace(
                        go.Scattermapbox(
                            lat=run_data['lat'],
                            lon=run_data['lon'],
                            mode='lines+markers',
                            line=dict(color=color, width=4),
                            marker=dict(size=4, color=color),
                            name=legend_name if run_idx == 0 else None,
                            showlegend=(run_idx == 0),
                            legendgroup=f'seg_{seg_id}',
                            hovertemplate=(
                                f'<b>Segment {seg_id}</b><br>'
                                f'Lat: %{{lat:.5f}}<br>'
                                f'Lon: %{{lon:.5f}}<br>'
                                f'Avg Gradient: {avg_grad:+.1f}%<br>'
                                f'Segment Length: {seg_distance:.2f} km<extra></extra>'
                            )
                        )
                    )
            else:
                # For non-contiguous segments (clustering), use markers only
                fig.add_trace(
                    go.Scattermapbox(
                        lat=seg_data['lat'],
                        lon=seg_data['lon'],
                        mode='markers',
                        marker=dict(size=6, color=color),
                        name=legend_name,
                        hovertemplate=(
                            f'<b>Segment {seg_id}</b><br>'
                            f'Lat: %{{lat:.5f}}<br>'
                            f'Lon: %{{lon:.5f}}<br>'
                            f'Avg Gradient: {avg_grad:+.1f}%<br>'
                            f'Segment Length: {seg_distance:.2f} km<extra></extra>'
                        )
                    )
                )
        
        # Calculate map center and zoom
        center_lat = df_sorted['lat'].mean()
        center_lon = df_sorted['lon'].mean()
        
        # Estimate zoom level based on coordinate range
        lat_range = df_sorted['lat'].max() - df_sorted['lat'].min()
        lon_range = df_sorted['lon'].max() - df_sorted['lon'].min()
        max_range = max(lat_range, lon_range)
        
        if max_range < 0.01:
            zoom = 15
        elif max_range < 0.05:
            zoom = 13
        elif max_range < 0.1:
            zoom = 12
        elif max_range < 0.5:
            zoom = 10
        else:
            zoom = 8
        
        title = title or f'Course Map ({method.title()} Method) - {n_segments} Segments'
        
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center'),
            height=height,
            mapbox=dict(
                style='open-street-map',
                center=dict(lat=center_lat, lon=center_lon),
                zoom=zoom
            ),
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='center',
                x=0.5
            ),
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        return fig
    
    def plot_segmentation_combined(self,
                                    df: pd.DataFrame = None,
                                    method: str = 'terrain',
                                    title: str = None,
                                    height: int = 800) -> go.Figure:
        """
        Create combined view with map and elevation profile.
        
        Args:
            df: DataFrame with segment assignments (uses self.df if None)
            method: 'terrain', 'equal', or 'clustering' - affects coloring
            title: Plot title (auto-generated if None)
            height: Total figure height in pixels
        
        Returns:
            Plotly Figure object
        """
        if df is None:
            df = self.df.copy()
        
        df_sorted = df.sort_values('cumulative_distance').reset_index(drop=True)
        cum_dist_km = df_sorted['cumulative_distance'] / 1000
        altitude = df_sorted['altitude']
        unique_segments = sorted(df_sorted['segment'].unique())
        n_segments = len(unique_segments)
        
        # Determine color scheme
        if method == 'terrain' and 'segment_terrain' in df_sorted.columns:
            use_terrain_colors = True
        else:
            use_terrain_colors = False
        
        # Create figure with two subplots side by side
        fig = make_subplots(
            rows=1, cols=2,
            column_widths=[0.5, 0.5],
            specs=[[{"type": "scattermapbox"}, {"type": "xy"}]],
            horizontal_spacing=0.05
        )
        
        # Add traces for each segment
        for i, seg_id in enumerate(unique_segments):
            seg_mask = df_sorted['segment'] == seg_id
            seg_data = df_sorted[seg_mask]
            seg_indices = df_sorted.index[seg_mask]
            
            if len(seg_data) == 0:
                continue
            
            start_idx = seg_indices[0]
            end_idx = seg_indices[-1] + 1
            
            # Determine color
            if use_terrain_colors:
                terrain = seg_data['segment_terrain'].iloc[0]
                color = TERRAIN_COLORS.get(terrain, SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)])
                legend_name = f'Seg {seg_id} ({terrain})'
            else:
                color = SEGMENT_COLORSCALE[i % len(SEGMENT_COLORSCALE)]
                legend_name = f'Segment {seg_id}'
            
            avg_grad = seg_data['gradient'].mean()
            seg_distance = seg_data['distance'].sum() / 1000
            
            # Map trace
            fig.add_trace(
                go.Scattermapbox(
                    lat=seg_data['lat'],
                    lon=seg_data['lon'],
                    mode='lines+markers',
                    line=dict(color=color, width=4),
                    marker=dict(size=3, color=color),
                    name=legend_name,
                    legendgroup=f'seg_{seg_id}',
                    hovertemplate=(
                        f'<b>Segment {seg_id}</b><br>'
                        f'Lat: %{{lat:.5f}}<br>'
                        f'Lon: %{{lon:.5f}}<extra></extra>'
                    )
                ),
                row=1, col=1
            )
            
            # Elevation profile trace
            seg_dist = cum_dist_km.iloc[start_idx:end_idx]
            seg_alt = altitude.iloc[start_idx:end_idx]
            
            # Convert color to rgba for fill
            fill_color = hex_to_rgba(color, 0.4) if color.startswith('#') else color
            
            fig.add_trace(
                go.Scatter(
                    x=seg_dist,
                    y=seg_alt,
                    mode='lines',
                    fill='tozeroy',
                    fillcolor=fill_color,
                    line=dict(color=color, width=2),
                    name=legend_name,
                    legendgroup=f'seg_{seg_id}',
                    showlegend=False,
                    hovertemplate=(
                        f'<b>Segment {seg_id}</b><br>'
                        f'Distance: %{{x:.2f}} km<br>'
                        f'Altitude: %{{y:.0f}} m<br>'
                        f'Avg Gradient: {avg_grad:+.1f}%<extra></extra>'
                    )
                ),
                row=1, col=2
            )
        
        # Calculate map center and zoom
        center_lat = df_sorted['lat'].mean()
        center_lon = df_sorted['lon'].mean()
        lat_range = df_sorted['lat'].max() - df_sorted['lat'].min()
        lon_range = df_sorted['lon'].max() - df_sorted['lon'].min()
        max_range = max(lat_range, lon_range)
        
        if max_range < 0.01:
            zoom = 15
        elif max_range < 0.05:
            zoom = 13
        elif max_range < 0.1:
            zoom = 12
        elif max_range < 0.5:
            zoom = 10
        else:
            zoom = 8
        
        title = title or f'Course Segmentation ({method.title()}) - {n_segments} Segments'
        
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center'),
            height=height,
            mapbox=dict(
                style='open-street-map',
                center=dict(lat=center_lat, lon=center_lon),
                zoom=zoom
            ),
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='center',
                x=0.5
            )
        )
        
        fig.update_xaxes(title_text='Distance (km)', row=1, col=2)
        fig.update_yaxes(title_text='Altitude (m)', row=1, col=2)
        
        return fig


class CourseSegmentation:
    def __init__(
        self, data, 
        smoothing_window=11, 
        poly_order=2, 
        distance_threshold=5.0, 
        linkage='complete',
        gradient_min=-1.0, 
        gradient_max=1.0,
        weight_dict=None
    ):
        self.data = data.copy()
        self.weight_dict = weight_dict if weight_dict is not None else {
            'thresholds': [2, -2],
            'weights': [(0.3, 0.7), (0.5, 0.5), (0.8, 0.2)]
        }
        self.smoothing_window = smoothing_window
        self.poly_order = poly_order
        self.distance_threshold = distance_threshold
        self.linkage = linkage
        self.gradient_min = gradient_min
        self.gradient_max = gradient_max

        self.smoothed_data = self.smooth_data()
        self.labels = None

    def smooth_data(self):
        smoothed = self.data.copy()
        for col in ['gradient', 'heading', 'altitude']:
            if col in smoothed.columns:
                smoothed[col] = savgol_filter(
                    smoothed[col], 
                    self.smoothing_window, 
                    self.poly_order
                )
        return smoothed

    @staticmethod
    def _compute_angular_distance(h1, h2):
        diff = abs(h1 - h2) % 360
        return min(diff, 360 - diff)

    def _normalize_heading_diff(self, h1, h2):
        ang_dist = self._compute_angular_distance(h1, h2)
        return ang_dist / 180.0  # range [0..1]

    def _normalize_gradient(self, g):
        return (g - self.gradient_min) / (self.gradient_max - self.gradient_min)

    def _compute_custom_distance(self, point_a, point_b):
        heading_a, grad_a = point_a
        heading_b, grad_b = point_b

        # Normalized heading difference
        heading_diff_norm = self._normalize_heading_diff(heading_a, heading_b)

        # Normalized gradient difference
        ga_norm = self._normalize_gradient(grad_a)
        gb_norm = self._normalize_gradient(grad_b)
        grad_diff_norm = abs(ga_norm - gb_norm)

        # Weighting based on avg gradient (actual slope, not normalized)
        avg_grad = (grad_a + grad_b) / 2.0

        thresholds = self.weight_dict['thresholds']
        weights = self.weight_dict['weights']

        if avg_grad > thresholds[0]:
            #climbing scenario
            w_heading, w_gradient = weights[0]
        elif avg_grad < thresholds[1]:
            #descending scenario
            w_heading, w_gradient = weights[1]
        else:
            #flat scenario
            w_heading, w_gradient = weights[2]

        return w_heading * heading_diff_norm + w_gradient * grad_diff_norm

    def cluster_course_segments(self):
        if not all(col in self.smoothed_data.columns for col in ['heading', 'gradient']):
            raise ValueError("Data must contain 'heading' and 'gradient' columns.")

        data_points = self.smoothed_data[['heading', 'gradient']].values
        
        dist_matrix = squareform(
            pdist(data_points, metric=lambda u, v: self._compute_custom_distance(u, v))
        )

        clusterer = AgglomerativeClustering(
            affinity='precomputed',
            linkage=self.linkage,
            distance_threshold=self.distance_threshold,
            n_clusters=None
        )
        self.labels = clusterer.fit_predict(dist_matrix)
        self.data['segment'] = self.labels
        self.aggregate_segments()  # Call the aggregation method
        return self.labels

    def plot_segments(self, save_plots=False, show_plot=True,  file="CourseSegmentation"):
        if self.labels is None:
            print("No clusters found. Please run 'cluster_course_segments()' first.")
            return

        fig = plt.figure(figsize=(14, 8))
        gs = fig.add_gridspec(2, 2, height_ratios=[3, 1])

        # First subplot: distance vs altitude
        ax1 = fig.add_subplot(gs[0, 0])
        if 'distance' in self.data.columns and 'altitude' in self.data.columns:
            for label in np.unique(self.labels):
                seg_data = self.data[self.data['segment'] == label]
                ax1.scatter(seg_data['cumulative_distance'], seg_data['altitude'], label=f"Seg {int(label)}",s=len(self.data)/100)
            ax1.set_xlabel("Distance")
            ax1.set_ylabel("Altitude")
            ax1.set_title(f"Segments: {len(np.unique(self.labels))}")
        else:
            ax1.text(0.5, 0.5, 'No distance/altitude columns', ha='center')

        # Second subplot: lat vs lon
        ax2 = fig.add_subplot(gs[0, 1])
        if all(col in self.data.columns for col in ['lat', 'lon']):
            for label in np.unique(self.labels):
                seg_data = self.data[self.data['segment'] == label]
                ax2.scatter(seg_data['lon'], seg_data['lat'], label=f"Seg {int(label)}", s=len(self.data)/100)
            ax2.set_xlabel("Longitude")
            ax2.set_ylabel("Latitude")
            ax2.set_aspect('equal')
            ax2.set_title("Course Layout by Segments")
        else:
            ax2.text(0.5, 0.5, 'No lat/lon columns', ha='center')

        # Third subplot: text block
        ax3 = fig.add_subplot(gs[1, :])
        ax3.axis('off')
        text = (f"Course: {''.join(file)}\n"
                f"Thresholds: {self.weight_dict['thresholds']}\nWeights: {self.weight_dict['weights']}\n"
                f"Segment number of rows: {len(self.data)} | Average distance between points: {np.mean(self.data['distance']):.0f} (m)")
        ax3.text(0.5, 0.5, text, ha='center', va='center', fontsize=12)

        plt.tight_layout()
        if save_plots:
            number_of_segments = len(np.unique(self.labels))
            plt.savefig(f"ref_plots/{file}_sw{self.smoothing_window}_po{self.poly_order}_dt{self.distance_threshold}_numsegments{number_of_segments}.png")
        
        if show_plot:
            plt.show()