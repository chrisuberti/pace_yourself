import pandas as pd
import numpy as np
import traceback
from app.strava_calls import get_activities, get_power_stream


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


# Main workflow - only runs when executed directly
if __name__ == "__main__":
    try:
        print('starting')
        # Fetch activities from the last 90 days
        activities = get_activities(days=90)
        print(f'Found {len(activities)} activities')
        
        durations = [5, 30, 60, 300, 1200]  # Durations in seconds (5s, 30s, 1min, 5min, 20min)
        critical_power = calculate_critical_power(activities, durations)

        print("Critical Power Profile:")
        for duration, power in critical_power.items():
            print(f"{duration}s: {power:.2f} watts")
    except Exception as e:
        print(f"Error: {e}")
        print("Traceback:")
        print(traceback.format_exc())