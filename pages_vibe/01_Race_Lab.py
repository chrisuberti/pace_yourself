"""Race Lab — canonical Course -> Segment -> Rider -> Optimize workspace."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import CourseDatabase
from pages_vibe.auth_ui import (
    render_account_footer,
    render_account_header,
    render_authentication,
)
from pages_vibe.privacy_ui import render_privacy_notice
from pages_vibe.tabs import (
    _workflow,
    tab_course,
    tab_optimization,
    tab_rider,
    tab_segmentation,
)
from pages_vibe.tabs.state import (
    BIKE_MASS_DEFAULTS,
    WORKFLOW_STEPS,
    get_course,
    get_rider,
    init_session_state,
)


init_session_state()
if st.query_params.get('view') == 'privacy':
    render_privacy_notice()
    st.stop()
render_authentication()

try:
    db = CourseDatabase()
    database_error = None
except Exception as error:
    db = None
    database_error = error


def _render_header() -> None:
    title_col, account_col, action_col = st.columns(
        [3.4, 1.4, 1],
        vertical_alignment="bottom",
    )
    with title_col:
        st.title("Race Lab")
        st.caption(
            "Build a race plan from course selection through a terrain-aware "
            "pacing strategy."
        )
    with account_col:
        render_account_header()
    with action_col:
        _render_new_analysis_action()


def _render_new_analysis_action() -> None:
    if st.session_state.get('_confirm_new_analysis'):
        st.warning("Clear this analysis? Your rider profile will be kept.")
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button(
                "Clear",
                key="confirm_new_analysis",
                type="primary",
                width="stretch",
            ):
                _workflow.reset_analysis()
                st.session_state['_confirm_new_analysis'] = False
                st.rerun()
        with cancel_col:
            if st.button(
                "Keep",
                key="cancel_new_analysis",
                width="stretch",
            ):
                st.session_state['_confirm_new_analysis'] = False
                st.rerun()
    elif st.button("New analysis", width="stretch"):
        st.session_state['_confirm_new_analysis'] = True
        st.rerun()


def _render_workflow_tabs() -> None:
    status_prefix = {
        'complete': '✓',
        'current': '●',
        'available': '○',
    }
    columns = st.columns(len(WORKFLOW_STEPS), gap="small")
    for index, (column, (step, label)) in enumerate(
        zip(columns, WORKFLOW_STEPS),
        start=1,
    ):
        status = _workflow.step_status(step)
        with column:
            summary = _step_summary(step)
            if st.button(
                f"{status_prefix[status]} {index}. {label}\n{summary}",
                key=f"workflow_nav_{step}",
                type='primary' if status == 'current' else 'secondary',
                width='stretch',
            ):
                try:
                    _workflow.set_active_step(step)
                except Exception as error:
                    st.error(f"Could not prepare {label}: {error}")
                    return
                st.rerun()


def _step_summary(step: str) -> str:
    course = get_course()
    rider = get_rider()
    if step == 'course':
        if course is None:
            return "Uses a starter course by default"
        cdf = course.df
        distance = (
            cdf['cumulative_distance'].max() / 1000
            if 'cumulative_distance' in cdf.columns
            else 0.0
        )
        return (
            f"{st.session_state.get('vibe_course_name') or 'Loaded course'}"
            f" · {distance:.1f} km"
        )
    if step == 'segment':
        return (
            st.session_state.get('vibe_segmentation_name')
            or "Uses terrain zones by default"
        )
    if step == 'rider':
        bike_mass = rider.get(
            'bike_mass',
            BIKE_MASS_DEFAULTS.get(rider.get('bike_type', 'Road'), 8.5),
        )
        return (
            f"{rider['critical_power']} W CP · "
            f"{rider['weight'] + bike_mass:.1f} kg system"
        )
    labels = {
        'not_run': "Click to start",
        'current': "Results ready · click to re-run",
        'stale': "Inputs changed · click to re-run",
    }
    return labels[_workflow.result_status()]


def _render_active_workspace() -> None:
    active_step = st.session_state.get('vibe_active_step', 'course')
    if not _workflow.can_open_step(active_step):
        active_step = 'course'
        _workflow.set_active_step(active_step)

    step_titles = dict(WORKFLOW_STEPS)
    st.markdown(f"## {step_titles[active_step]}")

    if active_step == 'course':
        tab_course.render(db, database_error=database_error)
    elif active_step == 'segment':
        tab_segmentation.render()
    elif active_step == 'rider':
        tab_rider.render()
    else:
        tab_optimization.render()


_render_header()
_render_workflow_tabs()
_render_active_workspace()
render_account_footer()
