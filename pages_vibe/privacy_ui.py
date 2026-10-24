"""User-facing privacy, consent, and support information."""

from __future__ import annotations

import os

import streamlit as st


DEFAULT_SUPPORT_URL = "https://github.com/chrisuberti/pace_yourself/issues"


def render_privacy_notice() -> None:
    """Render the public privacy and Strava-data notice."""
    st.title("Privacy & Strava data use")
    st.markdown(
        """
Pace Yourself can be used without Strava. Guest sessions may upload a course,
use the shared non-Strava course library, enter rider details, and run an
optimization.

When you connect Strava, the app collects:

- Your Strava athlete ID, display name, profile image, and optional weight.
- Your cycling activities and power streams when you explicitly refresh PBs.
- Segment geometry when you explicitly fetch a Strava segment.
- Derived CP, W′, rider settings, and optimization results.

Strava access and refresh tokens are encrypted in PostgreSQL. Rider data,
Strava-fetched courses, and optimization results are private to your application
user. Ordinary page reruns use cached data and do not call Strava.

Use **Log out** to end only the browser session. Use **Disconnect Strava and
delete my data** to revoke the grant and delete your encrypted tokens, cached
Strava data, private courses, rider profile, and private results. The shared
non-Strava course library is not deleted because it does not contain your
private Strava data.
"""
    )
    st.markdown(
        f"""
### Support and external policies

- [Pace Yourself support]({_support_url()})
- [Manage apps connected to Strava](https://www.strava.com/settings/apps)
- [Strava Privacy Policy](https://www.strava.com/legal/privacy)
- [Strava API Policy](https://www.strava.com/legal/api_policy)
"""
    )
    st.link_button("Return to Race Lab", "?", width="stretch")


def render_privacy_sidebar() -> None:
    """Keep privacy and support links visible throughout the app."""
    with st.sidebar.expander("Privacy, consent & support"):
        st.markdown(
            """
Strava connection is optional. Imported athlete data, Strava courses, and
results are private to the connected user.
"""
        )
        st.markdown(
            f"""
- [Privacy & data use](?view=privacy)
- [Support]({_support_url()})
- [Connected apps on Strava](https://www.strava.com/settings/apps)
"""
        )


def render_oauth_consent_summary() -> None:
    """Explain requested OAuth scopes before the user leaves for Strava."""
    with st.expander("What Strava access is requested and why"):
        st.markdown(
            """
- **read** — verify your athlete identity and fetch a segment you request.
- **activity:read_all** — read your cycling activities and power streams only
  when you click **Refresh My Strava Data**.
- **profile:read_all** — read optional profile weight; the app continues with
  manual weight if you do not grant it.

You can use guest mode instead. You may withdraw consent at any time with
**Disconnect Strava and delete my data**.
"""
        )


def _support_url() -> str:
    return os.getenv("APP_SUPPORT_URL", DEFAULT_SUPPORT_URL)
