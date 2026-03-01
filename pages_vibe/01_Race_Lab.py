"""
Race Lab — Tab-based workspace for course optimization.

Course → Segment → Rider → Optimize

Each tab's content lives in its own module under pages_vibe/tabs/ for
cleaner code organisation and easier maintenance.
"""

import streamlit as st
import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import CourseDatabase
from pages_vibe.tabs.state import init_session_state, get_tab_labels
from pages_vibe.tabs import tab_course, tab_segmentation, tab_rider, tab_optimization

# ── Session state (single source of truth) ───────────────────────────────────
init_session_state()

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
    .block-container {{ padding-top: 4rem; padding-bottom: 0rem; }}
    [data-testid="stMetricValue"] {{ font-size: 1.1rem; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.75rem; }}

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

# ── Tabs (labels include ✓ for completed steps) ─────────────────────────────
tab_crs, tab_seg, tab_rdr, tab_opt = st.tabs(get_tab_labels())

with tab_crs:
    tab_course.render(db)

with tab_seg:
    tab_segmentation.render()

with tab_rdr:
    tab_rider.render()

with tab_opt:
    tab_optimization.render()
