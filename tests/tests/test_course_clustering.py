import numpy as np
import pandas as pd

from app.course import Course


def _processed_course(gradients, bearings, point_distance=25.0):
    gradients = np.asarray(gradients, dtype=float)
    bearings = np.asarray(bearings, dtype=float)
    distances = np.full(len(gradients), point_distance)
    altitude = 100.0 + np.cumsum(gradients / 100.0 * distances)
    elevation_delta = np.diff(altitude, prepend=altitude[0])
    return Course(pd.DataFrame({
        'lat': np.linspace(47.5, 47.6, len(gradients)),
        'lon': np.linspace(-122.3, -122.2, len(gradients)),
        'altitude': altitude,
        'gradient': gradients,
        'bearing': bearings,
        'distance': distances,
        'cumulative_distance': np.cumsum(distances),
        'height_gain': np.maximum(elevation_delta, 0.0),
        'height_loss': np.maximum(-elevation_delta, 0.0),
    }), skip_processing=True)


def _recurring_terrain_course():
    rng = np.random.default_rng(42)
    terrain_blocks = [-6.0, 0.0, 4.0, 9.0, 0.0, -6.0, 4.0, 9.0]
    gradients = np.concatenate([
        rng.normal(grade, 0.25, 40) for grade in terrain_blocks
    ])
    bearings = np.concatenate([
        np.full(40, bearing)
        for bearing in [20, 90, 180, 270, 20, 90, 180, 270]
    ])
    return _processed_course(gradients, bearings)


def test_clustering_finds_recurring_ordered_terrain_types():
    course = _recurring_terrain_course()
    preview = course.preview_clustering_segmentation(
        max_clusters=4,
        gradient_weight=0.8,
        bearing_weight=0.2,
        smoothing_distance=75,
        min_segment_distance=200,
        gradient_clip=12,
    )

    summary = preview.groupby('segment').agg(
        mean_grade=('gradient_smoothed', 'mean'),
        distance=('distance', 'sum'),
    )
    run_ids = preview['segment'].ne(preview['segment'].shift()).cumsum()
    run_counts = preview.groupby(run_ids)['segment'].first().value_counts()

    assert preview['segment'].nunique() == 4
    assert summary['mean_grade'].is_monotonic_increasing
    assert summary['distance'].min() >= 1500
    assert (run_counts >= 2).all()


def test_preview_and_apply_use_identical_clustering():
    course = _recurring_terrain_course()
    original_columns = set(course.df.columns)
    params = dict(
        max_clusters=4,
        gradient_weight=0.8,
        bearing_weight=0.2,
        smoothing_distance=75,
        min_segment_distance=200,
        gradient_clip=12,
    )

    preview = course.preview_clustering_segmentation(**params)
    assert set(course.df.columns) == original_columns

    course.auto_segmentation(**params)
    pd.testing.assert_series_equal(
        preview['segment'], course.df['segment'], check_names=False)
    pd.testing.assert_series_equal(
        preview['segment_terrain'],
        course.df['segment_terrain'],
        check_names=False,
    )


def test_bearing_smoothing_is_circular_at_north():
    north = np.tile([359.0, 1.0], 50)
    south = np.tile([179.0, 181.0], 50)
    course = _processed_course(
        gradients=np.zeros(200),
        bearings=np.concatenate([north, south]),
    )

    preview = course.preview_clustering_segmentation(
        max_clusters=2,
        gradient_weight=0.0,
        bearing_weight=1.0,
        smoothing_distance=75,
        min_segment_distance=0,
        gradient_clip=12,
    )

    north_bearings = preview.loc[10:80, 'bearing_smoothed']
    north_distance = np.minimum(north_bearings, 360.0 - north_bearings)
    assert north_distance.max() < 2.0
    assert preview['segment'].nunique() == 2