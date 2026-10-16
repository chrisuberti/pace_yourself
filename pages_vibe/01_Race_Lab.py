"""Race Lab — guided Course -> Segment -> Rider -> Optimize workspace."""

import streamlit as st
import os, sys

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

# ── Session state (single source of truth) ───────────────────────────────────
init_session_state()
render_authentication()

# ── Database ─────────────────────────────────────────────────────────────────
db = CourseDatabase()

# ── Inline header ────────────────────────────────────────────────────────────
course_name = st.session_state.get('vibe_course_name')
if course_name:
    title_text = f"⚡ Pace Yourself — {course_name}"
else:
    title_text = "⚡ Pace Yourself"

st.markdown(f"""
<style>
    .block-container {{ padding-top: 3.5rem; padding-bottom: 2rem; }}
    [data-testid="stMetricValue"] {{ font-size: 1.1rem; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.75rem; }}
    [data-testid="stSidebar"] [data-testid="stButton"] button {{
        min-height: 2.7rem;
        justify-content: flex-start;
    }}

    /* App title injected into the Streamlit toolbar row */
    [data-testid="stToolbar"]::before {{
        content: "{title_text}";
        font-size: 1.15rem;
        font-weight: 700;
        opacity: 0.85;
        white-space: nowrap;
        flex: 1;
        padding-left: 1rem;
    }}
</style>
""", unsafe_allow_html=True)


def _render_workflow_rail() -> None:
    st.sidebar.markdown("### Race workflow")
    status_prefix = {
        'complete': '✓',
        'current': '●',
        'available': '○',
        'blocked': '—',
    }
    for index, (step, label) in enumerate(WORKFLOW_STEPS, start=1):
        status = _workflow.step_status(step)
        button_label = f"{status_prefix[status]}  {index}. {label}"
        if st.sidebar.button(
            button_label,
            key=f"workflow_nav_{step}",
            type='primary' if status == 'current' else 'secondary',
            disabled=status == 'blocked',
            width='stretch',
        ):
            _workflow.set_active_step(step)
            st.rerun()


def _render_context_summary() -> None:
    course = get_course()
    rider = get_rider()
    st.sidebar.divider()
    st.sidebar.markdown("### Active setup")

    if course is None:
        st.sidebar.caption("No course loaded")
    else:
        cdf = course.df
        distance = (cdf['cumulative_distance'].max() / 1000
                    if 'cumulative_distance' in cdf.columns else 0.0)
        st.sidebar.markdown(
            f"**{st.session_state.get('vibe_course_name') or 'Loaded course'}**  "
            f"\n{distance:.1f} km")

    segmentation = st.session_state.get('vibe_segmentation_name')
    if segmentation:
        st.sidebar.caption(f"Segmentation: {segmentation}")
    else:
        st.sidebar.caption("Segmentation: not applied")

    bike_mass = rider.get(
        'bike_mass',
        BIKE_MASS_DEFAULTS.get(rider.get('bike_type', 'Road'), 8.5),
    )
    system_mass = rider['weight'] + bike_mass
    bike_label = ('TT / Tri' if rider.get('bike_type') == 'TT'
                  else rider.get('bike_type', 'Road'))
    st.sidebar.markdown(
        f"**Rider**  \n"
        f"{rider['critical_power']} W CP · {rider['w_prime'] / 1000:.0f} kJ W'  \n"
        f"{bike_label} · {system_mass:.1f} kg system  \n"
        f"CdA {rider['cda']:.3f} · Crr {rider['crr']:.3f}")

    results = st.session_state.get('vibe_optimization_results')
    st.sidebar.caption("Results: ready" if results is not None
                       else "Results: not calculated")


_render_workflow_rail()
_render_context_summary()

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
