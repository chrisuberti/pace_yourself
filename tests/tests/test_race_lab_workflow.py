"""Focused regressions for Race Lab navigation and durable result state."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from pages_vibe.tabs import (
    _charts,
    _workflow,
    tab_course,
    tab_optimization,
    tab_segmentation,
)
from pages_vibe.tabs.state import RIDER_DEFAULTS, SESSION_DEFAULTS
from app.course import Course
from app.starter_courses import (
    STARTER_COURSES,
    build_starter_course_frame,
    get_starter_course,
)


class _State(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as error:
            raise AttributeError(key) from error

    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture
def workflow_state(monkeypatch):
    state = _State(SESSION_DEFAULTS.copy())
    state['vibe_rider'] = RIDER_DEFAULTS.copy()
    monkeypatch.setattr(_workflow.st, 'session_state', state)
    return state


def _course():
    return SimpleNamespace(
        df=pd.DataFrame({
            'cumulative_distance': [0.0, 1000.0],
            'altitude': [10.0, 20.0],
        }),
        course_segments=pd.DataFrame({'segment': [0]}),
    )


def _commit_ready_analysis(state):
    course = _course()
    _workflow.mark_course_loaded(course, 'course-1', 'Test Course')
    _workflow.mark_segmentation_applied(course, 'Equal', {'n_segments': 4})
    return course


def test_navigation_changes_only_active_step(workflow_state):
    course = _commit_ready_analysis(workflow_state)
    results = {'sentinel': True}
    _workflow.mark_results(results)
    signature = _workflow.current_input_signature()

    assert _workflow.set_active_step('rider')
    assert _workflow.set_active_step('optimize')

    assert workflow_state['vibe_active_step'] == 'optimize'
    assert _workflow.current_input_signature() == signature
    assert workflow_state['vibe_optimization_results'] is results
    assert workflow_state['vibe_results_course_df'].empty
    assert not _workflow.results_are_stale()


def test_returning_to_course_preserves_completed_analysis(workflow_state):
    starter = get_starter_course('mercer-island-loop-ccw')
    course = Course(build_starter_course_frame(starter.slug))
    course.starter_course = starter
    _workflow.mark_course_loaded(
        course,
        f'starter:{starter.slug}',
        starter.name,
        course_source='Starter Courses',
    )
    course.gradient_band_segmentation(**_workflow.DEFAULT_SEGMENTATION)
    course.enable_enhanced_segmentation()
    _workflow.mark_segmentation_applied(
        course,
        'Terrain',
        _workflow.DEFAULT_SEGMENTATION,
    )
    results = {'sentinel': True}
    _workflow.mark_results(results)
    signature = _workflow.current_input_signature()

    assert _workflow.set_active_step('course')

    labels = {
        starter.name: starter.slug
        for starter in STARTER_COURSES
    }
    assert tab_course._course_source_index(
        tab_course._course_sources(authenticated=False),
        workflow_state['vibe_course_source'],
    ) == 0
    assert tab_course._starter_course_index(
        labels,
        workflow_state['vibe_course_id'],
    ) == list(labels.values()).index(starter.slug)
    assert workflow_state['vibe_course'] is course
    assert workflow_state['vibe_segmentation_applied']
    assert workflow_state['vibe_rider'] == RIDER_DEFAULTS
    assert workflow_state['vibe_optimization_results'] is results
    assert _workflow.current_input_signature() == signature
    assert not _workflow.results_are_stale()


def test_forward_navigation_prepares_only_missing_defaults(workflow_state):
    assert _workflow.set_active_step('rider')

    course = workflow_state['vibe_course']
    assert workflow_state['vibe_course_id'].startswith('starter:')
    assert workflow_state['vibe_segmentation_applied']
    assert not course.course_segments.empty
    assert workflow_state['vibe_active_step'] == 'rider'
    assert workflow_state['vibe_optimization_results'] is None


def test_optimize_navigation_creates_one_shot_run_request(workflow_state):
    assert _workflow.set_active_step('optimize')

    assert workflow_state['vibe_active_step'] == 'optimize'
    assert _workflow.can_run_optimization()
    assert _workflow.consume_optimize_request()
    assert not _workflow.consume_optimize_request()


def test_successful_course_confirmation_advances_to_segmentation(
    workflow_state,
):
    course = _course()

    tab_course._commit_course_and_advance(
        course, 'course-1', 'Test Course')

    assert workflow_state['vibe_course'] is course
    assert workflow_state['vibe_active_step'] == 'segment'


@pytest.mark.parametrize(
    ('course_id', 'expected_index'),
    [
        ('starter:box-hill-527881', 0),
        ('starter:mercer-island-loop-ccw', 1),
        ('database-course', 0),
        (None, 0),
    ],
)
def test_starter_selector_index_uses_committed_course(
    course_id,
    expected_index,
):
    labels = {
        'Box Hill': 'box-hill-527881',
        'Mercer Island': 'mercer-island-loop-ccw',
    }

    assert tab_course._starter_course_index(
        labels,
        course_id,
    ) == expected_index


def test_starter_courses_build_without_authenticated_strava_data():
    assert {starter.slug for starter in STARTER_COURSES} == {
        'box-hill-527881',
        'hawk-hill-229781',
        'central-park-full-loop',
        'prospect-park-loop',
        'mt-lemmon-cookie-cabin',
        'mercer-island-loop-ccw',
        'alpe-d-huez-official-683473',
    }
    assert all(not starter.is_virtual for starter in STARTER_COURSES)

    for starter in STARTER_COURSES:
        frame = build_starter_course_frame(starter.slug)

        assert list(frame.columns) == ['lat', 'lon', 'altitude']
        assert len(frame) >= 90
        assert frame.isna().sum().sum() == 0

        mean_latitude = (
            (frame['lat'] + frame['lat'].shift()) / 2
        ).map(np.radians)
        delta_lat_m = frame['lat'].diff() * 111_139
        delta_lon_m = (
            frame['lon'].diff() * 111_139 * mean_latitude.map(np.cos)
        )
        distance_m = np.hypot(delta_lat_m, delta_lon_m).fillna(0).sum()
        assert distance_m == pytest.approx(starter.distance_m, rel=0.03)
        processed = Course(frame)
        assert processed.df['height_gain'].sum() == pytest.approx(
            starter.elevation_gain_m,
            abs=1.0,
        )


def test_central_park_starter_matches_segment_1532085():
    starter = get_starter_course('central-park-full-loop')
    frame = build_starter_course_frame(starter.slug)

    assert starter.segment_url == (
        'https://veloviewer.com/segment/1532085/Central+Park+Full+Loop'
    )
    assert starter.elevation_source == 'usgs_ned10m'
    assert frame.iloc[0]['lat'] == pytest.approx(40.7815, abs=0.0002)
    assert frame.iloc[0]['lon'] == pytest.approx(-73.9615, abs=0.0002)
    assert frame['altitude'].min() == pytest.approx(7.0, abs=1.0)
    assert frame['altitude'].max() == pytest.approx(37.0, abs=1.0)
    gain = frame['altitude'].diff().clip(lower=0).sum()
    assert gain == pytest.approx(93.0, abs=5.0)


def test_prospect_park_starter_is_official_counterclockwise_loop():
    starter = get_starter_course('prospect-park-loop')
    frame = build_starter_course_frame(starter.slug)

    assert '797660' not in starter.segment_url
    assert starter.elevation_source == 'usgs_ned10m'
    assert frame.iloc[0]['lat'] == pytest.approx(
        frame.iloc[-1]['lat'], abs=0.00001)
    assert frame.iloc[0]['lon'] == pytest.approx(
        frame.iloc[-1]['lon'], abs=0.00001)
    assert frame.iloc[1]['lat'] > frame.iloc[0]['lat']
    gain = frame['altitude'].diff().clip(lower=0).sum()
    assert gain == pytest.approx(48.0, abs=5.0)


@pytest.mark.parametrize(
    ('slug', 'start', 'finish', 'gain'),
    [
        (
            'mt-lemmon-cookie-cabin',
            (32.30512, -110.74458),
            (32.44143, -110.75950),
            1717.0,
        ),
        (
            'alpe-d-huez-official-683473',
            (45.06483, 6.03980),
            (45.09470, 6.07085),
            1139.0,
        ),
    ],
)
def test_open_dem_climb_starters_match_pinned_endpoints(
    slug,
    start,
    finish,
    gain,
):
    starter = get_starter_course(slug)
    frame = build_starter_course_frame(slug)

    assert frame.iloc[0]['lat'] == pytest.approx(start[0], abs=0.0001)
    assert frame.iloc[0]['lon'] == pytest.approx(start[1], abs=0.0001)
    assert frame.iloc[-1]['lat'] == pytest.approx(finish[0], abs=0.0001)
    assert frame.iloc[-1]['lon'] == pytest.approx(finish[1], abs=0.0001)
    derived_gain = frame['altitude'].diff().clip(lower=0).sum()
    assert derived_gain == pytest.approx(gain, rel=0.03)


def test_mercer_island_starter_is_counterclockwise_perimeter_loop():
    starter = get_starter_course('mercer-island-loop-ccw')
    frame = build_starter_course_frame(starter.slug)

    assert starter.segment_url == 'https://ridewithgps.com/routes/28507876'
    assert starter.elevation_source == 'usgs_ned10m'
    assert frame.iloc[0]['lat'] == pytest.approx(47.5892, abs=0.0001)
    assert frame.iloc[0]['lon'] == pytest.approx(-122.2336, abs=0.0001)
    assert frame.iloc[-1]['lat'] == pytest.approx(
        frame.iloc[0]['lat'], abs=0.0001)
    assert frame.iloc[-1]['lon'] == pytest.approx(
        frame.iloc[0]['lon'], abs=0.0001)
    assert frame.iloc[1]['lat'] > frame.iloc[0]['lat']
    longitude = frame['lon'].to_numpy()
    latitude = frame['lat'].to_numpy()
    signed_area = np.sum(
        longitude[:-1] * latitude[1:]
        - longitude[1:] * latitude[:-1]
    ) / 2
    assert signed_area > 0
    gain = frame['altitude'].diff().clip(lower=0).sum()
    assert gain == pytest.approx(191.0, abs=10.0)


def test_real_starter_course_maps_use_supported_map_traces():
    starter = next(course for course in STARTER_COURSES if not course.is_virtual)
    course = Course(build_starter_course_frame(starter.slug))

    preview = _charts.build_gps_map(course.df)
    assert {trace.type for trace in preview.data} == {'scattermap'}
    assert preview.layout.map.style == 'open-street-map'

    course.df['segment'] = np.arange(len(course.df)) % 3
    segmentation = course.plot_segmentation_map(method='clustering')
    assert {trace.type for trace in segmentation.data} == {'scattermap'}
    assert segmentation.layout.map.style == 'open-street-map'

    combined = course.plot_segmentation_combined(method='clustering')
    assert {trace.type for trace in combined.data} == {'scatter', 'scattermap'}
    assert combined.layout.map.style == 'open-street-map'


def test_starter_course_load_commits_and_advances(
    workflow_state,
    monkeypatch,
):
    monkeypatch.setattr(tab_course.st, 'toast', Mock())
    monkeypatch.setattr(tab_course.st, 'rerun', Mock())

    starter = STARTER_COURSES[0]
    tab_course._load_starter_course(starter.slug)

    course = workflow_state['vibe_course']
    assert course.starter_course is starter
    assert workflow_state['vibe_course_id'] == f'starter:{starter.slug}'
    assert workflow_state['vibe_course_name'] == starter.name
    assert workflow_state['vibe_course_source'] == 'Starter Courses'
    assert workflow_state['vibe_active_step'] == 'segment'


def test_starter_course_can_load_in_place_for_preview(
    workflow_state,
    monkeypatch,
):
    monkeypatch.setattr(tab_course.st, 'toast', Mock())
    monkeypatch.setattr(tab_course.st, 'rerun', Mock())

    starter = STARTER_COURSES[1]
    tab_course._load_starter_course(starter.slug, advance=False)

    assert workflow_state['vibe_course_name'] == starter.name
    assert workflow_state['vibe_active_step'] == 'course'


def test_successful_segmentation_advances_to_rider(
    workflow_state,
    monkeypatch,
):
    course = _course()
    course.gradient_band_segmentation = Mock()
    course.enable_enhanced_segmentation = Mock()
    _workflow.mark_course_loaded(course, 'course-1', 'Test Course')
    monkeypatch.setattr(
        tab_segmentation.st, 'spinner', lambda _label: nullcontext())
    monkeypatch.setattr(tab_segmentation.st, 'toast', Mock())
    monkeypatch.setattr(tab_segmentation.st, 'rerun', Mock())

    tab_segmentation._apply_segmentation(
        course,
        'Terrain',
        {
            'flat_threshold': 2.0,
            'steep_threshold': 6.0,
            'min_segment_distance': 200,
        },
    )

    assert workflow_state['vibe_segmentation_applied']
    assert workflow_state['vibe_active_step'] == 'rider'


def test_committed_course_change_retains_and_stales_result(workflow_state):
    _commit_ready_analysis(workflow_state)
    results = {'sentinel': True}
    _workflow.mark_results(results)

    _workflow.mark_course_loaded(_course(), 'course-2', 'New Course')

    assert workflow_state['vibe_optimization_results'] is results
    assert not workflow_state['vibe_segmentation_applied']
    assert _workflow.results_are_stale()
    assert _workflow.stale_result_reasons() == ['course', 'segmentation']
    assert _workflow.can_open_step('optimize')


def test_only_physics_relevant_rider_changes_stale_result(workflow_state):
    _commit_ready_analysis(workflow_state)
    _workflow.mark_results({'sentinel': True})

    _workflow.mark_strava_identity({
        'strava_athlete_id': '42',
        'strava_name': 'Test Rider',
    })
    assert not _workflow.results_are_stale()

    changed = workflow_state['vibe_rider'].copy()
    changed['critical_power'] += 10
    _workflow.mark_rider_profile(changed)

    assert _workflow.stale_result_reasons() == ['rider']


def test_athlete_switch_can_force_rider_revision(workflow_state):
    _commit_ready_analysis(workflow_state)
    _workflow.mark_results({'sentinel': True})

    unchanged_physics = workflow_state['vibe_rider'].copy()
    unchanged_physics['strava_athlete_id'] = 'new-athlete'
    _workflow.mark_rider_profile(unchanged_physics, force_revision=True)

    assert _workflow.stale_result_reasons() == ['rider']


def test_failed_reoptimization_preserves_previous_result(
    workflow_state,
    monkeypatch,
):
    course = _commit_ready_analysis(workflow_state)
    previous = {'sentinel': True}
    _workflow.mark_results(previous)

    monkeypatch.setattr(tab_optimization, '_make_optimizer', Mock())
    monkeypatch.setattr(
        tab_optimization,
        'create_course_segments_from_course',
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        tab_optimization,
        '_run_constant',
        Mock(return_value={'power': 250}),
    )
    monkeypatch.setattr(
        tab_optimization,
        '_run_variable',
        Mock(side_effect=RuntimeError('variable optimization failed')),
    )
    monkeypatch.setattr(tab_optimization.st, 'spinner', lambda _label: nullcontext())
    monkeypatch.setattr(tab_optimization.st, 'expander', lambda _label: nullcontext())
    monkeypatch.setattr(tab_optimization.st, 'error', Mock())
    monkeypatch.setattr(tab_optimization.st, 'code', Mock())

    tab_optimization._run_compare(course, RIDER_DEFAULTS.copy())

    assert workflow_state['vibe_optimization_results'] is previous
    assert not _workflow.results_are_stale()


def test_committed_rider_physics_construct_optimizer(monkeypatch):
    optimizer = Mock()
    optimizer_class = Mock(return_value=optimizer)
    monkeypatch.setattr(tab_optimization, 'CourseOptimizer', optimizer_class)
    rider = {
        **RIDER_DEFAULTS,
        'weight': 72.5,
        'bike_mass': 9.5,
        'critical_power': 310,
        'w_prime': 24500,
        'cda': 0.238,
        'crr': 0.003,
    }

    assert tab_optimization._make_optimizer(rider) is optimizer
    optimizer_class.assert_called_once_with(
        critical_power=310,
        w_prime=24500,
        mass=82.0,
        cda=0.238,
        crr=0.003,
    )


def test_results_power_axis_contains_high_variable_efforts():
    detailed = pd.DataFrame({
        'power': [170.0, 240.0, 420.0],
    })
    results = {
        'constant': {'detailed': pd.DataFrame({'power': [283.0]})},
        'variable': {'detailed': detailed},
    }

    lower, upper = _charts._power_axis_range(
        results,
        critical_power=250.0,
    )

    assert lower < 170.0
    assert upper > 420.0
    assert upper - 420.0 >= 15.0


def test_explicit_reset_preserves_rider_and_auth(workflow_state):
    _commit_ready_analysis(workflow_state)
    _workflow.mark_results({'sentinel': True})
    workflow_state['auth_user_id'] = 'user-1'
    rider = workflow_state['vibe_rider']

    _workflow.reset_analysis()

    assert workflow_state['auth_user_id'] == 'user-1'
    assert workflow_state['vibe_rider'] is rider
    assert workflow_state['vibe_course'] is None
    assert workflow_state['vibe_optimization_results'] is None
    assert workflow_state['vibe_active_step'] == 'course'
