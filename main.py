import streamlit as st

# Set up the main page
st.set_page_config(page_title="Pace Yourself", layout="centered")

st.title("Pace Yourself")
st.write("Welcome to the Pace Yourself app! Use the navigation menu to explore the features.")

st.markdown("""
### Features:
- **Segment Data and Course Segmentation**: Analyze and segment your course data.
- **Rider Profile**: Calculate rider-specific metrics like WTank and CdA.
- **Visualizations**: View route maps and altitude profiles.
""")
