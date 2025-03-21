import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os


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
                df = compute_heading_from_latlon(df)
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