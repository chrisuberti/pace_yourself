"""
Course Selection tab — load from DB, upload CSV, or fetch from Strava.

Chart construction (GPS map, elevation profile) lives in `_charts.py`.
All session-state writes go through `_workflow.py`.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.course import Course
from app.database import CourseDatabase, get_course_db
from app.starter_courses import (
    STARTER_COURSES,
    build_starter_course_frame,
    get_starter_course,
)
from pages_vibe.tabs import _charts, _workflow
from pages_vibe.tabs.state import get_course


# ── Public entry point ──────────────────────────────────────────────────────

def render(db: CourseDatabase) -> None:
    col_source, col_loader = st.columns([1, 3])

    with col_source:
        source = st.radio(
            "Course source",
            ["Starter Courses", "Database", "Upload CSV", "Strava Segment"],
            horizontal=False, label_visibility="collapsed",
        )

    with col_loader:
        if source == "Starter Courses":
            _render_starter_course_loader()
        elif source == "Database":
            _render_database_loader(db)
        elif source == "Upload CSV":
            _render_csv_upload()
        else:
            _render_strava_fetch()

    course = get_course()
    if course is None:
        st.info("Select a course above to get started.")
        return

    st.divider()
    _render_course_overview(course)


# ── Starter courses ─────────────────────────────────────────────────────────

def _render_starter_course_loader() -> None:
    labels = {
        (
            f"{starter.name} · {starter.distance_m / 1000:.1f} km · "
            f"{starter.elevation_gain_m:.0f} m gain"
        ): starter.slug
        for starter in STARTER_COURSES
    }

    with st.form("starter_course_form"):
        pick = st.selectbox("Starter course", labels, label_visibility="collapsed")
        load_course = st.form_submit_button(
            "Load Starter Course",
            type="primary",
            width="stretch",
        )

    starter = get_starter_course(labels[pick])
    st.caption(f"{starter.location} · {starter.description}")
    if starter.is_virtual:
        st.caption(
            "Virtual route profile with a schematic map; no real-world GPS "
            "location is implied."
        )
    else:
        st.caption(
            "Real-world GPS geometry from OpenStreetMap with a normalized "
            "elevation profile based on the linked public course reference."
        )
    st.link_button("View segment reference", starter.segment_url)

    if load_course:
        _load_starter_course(starter.slug)


def _load_starter_course(slug: str) -> None:
    starter = get_starter_course(slug)
    try:
        course = Course(build_starter_course_frame(slug))
        course.starter_course = starter
        _commit_course_and_advance(
            course=course,
            course_id=f"starter:{starter.slug}",
            course_name=starter.name,
        )
        st.toast(f"Loaded: {starter.name}")
        st.rerun()
    except Exception as error:
        st.error(f"Failed to load starter course: {error}")


# ── Database loader ─────────────────────────────────────────────────────────

def _render_database_loader(db: CourseDatabase) -> None:
    try:
        all_courses = db.list_courses()
    except Exception:
        all_courses = []

    if not all_courses:
        st.info("No courses in the database yet. Upload a CSV or fetch from Strava.")
        return

    labels: dict[str, str] = {}
    for c in all_courses:
        dist = c.get('total_distance_km', 0) or 0
        name = c.get('course_name', 'Unnamed')
        labels[f"{name} · {dist:.1f} km"] = c['course_id']

    current_id = st.session_state.get('vibe_course_id')
    current_index = 0
    if current_id in labels.values():
        current_index = list(labels.values()).index(current_id)

    with st.form("database_course_form"):
        pick = st.selectbox(
            "Select course",
            list(labels.keys()),
            index=current_index,
            label_visibility="collapsed",
        )
        load_course = st.form_submit_button(
            "Load Course",
            type="primary",
            width="stretch",
        )

    if load_course:
        _load_course_from_db(db, labels[pick], pick)


def _load_course_from_db(db: CourseDatabase, course_id: str, label: str) -> None:
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

        _commit_course_and_advance(
            course=course,
            course_id=course_id,
            course_name=cdata.get('course_name', label),
        )
        st.rerun()
    except Exception as e:
        st.error(f"Failed to load course: {e}")


# ── CSV upload ──────────────────────────────────────────────────────────────

def _render_csv_upload() -> None:
    with st.form("csv_course_form"):
        uploaded = st.file_uploader(
            "Course CSV",
            type=['csv'],
            label_visibility="collapsed",
        )
        csv_name = st.text_input(
            "Course name",
            "Uploaded Course",
            label_visibility="collapsed",
            placeholder="Course name",
        )
        process_upload = st.form_submit_button(
            "Process Upload",
            type="primary",
            width="stretch",
        )

    if process_upload:
        if uploaded is None:
            st.warning("Choose a CSV file before processing.")
            return
        try:
            with st.spinner("Processing CSV…"):
                df = pd.read_csv(uploaded)
                course = Course(df)
                _commit_course_and_advance(
                    course=course, course_id=None, course_name=csv_name)
            st.toast(f"Loaded: {csv_name}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to process CSV: {e}")


# ── Strava fetch ────────────────────────────────────────────────────────────

def _render_strava_fetch() -> None:
    auth_user_id = st.session_state.get('auth_user_id')
    if not auth_user_id:
        st.info("Connect Strava before fetching one of your accessible segments.")
        return

    with st.form("strava_course_form"):
        seg_id_input = st.text_input(
            "Strava Segment ID",
            "",
            label_visibility="collapsed",
            placeholder="Strava segment ID",
        )
        fetch_segment = st.form_submit_button(
            "Fetch Segment",
            type="primary",
            width="stretch",
        )

    if not fetch_segment:
        return
    if not seg_id_input.strip():
        st.warning("Enter a Strava segment ID before fetching.")
        return

    last_fetched = st.session_state.get('_last_strava_seg_id')
    if last_fetched == seg_id_input.strip() and get_course() is not None:
        return

    try:
        with st.spinner("Fetching from Strava…"):
            from app.strava_calls import fetch_segment_data, fetch_segment_details

            details = fetch_segment_details(
                seg_id_input, user_id=auth_user_id)
            seg_name = (details.get('name', f'Segment {seg_id_input}')
                        if details else f'Segment {seg_id_input}')

            stream_data = fetch_segment_data(
                seg_id_input, user_id=auth_user_id)
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
            course_id = _persist_strava_segment(seg_id_input, seg_name, raw_gps)

            _commit_course_and_advance(
                course=course, course_id=course_id, course_name=seg_name)
            st.session_state['_last_strava_seg_id'] = str(seg_id_input).strip()

        st.toast(f"Fetched & saved: {seg_name}")
        st.rerun()
    except Exception as e:
        st.error(f"Strava fetch failed: {e}")
        st.info("Check your STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, "
                "and tokens in `.env`.")


def _commit_course_and_advance(course: Course, course_id: str | None,
                               course_name: str) -> None:
    """Commit a successfully loaded course and open segmentation."""
    _workflow.mark_course_loaded(
        course=course,
        course_id=course_id,
        course_name=course_name,
    )
    if not _workflow.set_active_step('segment'):
        raise RuntimeError("Loaded course did not unlock segmentation.")


def _persist_strava_segment(seg_id: str, seg_name: str, raw_gps: list) -> str:
    """Upsert a Strava segment into the courses DB. Returns course_id."""
    db = get_course_db()
    strava_id = str(seg_id).strip()
    return db.store_course({
        'name': seg_name,
        'strava_segment_id': strava_id,
        'raw_gps_data': raw_gps,
        'created_by': 'strava',
        'course_type': 'strava_segment',
    })


# ── Overview ────────────────────────────────────────────────────────────────

def _render_course_overview(course: Course) -> None:
    cdf = course.df
    starter = getattr(course, "starter_course", None)

    if starter is not None:
        source_description = (
            "Virtual profile and schematic geometry"
            if starter.is_virtual
            else "OpenStreetMap GPS geometry with a normalized elevation profile"
        )
        st.caption(f"{source_description} · {starter.location}")

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

    has_latlon = 'lat' in cdf.columns and 'lon' in cdf.columns
    has_elev = ('cumulative_distance' in cdf.columns
                and 'altitude' in cdf.columns)

    if starter is not None and has_latlon and has_elev:
        col_map, col_elev = st.columns(2)
        with col_map:
            map_builder = (
                _charts.build_virtual_course_map
                if starter.is_virtual
                else _charts.build_gps_map
            )
            st.plotly_chart(map_builder(cdf), width="stretch")
        with col_elev:
            st.plotly_chart(_charts.build_elevation_profile(cdf),
                            width="stretch")
        st.link_button("View segment reference", starter.segment_url)
        st.link_button("Why this segment was selected", starter.research_url)
    elif has_latlon and has_elev:
        col_map, col_elev = st.columns(2)
        with col_map:
            st.plotly_chart(_charts.build_gps_map(cdf), width="stretch")
        with col_elev:
            st.plotly_chart(_charts.build_elevation_profile(cdf),
                            width="stretch")
    elif has_elev:
        st.plotly_chart(_charts.build_elevation_profile(cdf), width="stretch")
