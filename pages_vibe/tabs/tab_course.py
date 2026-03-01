"""
Course Selection tab — load from database, upload CSV, or fetch from Strava.

Also renders a GPS map + elevation profile for the loaded course.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

from app.course import Course
from app.database import CourseDatabase
from pages_vibe.tabs.state import get_course, get_rider


def render(db: CourseDatabase):
    """Render the Course Selection tab content."""

    # ── Source selector + loader side-by-side ─────────────────────────────
    col_source, col_loader = st.columns([1, 3])

    with col_source:
        source = st.radio(
            "Course source", ["Database", "Upload CSV", "Strava Segment"],
            horizontal=False, label_visibility="collapsed",
        )

    with col_loader:
        if source == "Database":
            _render_database_loader(db)
        elif source == "Upload CSV":
            _render_csv_upload()
        else:
            _render_strava_fetch()

    # ── Show loaded course overview ──────────────────────────────────────
    course = get_course()
    if course is None:
        st.info("Select a course above to get started.")
        return

    st.divider()
    _render_course_overview(course)


# ── Private helpers ─────────────────────────────────────────────────────────
def _render_database_loader(db: CourseDatabase):
    """Database course picker — auto-loads on selection change."""
    try:
        all_courses = db.list_courses()
    except Exception:
        all_courses = []

    if not all_courses:
        st.info("No courses in the database yet. Upload a CSV or fetch from Strava.")
        return

    labels = {}
    for c in all_courses:
        dist = c.get('total_distance_km', 0) or 0
        name = c.get('course_name', 'Unnamed')
        labels[f"{name} · {dist:.1f} km"] = c['course_id']

    pick = st.selectbox("Select course", list(labels.keys()),
                        index=0, label_visibility="collapsed")

    selected_id = labels[pick]
    current_id = st.session_state.get('vibe_course_id')

    # Auto-load if selection differs from current or nothing loaded yet
    if selected_id != current_id or get_course() is None:
        _load_course_from_db(db, selected_id, pick)

def _load_course_from_db(db: CourseDatabase, course_id: str, label: str):
    """Load course data from the database into session state."""
    cdata = db.get_course(course_id)
    if not cdata:
        st.error("Course not found in database.")
        return

    proc = cdata.get('processed_data')
    raw = cdata.get('raw_gps_data')

    try:
        if proc and isinstance(proc, (list, dict)) and len(proc) > 0:
            df = pd.DataFrame(proc)
            course = Course(df, skip_processing=True)
        elif raw and len(raw) > 0:
            df = pd.DataFrame(raw)
            course = Course(df)
        else:
            st.error("No GPS data available for this course.")
            return

        st.session_state.vibe_course = course
        st.session_state.vibe_course_id = course_id
        st.session_state.vibe_course_name = cdata.get('course_name', label)
        st.session_state.vibe_segmentation_applied = False
        st.session_state.vibe_optimization_results = None
        st.rerun()
    except Exception as e:
        st.error(f"Failed to load course: {e}")


def _render_csv_upload():
    """CSV file upload handler."""
    uploaded = st.file_uploader("Course CSV", type=['csv'],
                                label_visibility="collapsed")
    csv_name = st.text_input("Course name", "Uploaded Course",
                             label_visibility="collapsed",
                             placeholder="Course name")

    if uploaded and st.button("Process Upload", type="primary",
                              width="stretch"):
        try:
            with st.spinner("Processing CSV…"):
                df = pd.read_csv(uploaded)
                course = Course(df)
                st.session_state.vibe_course = course
                st.session_state.vibe_course_id = None
                st.session_state.vibe_course_name = csv_name
                st.session_state.vibe_segmentation_applied = False
                st.session_state.vibe_optimization_results = None
            st.toast(f"Loaded: {csv_name}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to process CSV: {e}")

def _render_strava_fetch():
    """Strava segment fetch handler — auto-fetches on ID entry."""
    seg_id_input = st.text_input("Strava Segment ID", "",
                                 label_visibility="collapsed",
                                 placeholder="Strava segment ID (press Enter)")

    if not seg_id_input:
        return

    # Avoid re-fetching if this segment is already loaded
    last_fetched = st.session_state.get('_last_strava_seg_id')
    if last_fetched == seg_id_input.strip() and get_course() is not None:
        return

    try:
        with st.spinner("Fetching from Strava…"):
            from app.strava_calls import fetch_segment_data, fetch_segment_details
            from app.database import get_course_db

            details = fetch_segment_details(seg_id_input)
            seg_name = (details.get('name', f'Segment {seg_id_input}')
                        if details else f'Segment {seg_id_input}')

            stream_data = fetch_segment_data(seg_id_input)
            if not (stream_data and stream_data.get('latlng')
                    and stream_data.get('altitude')):
                st.error("No stream data returned from Strava.")
                return

            latlng = stream_data['latlng']
            altitude_data = stream_data['altitude']

            if len(latlng) < 2:
                st.error("Not enough GPS points in segment.")
                return

            raw_gps = [
                {'lat': ll[0], 'lon': ll[1], 'ele': alt}
                for ll, alt in zip(latlng, altitude_data)
            ]
            df_raw = pd.DataFrame(raw_gps)
            if 'ele' in df_raw.columns and 'altitude' not in df_raw.columns:
                df_raw.rename(columns={'ele': 'altitude'}, inplace=True)

            course = Course(df_raw)

            # ── Save to database (upsert by strava_segment_id) ───────
            db = get_course_db()
            strava_id = str(seg_id_input).strip()

            # Check if segment already exists in DB
            existing = db.conn.execute(
                "SELECT course_id FROM courses WHERE strava_segment_id = ?",
                (strava_id,)
            ).fetchone()

            if existing:
                course_id = existing['course_id']
            else:
                course_id = db.store_course({
                    'name': seg_name,
                    'strava_segment_id': strava_id,
                    'raw_gps_data': raw_gps,
                    'created_by': 'strava',
                    'course_type': 'strava_segment',
                })

            st.session_state.vibe_course = course
            st.session_state.vibe_course_id = course_id
            st.session_state.vibe_course_name = seg_name
            st.session_state.vibe_segmentation_applied = False
            st.session_state.vibe_optimization_results = None
            st.session_state['_last_strava_seg_id'] = strava_id

        st.toast(f"Fetched & saved: {seg_name}")
        st.rerun()
    except Exception as e:
        st.error(f"Strava fetch failed: {e}")
        st.info("Check your STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, "
                "and tokens in `.env`.")

def _render_course_overview(course: Course):
    """Show course metrics, GPS map, and elevation profile side-by-side."""
    cdf = course.df

    total_dist_m = (cdf['cumulative_distance'].max()
                    if 'cumulative_distance' in cdf.columns else 0)
    total_gain = cdf['height_gain'].sum() if 'height_gain' in cdf.columns else 0
    total_loss = cdf['height_loss'].sum() if 'height_loss' in cdf.columns else 0
    avg_grad = cdf['gradient'].mean() if 'gradient' in cdf.columns else 0

    mc = st.columns(4)
    with mc[0]:
        st.metric("Distance", f"{total_dist_m / 1000:.1f} km")
    with mc[1]:
        st.metric("↑ Gain", f"{total_gain:.0f} m")
    with mc[2]:
        st.metric("↓ Loss", f"{total_loss:.0f} m")
    with mc[3]:
        st.metric("Avg Grade", f"{avg_grad:.1f}%")

    # ── Side-by-side: GPS map + elevation profile ────────────────────────
    has_latlon = 'lat' in cdf.columns and 'lon' in cdf.columns
    has_elevation = ('cumulative_distance' in cdf.columns
                     and 'altitude' in cdf.columns)

    if has_latlon and has_elevation:
        col_map, col_elev = st.columns(2)

        with col_map:
            _render_gps_map(cdf)

        with col_elev:
            _render_elevation_profile(cdf)

    elif has_elevation:
        _render_elevation_profile(cdf)


def _render_gps_map(cdf: pd.DataFrame):
    """Plotly Scattermapbox of the raw course GPS trace."""
    fig = go.Figure()

    # Color by gradient if available, else plain line
    if 'gradient' in cdf.columns:
        fig.add_trace(go.Scattermapbox(
            lat=cdf['lat'], lon=cdf['lon'],
            mode='markers+lines',
            marker=dict(
                size=4,
                color=cdf['gradient'] * 100,
                colorscale='RdYlGn_r',
                cmin=-10, cmax=10,
                colorbar=dict(title='Grade %', thickness=12, len=0.6),
            ),
            line=dict(width=2, color='gray'),
            hovertemplate=(
                'Lat: %{lat:.4f}<br>Lon: %{lon:.4f}<br>'
                'Grade: %{marker.color:.1f}%<extra></extra>'
            ),
        ))
    else:
        fig.add_trace(go.Scattermapbox(
            lat=cdf['lat'], lon=cdf['lon'],
            mode='lines',
            line=dict(width=3, color='#3498db'),
        ))

    center_lat = cdf['lat'].mean()
    center_lon = cdf['lon'].mean()
    lat_range = cdf['lat'].max() - cdf['lat'].min()
    lon_range = cdf['lon'].max() - cdf['lon'].min()
    max_range = max(lat_range, lon_range)
    zoom = 15 if max_range < 0.01 else 13 if max_range < 0.05 else 12 if max_range < 0.1 else 10

    fig.update_layout(
        mapbox=dict(style='open-street-map',
                    center=dict(lat=center_lat, lon=center_lon),
                    zoom=zoom),
        height=380,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")


def _render_elevation_profile(cdf: pd.DataFrame):
    """Simple elevation profile chart."""
    dist_km = cdf['cumulative_distance'] / 1000

    fig = go.Figure()

    # Gradient-colored scatter on top of area fill
    if 'gradient' in cdf.columns:
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            fill='tozeroy', fillcolor='rgba(149,165,166,0.15)',
            line=dict(color='rgba(149,165,166,0.4)', width=0.5),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            mode='markers',
            marker=dict(
                size=3,
                color=cdf['gradient'] * 100,
                colorscale='RdYlGn_r',
                cmin=-10, cmax=10,
                showscale=False,
            ),
            hovertemplate='%{y:.0f}m · %{marker.color:.1f}%<extra></extra>',
            showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=dist_km, y=cdf['altitude'],
            fill='tozeroy', fillcolor='rgba(149,165,166,0.3)',
            line=dict(color='gray', width=1),
            showlegend=False,
            hovertemplate='%{y:.0f}m<extra></extra>',
        ))

    fig.update_layout(
        height=380, template='plotly_dark',
        xaxis_title='Distance (km)', yaxis_title='Elevation (m)',
        margin=dict(l=50, r=20, t=10, b=40),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch")
