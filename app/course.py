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
    def __init__(self, df):
        self.df = df.copy()
        self.process_segment()
        self.calculate_bearing()
        #self.bearing_to_cardinal()

    def process_segment(self):
        print('running process segment')
        self.df["lat"] = self.df["lat"].astype(float)
        self.df["lon"] = self.df["lon"].astype(float)
        self.df["altitude"] = self.df["altitude"].astype(float)
        # Calculate the net distance between a pair of lat/lon points
        self.df["delta_lat"] = self.df["lat"].diff()
        self.df["delta_lon"] = self.df["lon"].diff()
        self.df["distance"] = (self.df["delta_lat"]**2 + self.df["delta_lon"]**2)**0.5
        self.df["distance"] = self.df["distance"].fillna(0)
        # Convert the lat/lon distance to meters
        self.df["distance"] = self.df["distance"] * 111139
        # Calculate the cumulative distance
        self.df["cumulative_distance"] = self.df["distance"].cumsum()
        # Calculate the gradient between two points
        self.df["delta_altitude"] = self.df["altitude"].diff()
        self.df["height_gain"] = self.df["delta_altitude"].clip(lower=0)
        self.df["height_loss"] = -self.df["delta_altitude"].clip(upper=0)
        # Handle inf values in the gradient and set them to zero
        self.df["gradient"] = (self.df["delta_altitude"] / self.df["distance"]) * 100
        self.df["gradient"] = self.df["gradient"].fillna(0)
        self.df['gradient'] = self.df['gradient'].replace([np.inf, -np.inf], 0)


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
        self.df["bearing"].fillna(0, inplace=True)  # Handle NaN for the last row

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
        """Aggregate segment data to calculate summary statistics."""
        self.course_segments = self.df.groupby('segment').agg({
            'lat': 'mean',
            'lon': 'mean',
            'bearing': 'mean',
            'altitude': ['mean', 'min', 'max'],
            'gradient': 'mean',
            'height_gain': 'sum',
            'height_loss': 'sum',
            'distance': 'sum'
        }).reset_index()
        #flatten multiindex columns
        self.course_segments.columns = ['_'.join(col).strip() for col in self.course_segments.columns.values]
        self.course_segments.rename(columns={'segment_': 'segment'}, inplace=True)
        #Convert distance to km instead of m
        self.course_segments['distance_sum'] = self.course_segments['distance_sum'] / 1000
        self.course_segments['gradient_mean'] = self.course_segments['gradient_mean'] * 100
        self.course_segments['gradient_mean'] = self.course_segments['gradient_mean'].round(2)
        self.course_segments.drop(columns = ['lat_mean', 'lon_mean'], inplace=True)
        self.course_segments.dropna(inplace=True)

    def smooth_data(self, df_col, window_size=5):
        return (
            df_col
            .rolling(window=window_size, center=True)
            .mean()
            .fillna(method='bfill')  # Fill the start of the DataFrame
            .fillna(method='ffill')  # Fill the end of the DataFrame
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

        # Smooth gradient and bearing columns
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



if __name__ == "__main__":

    
    for file in os.listdir():
        try:
            if file.endswith(".csv"):
                print(file)

                df = pd.read_csv(file)
                df = calculate_bearing(df)
                #normalize the gradient to below 1 breaks this a little bit
                #df['gradient'] = df['gradient']/100
                #print(df.head(2))


                weight_dict = {
                    'thresholds': [2, -2],
                    #climbing weight, descending weight, flat weight
                    'weights': [(0.1, 1.8), (0.5, 1), (1.8, 0.1)]
                }

                segmenter = CourseSegmentation(
                    data=df,
                    smoothing_window=68,    # smaller window for demonstration
                    poly_order=2,
                    distance_threshold=10.0, 
                    linkage='complete',
                    gradient_min=-0.3,     # match the extremes in this example
                    gradient_max=0.35,
                    weight_dict=weight_dict
                )

                labels = segmenter.cluster_course_segments()

                #print("Labels:", labels)
                print("Unique clusters found:", np.unique(labels))
                
                segmenter.plot_segments(save_plots=True, show_plot = False, file=file.split(".")[0])

        except PermissionError:
            pass


'''
v1 best hyperparameters:
smoothing_window=70,
poly_order=2,
distance_threshold=10.0,


I thin the possible short coming of this is that each course has a different number of points and thus there might be a LOT more segments if the course is longer.
Want to avoid this somehow.......possibly measure the average distance beteween points and then use that to determine the smoothing window?
or could use size of the course to determine the smoothing window, i.e. number of rows in the dataframe


Ok one issue now is that we're really not changing segments based on heading, we're changing based on gradient. 
This is not what we want. We want to change based on heading in addition 


'''