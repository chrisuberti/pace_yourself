"""
Optimization & Results tab — controls, run-orchestration, and result display.

Chart construction lives in `_charts.py`; workflow gating and state writes
go through `_workflow.py`. This module contains only flow control and the
Streamlit-specific result layout.
"""
from __future__ import annotations

import streamlit as st

from app.course import Course
from app.optimization import (
    CourseOptimizer,
    W_PRIME_BUDGET_CEILING,
    create_course_segments_from_course,
)
from pages_vibe.tabs import _charts, _workflow
from pages_vibe.tabs.state import (
    BIKE_MASS_DEFAULTS,
    get_course,
    get_results,
    get_rider,
)


# ── Public entry point ──────────────────────────────────────────────────────

def render() -> None:
    if not _workflow.require_segmentation():
        return

    course: Course = get_course()
    r = get_rider()
    results = get_results()

    _render_controls(course, r, has_results=results is not None)
    if results is None:
        st.info("Review the rider and segmentation summary, then run the optimization.")
        return

    st.divider()
    _render_summary_metrics(results)
    st.plotly_chart(_charts.build_results_chart(results, r, course),
                    width="stretch")
    _render_pacing_card(results, r)
    _render_strategy_table(results, r)
    _render_export(results)


# ── Controls ────────────────────────────────────────────────────────────────

def _render_controls(course: Course, r: dict, has_results: bool) -> None:
    """Render the explicit optimization action."""
    with st.form("optimization_form"):
        action = "Re-optimize" if has_results else "Optimize Course"
        run_opt = st.form_submit_button(
            action, type="primary", width="stretch")

    if run_opt:
        _run_compare(course, r)


# ── Runners (split for clarity; _run_compare orchestrates) ──────────────────

def _make_optimizer(r: dict) -> CourseOptimizer:
    bike_mass = r.get(
        'bike_mass', BIKE_MASS_DEFAULTS.get(r.get('bike_type', 'Road'), 8.5))
    return CourseOptimizer(critical_power=r['critical_power'],
                           w_prime=r['w_prime'],
                           mass=r['weight'] + bike_mass,
                           cda=r['cda'],
                           crr=r['crr'])


def _run_constant(optimizer: CourseOptimizer, course: Course,
                  opt_segments) -> dict:
    """Constant-power optimization + detailed sim. Returns one strategy dict."""
    const_power, const_time, const_results_df = optimizer.optimize_constant_power(
        opt_segments, target_w_utilization=W_PRIME_BUDGET_CEILING)
    const_detailed, const_detailed_time, _ = optimizer.simulate_course_detailed(
        course=course, course_segments=const_results_df,
        power_strategy=const_power)
    return {
        'power': const_power,
        'time': const_time,
        'results_df': const_results_df,
        'detailed': const_detailed,
        'detailed_time': const_detailed_time,
    }


def _run_variable(optimizer: CourseOptimizer, course: Course,
                  opt_segments, baseline_power: float) -> dict:
    """Variable pacing optimization + detailed sim. Returns one strategy dict."""
    var_results_df, var_time, var_analysis = optimizer.optimize_variable_pacing(
        opt_segments,
        target_w_utilization=W_PRIME_BUDGET_CEILING,
        baseline_power=baseline_power)
    # Build power_map keyed by segment_id (cluster label) so the detailed sim
    # can look up the right power for each cluster via _assign_powers_to_points.
    # For equal-seg (no segment_id) fall back to row-index keying.
    if 'segment_id' in var_results_df.columns:
        power_map = (var_results_df.groupby('segment_id')['target_power']
                     .first().to_dict())
    else:
        power_map = {i: p for i, p in enumerate(var_results_df['target_power'].tolist())}
    var_detailed, var_detailed_time, _ = optimizer.simulate_course_detailed(
        course=course, course_segments=var_results_df,
        power_strategy=power_map)
    return {
        'time': var_time,
        'results_df': var_results_df,
        'analysis': var_analysis,
        'power_map': power_map,
        'detailed': var_detailed,
        'detailed_time': var_detailed_time,
    }


def _run_compare(course: Course, r: dict) -> None:
    """Run constant + variable pacing and persist via _workflow.mark_results."""
    optimizer = _make_optimizer(r)
    opt_segments = create_course_segments_from_course(course)

    try:
        with st.spinner("Optimizing — this may take a moment…"):
            constant = _run_constant(optimizer, course, opt_segments)

            variable = _run_variable(
                optimizer, course, opt_segments,
                baseline_power=constant['power'])

        _workflow.mark_results(
            {'constant': constant, 'variable': variable},
            params={},
        )
        st.rerun()

    except Exception as e:
        st.error(f"Optimization failed: {e}")
        import traceback
        with st.expander("Details"):
            st.code(traceback.format_exc())


# ── Summary metrics ─────────────────────────────────────────────────────────

def _render_summary_metrics(results: dict) -> None:
    """Top metric row. Compare-both path shown when both strategies present."""
    has_c = 'constant' in results
    has_v = 'variable' in results

    if has_c and has_v:
        c_time = results['constant']['detailed_time']
        v_time = results['variable']['detailed_time']
        delta = c_time - v_time
        faster = "Variable" if delta > 0 else "Constant"

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Constant Power", f"{results['constant']['power']:.0f} W")
        with m2:
            st.metric("Constant Time", f"{c_time/60:.1f} min")
        with m3:
            avg_var = results['variable']['results_df']['target_power'].mean()
            st.metric("Variable Avg", f"{avg_var:.0f} W")
        with m4:
            st.metric("Variable Time", f"{v_time/60:.1f} min",
                      delta=f"{abs(delta):.1f}s ({faster} faster)",
                      delta_color="normal" if delta > 0 else "inverse")
        return

    r = get_rider()
    if has_c:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Optimal Power", f"{results['constant']['power']:.0f} W")
        with m2:
            st.metric("Race Time",
                      f"{results['constant']['detailed_time']/60:.1f} min")
        with m3:
            wkg = results['constant']['power'] / r['weight']
            st.metric("W/kg", f"{wkg:.2f}")
        return

    if has_v:
        m1, m2, m3 = st.columns(3)
        avg_var = results['variable']['results_df']['target_power'].mean()
        with m1:
            st.metric("Avg Power", f"{avg_var:.0f} W")
        with m2:
            st.metric("Race Time",
                      f"{results['variable']['detailed_time']/60:.1f} min")
        with m3:
            wkg = avg_var / r['weight']
            st.metric("W/kg", f"{wkg:.2f}")


# ── Pacing card ─────────────────────────────────────────────────────────────

def _render_pacing_card(results: dict, r: dict) -> None:
    """Compact, rider-digestible 'one power per zone' summary.

    Shown only when the strategy has a handful of recurring zones (Pacing Zones
    or Clustering) — the whole point of those methods is a rule you can hold in
    your head. Each zone's label is derived from its mean gradient.
    """
    if 'variable' not in results:
        return
    vr = results['variable'].get('results_df')
    if vr is None or 'segment_id' not in vr.columns or 'target_power' not in vr.columns:
        return

    from app.course import BAND_LABELS, BAND_COLORS, classify_gradient_band

    cp = r['critical_power']
    zones = (vr.groupby('segment_id')
               .agg(power=('target_power', 'first'),
                    grad=('gradient', 'mean'),
                    dist=('distance', 'sum'))
               .reset_index())
    # Only a digestible number of zones; otherwise the card defeats its purpose.
    if not (1 < len(zones) <= 6):
        return

    zones['band'] = zones['grad'].apply(lambda g: classify_gradient_band(g * 100))
    zones = zones.sort_values('grad')  # descents → climbs, left to right

    st.markdown("#### 🎯 Your pacing rule")
    cols = st.columns(len(zones))
    for col, (_, z) in zip(cols, zones.iterrows()):
        label = BAND_LABELS.get(z['band'], 'Zone')
        color = BAND_COLORS.get(z['band'], '#888')
        delta = z['power'] - cp
        with col:
            st.markdown(
                f"<span style='color:{color};font-weight:600'>● {label}</span>"
                f"<br><span style='font-size:0.8em;color:#aaa'>"
                f"{z['grad']*100:+.1f}% · {z['dist']/1000:.1f} km</span>",
                unsafe_allow_html=True)
            st.metric(label="zone", value=f"{z['power']:.0f} W",
                      delta=f"{delta:+.0f} vs CP", delta_color="off",
                      label_visibility="collapsed")


# ── Strategy table ──────────────────────────────────────────────────────────

def _render_strategy_table(results: dict, r: dict) -> None:
    if 'variable' not in results:
        return

    cp = r['critical_power']

    with st.expander("📊 Segment Power Strategy"):
        vr = results['variable']['results_df'].copy()

        cols_to_show: dict[str, str] = {}
        if 'segment' in vr.columns:
            cols_to_show['segment'] = 'Seg'
        if 'target_power' in vr.columns:
            vr['above_cp'] = vr['target_power'] - cp
            vr['zone'] = vr['above_cp'].apply(
                lambda x: "🔴 Above" if x > 0 else "🟢 Below")
            cols_to_show['target_power'] = 'Power (W)'
            cols_to_show['above_cp'] = 'vs CP (W)'
        if 'gradient' in vr.columns:
            vr['grad_pct'] = vr['gradient'] * 100
            cols_to_show['grad_pct'] = 'Grade (%)'
        if 'distance' in vr.columns:
            vr['dist_km'] = vr['distance'] / 1000
            cols_to_show['dist_km'] = 'Dist (km)'
        if 'time' in vr.columns:
            cols_to_show['time'] = 'Time (s)'
        if 'w_remaining' in vr.columns:
            vr['w_rem_kj'] = vr['w_remaining'] / 1000
            cols_to_show['w_rem_kj'] = "W' (kJ)"
        if 'zone' in vr.columns:
            cols_to_show['zone'] = 'Zone'

        avail = [c for c in cols_to_show if c in vr.columns]
        display_df = vr[avail].rename(columns=cols_to_show)
        st.dataframe(display_df, width="stretch", hide_index=True)

        if all(c in vr.columns for c in ['target_power', 'time', 'w_remaining']):
            above = vr[vr['target_power'] > cp]
            below = vr[vr['target_power'] <= cp]
            w_spent = (above['w_used_segment'].sum() / 1000
                       if 'w_used_segment' in above.columns else 0)
            w_recov = sum(
                (cp - row['target_power']) * row['time']
                for _, row in below.iterrows()) / 1000
            final_util = (
                1 - vr.iloc[-1]['w_remaining'] / r['w_prime']) * 100

            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                st.metric("W' Spent", f"{w_spent:.1f} kJ")
            with fc2:
                st.metric("W' Recovered", f"{w_recov:.1f} kJ")
            with fc3:
                st.metric("Final Utilization", f"{final_util:.1f}%")


# ── Export ───────────────────────────────────────────────────────────────────

def _render_export(results: dict) -> None:
    has_c = 'constant' in results
    has_v = 'variable' in results
    if not (has_c or has_v):
        return

    with st.expander("💾 Export"):
        ref_key = 'variable' if has_v else 'constant'
        csv = results[ref_key]['detailed'].to_csv(index=False)
        st.download_button(
            "Download Detailed Results (CSV)", csv,
            "race_lab_results.csv", "text/csv",
            width="stretch")
