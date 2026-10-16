"""
Workflow gating + state-write helpers for the Race Lab tabs.

All session-state writes for the workflow (`vibe_*` keys) should funnel
through this module. Tab modules read state via `state.get_*` and call
`require_*` to gate rendering on prerequisites.

This is the single funnel for workflow transitions:
  Course loaded -> mark_course_loaded
  Segmentation applied -> mark_segmentation_applied
  Optimization completed -> mark_results
  Reset everything downstream -> reset_after_course / reset_after_segmentation
"""
from __future__ import annotations

import streamlit as st

from pages_vibe.tabs.state import WORKFLOW_STEPS, get_course, get_results


def can_open_step(step: str) -> bool:
    """Return whether the step's true workflow prerequisites are satisfied."""
    if step == 'course':
        return True
    if step == 'segment':
        return get_course() is not None
    if step == 'rider':
        return bool(st.session_state.get('vibe_segmentation_applied'))
    if step == 'optimize':
        return (bool(st.session_state.get('vibe_segmentation_applied'))
                and bool(st.session_state.get('vibe_rider_configured')))
    return False


def step_status(step: str) -> str:
    """Return complete, current, available, or blocked for the workflow rail."""
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
    """Persist a freshly-loaded course; clear all downstream state."""
    st.session_state.vibe_course = course
    st.session_state.vibe_course_id = course_id
    st.session_state.vibe_course_name = course_name
    reset_after_course()


def mark_segmentation_applied(course, name: str, params: dict) -> None:
    """Persist a course whose segmentation just completed; clear downstream."""
    st.session_state.vibe_course = course
    st.session_state.vibe_segmentation_applied = True
    st.session_state.vibe_segmentation_name = name
    st.session_state.vibe_segmentation_params = params.copy()
    reset_after_segmentation()


def mark_rider_profile(rider: dict, rider_obj=None, *,
                       sync_weight: bool = False) -> None:
    """Commit rider inputs and invalidate results derived from the old rider."""
    st.session_state.vibe_rider = rider.copy()
    st.session_state.vibe_rider_obj = rider_obj
    st.session_state.vibe_rider_configured = True
    st.session_state.vibe_optimization_results = None
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


def mark_results(results: dict, params: dict | None = None) -> None:
    """Persist optimization results."""
    st.session_state.vibe_optimization_results = results
    if params is not None:
        st.session_state.vibe_optimization_params = params.copy()


def reset_after_course() -> None:
    """Invalidate segmentation + results when a new course is loaded."""
    st.session_state.vibe_segmentation_applied = False
    st.session_state.vibe_segmentation_name = None
    st.session_state.vibe_segmentation_params = None
    st.session_state.vibe_optimization_results = None


def reset_after_segmentation() -> None:
    """Invalidate results when a new segmentation is applied."""
    st.session_state.vibe_optimization_results = None
