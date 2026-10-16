import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app import auth
from app.auth_store import AUTH_SCHEMA_SQL
from pages_vibe.auth_ui import _rider_for_user


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
        'athlete': {'id': 42, 'firstname': 'Ada'},
    }

    with patch('app.auth.requests.post', return_value=response):
        user = auth.complete_oauth('code', 'same', 'same', store)

    assert user['strava_athlete_id'] == 42
    assert store.saved_grants[0][0]['id'] == 42
    assert store.saved_grants[0][1]['access_token'] == 'access-one'


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