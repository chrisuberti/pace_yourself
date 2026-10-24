"""Focused regressions for Race Lab navigation and durable result state."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from pages_vibe.tabs import (
    _workflow,
    tab_course,
    tab_optimization,
    tab_segmentation,
)
from pages_vibe.tabs.state import RIDER_DEFAULTS, SESSION_DEFAULTS
from app.starter_courses import STARTER_COURSES, build_starter_course_frame


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


def test_successful_course_confirmation_advances_to_segmentation(
    workflow_state,
):
    course = _course()

    tab_course._commit_course_and_advance(
        course, 'course-1', 'Test Course')

    assert workflow_state['vibe_course'] is course
    assert workflow_state['vibe_active_step'] == 'segment'


def test_starter_courses_build_without_authenticated_strava_data():
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
    assert workflow_state['vibe_active_step'] == 'segment'


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
