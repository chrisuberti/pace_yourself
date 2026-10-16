---
name: strava-data-path
description: Strava OAuth, segment/activity fetch, token refresh, and the path from API → DB → session state. Use when tokens expire, fetches return empty, or a new Strava endpoint needs wiring.
---

# Strava Data Path

## Flow (canonical)
```
Strava authorize callback
   │
   ▼
PostgreSQL users + encrypted strava_tokens
   │
   ▼
app/auth.py ──► per-user token lookup / refresh
   │
   ▼
app/strava_calls.py ──► fetch_segment_data / fetch_segment_details / get_activities / get_power_stream
   │
   ▼
app/database.py (CourseDatabase / get_course_db) ──► upsert by strava_segment_id
   │
   ▼
pages_vibe/tabs/tab_course.py::_persist_strava_segment   (single upsert helper)
app/rider.py ──► athlete identity + best-effort cache/provenance
pages_vibe/tabs/tab_rider.py::_render_strava_import      (best-efforts → CP / W' / CdA)
```

## Authentication boundary
- PostgreSQL `users` owns identity and `strava_tokens` stores encrypted grants
   through a cascading `user_id` foreign key.
- Every Strava client operation receives the current Streamlit session's
   `auth_user_id`; there is no deployment-global athlete token.
- `Verify Strava Account` fetches `/athlete` and updates profile identity only.
- `Refresh My Strava Data` bypasses cached efforts and performs activity/power
   API calls. These actions keep separate profile-check and PB-refresh times.
- Never trigger either action on an ordinary widget rerun.
- Course, rider, and result ownership must follow `user_id` during their staged
   migration from SQLite to PostgreSQL.

## Required env vars
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI`
- `DATABASE_URL`
- `TOKEN_ENCRYPTION_KEY`

`app/auth.py` handles per-user token refresh and persists rotated credentials.

## Common failure modes
| Symptom | Likely cause | Fix |
|---|---|---|
| 401 Unauthorized | User grant was revoked or refresh failed | Log out, reconnect Strava, and inspect the per-user grant. |
| "No stream data returned" | Segment has no GPS streams or rate-limited | Verify segment id; wait out 15-min rate window. |
| `get_activities() missing 'days'` | Calling stale signature | Use canonical signature: `get_activities(days=...)`. |
| Duplicate course on each fetch | Upsert helper bypassed | Use `tab_course._persist_strava_segment(...)` only. |
| Athlete has no weight | Token lacks `profile:read_all`, or Strava has no weight | Keep local rider weight; treat profile weight as optional. |
| Wrong athlete appears | Session is bound to the wrong user | Log out and reconnect the intended Strava account. |

## Key files
- [app/auth.py](../../app/auth.py)
- [app/auth_store.py](../../app/auth_store.py)
- [app/strava_calls.py](../../app/strava_calls.py)
- [app/database.py](../../app/database.py) — `CourseDatabase`, `get_course_db`
- [pages_vibe/tabs/tab_course.py](../../pages_vibe/tabs/tab_course.py) — `_render_strava_fetch`, `_persist_strava_segment`
- [pages_vibe/tabs/tab_rider.py](../../pages_vibe/tabs/tab_rider.py) — `_render_strava_import`

## Tests
Canonical API tests: [tests/test_strava_calls.py](../../tests/test_strava_calls.py).
Rider cache/provenance tests: [tests/tests/test_rider_strava_cache.py](../../tests/tests/test_rider_strava_cache.py).
A stale duplicate at `tests/tests/test_strava_calls.py` exists; do not extend it — slated for removal.

## Don't
- Don't hit the Strava API from a chart builder, optimizer, or notebook used by tests.
- Don't store raw tokens in code, `.env`, session state, logs, or UI.
- Don't write to `vibe_*` session keys outside `_workflow.mark_*` helpers.
