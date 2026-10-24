"""Per-user Strava OAuth and token refresh orchestration."""

from __future__ import annotations

import hmac
import os
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

from app.auth_store import PostgresAuthStore

load_dotenv()

STRAVA_AUTHORIZE_URL = 'https://www.strava.com/oauth/authorize'
STRAVA_TOKEN_URL = 'https://www.strava.com/oauth/token'
STRAVA_DEAUTHORIZE_URL = 'https://www.strava.com/oauth/deauthorize'
STRAVA_SCOPE = 'read,profile:read_all,activity:read_all'
REQUIRED_STRAVA_SCOPES = frozenset({'read', 'activity:read_all'})

# OAuth state must survive the full-page redirect to Strava and back. Streamlit
# discards session_state across that round trip (the callback arrives as a new
# session), so issued states are tracked server-side with a short TTL instead.
_ISSUED_OAUTH_STATES: dict[str, float] = {}
_OAUTH_STATE_TTL_SECONDS = 600


def _prune_oauth_states():
    now = time.time()
    for value, expiry in list(_ISSUED_OAUTH_STATES.items()):
        if expiry < now:
            _ISSUED_OAUTH_STATES.pop(value, None)


def _consume_oauth_state(state) -> bool:
    """Return True and invalidate the state if it was issued and unexpired."""
    _prune_oauth_states()
    return bool(state) and _ISSUED_OAUTH_STATES.pop(str(state), None) is not None



class AuthenticationRequired(RuntimeError):
    """Raised when a Strava operation has no authenticated application user."""


class InsufficientScope(RuntimeError):
    """Raised when a Strava grant omitted a required scope."""


def _setting(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'{name} is required for Strava authentication.')
    return value


def authentication_configured():
    required = (
        'DATABASE_URL', 'TOKEN_ENCRYPTION_KEY', 'STRAVA_CLIENT_ID',
        'STRAVA_CLIENT_SECRET', 'STRAVA_REDIRECT_URI',
    )
    return all(os.getenv(name) for name in required)


@lru_cache(maxsize=1)
def get_auth_store():
    store = PostgresAuthStore()
    store.initialize_schema()
    return store


def create_oauth_state():
    _prune_oauth_states()
    state = secrets.token_urlsafe(32)
    _ISSUED_OAUTH_STATES[state] = time.time() + _OAUTH_STATE_TTL_SECONDS
    return state


def get_authorization_url(state):
    query = urlencode({
        'client_id': _setting('STRAVA_CLIENT_ID'),
        'redirect_uri': _setting('STRAVA_REDIRECT_URI'),
        'response_type': 'code',
        'approval_prompt': 'auto',
        'scope': STRAVA_SCOPE,
        'state': state,
    })
    return f'{STRAVA_AUTHORIZE_URL}?{query}'


def complete_oauth(code, returned_state, expected_state=None, store=None):
    """Validate callback state, exchange code, and persist the user grant."""
    # Prefer the server-side issued-state store (survives the redirect); fall
    # back to the per-session expected_state when present.
    state_ok = _consume_oauth_state(returned_state)
    if not state_ok and expected_state and returned_state:
        state_ok = hmac.compare_digest(str(returned_state), str(expected_state))
    if not state_ok:
        raise ValueError('Invalid OAuth state. Start the Strava login again.')

    response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            'client_id': _setting('STRAVA_CLIENT_ID'),
            'client_secret': _setting('STRAVA_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code',
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f'Strava token exchange failed ({response.status_code}).')
    token_data = response.json()
    athlete = token_data.get('athlete')
    if not athlete:
        raise RuntimeError('Strava token exchange did not return an athlete.')
    user = (store or get_auth_store()).save_oauth_grant(athlete, token_data)
    user['scope'] = token_data.get('scope', '')
    user['missing_scopes'] = sorted(missing_required_scopes(user['scope']))
    return user


def refresh_access_token(user_id, store=None):
    """Refresh and persist one user's Strava token without touching `.env`."""
    if not user_id:
        raise AuthenticationRequired('Connect a Strava account first.')
    token_store = store or get_auth_store()
    current = token_store.get_token(user_id)
    if not current:
        raise AuthenticationRequired('No Strava token exists for this user.')

    response = requests.post(
        STRAVA_TOKEN_URL,
        data={
            'client_id': _setting('STRAVA_CLIENT_ID'),
            'client_secret': _setting('STRAVA_CLIENT_SECRET'),
            'grant_type': 'refresh_token',
            'refresh_token': current['refresh_token'],
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError(f'Strava token refresh failed ({response.status_code}).')
    refreshed = response.json()
    token_store.update_token(user_id, refreshed)
    return refreshed['access_token']


def get_access_token(user_id, store=None):
    """Return a valid access token belonging only to `user_id`."""
    if not user_id:
        raise AuthenticationRequired('Connect a Strava account first.')
    token_store = store or get_auth_store()
    token = token_store.get_token(user_id)
    if not token:
        raise AuthenticationRequired('No Strava token exists for this user.')
    if time.time() > token['expires_at'] - 300:
        return refresh_access_token(user_id, store=token_store)
    return token['access_token']


def parse_scopes(scope) -> set[str]:
    """Normalize Strava's comma- or space-delimited scope value."""
    if isinstance(scope, (list, tuple, set)):
        return {str(item).strip() for item in scope if str(item).strip()}
    return {
        item.strip()
        for item in str(scope or '').replace(',', ' ').split()
        if item.strip()
    }


def missing_required_scopes(scope) -> set[str]:
    """Return required scopes omitted from a Strava grant."""
    return REQUIRED_STRAVA_SCOPES - parse_scopes(scope)


def require_scopes(user_id, *scopes, store=None) -> None:
    """Raise with a reconnect action when the user's grant is insufficient."""
    if not user_id:
        raise AuthenticationRequired('Connect a Strava account first.')
    token = (store or get_auth_store()).get_token(user_id)
    if not token:
        raise AuthenticationRequired('No Strava token exists for this user.')
    missing = set(scopes) - parse_scopes(token.get('scope'))
    if missing:
        raise InsufficientScope(
            "Reconnect Strava and approve: " + ", ".join(sorted(missing))
        )


def disconnect_and_delete_user(user_id, store=None):
    """Revoke Strava when possible, then always delete local private data."""
    if not user_id:
        raise AuthenticationRequired('Connect a Strava account first.')
    token_store = store or get_auth_store()
    warning = None
    revoked = False
    try:
        access_token = get_access_token(user_id, store=token_store)
        response = requests.post(
            STRAVA_DEAUTHORIZE_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=15,
        )
        if response.status_code == 200:
            revoked = True
        else:
            warning = (
                f"Strava revocation returned {response.status_code}. "
                "Local data was deleted; revoke the app in Strava settings."
            )
    except requests.RequestException as error:
        warning = (
            f"Strava could not be reached ({error}). Local data was deleted; "
            "revoke the app in Strava settings."
        )
    except (AuthenticationRequired, RuntimeError) as error:
        warning = (
            f"Strava revocation could not be confirmed ({error}). Local data "
            "was deleted; revoke the app in Strava settings."
        )

    deleted = token_store.delete_user(user_id)
    if not deleted:
        raise LookupError('The connected application user no longer exists.')
    return {'strava_revoked': revoked, 'warning': warning}