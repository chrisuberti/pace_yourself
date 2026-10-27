"""Streamlit boundary for Strava login, callback, and logout."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st

from app.auth import (
    authentication_configured,
    complete_oauth,
    create_oauth_state,
    disconnect_and_delete_user,
    get_auth_store,
    get_authorization_url,
    missing_required_scopes,
)
from pages_vibe.privacy_ui import (
    render_oauth_consent_summary,
    render_privacy_footer,
)
from pages_vibe.tabs import _workflow
from pages_vibe.tabs.state import RIDER_DEFAULTS


STRAVA_CONNECT_ASSET = (
    Path(__file__).parent / 'assets' / 'btn_strava_connect_with_orange.svg')


def render_authentication() -> None:
    """Bind a Strava user or allow an isolated guest workflow."""
    if not authentication_configured():
        st.session_state.guest_mode = True
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
        st.session_state.guest_mode = False
        _bind_user_to_rider(user)
        if user.get('missing_scopes'):
            st.session_state.strava_scope_warning = user['missing_scopes']
        st.session_state.oauth_state = None
        st.query_params.clear()
        st.rerun()

    user_id = st.session_state.get('auth_user_id')
    if user_id:
        user = get_auth_store().get_user(user_id)
        if user:
            st.session_state.auth_user = user
            st.session_state.guest_mode = False
            _bind_user_to_rider(user)
            return
        st.session_state.auth_user_id = None
        st.session_state.auth_user = None

    if st.session_state.get('guest_mode'):
        return

    disconnect_status = st.query_params.get('disconnected')
    if disconnect_status == 'revoked':
        st.success('Strava was disconnected and your private data was deleted.')
        st.query_params.clear()
    elif disconnect_status == 'local_only':
        st.warning(
            'Your local data was deleted, but Strava revocation could not be '
            'confirmed. Revoke Pace Yourself in Strava Settings > My Apps.')
        st.query_params.clear()

    st.markdown('## Connect Strava')
    st.caption(
        'Connect Strava to fetch new segments and import your athlete profile, '
        'activities, and power data. You can also use the shared course library '
        'with the prefilled rider and segmentation defaults without connecting.'
    )
    render_oauth_consent_summary()
    if not st.session_state.get('oauth_state'):
        st.session_state.oauth_state = create_oauth_state()
    login_col, guest_col = st.columns(2)
    with login_col:
        _render_connect_with_strava(
            get_authorization_url(st.session_state.oauth_state))
        st.caption('You will review and approve access on Strava.')
    with guest_col:
        if st.button('Continue without Strava', width='stretch'):
            st.session_state.guest_mode = True
            st.session_state.auth_user_id = None
            st.session_state.auth_user = None
            st.rerun()
    st.stop()


def render_account_footer() -> None:
    """Render privacy and account controls at the bottom of Race Lab."""
    st.divider()
    info_col, account_col = st.columns([2, 1], vertical_alignment="top")

    with info_col:
        st.caption(
            "Pace Yourself · Strava connection is optional. Imported athlete "
            "data, private courses, and results stay tied to your account."
        )
        render_privacy_footer()

    with account_col:
        if not authentication_configured():
            st.caption(
                "Guest mode · Strava login is not configured for this deployment."
            )
            return

        user = st.session_state.get('auth_user')
        user_id = st.session_state.get('auth_user_id')
        if user and user_id:
            _render_scope_warning(user)
            if st.button('Log out', width='stretch'):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
            _render_disconnect_controls(user_id)
            return

        st.caption(
            "Guest mode · Connect Strava from the top of the page to fetch "
            "segments and import rider data."
        )


def render_account_header() -> None:
    """Keep Strava connection state and its primary action above the workflow."""
    status = _account_header_status(
        configured=authentication_configured(),
        user=st.session_state.get('auth_user'),
        user_id=st.session_state.get('auth_user_id'),
    )
    if status == 'unavailable':
        st.caption("○ Guest mode · Strava login unavailable")
        return

    user = st.session_state.get('auth_user')
    if status == 'connected':
        st.markdown("🟢 **Strava connected**")
        st.caption(user['display_name'])
        return

    st.caption("○ Strava not connected")
    if not st.session_state.get('oauth_state'):
        st.session_state.oauth_state = create_oauth_state()
    _render_connect_with_strava(
        get_authorization_url(st.session_state.oauth_state))


def _account_header_status(*, configured: bool, user, user_id) -> str:
    """Return unavailable, connected, or disconnected for header rendering."""
    if not configured:
        return 'unavailable'
    if user and user_id:
        return 'connected'
    return 'disconnected'


def _render_scope_warning(user) -> None:
    missing = missing_required_scopes(user.get('scope'))
    if not missing:
        return
    st.warning(
        'Strava access is incomplete. Reconnect and approve: '
        + ', '.join(sorted(missing)))
    if not st.session_state.get('oauth_state'):
        st.session_state.oauth_state = create_oauth_state()
    _render_connect_with_strava(
        get_authorization_url(st.session_state.oauth_state))


def _render_connect_with_strava(authorization_url: str) -> None:
    """Render Strava's unmodified official OAuth button asset."""
    encoded_asset = base64.b64encode(
        STRAVA_CONNECT_ASSET.read_bytes()).decode('ascii')
    st.markdown(
        (
            f'<a href="{escape(authorization_url, quote=True)}">'
            f'<img src="data:image/svg+xml;base64,{encoded_asset}" '
            'alt="Connect with Strava" width="237" height="48"></a>'
        ),
        unsafe_allow_html=True,
    )


def _render_disconnect_controls(user_id: str) -> None:
    with st.expander('Disconnect Strava and delete my data'):
        st.warning(
            'This permanently deletes your tokens, rider cache, private Strava '
            'courses, and private optimization results.')
        confirmed = st.checkbox(
            'I understand this cannot be undone',
            key='confirm_delete_private_data',
        )
        if st.button(
                'Disconnect and delete',
                type='primary',
                disabled=not confirmed,
                width='stretch'):
            try:
                result = disconnect_and_delete_user(user_id)
            except Exception as error:
                st.error(f'Account deletion failed: {error}')
                return
            st.session_state.clear()
            st.query_params.clear()
            st.query_params['disconnected'] = (
                'revoked' if result['strava_revoked'] else 'local_only')
            st.rerun()


def _begin_login() -> None:
    st.session_state.auth_user_id = None
    st.session_state.auth_user = None
    st.session_state.guest_mode = False
    st.session_state.oauth_state = create_oauth_state()
    st.query_params.clear()
    st.rerun()


def _bind_user_to_rider(user) -> None:
    """Prevent a session from inheriting another athlete's cached rider data."""
    rider = st.session_state.get('vibe_rider') or RIDER_DEFAULTS.copy()
    rider, switched_athlete = _rider_for_user(rider, user)
    if switched_athlete:
        _workflow.mark_rider_profile(rider, force_revision=True)
    else:
        _workflow.mark_strava_identity({
            'strava_athlete_id': rider.get('strava_athlete_id'),
            'strava_name': rider.get('strava_name'),
        })


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