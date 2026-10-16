"""
Workflow gating + state-write helpers for the Race Lab tabs.

All session-state writes for the workflow (`vibe_*` keys) should funnel
through this module. Tab modules read state via `state.get_*` and call
`require_*` to gate rendering on prerequisites.

This is the single funnel for workflow transitions:
  Course loaded -> mark_course_loaded
  Segmentation applied -> mark_segmentation_applied
  Optimization completed -> mark_results
  Start over explicitly -> reset_analysis
"""
from __future__ import annotations

import streamlit as st

from pages_vibe.tabs.state import (
    WORKFLOW_STEPS,
    get_course,
    get_results,
    get_rider,
)


RIDER_OPTIMIZATION_KEYS = (
    'weight',
    'bike_mass',
    'critical_power',
    'w_prime',
    'cda',
    'crr',
)


def current_input_signature() -> dict[str, int | None]:
    """Return the revisions that define the currently committed analysis."""
    return {
        'course': st.session_state.get('vibe_course_revision', 0),
        'segmentation': (
            st.session_state.get('vibe_segmentation_revision', 0)
            if st.session_state.get('vibe_segmentation_applied')
            else None
        ),
        'rider': st.session_state.get('vibe_rider_revision', 0),
        'optimization': st.session_state.get('vibe_optimization_revision', 0),
    }


def stale_result_reasons() -> list[str]:
    """Return committed input groups that differ from the saved result."""
    if get_results() is None:
        return []
    result_signature = st.session_state.get('vibe_results_signature')
    if result_signature is None:
        return ['inputs']
    current = current_input_signature()
    return [
        label
        for key, label in (
            ('course', 'course'),
            ('segmentation', 'segmentation'),
            ('rider', 'rider'),
            ('optimization', 'optimization settings'),
        )
        if result_signature.get(key) != current.get(key)
    ]


def results_are_stale() -> bool:
    """Return whether saved results differ from committed current inputs."""
    return bool(stale_result_reasons())


def result_status() -> str:
    """Return not_run, current, or stale for the last optimization."""
    if get_results() is None:
        return 'not_run'
    return 'stale' if results_are_stale() else 'current'


def can_run_optimization() -> bool:
    """Return whether the current committed setup can be optimized."""
    if not st.session_state.get('vibe_segmentation_applied'):
        return False
    if not st.session_state.get('vibe_rider_configured'):
        return False
    course = get_course()
    return bool(
        course is not None
        and hasattr(course, 'course_segments')
        and course.course_segments is not None
        and not course.course_segments.empty
    )


def can_open_step(step: str) -> bool:
    """Return whether the step's true workflow prerequisites are satisfied."""
    if step == 'course':
        return True
    if step == 'segment':
        return get_course() is not None
    if step == 'rider':
        return bool(st.session_state.get('vibe_segmentation_applied'))
    if step == 'optimize':
        return get_results() is not None or can_run_optimization()
    return False


def step_status(step: str) -> str:
    """Return complete, current, available, or blocked for the navigator."""
    active = st.session_state.get('vibe_active_step', 'course')
    if step == active:
        return 'current'
    if not can_open_step(step):
        return 'blocked'
    complete = {
        'course': get_course() is not None,
        'segment': bool(st.session_state.get('vibe_segmentation_applied')),
        'rider': bool(st.session_state.get('vibe_rider_configured')),
        'optimize': get_results() is not None,
    }
    if complete.get(step):
        return 'complete'
    return 'available'


def set_active_step(step: str) -> bool:
    """Navigate to an available workflow step."""
    valid_steps = {key for key, _ in WORKFLOW_STEPS}
    if step not in valid_steps or not can_open_step(step):
        return False
    st.session_state.vibe_active_step = step
    return True


# ── Gating helpers (return True if prerequisite satisfied) ──────────────────

def require_course(message: str = "Load a course in the **Course** tab first.") -> bool:
    """Return True if a course is loaded; otherwise show info and return False."""
    if get_course() is None:
        st.info(message)
        return False
    return True


def require_segmentation(
    message: str = "Apply a segmentation in the **Segment** tab first.",
) -> bool:
    """Return True if segmentation has been applied; otherwise show info."""
    if not require_course():
        return False
    if not st.session_state.get('vibe_segmentation_applied'):
        st.info(message)
        return False
    course = get_course()
    if (not hasattr(course, 'course_segments')
            or course.course_segments is None
            or course.course_segments.empty):
        st.warning("No segments found. Go back to the **Segment** tab.")
        return False
    return True


def require_results(
    message: str = "Run an optimization in the **Optimize** tab first.",
) -> bool:
    """Return True if optimization results exist; otherwise show info."""
    if get_results() is None:
        st.info(message)
        return False
    return True


# ── State write helpers (single funnel for workflow transitions) ────────────

def mark_course_loaded(course, course_id, course_name: str) -> None:
    """Persist a freshly-loaded course and invalidate current segmentation."""
    st.session_state.vibe_course = course
    st.session_state.vibe_course_id = course_id
    st.session_state.vibe_course_name = course_name
    _bump_revision('course')
    _reset_after_course()


def mark_segmentation_applied(course, name: str, params: dict) -> None:
    """Persist a course whose segmentation just completed."""
    st.session_state.vibe_course = course
    st.session_state.vibe_segmentation_applied = True
    st.session_state.vibe_segmentation_name = name
    st.session_state.vibe_segmentation_params = params.copy()
    _bump_revision('segmentation')


def mark_rider_profile(rider: dict, rider_obj=None, *,
                       sync_weight: bool = False,
                       force_revision: bool = False) -> None:
    """Commit rider inputs and revise only optimization-relevant changes."""
    previous = st.session_state.get('vibe_rider') or {}
    changed = (
        force_revision
        or any(previous.get(key) != rider.get(key)
               for key in RIDER_OPTIMIZATION_KEYS)
    )
    st.session_state.vibe_rider = rider.copy()
    st.session_state.vibe_rider_obj = rider_obj
    st.session_state.vibe_rider_configured = True
    if changed:
        _bump_revision('rider')
    if sync_weight:
        st.session_state.vibe_pending_rider_weight = float(rider['weight'])


def apply_pending_rider_weight() -> None:
    """Apply an imported weight before the general weight widget is created."""
    weight = st.session_state.get('vibe_pending_rider_weight')
    if weight is not None:
        st.session_state.rider_general_weight = weight
        st.session_state.vibe_pending_rider_weight = None


def mark_strava_identity(identity: dict) -> None:
    """Update non-physical Strava identity metadata without invalidating results."""
    rider = st.session_state.vibe_rider.copy()
    rider.update(identity)
    st.session_state.vibe_rider = rider


def mark_optimization_settings(params: dict) -> None:
    """Commit optimization settings and revise them only when changed."""
    committed = params.copy()
    if committed == st.session_state.get('vibe_optimization_params', {}):
        return
    st.session_state.vibe_optimization_params = committed
    _bump_revision('optimization')


def mark_results(results: dict, params: dict | None = None) -> None:
    """Atomically replace results and the input context that produced them."""
    committed_params = (
        params.copy()
        if params is not None
        else st.session_state.get('vibe_optimization_params', {}).copy()
    )
    optimization_revision = st.session_state.get(
        'vibe_optimization_revision',
        0,
    )
    if committed_params != st.session_state.get('vibe_optimization_params', {}):
        optimization_revision += 1

    course = get_course()
    course_df = None
    if course is not None and hasattr(course, 'df'):
        context_columns = [
            column
            for column in ('segment', 'segment_terrain')
            if column in course.df.columns
        ]
        course_df = course.df[context_columns].copy(deep=True)

    signature = current_input_signature()
    signature['optimization'] = optimization_revision
    st.session_state.update({
        'vibe_optimization_params': committed_params,
        'vibe_optimization_revision': optimization_revision,
        'vibe_optimization_results': results,
        'vibe_results_signature': signature,
        'vibe_results_rider': get_rider().copy(),
        'vibe_results_course_df': course_df,
    })


def _reset_after_course() -> None:
    """Invalidate segmentation when a new course is loaded."""
    st.session_state.vibe_segmentation_applied = False
    st.session_state.vibe_segmentation_name = None
    st.session_state.vibe_segmentation_params = None


def reset_analysis() -> None:
    """Clear the active analysis while preserving auth and rider profile."""
    st.session_state.update({
        'vibe_course': None,
        'vibe_course_id': None,
        'vibe_course_name': None,
        'vibe_segmentation_applied': False,
        'vibe_segmentation_name': None,
        'vibe_segmentation_params': None,
        'vibe_optimization_results': None,
        'vibe_optimization_params': {},
        'vibe_results_signature': None,
        'vibe_results_rider': None,
        'vibe_results_course_df': None,
        'vibe_active_step': 'course',
    })
    _bump_revision('course')
    _bump_revision('segmentation')
    _bump_revision('optimization')


def _bump_revision(input_group: str) -> None:
    key = f'vibe_{input_group}_revision'
    st.session_state[key] = st.session_state.get(key, 0) + 1
