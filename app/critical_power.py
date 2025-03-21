import pandas as pd
from strava_calls import *
import numpy as np

def calculate_critical_power(activities, durations):
    """
    Calculate the best critical power for specified durations.

    Args:
        activities: List of activities with IDs.
        durations: List of durations in seconds.

    Returns:
        A dictionary of best critical power for each duration.
    """
    best_power = {duration: 0 for duration in durations}

    for activity in activities:
        activity_id = activity["id"]

        try:
            # Attempt to get the power stream
            power_stream = get_power_stream(activity_id)
        except Exception as e:
            print(f"Error processing activity {activity_id}: {e}")
            continue

        for duration in durations:
            if len(power_stream) >= duration:
                avg_power = max(
                    np.mean(power_stream[i:i + duration])
                    for i in range(len(power_stream) - duration + 1)
                )
                best_power[duration] = max(best_power[duration], avg_power)

    return best_power



# Main workflow
try:
    print('starting')
    activities = get_activities()  # Retrieve activities using the token from auth.py
    print('activities', activities)
    durations = [5, 30, 60, 300, 1200]  # Durations in seconds (5s, 30s, 1min, 5min, 20min)
    critical_power = calculate_critical_power(activities, durations)

    print("Critical Power Profile:")
    for duration, power in critical_power.items():
        print(f"{duration}s: {power:.2f} watts")
except Exception as e:
    print(f"Error: {e}")
    print("Traceback:")
    print(traceback.format_exc())