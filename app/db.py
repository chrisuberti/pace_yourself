"""Shared PostgreSQL connection helper for application data stores.

Mirrors the connection style established in ``app/auth_store.py`` so every store
opens a psycopg connection with dict-row results and lazy-imports the driver.
"""

from __future__ import annotations

import math
import os


def _sanitize_json(value):
    """Recursively replace NaN/Infinity (invalid in JSON) with None for JSONB."""
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {key: _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json(item) for item in value]
    return value



def get_database_url() -> str:
    """Return the configured PostgreSQL URL or raise a clear error."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required. Start local Postgres with "
            "`docker compose up -d db` or set DATABASE_URL in the environment."
        )
    return url


def connect(database_url: str | None = None):
    """Open a psycopg connection with dict rows. Lazy-imports psycopg."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError(
            "Install the 'psycopg[binary]' package for PostgreSQL access."
        ) from error
    return psycopg.connect(database_url or get_database_url(), row_factory=dict_row)


def as_jsonb(value):
    """Adapt a Python value as a JSONB query parameter (NaN/Inf coerced to null)."""
    try:
        from psycopg.types.json import Jsonb
    except ImportError as error:  # pragma: no cover - environment guard
        raise RuntimeError(
            "Install the 'psycopg[binary]' package for PostgreSQL access."
        ) from error
    return Jsonb(_sanitize_json(value))
