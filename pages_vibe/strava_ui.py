"""Shared presentation for actionable Strava API failures."""

from __future__ import annotations

import streamlit as st

from app.auth import AuthenticationRequired, InsufficientScope
from app.strava_calls import (
    StravaAPIError,
    StravaRateLimitError,
    StravaScopeError,
)


def render_strava_failure(error: Exception, action: str) -> None:
    """Render scope, authentication, quota, and API failures distinctly."""
    if isinstance(error, StravaRateLimitError):
        st.error(f"{action} is temporarily unavailable: {error}")
        st.info(
            "Strava quotas are shared by all app users. Cached data and manual "
            "inputs remain available without another API request.")
    elif isinstance(
            error,
            (StravaScopeError, InsufficientScope, AuthenticationRequired)):
        st.error(f"{action} needs renewed Strava access: {error}")
        st.info(
            "Use **Reconnect with Strava** in the page footer and approve the "
            "requested scopes.")
    elif isinstance(error, StravaAPIError):
        st.error(f"{action} failed: {error}")
        st.info("Try again later or continue with cached/manual data.")
    else:
        st.error(f"{action} failed: {error}")
