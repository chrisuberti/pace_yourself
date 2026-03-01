"""Debug script: diagnose variable pacing issues with clustering segmentation."""
import pandas as pd
import numpy as np
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.course import Course
from app.optimization import create_course_segments_from_course, CourseOptimizer

# Create a synthetic Hawk Hill-like course for reproducible testing
np.random.seed(42)
n_points = 200
total_dist = 3000  # 3km hill climb
cum_dist = np.linspace(0, total_dist, n_points)
dist = np.diff(cum_dist, prepend=0)
# Mostly uphill with some flatter sections
gradient_base = 6.0 + 3.0 * np.sin(cum_dist / total_dist * 4 * np.pi)  # 3-9% 
gradient = gradient_base + np.random.normal(0, 1.0, n_points)
bearing = np.cumsum(np.random.normal(0, 5, n_points)) % 360
bearing_change = np.diff(bearing, prepend=bearing[0])
altitude = np.cumsum(gradient / 100 * dist)
df = pd.DataFrame({
    'lat': np.linspace(37.83, 37.84, n_points),
    'lon': np.linspace(-122.50, -122.49, n_points),
    'altitude': altitude,
    'gradient': gradient,
    'bearing': bearing,
    'bearing_change': bearing_change,
    'distance': dist,
    'cumulative_distance': cum_dist,
    'height_gain': np.where(gradient > 0, gradient / 100 * dist, 0),
    'height_loss': np.where(gradient < 0, abs(gradient) / 100 * dist, 0),
})
print(f'Synthetic course: {df["cumulative_distance"].iloc[-1]/1000:.1f}km, '
      f'gradient range: [{df["gradient"].min():.1f}%, {df["gradient"].max():.1f}%]')

course = Course(df)
course.auto_segmentation(max_clusters=6)
course.enable_enhanced_segmentation()

segs = course.course_segments
print(f'\nClustering => {len(segs)} sequence segments, '
      f'{len(segs["segment_id"].unique())} clusters')
for cid in sorted(segs['segment_id'].unique()):
    mask = segs['segment_id'] == cid
    grads = segs.loc[mask, 'gradient_mean']
    dists = segs.loc[mask, 'distance_sum']
    print(f'  Cluster {cid}: mean_grad={grads.mean():+.2f}%, '
          f'total_dist={dists.sum():.3f}km, n_segs={mask.sum()}')

opt_segs = create_course_segments_from_course(course)
print(f'\nOpt segments: {len(opt_segs)}, '
      f'gradient range: [{opt_segs["gradient"].min():.4f}, {opt_segs["gradient"].max():.4f}]')

# Check effort/recovery classification
effort_threshold = -0.005
cluster_grads = {}
for cid in sorted(opt_segs['segment_id'].unique()):
    mask = opt_segs['segment_id'] == cid
    mg = opt_segs.loc[mask, 'gradient'].mean()
    cluster_grads[cid] = mg
    print(f'  Cluster {cid}: mean_grad={mg:+.4f} '
          f'=> {"EFFORT" if mg > effort_threshold else "recovery"}')

print(f'\nAll clusters EFFORT: {all(g > effort_threshold for g in cluster_grads.values())}')
print(f'Gradient std across clusters: {np.std(list(cluster_grads.values())):.4f}')
print(f'Median cluster gradient: {np.median(list(cluster_grads.values())):.4f}')

# Now run both optimizations and compare
CP, WPRIME = 300, 25000
optimizer = CourseOptimizer(critical_power=CP, w_prime=WPRIME)

print('\n' + '='*60)
print('CONSTANT POWER OPTIMIZATION')
const_power, const_time, const_df = optimizer.optimize_constant_power(opt_segs, target_w_utilization=0.85)
print(f'Constant: {const_power:.0f}W, time={const_time/60:.2f}min')

print('\n' + '='*60)
print('VARIABLE PACING OPTIMIZATION')
# Match W' utilization from constant
_, _, const_w_rem, _ = optimizer.simulate_course_time(const_power, opt_segs)
matched_util = 1 - (const_w_rem / WPRIME)
print(f'Matched W util: {matched_util:.2%}')

var_df, var_time, var_analysis = optimizer.optimize_variable_pacing(
    opt_segs, target_w_utilization=matched_util, aggressive_factor=1.2)

print(f'\nVariable: time={var_time/60:.2f}min')
print(f'Power range: [{var_df["target_power"].min():.0f}, {var_df["target_power"].max():.0f}]W')
print(f'All powers above constant ({const_power:.0f}W): '
      f'{(var_df["target_power"] > const_power).all()}')
print(f'Powers above CP ({CP}W): {(var_df["target_power"] > CP).sum()}/{len(var_df)}')
print(f'\nPer-segment powers:')
for _, row in var_df.iterrows():
    print(f'  grad={row.get("gradient", "?")*100:+.1f}%, '
          f'power={row["target_power"]:.0f}W, '
          f'w_remaining={row.get("w_remaining", "?")}')
