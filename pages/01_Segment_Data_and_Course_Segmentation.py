import streamlit as st
import pandas as pd
import os
import sys
from app.page_helpers import *

# Add the app directory to the Python module search path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.course import *
from app.visualizations import *
#find all files in route_path that end with '_raw_strava.csv'
route_path = os.getenv('ROUTE_PATH')
files = [f for f in os.listdir(route_path) if f.endswith('_raw_strava.csv')]

segment_id = st.sidebar.selectbox("Select Segment ID", files)
#add button to ennsure we don't run the following code if the button is not clicked
if st.sidebar.button("Fetch saved Data"):
    course = Course(pd.read_csv(os.path.join(route_path, segment_id)))
    st.session_state.course = course

# Ensure session state for course
if "course" not in st.session_state:
    course = Course(pd.read_csv(os.path.join(route_path, files[0])))
    st.session_state.course = course

# Sidebar input for segment ID
st.sidebar.header("Segment Data")
segment_id = st.sidebar.text_input("Enter Segment ID", "1555983")  # Example segment ID input

if st.sidebar.button("Fetch Segment Data"):
    # Fetch and process segment data
    from app.strava_calls import fetch_segment_data
    segment_data = fetch_segment_data(segment_id)
    latlng_data = segment_data.get("latlng", {}).get("data", [])
    altitude_data = segment_data.get("altitude", {}).get("data", [])
    if latlng_data and altitude_data and len(latlng_data) == len(altitude_data):
        df = pd.DataFrame(latlng_data, columns=["lat", "lon"])
        df["altitude"] = altitude_data
        course = Course(df)
        st.session_state.course = course  # Save course to session state

# Sidebar option for segmentation method
segmentation_method = st.sidebar.selectbox(
    "Select Segmentation Method",
    ['auto-segmentation', 'equal segments', 'manual segmentation']
)

# Segmentation logic
if st.session_state.course:
    course = st.session_state.course

    if segmentation_method == 'manual segmentation':
        slider_values = course_segmentation_slider()
        if st.sidebar.button("Confirm Manual Segmentation"):
            course.slider_segmentation(slider_values)
            st.session_state.course = course
            st.sidebar.write(f"Slider values: {slider_values}")

    elif segmentation_method == 'equal segments':
        num_segments = st.sidebar.slider("Number of Equal Segments", min_value=1, max_value=10, value=5)
        if st.sidebar.button("Confirm Segmentation"):
            course.equal_segmentation(num_segments)
            st.session_state.course = course

    elif segmentation_method == 'auto-segmentation':
        max_clusters = st.sidebar.slider("Max Clusters", min_value=1, max_value=3, value=5)
        weight_balance = st.sidebar.slider(
            "Weight Balance (Gradient ↔ Bearing)",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help="Adjust the balance between gradient and course direction weights"
        )
        gradient_weight = 1.0 - weight_balance
        bearing_weight = weight_balance
        smoothing_window = st.sidebar.slider("Smoothing Window", min_value=5, max_value=50, value=20, step=5)
        if st.sidebar.button("Run Auto-Segmentation"):
            course.auto_segmentation(
                max_clusters=max_clusters,
                gradient_weight=gradient_weight,
                bearing_weight=bearing_weight,
                smoothing_window=smoothing_window
            )
            st.session_state.course = course

# Display course visualizations and segmentation details
if st.session_state.course:
    course = st.session_state.course

    # Collapsible section for visualizations
    with st.expander("Visualizations", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write("Segment Route Map with Altitude Data")
            if 'segment' in course.df.columns:
                map_deck = create_map(course.df, color='segment')
            else:
                map_deck = create_map(course.df, color='altitude')
            st.pydeck_chart(map_deck)

        with col2:
            st.write("Cumulative Distance vs Altitude")
            if 'segment' in course.df.columns:
                fig = plot_cumulative_distance_vs_altitude(course.df, color='segment')
            else:
                fig = plot_cumulative_distance_vs_altitude(course.df, color='altitude')
            st.plotly_chart(fig)
        st.write(course.df)

    # Display aggregated segment data
    if hasattr(course, 'course_segments'):
        st.header("Segment Aggregated Data")
        st.write(course.course_segments)

    # Save processed course data
    if st.button("Save Processed Course Data"):
        route_path = os.getenv('ROUTE_PATH')
        save_path = os.path.join(route_path, f"{segment_id}_processed_course.csv")
        course.df.to_csv(save_path, index=False)
        st.success(f"Processed course data saved to {save_path}")
