"""
Rider Setup tab — Top-to-bottom workflow.

Power-duration chart construction lives in `_charts.py`.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.rider import (
    Rider,
    fit_power_profile,
    get_cached_strava_rider,
    save_strava_profile,
)
from app.strava_calls import get_athlete_profile
from pages_vibe.tabs import _charts, _workflow
from pages_vibe.tabs.state import BIKE_MASS_DEFAULTS, get_rider


CRR_DEFAULTS = {
    "Road": 0.004,
    "TT": 0.003,
    "Gravel": 0.008,
    "MTB": 0.012,
}


# ── Public entry point ──────────────────────────────────────────────────────

def render() -> None:
    r = get_rider()
    bike_label = "TT / Tri" if r.get('bike_type') == 'TT' else r['bike_type']

    _render_rider_identity(r)
    st.divider()

    st.subheader("1. General Characteristics")
    _render_general(r)

    st.divider()
    st.subheader("2. Power Profile")
    _render_power_profile(r)

    st.divider()
    st.subheader("3. Aerodynamic Drag (CdA)")
    _render_cda_info(r)

    st.divider()
    st.caption(
        f"**Active Profile** — {r['weight']}kg rider + "
        f"{r.get('bike_mass', BIKE_MASS_DEFAULTS[r['bike_type']])}kg bike · "
        f"{bike_label} · "
        f"CP {r['critical_power']}W · "
        f"W' {r['w_prime'] / 1000:.0f}kJ · CdA {r['cda']:.3f}m² · "
        f"W/kg {r['critical_power'] / r['weight']:.2f}"
    )
    if st.button("Continue to Optimize", type="primary", width="stretch"):
        _workflow.set_active_step('optimize')
        st.rerun()

def _render_general(r: dict) -> None:
    _workflow.apply_pending_rider_weight()
    draft_defaults = {
        'rider_general_height': float(r.get('height', 1.78)),
        'rider_general_weight': float(r.get('weight', 80.0)),
        'rider_general_bike': r.get('bike_type', 'Road'),
        'rider_general_bike_mass': float(r.get(
            'bike_mass', BIKE_MASS_DEFAULTS.get(r.get('bike_type', 'Road'), 8.5))),
        'rider_general_position': r.get('position', 'Hoods'),
        'rider_general_crr': float(r.get('crr', 0.004)),
    }
    for key, value in draft_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    col_phys, col_bike = st.columns(2)

    with col_phys:
        new_height = st.number_input(
            "Height (m)", min_value=1.40, max_value=2.10, step=0.01,
            key='rider_general_height')
        new_weight = st.number_input(
            "Weight (kg)", min_value=40.0, max_value=150.0, step=1.0,
            key='rider_general_weight')

    with col_bike:
        bike_options = ["Road", "TT", "Gravel", "MTB"]
        new_bike_type = st.selectbox(
            "Bike Type", bike_options,
            format_func=lambda bike: "TT / Tri" if bike == "TT" else bike,
            key='rider_general_bike')

        valid_positions = list(Rider.BIKE_TYPE_CDA.get(new_bike_type, {}).keys())
        if not valid_positions:
            valid_positions = ["Hoods"]

        bike_changed = new_bike_type != r.get('bike_type')
        if bike_changed:
            st.session_state.rider_general_position = valid_positions[0]
            st.session_state.rider_general_crr = CRR_DEFAULTS[new_bike_type]
            st.session_state.rider_general_bike_mass = (
                BIKE_MASS_DEFAULTS[new_bike_type])
        elif st.session_state.rider_general_position not in valid_positions:
            st.session_state.rider_general_position = valid_positions[0]

        new_position = st.selectbox(
            "Position", valid_positions, key='rider_general_position')
        new_bike_mass = st.number_input(
            "Bike Mass (kg)", min_value=5.0, max_value=25.0, step=0.5,
            help="Bike and fixed equipment mass used in the physics model",
            key='rider_general_bike_mass')
        new_crr = st.number_input(
            "Crr", min_value=0.001, max_value=0.025, step=0.001,
            format="%.3f", help="Rolling resistance",
            key='rider_general_crr')

    base_cda = Rider.BIKE_TYPE_CDA.get(new_bike_type, {}).get(new_position, 0.35)
    estimated_cda = round(base_cda * new_height / 1.75, 3)
    updated = {
        **r,
        'height': new_height,
        'weight': new_weight,
        'bike_type': new_bike_type,
        'bike_mass': new_bike_mass,
        'position': new_position,
        'crr': new_crr,
        'cda': estimated_cda,
    }
    if updated != r:
        _workflow.mark_rider_profile(updated)
        r.update(updated)
        st.rerun()

def _render_power_profile(r: dict) -> None:
    cached_profile = _get_session_rider_cache(r)
    source_options = ["Rider Type", "Manual Entry", "Strava Import"]
    default_source = "Strava Import" if cached_profile else "Rider Type"
    selected_source = st.segmented_control(
        "Power profile source",
        source_options,
        default=default_source,
        key="rider_power_source_mode",
        label_visibility="collapsed",
        width="stretch",
    )
    if selected_source == "Strava Import" and cached_profile:
        _apply_cached_strava_power(r, cached_profile)
    col_input, col_chart = st.columns([1, 1.2])

    with col_input:
        if selected_source == "Rider Type":
            with st.form("rider_type_power_form"):
                st.caption("Estimate W' based on Critical Power and rider profile.")
                cp_input = st.number_input(
                    "Critical Power (W)", 100, 500,
                    int(r['critical_power']), 5)
                r_type = st.selectbox(
                    "Rider Type",
                    ["time_trialist", "all_rounder", "sprinter"])
                calculate_type = st.form_submit_button(
                    "Calculate Profile", type="primary", width="stretch")

            if calculate_type:
                try:
                    rider_obj = Rider(
                        height=r.get('height', 1.78), weight=r['weight'],
                        bike_type=r.get('bike_type', 'Road'),
                        position=r.get('position', 'Hoods'),
                        rider_type=r_type, critical_power=cp_input)
                    _commit_power_profile(r, rider_obj, source='rider_type')
                except Exception as error:
                    st.error(f"Profile calculation failed: {error}")

        elif selected_source == "Manual Entry":
            with st.form("manual_power_form"):
                st.caption("Curve fit CP and W' from known best efforts.")
                c1, c2 = st.columns(2)
                with c1:
                    p30 = st.number_input("30s Power (W)", 0, 2000, 800, 10)
                    p60 = st.number_input("1min Power (W)", 0, 1500, 500, 10)
                    p120 = st.number_input("2min Power (W)", 0, 1000, 400, 10)
                with c2:
                    p300 = st.number_input("5min Power (W)", 0, 800, 320, 10)
                    p1200 = st.number_input("20min Power (W)", 0, 600, 270, 10)
                calculate_manual = st.form_submit_button(
                    "Fit Power Curve", type="primary", width="stretch")

            if calculate_manual:
                efforts = {30: p30, 60: p60, 120: p120,
                           300: p300, 1200: p1200}
                efforts = {duration: power for duration, power in efforts.items()
                           if power > 0}
                if len(efforts) < 2:
                    st.warning("Enter at least two non-zero efforts.")
                else:
                    try:
                        rider_obj = Rider(
                            height=r.get('height', 1.78), weight=r['weight'],
                            bike_type=r.get('bike_type', 'Road'),
                            position=r.get('position', 'Hoods'),
                            best_efforts=efforts)
                        _commit_power_profile(r, rider_obj, source='manual')
                    except Exception as error:
                        st.error(f"Power curve fit failed: {error}")

        else:
            _render_strava_status(cached_profile)

            with st.form("strava_power_form"):
                st.caption(
                    "Refresh the authenticated athlete's profile and cycling "
                    "power efforts. This always calls Strava; cached data is "
                    "shown above without a network request.")
                days_back = st.slider(
                    "Look back (days)", 30, 365, 90, 30)
                use_strava_weight = st.checkbox(
                    "Use profile weight from Strava when available", value=True)
                fetch_power = st.form_submit_button(
                    "Refresh My Strava Data", type="primary", width="stretch")

            if fetch_power:
                try:
                    with st.spinner("Refreshing your Strava profile and power efforts…"):
                        rider_obj = Rider(
                            height=r.get('height', 1.78), weight=r['weight'],
                            bike_type=r.get('bike_type', 'Road'),
                            position=r.get('position', 'Hoods'),
                            days=days_back, force_strava_refresh=True,
                            auth_user_id=st.session_state.get('auth_user_id'))
                    if not rider_obj.best_efforts or len(rider_obj.best_efforts) < 2:
                        st.warning(
                            "Strava returned fewer than two usable cycling power "
                            "efforts. Check activity visibility and power streams.")
                    else:
                        _commit_power_profile(
                            r, rider_obj,
                            use_strava_weight=use_strava_weight)
                except Exception as error:
                    st.error(f"Strava refresh failed: {error}")

    with col_chart:
        chart_options = {}
        if selected_source == "Strava Import" and cached_profile:
            athlete_name = ' '.join(filter(None, [
                cached_profile.get('athlete_first_name'),
                cached_profile.get('athlete_last_name'),
            ])) or 'Strava athlete'
            athlete_label = (
                f"{athlete_name} · Strava #{cached_profile['strava_athlete_id']}")
            refreshed = cached_profile.get('strava_last_synced_at')
            provenance = 'Cached best efforts'
            if refreshed:
                parsed = pd.to_datetime(refreshed, utc=True, errors='coerce')
                if pd.notna(parsed):
                    provenance += (
                        f" · Refreshed {parsed.strftime('%b %d, %Y')}")
            chart_options = {
                'best_efforts': cached_profile.get('best_efforts'),
                'athlete_label': athlete_label,
                'provenance': provenance,
            }
        st.plotly_chart(
            _charts.build_power_duration_curve(
                r['critical_power'], r['w_prime'], **chart_options),
            width="stretch",
            key="rider_power_duration",
            config={'displayModeBar': False},
        )


def _commit_power_profile(r: dict, rider_obj: Rider,
                          use_strava_weight: bool = False,
                          source: str | None = None) -> None:
    """Commit a successfully calculated power profile."""
    updated = r.copy()
    if rider_obj.critical_power:
        updated['critical_power'] = int(rider_obj.critical_power)
    if rider_obj.WTank and rider_obj.WTank > 0:
        updated['w_prime'] = round(rider_obj.WTank)
    if source:
        updated['best_efforts'] = (rider_obj.best_efforts or {}).copy()
        updated['power_source'] = source
    if rider_obj.strava_athlete_id:
        athlete_name = ' '.join(filter(None, [
            rider_obj.athlete_first_name,
            rider_obj.athlete_last_name,
        ]))
        updated.update({
            'strava_athlete_id': str(rider_obj.strava_athlete_id),
            'strava_name': athlete_name or None,
            'strava_weight': rider_obj.strava_weight,
            'strava_last_synced_at': rider_obj.strava_last_synced_at,
            'strava_lookback_days': rider_obj.strava_lookback_days,
            'best_efforts': rider_obj.best_efforts.copy(),
            'power_source': 'strava',
        })
        if use_strava_weight and rider_obj.strava_weight:
            updated['weight'] = rider_obj.strava_weight
    _workflow.mark_rider_profile(
        updated, rider_obj=rider_obj,
        sync_weight=bool(use_strava_weight and rider_obj.strava_athlete_id
                         and rider_obj.strava_weight))
    r.update(updated)
    st.toast("Rider profile updated")
    st.rerun()


def _apply_cached_strava_power(r: dict, profile: dict) -> None:
    """Use a sufficient cached Strava profile as the active power model."""
    efforts = profile.get('best_efforts') or {}
    if len(efforts) < 2:
        return

    fitted = fit_power_profile(efforts)
    if not fitted:
        return
    critical_power, w_prime = fitted

    athlete_name = ' '.join(filter(None, [
        profile.get('athlete_first_name'),
        profile.get('athlete_last_name'),
    ]))
    updated = {
        **r,
        'critical_power': round(float(critical_power)),
        'w_prime': round(float(w_prime)),
        'strava_athlete_id': str(profile['strava_athlete_id']),
        'strava_name': athlete_name or None,
        'strava_weight': profile.get('strava_weight'),
        'strava_last_synced_at': profile.get('strava_last_synced_at'),
        'strava_lookback_days': profile.get('strava_lookback_days'),
        'best_efforts': efforts.copy(),
        'power_source': 'strava',
    }
    if updated != r:
        _workflow.mark_rider_profile(updated)
        r.update(updated)
        st.rerun()


def _render_strava_status(profile: dict | None) -> None:
    """Render cached Strava identity, provenance, and key cycling PBs."""
    if not profile:
        st.info(
            "No Strava rider is cached yet. Refresh to verify the authenticated "
            "athlete and import power efforts.")
        return

    athlete_name = ' '.join(filter(None, [
        profile.get('athlete_first_name'),
        profile.get('athlete_last_name'),
    ])) or f"Athlete {profile['strava_athlete_id']}"
    st.markdown(f"**{athlete_name}** · Strava athlete #{profile['strava_athlete_id']}")

    synced = profile.get('strava_last_synced_at')
    synced_text = 'Refresh date unavailable'
    if synced:
        parsed = pd.to_datetime(synced, utc=True, errors='coerce')
        if pd.notna(parsed):
            synced_text = f"Last refreshed {parsed.strftime('%b %d, %Y at %H:%M UTC')}"
    lookback = profile.get('strava_lookback_days')
    provenance = synced_text
    if lookback:
        provenance += f" · {lookback}-day activity window"
    st.caption(f"{provenance} · Cached locally")

    profile_weight = profile.get('strava_weight')
    if profile_weight:
        st.caption(f"Strava profile weight: {profile_weight:.1f} kg")

    efforts = profile.get('best_efforts') or {}
    durations = ((60, '1 min'), (300, '5 min'),
                 (1200, '20 min'), (3600, '60 min'))
    columns = st.columns(4)
    for column, (duration, label) in zip(columns, durations):
        power = efforts.get(duration)
        column.metric(label, f"{power:.0f} W" if power else '—')
    if efforts:
        st.caption(
            "CP and W' are fitted from 2–30 minute best efforts. Shorter "
            "sprint PBs are shown on the graph but do not determine CP.")


def _render_rider_identity(r: dict) -> None:
    """Show whose Strava account and cached power data drive this profile."""
    profile = _get_session_rider_cache(r)
    if profile:
        athlete_name = ' '.join(filter(None, [
            profile.get('athlete_first_name'),
            profile.get('athlete_last_name'),
        ])) or f"Strava athlete {profile['strava_athlete_id']}"
        st.markdown(f"### {athlete_name}")
        checked_at = profile.get('strava_profile_checked_at')
        if checked_at:
            checked = pd.to_datetime(checked_at, utc=True, errors='coerce')
            checked_text = (
                checked.strftime('%b %d, %Y at %H:%M UTC')
                if pd.notna(checked) else 'unknown')
            st.caption(
                f"Strava athlete #{profile['strava_athlete_id']} · "
                f"Account verified {checked_text}")
        else:
            st.caption(
                f"Cached Strava athlete #{profile['strava_athlete_id']} · "
                "Account identity has not been verified in this app version")

        if profile.get('strava_weight'):
            st.caption(f"Strava profile weight: {profile['strava_weight']:.1f} kg")
        else:
            st.caption(
                "Strava did not return profile weight. Enter it manually; "
                "profile:read_all authorization may be required.")
    else:
        st.markdown("### Manual rider profile")
        st.caption("No Strava athlete has been verified or cached.")

    if st.button("Verify Strava Account", width="stretch"):
        try:
            with st.spinner("Checking the authenticated Strava account…"):
                verified = save_strava_profile(get_athlete_profile(
                    user_id=st.session_state.get('auth_user_id')))
            athlete_name = ' '.join(filter(None, [
                verified.get('athlete_first_name'),
                verified.get('athlete_last_name'),
            ]))
            _workflow.mark_strava_identity({
                'strava_athlete_id': str(verified['strava_athlete_id']),
                'strava_name': athlete_name or None,
                'strava_weight': verified.get('strava_weight'),
            })
            st.session_state.rider_power_source_mode = "Strava Import"
            st.toast(f"Verified {athlete_name or 'Strava athlete'}")
            st.rerun()
        except Exception as error:
            st.error(f"Strava account verification failed: {error}")

    st.caption(
        "Verification checks the Strava account connected to this session. "
        "It does not refresh power efforts.")


def _get_session_rider_cache(r: dict):
    """Load only the athlete cache owned by the authenticated session."""
    auth_user = st.session_state.get('auth_user')
    if auth_user:
        athlete_id = str(auth_user['strava_athlete_id'])
        return get_cached_strava_rider(athlete_id)
    return get_cached_strava_rider(r.get('strava_athlete_id'))

def _render_cda_info(r: dict) -> None:
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Estimated CdA", f"{r['cda']:.4f} m²")
        st.caption(f"Scaling factor: Height ({r.get('height', 1.78)}m) / 1.75m")
        st.info("CdA is automatically updated when you change Height, Bike Type, or Position in the General Characteristics section.")

    with c2:
        cda_rows = []
        for bk, positions_dict in Rider.BIKE_TYPE_CDA.items():
            for pos, base_val in positions_dict.items():
                cda_rows.append({"Bike": bk, "Position": pos, "Base CdA (m²)": f"{base_val:.3f}"})
        if cda_rows:
            st.dataframe(pd.DataFrame(cda_rows), width="stretch", hide_index=True)
