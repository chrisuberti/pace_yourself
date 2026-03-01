"""
Shared session state management for the Race Lab.

Single source of truth for all session state defaults. Import and call
`init_session_state()` once at the top of the main page to guarantee
consistent defaults regardless of which tab the user visits first.
"""

import streamlit as st

# ── Default values ──────────────────────────────────────────────────────────
RIDER_DEFAULTS = {
    'weight': 80,
    'critical_power': 250,
    'w_prime': 20000,
    'cda': 0.32,
    'crr': 0.004,
}

SESSION_DEFAULTS = {
    'vibe_course': None,
    'vibe_course_id': None,
    'vibe_course_name': None,
    'vibe_segmentation_applied': False,
    'vibe_optimization_results': None,
    'vibe_rider': None,          # will be filled with RIDER_DEFAULTS copy
    'vibe_rider_obj': None,
    'vibe_active_tab': 0,        # track active tab for stepper
}


def init_session_state():
    """Initialize all session state keys with defaults (idempotent)."""
    for key, default in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            if key == 'vibe_rider':
                st.session_state[key] = RIDER_DEFAULTS.copy()
            else:
                st.session_state[key] = default


def get_rider() -> dict:
    """Return the current rider config dict from session state."""
    init_session_state()
    return st.session_state.vibe_rider


def get_course():
    """Return the current Course object (or None)."""
    return st.session_state.get('vibe_course')


def get_results():
    """Return optimization results (or None)."""
    return st.session_state.get('vibe_optimization_results')


# ── Stepper / workflow progress ──────────────────────────────────────────────
TAB_LABELS_BASE = [
    ("📂 Course",  1),   # complete when course loaded
    ("🔪 Segment", 2),   # complete when segmentation applied
    ("🚴 Rider",   3),   # complete when rider configured (always after seg)
    ("🚀 Optimize", 4),  # complete when optimization results exist
]


def _completed_steps() -> int:
    """Return number of completed workflow steps (0-4)."""
    results = get_results()
    if results is not None:
        return 4
    seg_applied = st.session_state.get('vibe_segmentation_applied', False)
    if seg_applied:
        return 2
    course = get_course()
    if course is not None:
        return 1
    return 0


def get_tab_labels() -> list[str]:
    """Return tab label strings with ✓ appended for completed steps."""
    completed = _completed_steps()
    labels = []
    for base_label, threshold in TAB_LABELS_BASE:
        if threshold <= completed:
            labels.append(f"{base_label} ✓")
        else:
            labels.append(base_label)
    return labels


# Legacy — kept for backwards compatibility; no longer called from main page.
def render_stepper():
    """Show a horizontal progress indicator across the top of Race Lab."""
    completed = _completed_steps()
    WORKFLOW_STEPS = [
        ("Load Course", "📂"),
        ("Segment", "🔪"),
        ("Rider Setup", "🚴"),
        ("Optimize", "🚀"),
    ]
    cols = st.columns(len(WORKFLOW_STEPS))
    for i, (label, icon) in enumerate(WORKFLOW_STEPS):
        with cols[i]:
            if i < completed:
                st.markdown(f"<div style='text-align:center;opacity:0.5'>{icon} <s>{label}</s> ✓</div>",
                            unsafe_allow_html=True)
            elif i == completed:
                st.markdown(f"<div style='text-align:center;font-weight:bold'>{icon} <u>{label}</u></div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;opacity:0.35'>{icon} {label}</div>",
                            unsafe_allow_html=True)
