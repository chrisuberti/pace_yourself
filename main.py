import streamlit as st

# Set up the main page
st.set_page_config(page_title="Pace Yourself", layout="centered")

st.title("Pace Yourself")
st.write("Welcome to the Pace Yourself app! Use the navigation menu to explore the features.")

st.markdown("""
### Features:
- **Segment Data and Course Segmentation**: Analyze and segment your course data.
- **Rider Profile**: Calculate rider-specific metrics like WTank and CdA.
- **Course Optimization**: 🆕 Optimize pacing strategies and analyze power outputs.
- **Visualizations**: View route maps and altitude profiles.

### 🚀 **New in Phase 1: Course Optimization Engine**
The optimization engine has been integrated from research notebooks, providing:
- Physics-based power modeling and speed calculations
- W' (anaerobic capacity) tracking and recovery modeling  
- Optimal constant power strategy calculation
- Performance metrics including TSS, IF, and power-to-weight ratios
- Critical segment analysis for race strategy planning
""")
