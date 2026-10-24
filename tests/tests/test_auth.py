import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app import auth
from app.auth_store import AUTH_SCHEMA_SQL
from app.database import SCHEMA_SQL
from app.rider import RIDER_SCHEMA_SQL
from pages_vibe.auth_ui import _rider_for_user
from pages_vibe.tabs import tab_rider
from pages_vibe.tabs.tab_course import _course_sources
from pages_vibe.tabs.tab_rider import _power_source_options


class FakeAuthStore:
    def __init__(self, tokens=None):
        self.tokens = tokens or {}
        self.saved_grants = []
        self.updated_users = []

    def save_oauth_grant(self, athlete, token_data):
        self.saved_grants.append((athlete, token_data))
        return {
            'user_id': 'user-1',
            'strava_athlete_id': athlete['id'],
            'display_name': athlete['firstname'],
        }

    def get_token(self, user_id):
        return self.tokens.get(user_id)

    def update_token(self, user_id, token_data):
        self.tokens[user_id] = token_data
        self.updated_users.append(user_id)

    def delete_user(self, user_id):
        self.tokens.pop(user_id, None)
        return True


@pytest.fixture
def oauth_environment():
    with patch.dict('os.environ', {
        'STRAVA_CLIENT_ID': 'client-id',
        'STRAVA_CLIENT_SECRET': 'client-secret',
        'STRAVA_REDIRECT_URI': 'https://pace.example/auth/callback',
    }, clear=False):
        yield


def test_authorization_url_contains_callback_scope_and_state(oauth_environment):
    url = urlparse(auth.get_authorization_url('csrf-state'))
    query = parse_qs(url.query)

    assert query['client_id'] == ['client-id']
    assert query['redirect_uri'] == ['https://pace.example/auth/callback']
    assert query['state'] == ['csrf-state']
    assert 'activity:read_all' in query['scope'][0]
    assert 'profile:read_all' in query['scope'][0]


def test_oauth_state_is_validated_before_exchange(oauth_environment):
    with patch('app.auth.requests.post') as post:
        with pytest.raises(ValueError, match='Invalid OAuth state'):
            auth.complete_oauth('code', 'wrong', 'expected', FakeAuthStore())

    post.assert_not_called()


def test_oauth_exchange_persists_returned_athlete(oauth_environment):
    store = FakeAuthStore()
    response = MagicMock(status_code=200)
    response.json.return_value = {
        'access_token': 'access-one',
        'refresh_token': 'refresh-one',
        'expires_at': int(time.time()) + 3600,
        'scope': 'read,activity:read_all',
        'athlete': {'id': 42, 'firstname': 'Ada'},
    }

    with patch('app.auth.requests.post', return_value=response):
        user = auth.complete_oauth('code', 'same', 'same', store)

    assert user['strava_athlete_id'] == 42
    assert store.saved_grants[0][0]['id'] == 42
    assert store.saved_grants[0][1]['access_token'] == 'access-one'
    assert user['missing_scopes'] == []


def test_scope_normalization_and_required_scope_validation():
    assert auth.parse_scopes('read, profile:read_all activity:read_all') == {
        'read', 'profile:read_all', 'activity:read_all'}
    assert auth.missing_required_scopes('read') == {'activity:read_all'}


def test_require_scopes_rejects_incomplete_grant():
    store = FakeAuthStore({
        'user-a': {'scope': 'read', 'access_token': 'token'},
    })
    with pytest.raises(auth.InsufficientScope, match='activity:read_all'):
        auth.require_scopes('user-a', 'read', 'activity:read_all', store=store)


def test_disconnect_deauthorizes_before_local_deletion():
    store = FakeAuthStore({
        'user-a': {
            'scope': 'read,activity:read_all',
            'access_token': 'token-a',
            'expires_at': int(time.time()) + 3600,
        },
    })
    response = MagicMock(status_code=200)

    with patch('app.auth.requests.post', return_value=response) as post:
        result = auth.disconnect_and_delete_user('user-a', store=store)

    assert result == {'strava_revoked': True, 'warning': None}
    assert 'user-a' not in store.tokens
    assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer token-a'


def test_disconnect_deletes_local_data_when_strava_revocation_fails():
    store = FakeAuthStore({
        'user-a': {
            'scope': 'read,activity:read_all',
            'access_token': 'token-a',
            'expires_at': int(time.time()) + 3600,
        },
    })
    response = MagicMock(status_code=500)

    with patch('app.auth.requests.post', return_value=response):
        result = auth.disconnect_and_delete_user('user-a', store=store)

    assert result['strava_revoked'] is False
    assert 'revoke the app in Strava settings' in result['warning']
    assert 'user-a' not in store.tokens


def test_refresh_is_isolated_to_requested_user(oauth_environment):
    store = FakeAuthStore({
        'user-a': {
            'access_token': 'expired-a',
            'refresh_token': 'refresh-a',
            'expires_at': 0,
            'scope': 'read',
        },
        'user-b': {
            'access_token': 'valid-b',
            'refresh_token': 'refresh-b',
            'expires_at': int(time.time()) + 3600,
            'scope': 'read',
        },
    })
    response = MagicMock(status_code=200)
    response.json.return_value = {
        'access_token': 'new-a',
        'refresh_token': 'new-refresh-a',
        'expires_at': int(time.time()) + 3600,
    }

    with patch('app.auth.requests.post', return_value=response):
        assert auth.get_access_token('user-a', store) == 'new-a'
        assert auth.get_access_token('user-b', store) == 'valid-b'

    assert store.updated_users == ['user-a']
    assert store.tokens['user-b']['refresh_token'] == 'refresh-b'


def test_token_table_is_owned_by_users():
    normalized = ' '.join(AUTH_SCHEMA_SQL.split())
    assert 'strava_tokens' in normalized
    assert 'REFERENCES users(user_id) ON DELETE CASCADE' in normalized


def test_private_application_data_has_auth_foreign_keys():
    rider_schema = ' '.join(RIDER_SCHEMA_SQL.split())
    result_schema = ' '.join(SCHEMA_SQL.split())

    assert 'owner_user_id UUID UNIQUE NOT NULL REFERENCES users(user_id)' in rider_schema
    assert 'owner_user_id UUID NOT NULL REFERENCES users(user_id)' in result_schema
    assert 'FOREIGN KEY (owner_user_id) REFERENCES users(user_id)' in result_schema


def test_token_access_requires_user_before_store_lookup():
    with pytest.raises(auth.AuthenticationRequired, match='Connect'):
        auth.get_access_token(None)


def test_env_file_mutation_api_is_removed():
    assert not hasattr(auth, 'update_env_file')


def test_switching_users_cannot_inherit_rider_data():
    rider_a = {
        'strava_athlete_id': '101',
        'strava_name': 'Athlete A',
        'critical_power': 410,
        'w_prime': 26000,
        'best_efforts': {1200: 425},
        'power_source': 'strava',
    }

    rider_b, switched = _rider_for_user(rider_a, {
        'strava_athlete_id': 202,
        'display_name': 'Athlete B',
    })

    assert switched is True
    assert rider_b['strava_athlete_id'] == '202'
    assert rider_b['strava_name'] == 'Athlete B'
    assert rider_b['critical_power'] == 250
    assert rider_b['best_efforts'] == {}


def test_guest_mode_excludes_strava_only_actions():
    assert _course_sources(authenticated=False) == [
        'Starter Courses', 'Database', 'Upload CSV']
    assert _power_source_options(authenticated=False) == [
        'Rider Type', 'Manual Entry']


def test_database_outage_preserves_csv_guest_path():
    assert _course_sources(
        authenticated=False,
        database_available=False,
    ) == ['Starter Courses', 'Upload CSV']


def test_authenticated_mode_includes_strava_actions():
    assert _course_sources(authenticated=True)[-1] == 'Strava Segment'
    assert _power_source_options(authenticated=True)[-1] == 'Strava Import'


def test_guest_mode_never_reads_cached_strava_rider(monkeypatch):
    cached_rider = MagicMock()
    monkeypatch.setattr(tab_rider.st, 'session_state', {})
    monkeypatch.setattr(tab_rider, 'get_cached_strava_rider', cached_rider)

    assert tab_rider._get_session_rider_cache({}) is None
    cached_rider.assert_not_called()
