"""
Optimization & Results tab — run optimization, display charts and strategy.

Combines the optimization controls and results visualization from the
original Race Lab monolith into a single focused tab.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.course import Course
from app.optimization import CourseOptimizer, create_course_segments_from_course
from pages_vibe.tabs.state import get_course, get_rider, get_results


def render():
    """Render the Optimization tab content."""
    course: Course = get_course()
    r = get_rider()

    if course is None:
        st.info("Load a course in the **Course** tab first.")
        return

    if not st.session_state.get('vibe_segmentation_applied'):
        st.info("Apply a segmentation in the **Segment** tab first.")
        return

    if (not hasattr(course, 'course_segments')
            or course.course_segments is None
            or course.course_segments.empty):
        st.warning("No segments found. Go back to the **Segment** tab.")
        return

    # ── Optimization controls ────────────────────────────────────────────
    _render_controls(course, r)

    # ── Auto-run on first visit (no results yet) ────────────────────────
    results = get_results()
    if results is None:
        _run_optimization(course, r)
        results = get_results()
        if results is None:
            return

    st.divider()
    _render_summary_metrics(results, r)
    _render_results_chart(results, r, course)
    _render_strategy_table(results, r)
    _render_export(results)


# ── Optimization controls ───────────────────────────────────────────────────

def _render_controls(course: Course, r: dict):
    """W' target, aggression, and re-run button. Always compares both strategies."""
    col1, col2, col3 = st.columns([1, 1, 0.7])

    with col1:
        w_util = st.slider(
            "W' Target (%)", 50, 95, 85, 5,
            help="Target anaerobic capacity usage") / 100
    with col2:
        aggressive = st.slider(
            "Climb Aggression", 1.0, 2.0, 1.2, 0.1,
            help="Power multiplier on climbs vs CP")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_opt = st.button("🔄 Re-optimize", type="primary",
                            width="stretch")

    # Store slider values in session state for auto-run to pick up
    st.session_state['_opt_w_util'] = w_util
    st.session_state['_opt_aggressive'] = aggressive

    if run_opt:
        _run_optimization(course, r, w_util=w_util, aggressive=aggressive)


def _run_optimization(course: Course, r: dict,
                      w_util: float = None, aggressive: float = None):
    """Execute Compare Both optimization, store results in session state."""
    if w_util is None:
        w_util = st.session_state.get('_opt_w_util', 0.85)
    if aggressive is None:
        aggressive = st.session_state.get('_opt_aggressive', 1.2)

    optimizer = CourseOptimizer(
        critical_power=r['critical_power'], w_prime=r['w_prime'],
    )
    opt_segments = create_course_segments_from_course(course)
    results = {}

    try:
        with st.spinner("Optimizing — this may take a moment…"):

            # ── Constant power ───────────────────────────────────────────
            const_power, const_time, const_results_df = \
                optimizer.optimize_constant_power(
                    opt_segments, target_w_utilization=w_util)
            results['constant'] = {
                'power': const_power, 'time': const_time,
                'results_df': const_results_df,
            }
            const_detailed, const_detailed_time, _ = \
                optimizer.simulate_course_detailed(
                    course=course, course_segments=const_results_df,
                    power_strategy=const_power)
            results['constant']['detailed'] = const_detailed
            results['constant']['detailed_time'] = const_detailed_time

            # ── Variable pacing (matched W' utilization) ─────────────────
            _, _, const_w_rem, _ = optimizer.simulate_course_time(
                results['constant']['power'], opt_segments)
            matched_util = 1 - (const_w_rem / r['w_prime'])

            var_results_df, var_time, var_analysis = \
                optimizer.optimize_variable_pacing(
                    opt_segments,
                    target_w_utilization=matched_util,
                    aggressive_factor=aggressive)
            power_map = {i: p for i, p in enumerate(
                var_results_df['target_power'].tolist())}

            var_detailed, var_detailed_time, _ = \
                optimizer.simulate_course_detailed(
                    course=course, course_segments=var_results_df,
                    power_strategy=power_map)
            results['variable'] = {
                'time': var_time, 'results_df': var_results_df,
                'analysis': var_analysis, 'power_map': power_map,
                'detailed': var_detailed,
                'detailed_time': var_detailed_time,
            }

        st.session_state.vibe_optimization_results = results
        st.rerun()

    except Exception as e:
        st.error(f"Optimization failed: {e}")
        import traceback
        with st.expander("Details"):
            st.code(traceback.format_exc())


# ── Summary metrics ─────────────────────────────────────────────────────────

def _render_summary_metrics(results: dict, r: dict):
    has_const = 'constant' in results
    has_var = 'variable' in results

    if has_const and has_var:
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

    elif has_const:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Optimal Power", f"{results['constant']['power']:.0f} W")
        with m2:
            st.metric("Race Time",
                      f"{results['constant']['detailed_time']/60:.1f} min")
        with m3:
            wkg = results['constant']['power'] / r['weight']
            st.metric("W/kg", f"{wkg:.2f}")

    elif has_var:
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


# ── Results chart ────────────────────────────────────────────────────────────

def _render_results_chart(results: dict, r: dict, course: Course):
    fig = build_results_chart(results, r, course)
    st.plotly_chart(fig, width="stretch")


def build_results_chart(results: dict, rider_config: dict,
                        course_obj: Course) -> go.Figure:
    """Multi-panel Plotly chart.

    Panel 1: Power (left axis) + Elevation (right axis) with terrain colors
    Panel 2: Time delta (Compare Both only)
    Panel 3: W' balance
    """
    has_c = 'constant' in results
    has_v = 'variable' in results
    cp = rider_config['critical_power']

    ref = results.get('variable', results.get('constant'))
    det = ref['detailed']
    dist_km = det['cumulative_distance'] / 1000
    altitude = det['altitude']

    # Total work annotation text
    work_annotations = []
    if has_c:
        c_det = results['constant']['detailed']
        const_work_kj = (c_det['power'] * c_det['time']).sum() / 1000
        work_annotations.append(f"Const: {const_work_kj:.1f} kJ")
    if has_v:
        v_det = results['variable']['detailed']
        var_work_kj = (v_det['power'] * v_det['time']).sum() / 1000
        work_annotations.append(f"Var: {var_work_kj:.1f} kJ")

    n_rows = 3 if (has_c and has_v) else 2
    row_heights = [0.5, 0.25, 0.25] if n_rows == 3 else [0.6, 0.4]
    subtitles = (["Power & Elevation", "Time Delta", "W' Balance"]
                 if n_rows == 3 else ["Power & Elevation", "W' Balance"])
    specs = [[{"secondary_y": True}]]
    for _ in range(n_rows - 1):
        specs.append([{"secondary_y": False}])

    fig = make_subplots(
        rows=n_rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=row_heights,
        subplot_titles=subtitles, specs=specs,
    )

    # ── Panel 1: Elevation (secondary y) ─────────────────────────────────
    _add_elevation_traces(fig, course_obj, det, dist_km, altitude)

    # ── Panel 1: Power traces (primary y) ────────────────────────────────
    if has_c:
        c_det = results['constant']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=c_det['power'],
            line=dict(color='#3498db', width=1.8, dash='dash', shape='hv'),
            name="Constant Power", opacity=0.9,
            hovertemplate='%{y:.0f}W<extra>Constant</extra>',
        ), row=1, col=1, secondary_y=False)

    if has_v:
        v_det = results['variable']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=v_det['power'],
            line=dict(color='#e67e22', width=1.8, shape='hv'),
            name="Variable Pacing", opacity=0.9,
            hovertemplate='%{y:.0f}W<extra>Variable</extra>',
        ), row=1, col=1, secondary_y=False)

    fig.add_hline(y=cp, line=dict(color='red', width=1, dash='dot'),
                  annotation_text=f"CP = {cp}W",
                  annotation_font=dict(color='red', size=10),
                  row=1, col=1, secondary_y=False)

    work_text = "Total Work — " + "  |  ".join(work_annotations)
    fig.add_annotation(
        text=work_text, xref='x domain', yref='y domain',
        x=0.98, y=0.02, showarrow=False,
        font=dict(size=10, color='white'),
        bgcolor='rgba(50,50,50,0.7)',
        bordercolor='gray', borderwidth=1, borderpad=4,
        row=1, col=1,
    )

    current_row = 2

    # ── Panel 2: Time delta (compare mode) ───────────────────────────────
    if has_c and has_v:
        _add_time_delta_panel(fig, results, dist_km, current_row)
        current_row += 1

    # ── Panel 3: W' balance ──────────────────────────────────────────────
    w_max_kj = rider_config['w_prime'] / 1000
    _add_w_prime_panel(fig, results, dist_km, w_max_kj, current_row)

    # ── Layout ───────────────────────────────────────────────────────────
    total_height = 750 if n_rows == 3 else 550
    fig.update_layout(
        height=total_height, template='plotly_dark',
        margin=dict(l=60, r=60, t=40, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='center', x=0.5, font=dict(size=11)),
        hovermode='x unified',
    )
    fig.update_yaxes(title_text="Power (W)", row=1, col=1,
                     secondary_y=False, range=[cp * 0.5, cp * 1.5])
    fig.update_yaxes(title_text="Elevation (m)", row=1, col=1,
                     secondary_y=True, showgrid=False,
                     title_font=dict(color='gray'),
                     tickfont=dict(color='gray'))
    if has_c and has_v:
        fig.update_yaxes(title_text="Time Δ (s)", row=2, col=1)
    fig.update_yaxes(title_text="W' (kJ)", row=current_row, col=1,
                     range=[-0.5, w_max_kj * 1.1])
    fig.update_xaxes(title_text="Distance (km)", row=current_row, col=1)

    return fig


# ── Chart sub-builders ──────────────────────────────────────────────────────

def _add_elevation_traces(fig, course_obj, det, dist_km, altitude):
    """Add terrain-colored or plain elevation fill to panel 1."""
    terrain_values = set()
    if 'segment_terrain' in course_obj.df.columns:
        terrain_values = set(course_obj.df['segment_terrain'].dropna().unique())
    is_terrain = (terrain_values <= {'uphill', 'flat', 'downhill'}
                  and len(terrain_values) > 0)

    if is_terrain and 'segment_index' in det.columns:
        terrain_fill = {
            'uphill': 'rgba(46,204,113,0.25)',
            'flat': 'rgba(149,165,166,0.25)',
            'downhill': 'rgba(231,76,60,0.25)',
        }
        terrain_line = {
            'uphill': 'rgb(46,204,113)',
            'flat': 'rgb(149,165,166)',
            'downhill': 'rgb(231,76,60)',
        }
        terrain_labels = {'uphill': 'Uphill', 'flat': 'Flat',
                          'downhill': 'Downhill'}
        seg_terrain_map = (course_obj.df
                           .groupby('segment')['segment_terrain']
                           .first().to_dict())
        seg_idx = det['segment_index']
        shown = set()
        prev = seg_terrain_map.get(
            int(seg_idx.iloc[0]) if pd.notna(seg_idx.iloc[0]) else 0, 'flat')
        run_start = 0

        def _flush(start, end, terrain):
            sl = slice(start, end)
            show_leg = terrain not in shown
            if show_leg:
                shown.add(terrain)
            fig.add_trace(go.Scatter(
                x=dist_km.iloc[sl], y=altitude.iloc[sl],
                fill='tozeroy',
                fillcolor=terrain_fill.get(terrain, terrain_fill['flat']),
                line=dict(color=terrain_line.get(terrain,
                                                 terrain_line['flat']),
                          width=0.8),
                name=terrain_labels.get(terrain, terrain),
                legendgroup=f'terrain_{terrain}',
                showlegend=show_leg,
                hovertemplate=('%{y:.0f}m<extra>'
                               + terrain_labels.get(terrain, '')
                               + '</extra>'),
                opacity=0.6,
            ), row=1, col=1, secondary_y=True)

        for i in range(1, len(seg_idx)):
            cur = seg_terrain_map.get(
                int(seg_idx.iloc[i]) if pd.notna(seg_idx.iloc[i]) else 0,
                'flat')
            if cur != prev:
                _flush(run_start, i + 1, prev)
                run_start = i
                prev = cur
        _flush(run_start, len(seg_idx), prev)
    else:
        fig.add_trace(go.Scatter(
            x=dist_km, y=altitude,
            fill='tozeroy', fillcolor='rgba(149,165,166,0.2)',
            line=dict(color='rgba(149,165,166,0.5)', width=0.8),
            name='Elevation', showlegend=False,
            hovertemplate='%{y:.0f}m<extra></extra>', opacity=0.6,
        ), row=1, col=1, secondary_y=True)


def _add_time_delta_panel(fig, results, dist_km, row):
    c_det = results['constant']['detailed']
    v_det = results['variable']['detailed']
    min_len = min(len(c_det), len(v_det))
    time_delta = (c_det['cumulative_time'].values[:min_len]
                  - v_det['cumulative_time'].values[:min_len])
    td_dist = dist_km.iloc[:min_len]

    td_pos = np.where(time_delta >= 0, time_delta, 0)
    td_neg = np.where(time_delta < 0, time_delta, 0)

    fig.add_trace(go.Scatter(
        x=td_dist, y=td_pos,
        fill='tozeroy', fillcolor='rgba(230,126,34,0.3)',
        line=dict(color='rgba(0,0,0,0)', width=0),
        name='Variable ahead', hoverinfo='skip',
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=td_dist, y=td_neg,
        fill='tozeroy', fillcolor='rgba(52,152,219,0.3)',
        line=dict(color='rgba(0,0,0,0)', width=0),
        name='Constant ahead', hoverinfo='skip',
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=td_dist, y=time_delta,
        line=dict(color='#2c3e50', width=1.2),
        name='Time Δ', showlegend=False,
        hovertemplate='%{y:+.1f}s<extra></extra>',
    ), row=row, col=1)
    fig.add_hline(y=0, line=dict(color='gray', width=1), row=row, col=1)

    final_d = time_delta[-1]
    fig.add_annotation(
        x=float(td_dist.iloc[-1]), y=float(final_d),
        text=f"{final_d:+.1f}s",
        showarrow=True, arrowhead=2,
        font=dict(size=11,
                  color='#e67e22' if final_d >= 0 else '#3498db',
                  weight='bold'),
        row=row, col=1,
    )


def _add_w_prime_panel(fig, results, dist_km, w_max_kj, row):
    if 'constant' in results:
        c_det = results['constant']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=c_det['w_remaining'] / 1000,
            line=dict(color='#3498db', width=1.5, dash='dash'),
            fill='tozeroy', fillcolor='rgba(52,152,219,0.1)',
            name="W' Constant",
            hovertemplate="%{y:.1f} kJ<extra>Constant</extra>",
        ), row=row, col=1)

    if 'variable' in results:
        v_det = results['variable']['detailed']
        fig.add_trace(go.Scatter(
            x=dist_km, y=v_det['w_remaining'] / 1000,
            line=dict(color='#e67e22', width=1.5),
            fill='tozeroy', fillcolor='rgba(230,126,34,0.1)',
            name="W' Variable",
            hovertemplate="%{y:.1f} kJ<extra>Variable</extra>",
        ), row=row, col=1)

    fig.add_hline(y=0, line=dict(color='red', width=1.5), row=row, col=1)
    fig.add_hline(y=w_max_kj, line=dict(color='gray', width=1, dash='dot'),
                  opacity=0.3, row=row, col=1)


# ── Strategy table ──────────────────────────────────────────────────────────

def _render_strategy_table(results: dict, r: dict):
    if 'variable' not in results:
        return

    cp = r['critical_power']

    with st.expander("📊 Segment Power Strategy"):
        vr = results['variable']['results_df'].copy()

        cols_to_show = {}
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

        # W' flow summary
        if all(c in vr.columns for c in ['target_power', 'time',
                                          'w_remaining']):
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

def _render_export(results: dict):
    has_const = 'constant' in results
    has_var = 'variable' in results

    if not (has_const or has_var):
        return

    with st.expander("💾 Export"):
        ref_key = 'variable' if has_var else 'constant'
        csv = results[ref_key]['detailed'].to_csv(index=False)
        st.download_button(
            "Download Detailed Results (CSV)", csv,
            "race_lab_results.csv", "text/csv",
            width="stretch")
