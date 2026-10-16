"""Race Lab — canonical Course -> Segment -> Rider -> Optimize workspace."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import CourseDatabase
from pages_vibe.auth_ui import render_authentication
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
render_authentication()

db = CourseDatabase()


def _render_header() -> None:
    st.title("Race Lab")
    st.caption(
        "Build a race plan from course selection through a terrain-aware "
        "pacing strategy."
    )


def _render_workflow_tabs() -> None:
    status_prefix = {
        'complete': '✓',
        'current': '●',
        'available': '○',
        'blocked': '—',
    }
    columns = st.columns(len(WORKFLOW_STEPS), gap="small")
    for index, (column, (step, label)) in enumerate(
        zip(columns, WORKFLOW_STEPS),
        start=1,
    ):
        status = _workflow.step_status(step)
        with column:
            if st.button(
                f"{status_prefix[status]}  {index}. {label}",
                key=f"workflow_nav_{step}",
                type='primary' if status == 'current' else 'secondary',
                disabled=status == 'blocked',
                width='stretch',
            ):
                _workflow.set_active_step(step)
                st.rerun()


def _render_setup_strip() -> None:
    course = get_course()
    rider = get_rider()

    with st.container(border=True):
        course_col, segment_col, rider_col, result_col = st.columns(
            [1.1, 1, 1.35, 1],
            gap="medium",
        )

        with course_col:
            st.markdown("**Course**")
            if course is None:
                st.caption("Not loaded")
            else:
                cdf = course.df
                distance = (
                    cdf['cumulative_distance'].max() / 1000
                    if 'cumulative_distance' in cdf.columns
                    else 0.0
                )
                st.caption(
                    f"{st.session_state.get('vibe_course_name') or 'Loaded course'}"
                    f" · {distance:.1f} km"
                )

        with segment_col:
            st.markdown("**Segmentation**")
            segmentation = st.session_state.get('vibe_segmentation_name')
            st.caption(segmentation if segmentation else "Not applied")

        with rider_col:
            st.markdown("**Rider & physics**")
            bike_mass = rider.get(
                'bike_mass',
                BIKE_MASS_DEFAULTS.get(rider.get('bike_type', 'Road'), 8.5),
            )
            system_mass = rider['weight'] + bike_mass
            st.caption(
                f"{rider['critical_power']} W CP · "
                f"{rider['w_prime'] / 1000:.0f} kJ W' · "
                f"{system_mass:.1f} kg · "
                f"CdA {rider['cda']:.3f} · Crr {rider['crr']:.3f}"
            )

        with result_col:
            st.markdown("**Result**")
            status = _workflow.result_status()
            labels = {
                'not_run': "Not run",
                'current': "✓ Current",
                'stale': "⚠ Inputs changed",
            }
            st.caption(labels[status])


def _render_sidebar_actions() -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Analysis")

    if st.session_state.get('_confirm_new_analysis'):
        st.sidebar.warning(
            "Start a new analysis? The active course, segmentation, and saved "
            "result will be cleared. Your rider profile stays available."
        )
        confirm_col, cancel_col = st.sidebar.columns(2)
        with confirm_col:
            if st.button(
                "Confirm",
                key="confirm_new_analysis",
                type="primary",
                width="stretch",
            ):
                _workflow.reset_analysis()
                st.session_state['_confirm_new_analysis'] = False
                st.rerun()
        with cancel_col:
            if st.button(
                "Cancel",
                key="cancel_new_analysis",
                width="stretch",
            ):
                st.session_state['_confirm_new_analysis'] = False
                st.rerun()
    elif st.sidebar.button("New analysis", width="stretch"):
        st.session_state['_confirm_new_analysis'] = True
        st.rerun()


def _render_active_workspace() -> None:
    active_step = st.session_state.get('vibe_active_step', 'course')
    if not _workflow.can_open_step(active_step):
        active_step = 'course'
        _workflow.set_active_step(active_step)

    step_titles = dict(WORKFLOW_STEPS)
    st.markdown(f"## {step_titles[active_step]}")

    if active_step == 'course':
        tab_course.render(db)
    elif active_step == 'segment':
        tab_segmentation.render()
    elif active_step == 'rider':
        tab_rider.render()
    else:
        tab_optimization.render()


_render_header()
_render_workflow_tabs()
_render_setup_strip()
_render_sidebar_actions()
_render_active_workspace()
