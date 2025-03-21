import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
route_path = os.getenv('ROUTE_PATH')

# Local pace-yourself imports
from app.course import *
from app.visualizations import *
from app.strava_calls import *
from slider_test import course_segmentation_slider

@st.cache_data
def cached_fetch_segment_data(segment_id, save_file=False):
    segment_data=fetch_segment_data(segment_id)
    latlng_data = segment_data.get("latlng", {}).get("data", [])
    altitude_data = segment_data.get("altitude", {}).get("data", [])
    # Ensure we have both lat/lng and altitude data to proceed
    if latlng_data and altitude_data and len(latlng_data) == len(altitude_data):
        df = pd.DataFrame(latlng_data, columns=["lat", "lon"])
        df["altitude"] = altitude_data  
        
    if save_file:
        df.to_csv(os.path.join(route_path, segment_id+'_raw_strava.csv'), index=False)

    #df.to_csv(os.path.join(route_path, segment_id+'_raw_strava.csv'), index=False)
    df_raw = df.copy()
    course = Course(df)
    return course

# Sidebar input for segment ID
st.sidebar.header("Segment Data")
segment_id = st.sidebar.text_input("Enter Segment ID", "1555983")  # Example segment ID input

if st.sidebar.button("Fetch Segment Data"):
    #this initalizes a new course object by calling the strava fetch thing
    course = cached_fetch_segment_data(segment_id)
    st.session_state.course = course  # Store in session state
    
# Sidebar option for segmentation method
segmentation_method = st.sidebar.selectbox("Select Segmentation Method", ['manual segmentation', 'auto-segmentation'])
# Retrieve segment data from session state if available
segment_data = st.session_state.get('segment_data', None)

if 'course' not in st.session_state:
    course = Course(pd.read_csv(os.path.join(route_path, segment_id+'_raw_strava.csv')))
    st.session_state.course = course
else:
    course = st.session_state.course
    

    
col1, col2 = st.columns(2)
if course:
    with col1:
        st.write("Segment Route Map with Altitude Data")
        if 'segment' in course.df.columns:
            map_deck = create_map(course.df, color = 'segment')
        else:
            map_deck = create_map(course.df)
        st.pydeck_chart(map_deck)

    with col2:
        st.write("Cumulative Distance vs Altitude")
        if 'segment' in course.df.columns:
            fig = plot_cumulative_distance_vs_altitude(course.df, color = 'segment')
        else:
            fig = plot_cumulative_distance_vs_altitude(course.df)
        st.plotly_chart(fig)
     
        # Add a button to save the processed course.df to a CSV file
        if st.button("Save Processed Course Data"):
            save_path = os.path.join(route_path, f"{segment_id}_processed_course.csv")
            course.df.to_csv(save_path, index=False)
            st.write(course.df.head())
            st.success(f"Processed course data saved to {save_path}")

        course.df.to_csv(os.path.join(route_path, segment_id+'_preprocessed_route.csv'), index=False)


# Call the course_segmentation_slider function if manual segmentation is selected
if segmentation_method == 'manual segmentation':
    st.sidebar.header("Manual Segmentation")
    slider_values =course_segmentation_slider()
    if course:
        #course = st.session_state.course
        print('-------------------------------------------------')
        course.slider_segmentation(slider_values)
        st.session_state.course = course
