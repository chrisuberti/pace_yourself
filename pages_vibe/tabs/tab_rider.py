"""
Rider Setup tab — moved from the standalone 02_Rider_Setup.py page.

Quick config, advanced CdA estimation, Strava import, and power-duration curve.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from app.rider import Rider
from pages_vibe.tabs.state import get_rider


def render():
    """Render the Rider Setup tab content."""
    r = get_rider()

    tab_quick, tab_advanced, tab_strava = st.tabs(
        ["Quick Setup", "Advanced", "Strava Import"]
    )

    with tab_quick:
        _render_quick_setup(r)

    with tab_advanced:
        _render_advanced(r)

    with tab_strava:
        _render_strava_import(r)

    # ── Footer: active profile summary ───────────────────────────────────
    st.divider()
    st.caption(
        f"**Active Profile** — {r['weight']}kg · CP {r['critical_power']}W · "
        f"W' {r['w_prime']/1000:.0f}kJ · CdA {r['cda']:.3f}m² · "
        f"W/kg {r['critical_power']/r['weight']:.2f}"
    )


# ── Quick Setup ─────────────────────────────────────────────────────────────

def _render_quick_setup(r: dict):
    col1, col2 = st.columns(2)

    with col1:
        r['weight'] = st.number_input(
            "Total Weight (kg)", 50, 150, r['weight'], 1,
            help="Rider + bike + gear", key="qs_weight")
        r['critical_power'] = st.number_input(
            "CP (W)", 100, 500, r['critical_power'], 5,
            help="~1hr max sustainable", key="qs_cp")
        r['crr'] = st.number_input(
            "Crr", 0.001, 0.010, r['crr'], 0.001,
            help="Rolling resistance coefficient", key="qs_crr")

    with col2:
        r['w_prime'] = st.number_input(
            "W' (J)", 5000, 50000, r['w_prime'], 1000,
            help="Anaerobic capacity", key="qs_wp")
        r['cda'] = st.number_input(
            "CdA (m²)", 0.15, 0.60, r['cda'], 0.01,
            help="Drag coefficient × frontal area", key="qs_cda")

    st.session_state.vibe_rider = r

    # CdA reference card
    st.divider()
    st.caption("Typical CdA reference")
    ref_data = pd.DataFrame([
        {"Position": "Aero bars (TT)", "CdA": "0.22–0.25"},
        {"Position": "Drops", "CdA": "0.28–0.32"},
        {"Position": "Hoods", "CdA": "0.32–0.38"},
        {"Position": "Upright / MTB", "CdA": "0.38–0.45"},
    ])
    st.dataframe(ref_data, width="stretch", hide_index=True)

    # Power-duration curve
    _render_power_duration_curve(r['critical_power'], r['w_prime'])


# ── Advanced CdA Estimation ─────────────────────────────────────────────────

def _render_advanced(r: dict):
    col_body, col_bike = st.columns(2)

    with col_body:
        height = st.number_input("Height (m)", 1.40, 2.10, 1.78, 0.01,
                                 key="adv_height")
        weight_adv = st.number_input("Weight (kg)", 40, 150, r['weight'], 1,
                                     key="adv_weight")

    with col_bike:
        bike_type = st.selectbox("Bike Type", ["Road", "TT", "Gravel", "MTB"],
                                 key="adv_bike")
        valid_positions = list(Rider.BIKE_TYPE_CDA.get(bike_type, {}).keys())
        if not valid_positions:
            valid_positions = ["Hoods"]
        position = st.selectbox("Position", valid_positions, key="adv_pos")

    col_cp, col_type = st.columns(2)
    with col_cp:
        cp_adv = st.number_input("CP (W)", 100, 500, r['critical_power'], 5,
                                 key="adv_cp")
    with col_type:
        rider_type = st.selectbox(
            "Rider Type", ["time_trialist", "all_rounder", "sprinter"],
            help="Affects W' estimation from CP", key="adv_type")

    if st.button("Calculate", type="primary", key="adv_calc"):
        try:
            rider_obj = Rider(
                height=height, weight=weight_adv,
                bike_type=bike_type, position=position,
                rider_type=rider_type, critical_power=cp_adv,
            )
            st.session_state.vibe_rider_obj = rider_obj

            # Push to shared config
            r['weight'] = weight_adv
            r['critical_power'] = cp_adv
            r['cda'] = rider_obj.CdA
            if rider_obj.WTank and rider_obj.WTank > 0:
                r['w_prime'] = int(rider_obj.WTank)
            st.session_state.vibe_rider = r

            st.toast("Profile updated ✓")
            st.rerun()
        except Exception as e:
            st.error(f"Calculation failed: {e}")

    # ── Show computed results ────────────────────────────────────────────
    rider_obj = st.session_state.get('vibe_rider_obj')
    if rider_obj:
        st.divider()
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("CdA", f"{rider_obj.CdA:.4f} m²")
        with mc2:
            st.metric("CP", f"{r['critical_power']} W")
        with mc3:
            st.metric("W'", f"{r['w_prime']:,} J")
        with mc4:
            st.metric("W/kg", f"{r['critical_power'] / r['weight']:.2f}")

        # CdA comparison across bike types
        st.caption("CdA across bike types & positions")
        cda_rows = []
        for bk, positions_dict in Rider.BIKE_TYPE_CDA.items():
            for pos in positions_dict.keys():
                try:
                    temp = Rider(height=rider_obj.height, weight=rider_obj.weight,
                                 bike_type=bk, position=pos,
                                 rider_type=rider_type, critical_power=cp_adv)
                    cda_rows.append({"Bike": bk, "Position": pos,
                                     "CdA (m²)": f"{temp.CdA:.4f}"})
                except Exception:
                    pass
        if cda_rows:
            st.dataframe(pd.DataFrame(cda_rows), width="stretch",
                         hide_index=True)

        # Power-duration curve with computed W'
        _render_power_duration_curve(r['critical_power'], r['w_prime'])


# ── Strava Import ────────────────────────────────────────────────────────────

def _render_strava_import(r: dict):
    st.caption("Pull best efforts from Strava to calculate CP and W'.")

    days_back = st.slider("Look back (days)", 30, 365, 90, 30,
                          key="strava_days")

    if st.button("Fetch from Strava", type="primary", key="strava_fetch"):
        try:
            with st.spinner("Fetching from Strava…"):
                rider_obj = Rider(
                    height=1.78, weight=r['weight'], days=days_back,
                )
                st.session_state.vibe_rider_obj = rider_obj

                if rider_obj.critical_power:
                    r['critical_power'] = int(rider_obj.critical_power)
                if rider_obj.WTank and rider_obj.WTank > 0:
                    r['w_prime'] = int(rider_obj.WTank)
                if rider_obj.CdA:
                    r['cda'] = rider_obj.CdA
                st.session_state.vibe_rider = r

                st.toast("Strava data imported ✓")
                st.rerun()
        except Exception as e:
            st.error(f"Strava import failed: {e}")
            st.info("Make sure STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, "
                    "and tokens are set in `.env`.")

    # Show best efforts if available
    rider_obj = st.session_state.get('vibe_rider_obj')
    if (rider_obj and hasattr(rider_obj, 'best_efforts')
            and rider_obj.best_efforts):
        st.divider()
        st.caption("Best Efforts")
        be = rider_obj.best_efforts
        be_df = pd.DataFrame([
            {"Duration": f"{int(d)}s" if d < 60 else f"{d/60:.0f} min",
             "Power (W)": f"{p:.0f}"}
            for d, p in sorted(be.items())
        ])
        st.dataframe(be_df, width="stretch", hide_index=True)


# ── Shared visualisation ────────────────────────────────────────────────────

def _render_power_duration_curve(cp: int, w_prime: int):
    """Power-duration curve from the CP + W' model."""
    st.divider()
    st.caption("Power-Duration Curve (CP + W' model)")

    durations = np.array([5, 10, 15, 30, 60, 120, 180, 300,
                          600, 900, 1200, 1800, 3600])
    powers = cp + w_prime / durations

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=durations, y=powers,
        mode='lines+markers',
        line=dict(color='#e67e22', width=2),
        name='Power-Duration',
        hovertemplate='%{x}s → %{y:.0f}W<extra></extra>',
    ))
    fig.add_hline(y=cp, line=dict(color='red', dash='dot'),
                  annotation_text=f"CP = {cp}W")
    fig.update_xaxes(
        type='log', title='Duration',
        tickvals=[5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
        ticktext=['5s', '10s', '30s', '1m', '2m', '5m', '10m',
                  '20m', '30m', '1hr'],
    )
    fig.update_yaxes(title='Power (W)')
    fig.update_layout(
        height=350, template='plotly_dark',
        margin=dict(l=50, r=30, t=20, b=40), showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")
