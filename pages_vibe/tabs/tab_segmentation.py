"""
Segmentation tab — pick method, preview, apply.

All session-state writes go through `_workflow.py`. Tab gating requires a
loaded course; downstream optimization results are cleared on apply.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from app.course import BAND_LABELS, Course
from pages_vibe.tabs import _workflow
from pages_vibe.tabs.state import get_course


# ── Public entry point ──────────────────────────────────────────────────────

def render() -> None:
    if not _workflow.require_course():
        return

    course: Course = get_course()
    cdf = course.df

    seg_col_controls, seg_col_viz = st.columns([1, 3])

    with seg_col_controls:
        seg_method = st.radio("Method",
                              ["Terrain", "Equal", "Clustering"],
                              horizontal=True, label_visibility="collapsed")
        seg_params, method_key = _segmentation_controls(seg_method)
        apply_btn = st.button("✅ Apply Segmentation", type="primary",
                              width="stretch")

    with seg_col_viz:
        preview_df = _render_preview(course, method_key, seg_params, cdf)
        if method_key == 'clustering' and preview_df is not None:
            _render_clustering_diagnostics(preview_df, seg_params)

    if apply_btn:
        _apply_segmentation(course, seg_method, seg_params)

    if (st.session_state.vibe_segmentation_applied
            and hasattr(course, 'course_segments')
            and course.course_segments is not None):
        applied_name = st.session_state.get('vibe_segmentation_name') or seg_method
        applied_method_key = {
            'Terrain': 'bands',
            'Equal': 'equal',
            'Clustering': 'clustering',
        }.get(applied_name, method_key)
        st.success(f"Applied segmentation: {applied_name}")
        _render_segment_table(course)

        if ('lat' in cdf.columns and 'lon' in cdf.columns
                and 'segment' in cdf.columns):
            with st.expander("🗺️ Segmentation Map", expanded=True):
                try:
                    fig_map = course.plot_segmentation_map(
                        method=applied_method_key,
                        title=f"Segmented Course — {applied_name}",
                        height=420,
                    )
                    st.plotly_chart(fig_map, width="stretch")
                except Exception as e:
                    st.warning(f"Map unavailable: {e}")

# ── Controls ────────────────────────────────────────────────────────────────

def _segmentation_controls(seg_method: str) -> tuple[dict, str]:
    """Render method-specific sliders; return (params, method_key)."""
    if seg_method == "Terrain":
        st.caption("Classifies the course into a few recurring gradient zones — "
                   "one power per zone, easy to follow while riding hard.")
        return dict(
            flat_threshold=st.slider(
                "Flat band (±%)", 0.5, 4.0, 2.0, 0.5,
                help="|gradient| below this is Flat"),
            steep_threshold=st.slider(
                "Steep band (±%)", 4.0, 12.0, 6.0, 0.5,
                help="|gradient| above this is a steep climb/descent"),
            min_segment_distance=st.slider(
                "Min zone (m)", 50, 1000, 200, 50,
                help="Merge zones shorter than this into a neighbor"),
        ), 'bands'

    if seg_method == "Equal":
        return dict(n_segments=st.slider("Segments", 2, 30, 4, 1)), 'equal'

    # Clustering
    st.caption("Groups recurring terrain with similar smoothed grade and "
               "direction. A type can appear multiple times along the course.")
    max_cl = st.slider("Cluster types", 2, 8, 4, 1,
                       help="Exact number of recurring terrain types to find")
    bearing_influence = st.slider(
        "Bearing influence", 0.0, 0.75, 0.20, 0.05,
        help="0 = gradient only; higher values split similar grades by direction")
    smoothing_distance = st.slider(
        "Smoothing distance (m)", 25, 500, 150, 25,
        help="Average gradient and direction over this distance before clustering")
    min_seg = st.slider(
        "Min spatial run (m)", 0, 500, 200, 25,
        help="Absorb short repeated fragments without deleting a cluster type")

    with st.expander("Advanced clustering"):
        gradient_clip = st.slider(
            "Gradient cap (±%)", 6.0, 25.0, 12.0, 1.0,
            help="Limits GPS grade spikes before fitting cluster types")
        st.caption(
            f"Feature weighting: {1.0 - bearing_influence:.0%} gradient · "
            f"{bearing_influence:.0%} bearing")

    return dict(
        max_clusters=max_cl,
        gradient_weight=1.0 - bearing_influence,
        bearing_weight=bearing_influence,
        smoothing_distance=float(smoothing_distance),
        min_segment_distance=float(min_seg),
        gradient_clip=float(gradient_clip),
    ), 'clustering'


# ── Preview ─────────────────────────────────────────────────────────────────

def _render_preview(course: Course, method_key: str, seg_params: dict, cdf):
    """Show segmentation preview chart or fallback elevation profile."""
    try:
        if method_key == 'bands':
            preview_df = course.preview_gradient_band_segmentation(**seg_params)
        elif method_key == 'equal':
            preview_df = course.preview_equal_segmentation(**seg_params)
        else:
            preview_df = course.preview_clustering_segmentation(**seg_params)

        n_preview = preview_df['segment'].nunique()
        if method_key == 'clustering':
            title = f"{n_preview} recurring terrain types — Clustering"
        else:
            title = f"{n_preview} segments — {method_key.title()}"
        fig_profile = course.plot_segmentation_profile(
            df=preview_df, method=method_key,
            title=title,
            show_segment_bar=True, height=350,
        )
        st.plotly_chart(fig_profile, width="stretch")
        return preview_df
    except Exception as e:
        st.warning(f"Preview unavailable ({e}). Showing raw profile.")
        if 'cumulative_distance' in cdf.columns and 'altitude' in cdf.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=cdf['cumulative_distance'] / 1000,
                y=cdf['altitude'],
                fill='tozeroy', fillcolor='rgba(149,165,166,0.3)',
                line=dict(color='gray', width=1),
            ))
            fig.update_layout(
                height=300, template='plotly_dark',
                xaxis_title='Distance (km)', yaxis_title='Elevation (m)',
                margin=dict(l=50, r=30, t=20, b=40), showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")
        return None


def _render_clustering_diagnostics(preview_df, seg_params: dict) -> None:
    """Summarize cluster meaning, coverage, and spatial recurrence."""
    run_ids = preview_df['segment'].ne(preview_df['segment'].shift()).cumsum()
    run_counts = preview_df.groupby(run_ids)['segment'].first().value_counts()

    def _circular_mean_degrees(values):
        radians = np.radians(values)
        return np.mod(np.degrees(np.arctan2(
            np.sin(radians).mean(), np.cos(radians).mean())), 360.0)

    summary = preview_df.groupby('segment').agg(
        terrain=('segment_terrain', 'first'),
        avg_grade=('gradient_smoothed', 'mean'),
        direction=('bearing_smoothed', _circular_mean_degrees),
        distance_m=('distance', 'sum'),
    )
    summary['runs'] = run_counts
    total_distance = max(float(summary['distance_m'].sum()), 1.0)
    summary['share'] = summary['distance_m'] / total_distance * 100.0
    summary = summary.reset_index().sort_values('segment')
    summary['Type'] = summary['segment'].map(lambda value: f"Type {int(value) + 1}")
    summary['Terrain'] = summary['terrain'].map(
        lambda value: BAND_LABELS.get(value, value))
    summary['Avg grade'] = summary['avg_grade'].map(lambda value: f"{value:+.1f}%")
    summary['Direction'] = summary['direction'].map(lambda value: f"{value:.0f}°")
    summary['Distance'] = summary['distance_m'].map(lambda value: f"{value / 1000:.2f} km")
    summary['Share'] = summary['share'].map(lambda value: f"{value:.0f}%")
    summary['Runs'] = summary['runs'].astype(int)

    actual_clusters = len(summary)
    requested_clusters = int(seg_params['max_clusters'])
    with st.expander("Cluster diagnostics", expanded=True):
        smoothing_points = preview_df.attrs.get('smoothing_window_points')
        smoothing_detail = (
            f" ({smoothing_points} data points)" if smoothing_points else "")
        st.caption(
            f"{actual_clusters} terrain types across {int(run_ids.nunique())} "
            "spatial runs. Types are ordered from descending to climbing terrain. "
            f"Smoothing: {seg_params['smoothing_distance']:.0f} m"
            f"{smoothing_detail}.")
        if actual_clusters < requested_clusters:
            st.warning(
                f"Requested {requested_clusters} types, but the course only has "
                f"enough distinct terrain for {actual_clusters}.")
        st.dataframe(
            summary[['Type', 'Terrain', 'Avg grade', 'Direction',
                     'Distance', 'Share', 'Runs']],
            width="stretch",
            hide_index=True,
        )


# ── Apply ───────────────────────────────────────────────────────────────────

def _apply_segmentation(course: Course, seg_method: str, seg_params: dict) -> None:
    """Run the selected segmentation algorithm; funnel state via _workflow."""
    try:
        with st.spinner("Applying segmentation…"):
            if seg_method == "Terrain":
                course.gradient_band_segmentation(**seg_params)
                course.enable_enhanced_segmentation()
            elif seg_method == "Equal":
                course.equal_segmentation(seg_params['n_segments'])
                # Equal segments don't have cluster types — keep legacy format
            else:
                course.auto_segmentation(**seg_params)
                course.enable_enhanced_segmentation()

        _workflow.mark_segmentation_applied(
            course,
            name=seg_method,
            params=seg_params,
        )
        if not _workflow.set_active_step('rider'):
            raise RuntimeError(
                "Applied segmentation did not unlock rider setup.")
        st.toast("Segmentation applied ✓")
        st.rerun()
    except Exception as e:
        st.error(f"Segmentation failed: {e}")
        st.info("Try changing parameters or switching methods.")


# ── Segment table ───────────────────────────────────────────────────────────

def _render_segment_table(course: Course) -> None:
    segs = course.course_segments
    if segs.empty:
        return

    with st.expander(f"📋 {len(segs)} Segments", expanded=False):
        display = segs.copy()

        # Friendly pacing-zone labels (terrain column holds band names for the
        # Pacing Zones method, e.g. 'steep_climb' → 'Steep Climb').
        from app.course import BAND_LABELS
        is_zones = ('terrain' in display.columns
                    and display['terrain'].isin(BAND_LABELS).any())
        if is_zones:
            display['terrain'] = display['terrain'].map(
                lambda t: BAND_LABELS.get(t, t))

        cols_map: dict[str, str] = {}
        if 'segment_sequence' in display.columns:
            cols_map['segment_sequence'] = '#'
        if 'segment_id' in display.columns:
            cols_map['segment_id'] = 'Zone' if is_zones else 'Cluster'
        if 'segment' in display.columns and 'segment_id' not in display.columns:
            cols_map['segment'] = 'Seg'
        if 'distance_sum' in display.columns:
            cols_map['distance_sum'] = 'Dist (km)'
        if 'gradient_mean' in display.columns:
            cols_map['gradient_mean'] = 'Grade (%)'
        if 'height_gain_sum' in display.columns:
            cols_map['height_gain_sum'] = '↑ (m)'
        if 'height_loss_sum' in display.columns:
            cols_map['height_loss_sum'] = '↓ (m)'
        if 'altitude_mean' in display.columns:
            cols_map['altitude_mean'] = 'Avg Alt (m)'
        if 'terrain' in display.columns:
            cols_map['terrain'] = 'Zone' if is_zones else 'Terrain'

        avail = [c for c in cols_map if c in display.columns]
        show_df = display[avail].rename(columns=cols_map)
        st.dataframe(show_df, width="stretch", hide_index=True)
