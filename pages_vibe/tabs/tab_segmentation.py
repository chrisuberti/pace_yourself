"""
Segmentation tab — choose method, preview, apply.

Preserves the existing segmentation methodology from Race Lab with
terrain/equal/clustering options and the interactive preview chart.
"""

import streamlit as st
import plotly.graph_objects as go

from app.course import Course
from pages_vibe.tabs.state import get_course


def render():
    """Render the Segmentation tab content."""
    course: Course = get_course()

    if course is None:
        st.info("Load a course in the **Course** tab first.")
        return

    cdf = course.df

    # ── Controls + preview side-by-side ──────────────────────────────────
    seg_col_controls, seg_col_viz = st.columns([1, 3])

    with seg_col_controls:
        seg_method = st.radio("Method", ["Terrain", "Equal", "Clustering"],
                              horizontal=True, label_visibility="collapsed")

        seg_params, method_key = _segmentation_controls(seg_method)

        apply_btn = st.button("✅ Apply Segmentation", type="primary",
                              width="stretch")

    # ── Preview chart ────────────────────────────────────────────────────
    with seg_col_viz:
        _render_preview(course, method_key, seg_params, cdf)

    # ── Apply segmentation ───────────────────────────────────────────────
    if apply_btn:
        _apply_segmentation(course, seg_method, method_key, seg_params)

    # ── Segment details table ────────────────────────────────────────────
    if (st.session_state.vibe_segmentation_applied
            and hasattr(course, 'course_segments')
            and course.course_segments is not None):
        _render_segment_table(course)

    # ── Segmentation map (when applied + latlon available) ───────────────
    if (st.session_state.vibe_segmentation_applied
            and hasattr(course, 'course_segments')
            and course.course_segments is not None
            and 'lat' in cdf.columns and 'lon' in cdf.columns
            and 'segment' in cdf.columns):
        with st.expander("🗺️ Segmentation Map", expanded=True):
            try:
                fig_map = course.plot_segmentation_map(
                    method=method_key,
                    title=f"Segmented Course — {seg_method}",
                    height=420,
                )
                st.plotly_chart(fig_map, width="stretch")
            except Exception as e:
                st.warning(f"Map unavailable: {e}")


# ── Private helpers ─────────────────────────────────────────────────────────

def _segmentation_controls(seg_method: str) -> tuple[dict, str]:
    """Render method-specific sliders, return (params_dict, method_key)."""
    if seg_method == "Terrain":
        uphill_t = st.slider("Uphill (%)", 0.5, 10.0, 2.0, 0.5,
                             help="Gradient above this → uphill")
        downhill_t = st.slider("Downhill (%)", -10.0, -0.5, -2.0, 0.5,
                               help="Gradient below this → downhill")
        bearing_t = st.slider("Bearing Δ (°)", 15, 180, 60, 5,
                              help="Cumulative bearing change to split")
        min_seg = st.slider("Min segment (m)", 50, 1000, 300, 50,
                            help="Merge segments shorter than this")
        return dict(uphill_threshold=uphill_t,
                    downhill_threshold=downhill_t,
                    bearing_change_threshold=bearing_t,
                    min_segment_distance=min_seg), 'terrain'

    elif seg_method == "Equal":
        n_segs = st.slider("Segments", 2, 30, 4, 1)
        return dict(n_segments=n_segs), 'equal'

    else:  # Clustering
        max_cl = st.slider("Max clusters", 2, 15, 4, 1)
        gw = st.slider("Gradient ↔ Bearing", 0.0, 1.0, 0.5, 0.05,
                        help="0 = gradient only, 1 = bearing only")
        return dict(max_clusters=max_cl,
                    gradient_weight=1.0 - gw,
                    bearing_weight=gw), 'clustering'


def _render_preview(course: Course, method_key: str, seg_params: dict,
                    cdf):
    """Show segmentation preview chart or fallback elevation profile."""
    try:
        if method_key == 'terrain':
            preview_df = course.preview_terrain_segmentation(**seg_params)
        elif method_key == 'equal':
            preview_df = course.preview_equal_segmentation(**seg_params)
        else:
            preview_df = course.preview_clustering_segmentation(**seg_params)

        n_preview = preview_df['segment'].nunique()

        fig_profile = course.plot_segmentation_profile(
            df=preview_df, method=method_key,
            title=f"{n_preview} segments — {method_key.title()}",
            show_segment_bar=True, height=350,
        )
        st.plotly_chart(fig_profile, width="stretch")

    except Exception as e:
        st.warning(f"Preview unavailable ({e}). Showing raw profile.")
        if ('cumulative_distance' in cdf.columns
                and 'altitude' in cdf.columns):
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


def _apply_segmentation(course: Course, seg_method: str, method_key: str,
                        seg_params: dict):
    """Run the selected segmentation algorithm and update session state."""
    try:
        with st.spinner("Applying segmentation…"):
            if seg_method == "Terrain":
                course.gradient_bearing_segmentation(**seg_params)
                # Enable sequence-preserving segments so optimizer sees
                # spatial order and can assign per-cluster-type power
                course.enable_enhanced_segmentation()
            elif seg_method == "Equal":
                course.equal_segmentation(seg_params['n_segments'])
                # Equal segments don't have cluster types — keep legacy format
            else:
                course.auto_segmentation(**seg_params)
                course.enable_enhanced_segmentation()

        st.session_state.vibe_course = course
        st.session_state.vibe_segmentation_applied = True
        st.session_state.vibe_optimization_results = None
        st.toast("Segmentation applied ✓")
        st.rerun()
    except Exception as e:
        st.error(f"Segmentation failed: {e}")
        st.info("Try changing parameters or switching methods.")


def _render_segment_table(course: Course):
    """Collapsible table of segment details."""
    segs = course.course_segments
    if segs.empty:
        return

    with st.expander(f"📋 {len(segs)} Segments", expanded=False):
        display = segs.copy()
        cols_map = {}
        # Enhanced (sequence-preserving) format columns
        if 'segment_sequence' in display.columns:
            cols_map['segment_sequence'] = '#'
        if 'segment_id' in display.columns:
            cols_map['segment_id'] = 'Cluster'
        # Legacy format columns
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
            cols_map['terrain'] = 'Terrain'

        avail = [c for c in cols_map if c in display.columns]
        show_df = display[avail].rename(columns=cols_map)
        st.dataframe(show_df, width="stretch", hide_index=True)
