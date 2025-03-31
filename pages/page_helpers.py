import streamlit as st
import pandas as pd

def course_segmentation_slider(distance=100):
    # Input box to take the number of sliders from the user
    num_sliders = st.sidebar.number_input("Enter the number of sliders", min_value=1, max_value=10, value=3)

    # Create a list to store the slider values
    slider_values = [0]

    # Calculate the equal distance between 0 and the distance variable
    equal_distance = distance / num_sliders

    # Generate sliders dynamically based on user input
    for i in range(1, num_sliders):
        # For subsequent sliders, use the value of the previous slider as min_value
        min_value = slider_values[i-1]
        initial_value = min_value + equal_distance

        slider_value = st.sidebar.slider(f"Segment {i}", min_value=min_value, max_value=distance, value=int(initial_value))

        # Check if the current slider value is less than the previous slider value
        if slider_value < slider_values[i-1]:
            st.sidebar.error(f"Slider {i} value cannot be less than Slider {i-1} value.")
        else:
            slider_values.append(slider_value)
    
    return slider_values

def format_and_display_table(df, decimal_places=2):
    """
    Format a DataFrame to display with a specified number of decimal places and return the st.write statement.

    Args:
        df (pd.DataFrame): The DataFrame to format.
        decimal_places (int): Number of decimal places to round to.

    Returns:
        None: Displays the formatted DataFrame using st.write.
    """
    formatted_df = df.round(decimal_places)
    st.write(formatted_df)