import streamlit as st
from app.rider import *
import pandas as pd

# Ensure session state for rider profile
if "rider" not in st.session_state:
    st.session_state.rider = None

# Sidebar input for rider profile calculation method
st.sidebar.header("Rider Profile")
calculation_method = st.sidebar.selectbox(
    "Select Calculation Method",
    ["Calculate based on CP and rider type", "Calculate based on best efforts"]
)

# Inputs for "Calculate based on CP and rider type"
if calculation_method == "Calculate based on CP and rider type":
    rider_type = st.sidebar.selectbox("Rider Type", ["time_trialist", "sprinter", "all_rounder"])
    critical_power = st.sidebar.number_input("Critical Power (W)", min_value=0, value=300)
    best_efforts = None  # Ensure best_efforts is not used in this case

# Inputs for "Calculate based on best efforts"
elif calculation_method == "Calculate based on best efforts":
    best_efforts_input = st.sidebar.text_area(
        "Best Efforts (JSON format)",
        '{60: 400, 300: 350, 600: 330, 1200: 310, 1800: 290}'
    )
    critical_power = None  # Ensure critical_power is not used in this case
    rider_type = None  # Ensure rider_type is not used in this case
    best_efforts = None
    if best_efforts_input:
        try:
            best_efforts = eval(best_efforts_input)
            # Convert all JSON keys and values to floats
            best_efforts = {float(k): float(v) for k, v in best_efforts.items()}
        except Exception as e:
            st.sidebar.error(f"Invalid JSON format: {e}")

# Inputs for additional rider attributes
st.sidebar.header("Additional Rider Attributes")
height = st.sidebar.number_input("Height (m)", min_value=0.0, value=1.75, step=0.01)
weight = st.sidebar.number_input("Weight (kg)", min_value=0.0, value=70.0, step=0.1)
bike_type = st.sidebar.selectbox("Bike Type", ["Road", "TT", "Gravel", "MTB"])
position = st.sidebar.selectbox("Position", ["Hoods", "Drops", "Aero", "Flat"])

# Button to initialize the Rider instance
if st.sidebar.button("Calculate"):
    rider = Rider(
        height=height,
        weight=weight,
        bike_type=bike_type,
        position=position,
        rider_type=rider_type,
        critical_power=critical_power,
        best_efforts=best_efforts
    )
    st.session_state.rider = rider  # Save the Rider instance to session state
    st.sidebar.success("Rider instance created successfully!")

# Display Rider details if initialized
if st.session_state.rider:
    st.header("Rider Details")

    # Create a table of dynamically calculated CdA values for all bike type positions
    rider = st.session_state.rider
    st.write(st.session_state.rider)
    cda_table = []
    for bike, positions in rider.BIKE_TYPE_CDA.items():
        for pos in positions.keys():
            rider.bike_type = bike
            rider.position = pos
            cda = rider.estimate_CdA()  # Dynamically calculate CdA
            cda_table.append({"Bike Type": bike, "Position": pos, "CdA (m²)": cda})

    st.table(pd.DataFrame(cda_table))

# Visualize power-duration curve
if st.sidebar.button("Plot Power-Duration Curve"):
    if st.session_state.rider and st.session_state.rider.WTank_calculator:
        wt_calculator = st.session_state.rider.WTank_calculator
        st.write("Power-Duration Curve")
        fig = wt_calculator.plot_power_duration_curve()  # Get the plot object
        st.pyplot(fig)  # Display the plot in Streamlit
    else:
        st.sidebar.error("Please calculate the Rider instance first.")
