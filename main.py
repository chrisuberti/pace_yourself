import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Local pace-yourself imports
from auth import fetch_segment_data
from data_proc_helper import *
from visualizations import *

@st.cache_data
def cached_fetch_segment_data(segment_id):
    return fetch_segment_data(segment_id)

# Sidebar input for segment ID
st.sidebar.header("Segment Data")
segment_id = st.sidebar.text_input("Enter Segment ID", "1555983")  # Example segment ID input

if st.sidebar.button("Fetch Segment Data"):
    segment_data = cached_fetch_segment_data(segment_id)
    st.session_state.segment_data = segment_data  # Store in session state

# Retrieve segment data from session state if available
segment_data = st.session_state.get('segment_data', None)

if segment_data:
    # Extract lat/lng and altitude data if available
    latlng_data = segment_data.get("latlng", {}).get("data", [])
    altitude_data = segment_data.get("altitude", {}).get("data", [])

    # Ensure we have both lat/lng and altitude data to proceed
    if latlng_data and altitude_data and len(latlng_data) == len(altitude_data):
        # Create a DataFrame with latitude, longitude, and altitude
        df = pd.DataFrame(latlng_data, columns=["lat", "lon"])
        df["altitude"] = altitude_data  
        df = process_segment(df)
        

        col1, col2 = st.columns(2)
        with col1:
            st.write("Segment Route Map with Altitude Data")
            map_deck = create_map(df)
            st.pydeck_chart(map_deck)

        with col2:
            st.write("Cumulative Distance vs Altitude")
            fig = plot_cumulative_distance_vs_altitude(df)
            st.plotly_chart(fig)
        df.to_csv('data_sample.csv', index=False)
    else:
        st.warning("Mismatch or missing lat/lng and altitude data for this segment.")
else:
    st.error("Failed to retrieve segment data.")