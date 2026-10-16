"""PostgreSQL persistence for application users and Strava OAuth tokens."""

from __future__ import annotations

import os
import uuid


AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY,
    strava_athlete_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    display_name VARCHAR(200) NOT NULL,
    profile_picture_url TEXT,
    profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS strava_tokens (
    user_id UUID PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    access_token_ciphertext BYTEA NOT NULL,
    refresh_token_ciphertext BYTEA NOT NULL,
    expires_at BIGINT NOT NULL,
    scope TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_strava_athlete
    ON users(strava_athlete_id);
"""


class PostgresAuthStore:
    """Persist users and encrypted Strava credentials in PostgreSQL."""

    def __init__(self, database_url=None, encryption_key=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.encryption_key = encryption_key or os.getenv('TOKEN_ENCRYPTION_KEY')
        if not self.database_url:
            raise RuntimeError('DATABASE_URL is required for authentication.')
        if not self.encryption_key:
            raise RuntimeError(
                'TOKEN_ENCRYPTION_KEY is required for authentication.')

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "Install the 'psycopg[binary]' package for PostgreSQL auth.") from error
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _cipher(self):
        try:
            from cryptography.fernet import Fernet
        except ImportError as error:
            raise RuntimeError(
                "Install the 'cryptography' package for token encryption.") from error
        return Fernet(self.encryption_key.encode())

    def initialize_schema(self):
        with self._connect() as connection:
            connection.execute(AUTH_SCHEMA_SQL)

    def save_oauth_grant(self, athlete, token_data):
        athlete_id = athlete.get('id')
        if not athlete_id:
            raise ValueError('Strava OAuth response did not include an athlete ID.')

        display_name = ' '.join(filter(None, [
            athlete.get('firstname'), athlete.get('lastname'),
        ])) or f'Strava athlete {athlete_id}'
        cipher = self._cipher()
        access_token = cipher.encrypt(token_data['access_token'].encode())
        refresh_token = cipher.encrypt(token_data['refresh_token'].encode())
        try:
            from psycopg.types.json import Jsonb
        except ImportError as error:
            raise RuntimeError(
                "Install the 'psycopg[binary]' package for PostgreSQL auth.") from error

        with self._connect() as connection:
            existing = connection.execute(
                'SELECT user_id FROM users WHERE strava_athlete_id = %s',
                (athlete_id,),
            ).fetchone()
            user_id = existing['user_id'] if existing else uuid.uuid4()
            user = connection.execute(
                """INSERT INTO users (
                       user_id, strava_athlete_id, username, display_name,
                       profile_picture_url, profile, last_login
                   ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (strava_athlete_id) DO UPDATE SET
                       username = EXCLUDED.username,
                       display_name = EXCLUDED.display_name,
                       profile_picture_url = EXCLUDED.profile_picture_url,
                       profile = EXCLUDED.profile,
                       updated_at = NOW(), last_login = NOW(), is_active = TRUE
                   RETURNING user_id, strava_athlete_id, username, display_name,
                             profile_picture_url""",
                (
                    user_id, athlete_id, athlete.get('username'), display_name,
                    athlete.get('profile_medium') or athlete.get('profile'),
                    Jsonb(athlete),
                ),
            ).fetchone()
            connection.execute(
                """INSERT INTO strava_tokens (
                       user_id, access_token_ciphertext,
                       refresh_token_ciphertext, expires_at, scope
                   ) VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                       refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                       expires_at = EXCLUDED.expires_at,
                       scope = EXCLUDED.scope, updated_at = NOW()""",
                (
                    user['user_id'], access_token, refresh_token,
                    int(token_data['expires_at']), token_data.get('scope'),
                ),
            )
        return dict(user)

    def get_token(self, user_id):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT access_token_ciphertext, refresh_token_ciphertext,
                          expires_at, scope
                   FROM strava_tokens WHERE user_id = %s""",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        cipher = self._cipher()
        return {
            'access_token': cipher.decrypt(
                bytes(row['access_token_ciphertext'])).decode(),
            'refresh_token': cipher.decrypt(
                bytes(row['refresh_token_ciphertext'])).decode(),
            'expires_at': int(row['expires_at']),
            'scope': row['scope'],
        }

    def update_token(self, user_id, token_data):
        cipher = self._cipher()
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE strava_tokens SET
                       access_token_ciphertext = %s,
                       refresh_token_ciphertext = %s,
                       expires_at = %s,
                       scope = COALESCE(%s, scope), updated_at = NOW()
                   WHERE user_id = %s""",
                (
                    cipher.encrypt(token_data['access_token'].encode()),
                    cipher.encrypt(token_data['refresh_token'].encode()),
                    int(token_data['expires_at']), token_data.get('scope'),
                    user_id,
                ),
            )
            if result.rowcount != 1:
                raise LookupError(f'No Strava token exists for user {user_id}.')

    def get_user(self, user_id):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT user_id, strava_athlete_id, username, display_name,
                          profile_picture_url
                   FROM users WHERE user_id = %s AND is_active = TRUE""",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None