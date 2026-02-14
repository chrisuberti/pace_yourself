import streamlit as st
import pandas as pd
import os
import sys

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.course import Course
from app.database import CourseDatabase

# Page config
st.set_page_config(page_title="Course Segmentation", page_icon="🗺️", layout="wide")

# Initialize database connection
db = CourseDatabase()

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if "course" not in st.session_state:
    st.session_state.course = None
if "preview_df" not in st.session_state:
    st.session_state.preview_df = None
if "segmentation_method" not in st.session_state:
    st.session_state.segmentation_method = "Terrain-Based"
if "current_course_id" not in st.session_state:
    st.session_state.current_course_id = None

# ============================================================================
# SIDEBAR - COURSE LOADING
# ============================================================================

st.sidebar.header("📂 Load Course")

# Course selector - show all courses
all_courses = db.conn.execute(
    "SELECT course_id, course_name, total_distance_km, total_elevation_gain_m, course_type FROM courses ORDER BY course_type, course_name"
).fetchall()

if all_courses:
    course_options = {
        f"[{c['course_type'].replace('_', ' ').title()}] {c['course_name']} ({c['total_distance_km']:.1f}km, {c['total_elevation_gain_m']:.0f}m)": c['course_id'] 
        for c in all_courses
    }
    selected_course = st.sidebar.selectbox(
        "Available Courses", 
        ["-- Select --"] + list(course_options.keys()),
        key="course_selector"
    )
    
    if selected_course != "-- Select --":
        if st.sidebar.button("Load Course", type="primary"):
            course_id = course_options[selected_course]
            course_data = db.get_course(course_id)
            
            if course_data is None:
                st.sidebar.error("❌ Course not found in database")
            elif not course_data.get('processed_data'):
                st.sidebar.error(f"❌ Course '{course_data['course_name']}' has no processed GPS data")
            else:
                df = pd.DataFrame(course_data['processed_data'])
                course = Course(df, skip_processing=True)
                st.session_state.course = course
                st.session_state.current_course_id = course_id
                st.session_state.preview_df = None
                st.sidebar.success(f"✅ Loaded: {course_data['course_name']}")
                st.rerun()
else:
    st.sidebar.info("No courses available in database.")

# Strava segment fetcher
st.sidebar.divider()
st.sidebar.header("🔗 Fetch from Strava")
segment_id = st.sidebar.text_input("Segment ID", "1555983")

if st.sidebar.button("Fetch Segment"):
    try:
        # First check if this segment is already in our database
        existing_course = db.conn.execute(
            "SELECT course_id, course_name FROM courses WHERE strava_segment_id = ?",
            (str(segment_id),)
        ).fetchone()
        
        if existing_course:
            # Load from database instead of fetching from Strava
            course_data = db.get_course(existing_course['course_id'])
            if course_data and course_data.get('processed_data'):
                df = pd.DataFrame(course_data['processed_data'])
                course = Course(df, skip_processing=True)
                st.session_state.course = course
                st.session_state.current_course_id = existing_course['course_id']
                st.session_state.preview_df = None
                st.sidebar.success(f"✅ Found in database: {existing_course['course_name']}")
                st.rerun()
            else:
                st.sidebar.warning(f"⚠️ Segment exists but needs reprocessing")
                # Fall through to fetch from Strava
        
        # Fetch from Strava API if not in database
        if not existing_course or not course_data.get('processed_data'):
            from app.strava_calls import fetch_segment_data, fetch_segment_details
            
            # Get segment details for name
            segment_details = fetch_segment_details(segment_id)
            segment_name = segment_details.get('name', f'Strava Segment {segment_id}') if segment_details else f'Strava Segment {segment_id}'
            
            segment_data = fetch_segment_data(segment_id)
            
            if segment_data is None:
                st.sidebar.error("Failed to fetch segment from Strava API")
            else:
                # fetch_segment_data returns {"latlng": [...], "altitude": [...]}
                latlng_data = segment_data.get("latlng", [])
                altitude_data = segment_data.get("altitude", [])
                
                if latlng_data and altitude_data and len(latlng_data) == len(altitude_data):
                    df = pd.DataFrame(latlng_data, columns=["lat", "lon"])
                    df["altitude"] = altitude_data
                    course = Course(df)
                    st.session_state.course = course
                    st.session_state.preview_df = None
                    
                    # Save to database with auto-processing
                    raw_gps = [{"lat": row.lat, "lon": row.lon, "altitude": row.altitude} for row in df.itertuples()]
                    new_course_id = db.store_course({
                        'name': segment_name,
                        'strava_segment_id': str(segment_id),
                        'raw_gps_data': raw_gps,
                        'course_type': 'strava_segment',
                        'created_by': 'strava_api'
                    })
                    st.session_state.current_course_id = new_course_id
                    st.sidebar.success(f"✅ Fetched & saved: {segment_name}")
                    st.rerun()
                else:
                    st.sidebar.error(f"Invalid segment data: latlng={len(latlng_data) if latlng_data else 0}, altitude={len(altitude_data) if altitude_data else 0}")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# ============================================================================
# SIDEBAR - SEGMENTATION CONTROLS
# ============================================================================

st.sidebar.divider()
st.sidebar.header("⚙️ Segmentation Method")

segmentation_method = st.sidebar.radio(
    "Select Method",
    ["Equal Segments", "Terrain-Based", "Clustering (Auto)"],
    index=["Equal Segments", "Terrain-Based", "Clustering (Auto)"].index(st.session_state.segmentation_method),
    key="method_radio"
)
st.session_state.segmentation_method = segmentation_method

# Method-specific hyperparameters
st.sidebar.subheader("Parameters")

if segmentation_method == "Equal Segments":
    n_segments = st.sidebar.slider(
        "Number of Segments",
        min_value=2,
        max_value=50,
        value=10,
        step=1,
        help="Divide course into N equal-distance segments"
    )
    
    # Store params for preview
    seg_params = {"n_segments": n_segments}

elif segmentation_method == "Terrain-Based":
    uphill_threshold = st.sidebar.slider(
        "Uphill Threshold (%)",
        min_value=0.5,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="Gradient above this = uphill"
    )
    downhill_threshold = st.sidebar.slider(
        "Downhill Threshold (%)",
        min_value=-10.0,
        max_value=-0.5,
        value=-2.0,
        step=0.5,
        help="Gradient below this = downhill"
    )
    bearing_threshold = st.sidebar.slider(
        "Bearing Change Threshold (°)",
        min_value=15,
        max_value=180,
        value=45,
        step=5,
        help="Cumulative bearing change to trigger segment boundary"
    )
    min_segment_dist = st.sidebar.slider(
        "Min Segment Distance (m)",
        min_value=50,
        max_value=1000,
        value=200,
        step=50,
        help="Merge segments shorter than this"
    )
    smoothing_window = st.sidebar.slider(
        "Smoothing Window",
        min_value=5,
        max_value=51,
        value=21,
        step=2,
        help="Window size for gradient smoothing (must be odd)"
    )
    # Ensure odd
    if smoothing_window % 2 == 0:
        smoothing_window += 1
    
    seg_params = {
        "uphill_threshold": uphill_threshold,
        "downhill_threshold": downhill_threshold,
        "bearing_change_threshold": bearing_threshold,
        "min_segment_distance": min_segment_dist,
        "smoothing_window": smoothing_window
    }

else:  # Clustering (Auto)
    max_clusters = st.sidebar.slider(
        "Max Clusters",
        min_value=2,
        max_value=10,
        value=4,
        step=1,
        help="Maximum number of segment types"
    )
    weight_balance = st.sidebar.slider(
        "Weight: Gradient ↔ Bearing",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05,
        help="0 = gradient only, 1 = bearing only"
    )
    gradient_weight = 1.0 - weight_balance
    bearing_weight = weight_balance
    
    smoothing_window = st.sidebar.slider(
        "Smoothing Window",
        min_value=3,
        max_value=51,
        value=11,
        step=2,
        help="Window size for data smoothing"
    )
    if smoothing_window % 2 == 0:
        smoothing_window += 1
    
    seg_params = {
        "max_clusters": max_clusters,
        "gradient_weight": gradient_weight,
        "bearing_weight": bearing_weight,
        "smoothing_window": smoothing_window
    }

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.title("🗺️ Course Segmentation")

if st.session_state.course is None:
    st.info("👈 Load a course from the sidebar to begin.")
    st.stop()

course = st.session_state.course

# Course overview
col1, col2, col3, col4 = st.columns(4)
with col1:
    total_dist = course.df['cumulative_distance'].max() / 1000
    st.metric("Total Distance", f"{total_dist:.2f} km")
with col2:
    total_gain = course.df['height_gain'].sum()
    st.metric("Elevation Gain", f"{total_gain:.0f} m")
with col3:
    total_loss = course.df['height_loss'].sum()
    st.metric("Elevation Loss", f"{total_loss:.0f} m")
with col4:
    n_points = len(course.df)
    st.metric("Data Points", f"{n_points:,}")

st.divider()

# ============================================================================
# PREVIEW SEGMENTATION (Live update on parameter change)
# ============================================================================

# Generate preview based on current parameters
with st.spinner("Computing segmentation preview..."):
    if segmentation_method == "Equal Segments":
        preview_df = course.preview_equal_segmentation(**seg_params)
        method_key = 'equal'
    elif segmentation_method == "Terrain-Based":
        preview_df = course.preview_terrain_segmentation(**seg_params)
        method_key = 'terrain'
    else:  # Clustering
        preview_df = course.preview_clustering_segmentation(**seg_params)
        method_key = 'clustering'
    
    st.session_state.preview_df = preview_df

n_segments_preview = preview_df['segment'].nunique()

st.subheader(f"📊 Preview: {segmentation_method} ({n_segments_preview} segments)")

# Create visualizations
tab1, tab2, tab3 = st.tabs(["🏔️ Elevation Profile", "🗺️ Map View", "📋 Segment Details"])

with tab1:
    fig_profile = course.plot_segmentation_profile(
        df=preview_df,
        method=method_key,
        title=f"{segmentation_method} - {n_segments_preview} Segments",
        show_segment_bar=True,
        height=500
    )
    st.plotly_chart(fig_profile, use_container_width=True)

with tab2:
    fig_map = course.plot_segmentation_map(
        df=preview_df,
        method=method_key,
        title=f"Course Map - {segmentation_method}",
        height=500
    )
    st.plotly_chart(fig_map, use_container_width=True)

with tab3:
    # Show segment summary statistics
    segment_stats = preview_df.groupby('segment').agg({
        'distance': 'sum',
        'gradient': 'mean',
        'altitude': ['min', 'max', 'mean'],
        'height_gain': 'sum',
        'height_loss': 'sum'
    }).reset_index()
    
    # Flatten column names
    segment_stats.columns = [
        'Segment', 'Distance (m)', 'Avg Gradient (%)', 
        'Min Alt (m)', 'Max Alt (m)', 'Mean Alt (m)',
        'Height Gain (m)', 'Height Loss (m)'
    ]
    
    # Format
    segment_stats['Distance (km)'] = (segment_stats['Distance (m)'] / 1000).round(2)
    segment_stats['Avg Gradient (%)'] = segment_stats['Avg Gradient (%)'].round(1)
    segment_stats = segment_stats[[
        'Segment', 'Distance (km)', 'Avg Gradient (%)', 
        'Min Alt (m)', 'Max Alt (m)', 'Height Gain (m)', 'Height Loss (m)'
    ]]
    
    # Add terrain type if available
    if 'segment_terrain' in preview_df.columns:
        terrain_map = preview_df.groupby('segment')['segment_terrain'].first().to_dict()
        segment_stats['Terrain'] = segment_stats['Segment'].map(terrain_map)
    
    st.dataframe(segment_stats, use_container_width=True, hide_index=True)

# ============================================================================
# CONFIRM SEGMENTATION
# ============================================================================

st.divider()

col_confirm, col_info = st.columns([1, 2])

with col_confirm:
    if st.button("✅ Confirm Segmentation", type="primary", use_container_width=True):
        # Apply segmentation to the actual course object
        if segmentation_method == "Equal Segments":
            course.equal_segmentation(seg_params['n_segments'])
        elif segmentation_method == "Terrain-Based":
            course.gradient_bearing_segmentation(**seg_params)
        else:  # Clustering
            course.auto_segmentation(**seg_params)
        
        st.session_state.course = course
        
        # Save to database if we have a course_id
        if st.session_state.current_course_id:
            try:
                # Prepare segment data for storage
                if hasattr(course, 'course_segments'):
                    segment_data = course.course_segments.to_dict('records')
                    
                    # Save segmentation to database
                    db.conn.execute("""
                        INSERT OR REPLACE INTO segmentations 
                        (course_id, segmentation_name, method, parameters, segment_data, is_default)
                        VALUES (?, ?, ?, ?, ?, 1)
                    """, (
                        st.session_state.current_course_id,
                        f"{segmentation_method}_{n_segments_preview}seg",
                        segmentation_method.lower().replace(" ", "_").replace("(", "").replace(")", ""),
                        str(seg_params),
                        str(segment_data)
                    ))
                    db.conn.commit()
                    st.success(f"✅ Segmentation saved! ({n_segments_preview} segments)")
            except Exception as e:
                st.warning(f"Segmentation applied but not saved to DB: {e}")
        else:
            st.success(f"✅ Segmentation applied! ({n_segments_preview} segments)")

with col_info:
    st.info(
        "💡 **Tip:** Adjust the parameters in the sidebar to preview different segmentations. "
        "Click 'Confirm Segmentation' to apply and save your chosen configuration."
    )

# ============================================================================
# RAW DATA VIEWER (Collapsible)
# ============================================================================

with st.expander("🔍 View Raw Course Data"):
    st.dataframe(course.df, use_container_width=True, height=300)

# ============================================================================
# EXPORT OPTIONS
# ============================================================================

with st.expander("💾 Export Options"):
    col_export1, col_export2 = st.columns(2)
    
    with col_export1:
        if st.button("Export Segmented Course (CSV)"):
            if st.session_state.preview_df is not None:
                save_path = f"data/exports/segmented_course_{segment_id if segment_id else 'custom'}.csv"
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                st.session_state.preview_df.to_csv(save_path, index=False)
                st.success(f"Saved to {save_path}")
    
    with col_export2:
        if hasattr(course, 'course_segments'):
            if st.button("Export Segment Summary (CSV)"):
                save_path = f"data/exports/segment_summary_{segment_id if segment_id else 'custom'}.csv"
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                course.course_segments.to_csv(save_path, index=False)
                st.success(f"Saved to {save_path}")

