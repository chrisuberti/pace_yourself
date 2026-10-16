"""
Shared session state management for the Race Lab.

Single source of truth for all session state defaults. Import and call
`init_session_state()` once at the top of the main page to guarantee
consistent defaults regardless of which tab the user visits first.
"""

import streamlit as st

# ── Default values ──────────────────────────────────────────────────────────
BIKE_MASS_DEFAULTS = {
    'Road': 8.5,
    'TT': 9.5,
    'Gravel': 10.5,
    'MTB': 12.5,
}

RIDER_DEFAULTS = {
    'height': 1.78,
    'weight': 80.0,
    'bike_type': 'Road',
    'bike_mass': BIKE_MASS_DEFAULTS['Road'],
    'position': 'Hoods',
    'critical_power': 250,
    'w_prime': 20000,
    'cda': 0.32,
    'crr': 0.004,
    'strava_athlete_id': None,
    'strava_name': None,
    'strava_weight': None,
    'strava_last_synced_at': None,
    'strava_lookback_days': None,
    'best_efforts': {},
    'power_source': None,
}

SESSION_DEFAULTS = {
    'auth_user_id': None,
    'auth_user': None,
    'oauth_state': None,
    'vibe_course': None,
    'vibe_course_id': None,
    'vibe_course_name': None,
    'vibe_segmentation_applied': False,
    'vibe_segmentation_name': None,
    'vibe_segmentation_params': None,
    'vibe_course_revision': 0,
    'vibe_segmentation_revision': 0,
    'vibe_rider_revision': 0,
    'vibe_optimization_revision': 0,
    'vibe_optimization_results': None,
    'vibe_optimization_params': {},
    'vibe_results_signature': None,
    'vibe_results_rider': None,
    'vibe_results_course_df': None,
    'vibe_rider': None,          # will be filled with RIDER_DEFAULTS copy
    'vibe_rider_obj': None,
    'vibe_pending_rider_weight': None,
    'vibe_rider_configured': True,
    'vibe_active_step': 'course',
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


WORKFLOW_STEPS = (
    ('course', 'Course'),
    ('segment', 'Segment'),
    ('rider', 'Rider'),
    ('optimize', 'Optimize'),
)
