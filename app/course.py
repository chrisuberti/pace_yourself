import pandas as pd
import numpy as np
from scipy.signal import savgol_filter
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import AgglomerativeClustering
import matplotlib.pyplot as plt
import os
from dotenv import load_dotenv
import os
load_dotenv()
route_path = os.getenv('ROUTE_PATH')

class Course:
    def __init__(self, df, skip_processing: bool = False):
        """
        Initialize a Course object.
        
        Args:
            df: DataFrame with GPS data (lat, lon, altitude at minimum)
            skip_processing: If True, assume df is already processed (has gradient, 
                           cumulative_distance, etc.). Used when loading from database.
        """
        self.df = df.copy()
        
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
        # Use adaptive window based on point density - target ~50m of distance for smoothing
        avg_point_spacing = self.df["distance"].median()
        if avg_point_spacing > 0:
            # Target 50m smoothing window, minimum 5 points, maximum 51 points
            target_points = max(5, min(51, int(50 / avg_point_spacing)))
            # Window must be odd
            window_length = target_points if target_points % 2 == 1 else target_points + 1
        else:
            window_length = 21
        
        # Apply Savitzky-Golay filter for smooth altitude
        if window_length >= 5 and len(self.df) >= window_length:
            self.df["altitude_smoothed"] = savgol_filter(
                self.df["altitude"].ffill().bfill(), 
                window_length=window_length, 
                polyorder=2
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
        
        # Clamp gradient to realistic values (±30% is extremely steep - steeper than most paved roads)
        max_gradient = 30.0  # percentage
        self.df['gradient'] = self.df['gradient'].clip(lower=-max_gradient, upper=max_gradient)


    def calculate_bearing(self):
        """
        Calculate the compass bearing between consecutive points in the DataFrame.
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

    def bearing_to_cardinal(self):
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = ((self.df["bearing"] + 11.25) / 22.5).astype(int)
        self.df["cardinal"] = idx.apply(lambda x: directions[x % 16])

    def equal_segmentation(self, n):
        """Divide the course into equal segments based on distance."""
        self.df['segment'] = pd.cut(self.df['cumulative_distance'], bins=n, labels=False)+1
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
        if hasattr(self, 'course_segments'):
            delattr(self, 'course_segments')
        if hasattr(self, 'course_segments_aggregated'):
            delattr(self, 'course_segments_aggregated')
        
        def normalize_bearing(bearing):
            """Normalize bearing to handle circularity (e.g., 359 is close to 0)."""
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

        # Aggregate segments
        self.aggregate_segments()


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