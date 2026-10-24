"""Strava API reads with consistent authentication and failure handling."""

from __future__ import annotations

import datetime
from typing import Any

import requests

from app.auth import get_access_token


STRAVA_API_ROOT = "https://www.strava.com/api/v3"
REQUEST_TIMEOUT_SECONDS = 15


class StravaAPIError(RuntimeError):
    """A Strava request failed and can be shown safely to the user."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class StravaScopeError(StravaAPIError):
    """The connected grant is absent, expired, or insufficient."""


class StravaRateLimitError(StravaAPIError):
    """The Strava application or read quota is exhausted."""

    def __init__(
        self,
        message: str,
        *,
        limit: str | None = None,
        usage: str | None = None,
        read_limit: str | None = None,
        read_usage: str | None = None,
    ):
        super().__init__(message, status_code=429)
        self.limit = limit
        self.usage = usage
        self.read_limit = read_limit
        self.read_usage = read_usage


def _parse_stream_response(response_json, stream_type):
    """Return one stream's values from either Strava response shape."""
    if isinstance(response_json, dict):
        stream_data = response_json.get(stream_type, {})
        return stream_data.get("data", [])
    if isinstance(response_json, list):
        for stream in response_json:
            if stream.get("type") == stream_type:
                return stream.get("data", [])
    return []


def _get_json(
    path: str,
    *,
    user_id=None,
    params: dict[str, Any] | None = None,
    operation: str,
):
    access_token = get_access_token(user_id)
    response = requests.get(
        f"{STRAVA_API_ROOT}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 200:
        return response.json()
    _raise_strava_error(response, operation)


def _raise_strava_error(response, operation: str) -> None:
    detail = _response_detail(response)
    if response.status_code == 429:
        headers = response.headers
        limit = headers.get("X-RateLimit-Limit")
        usage = headers.get("X-RateLimit-Usage")
        read_limit = headers.get("X-ReadRateLimit-Limit")
        read_usage = headers.get("X-ReadRateLimit-Usage")
        reset_time = _next_quarter_hour_utc()
        quotas = []
        if usage and limit:
            quotas.append(f"overall usage {usage} of {limit}")
        if read_usage and read_limit:
            quotas.append(f"read usage {read_usage} of {read_limit}")
        quota_text = f" ({'; '.join(quotas)})" if quotas else ""
        raise StravaRateLimitError(
            f"Strava rate limit reached while {operation}{quota_text}. "
            f"Try again after {reset_time}.",
            limit=limit,
            usage=usage,
            read_limit=read_limit,
            read_usage=read_usage,
        )
    if response.status_code in (401, 403):
        raise StravaScopeError(
            f"Strava access failed with {response.status_code} while "
            f"{operation}: {detail}. Reconnect Strava and approve the "
            "requested scopes.",
            status_code=response.status_code,
        )
    raise StravaAPIError(
        f"Strava returned {response.status_code} while {operation}: {detail}",
        status_code=response.status_code,
    )


def _response_detail(response) -> str:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        parts = []
        if payload.get("message"):
            parts.append(str(payload["message"]))
        if payload.get("errors"):
            parts.append(str(payload["errors"]))
        if parts:
            return " - ".join(parts)
    return str(getattr(response, "text", "") or "No error details returned")


def _next_quarter_hour_utc() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    minutes = 15 - (now.minute % 15)
    reset = (now + datetime.timedelta(minutes=minutes)).replace(
        second=0, microsecond=0)
    return reset.strftime("%H:%M UTC")


def fetch_segment_data(segment_id, user_id=None):
    """Fetch latitude, longitude, and altitude streams for one segment."""
    data = _get_json(
        f"/segments/{segment_id}/streams",
        user_id=user_id,
        params={"keys": "latlng,altitude", "key_by_type": "true"},
        operation=f"fetching segment {segment_id} streams",
    )
    return {
        "latlng": _parse_stream_response(data, "latlng"),
        "altitude": _parse_stream_response(data, "altitude"),
    }


def get_activities(days, per_page=100, user_id=None):
    """Fetch this athlete's activities within the requested lookback."""
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    params = {
        "after": int(start_date.timestamp()),
        "before": int(end_date.timestamp()),
        "per_page": min(per_page, 200),
    }
    all_activities = []
    page = 1
    while True:
        params["page"] = page
        activities = _get_json(
            "/athlete/activities",
            user_id=user_id,
            params=params,
            operation="fetching activities",
        )
        if not activities:
            break
        all_activities.extend(activities)
        if len(activities) < params["per_page"]:
            break
        page += 1
    return all_activities


def get_power_stream(activity_id, user_id=None):
    """Return non-null recorded watts for one activity."""
    data = _get_json(
        f"/activities/{activity_id}/streams",
        user_id=user_id,
        params={"keys": "watts", "key_by_type": "true"},
        operation=f"fetching activity {activity_id} power",
    )
    return [
        value
        for value in _parse_stream_response(data, "watts")
        if value is not None
    ]


def get_athlete_profile(user_id=None):
    """Return the authenticated Strava athlete profile."""
    return _get_json(
        "/athlete",
        user_id=user_id,
        operation="fetching the athlete profile",
    )


def get_athlete_id(user_id=None):
    """Return the authenticated athlete ID, or None for legacy callers."""
    try:
        return get_athlete_profile(user_id=user_id).get("id")
    except StravaAPIError:
        return None


def fetch_segment_details(segment_id, user_id=None):
    """Fetch one segment's metadata."""
    return _get_json(
        f"/segments/{segment_id}",
        user_id=user_id,
        operation=f"fetching segment {segment_id}",
    )


def get_activity_by_id(activity_id, include_all_efforts=False, user_id=None):
    """Fetch one detailed activity."""
    return _get_json(
        f"/activities/{activity_id}",
        user_id=user_id,
        params={"include_all_efforts": str(include_all_efforts).lower()},
        operation=f"fetching activity {activity_id}",
    )
