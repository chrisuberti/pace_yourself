"""Streamlit boundary for Strava login, callback, and logout."""

from __future__ import annotations

import streamlit as st

from app.auth import (
    authentication_configured,
    complete_oauth,
    create_oauth_state,
    get_auth_store,
    get_authorization_url,
)
from pages_vibe.tabs.state import RIDER_DEFAULTS


def render_authentication() -> None:
    """Bind one PostgreSQL-backed Strava user to this Streamlit session."""
    if not authentication_configured():
        st.sidebar.caption(
            'Local mode · Strava login unavailable until PostgreSQL auth '
            'environment variables are configured.')
        return

    code = st.query_params.get('code')
    returned_state = st.query_params.get('state')
    if code:
        try:
            user = complete_oauth(
                code,
                returned_state,
                st.session_state.get('oauth_state'),
            )
        except Exception as error:
            st.error(f'Strava login failed: {error}')
            if st.button('Start Strava login again', type='primary'):
                _begin_login()
            st.stop()
        st.session_state.auth_user_id = str(user['user_id'])
        st.session_state.auth_user = user
        _bind_user_to_rider(user)
        st.session_state.oauth_state = None
        st.query_params.clear()
        st.rerun()

    user_id = st.session_state.get('auth_user_id')
    if user_id:
        user = get_auth_store().get_user(user_id)
        if user:
            st.session_state.auth_user = user
            _bind_user_to_rider(user)
            st.sidebar.caption(f"Connected as {user['display_name']}")
            if st.sidebar.button('Log out', width='stretch'):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
            return
        st.session_state.auth_user_id = None
        st.session_state.auth_user = None

    st.markdown('## Connect Strava')
    st.caption(
        'Sign in with Strava to load your athlete profile, activities, and '
        'power data. Your credentials are stored per user in PostgreSQL.')
    if not st.session_state.get('oauth_state'):
        st.session_state.oauth_state = create_oauth_state()
    st.link_button(
        'Continue with Strava',
        get_authorization_url(st.session_state.oauth_state),
        type='primary',
        width='stretch',
    )
    st.stop()


def _begin_login() -> None:
    st.session_state.auth_user_id = None
    st.session_state.auth_user = None
    st.session_state.oauth_state = create_oauth_state()
    st.query_params.clear()
    st.rerun()


def _bind_user_to_rider(user) -> None:
    """Prevent a session from inheriting another athlete's cached rider data."""
    rider = st.session_state.get('vibe_rider') or RIDER_DEFAULTS.copy()
    rider, switched_athlete = _rider_for_user(rider, user)
    if switched_athlete:
        st.session_state.vibe_optimization_results = None
    st.session_state.vibe_rider = rider


def _rider_for_user(rider, user):
    """Return rider state constrained to one authenticated Strava athlete."""
    athlete_id = str(user['strava_athlete_id'])
    switched_athlete = rider.get('strava_athlete_id') not in (None, athlete_id)
    updated = RIDER_DEFAULTS.copy() if switched_athlete else rider.copy()
    updated.update({
        'strava_athlete_id': athlete_id,
        'strava_name': user.get('display_name'),
    })
    return updated, switched_athlete