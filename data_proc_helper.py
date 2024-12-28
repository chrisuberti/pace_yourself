import pandas as pd
import numpy as np


def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    initial_bearing = np.arctan2(x, y)
    initial_bearing = np.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return compass_bearing

# Function to convert bearing to cardinal direction
def bearing_to_cardinal(bearing):
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((bearing + 11.25) / 22.5)
    return directions[idx % 16]


def process_segment(df):
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)
    df["altitude"] = df["altitude"].astype(float)
    #calculate the net distance between a pair of lat/lon points
    df["delta_lat"] = df["lat"].diff()
    df["delta_lon"] = df["lon"].diff()
    df["distance"] = (df["delta_lat"]**2 + df["delta_lon"]**2)**0.5
    df["distance"] = df["distance"].fillna(0)
    #convert the lat/lon distance to meters
    df["distance"] = df["distance"] * 111139
    #calculate the cumulative distance
    df["cumulative_distance"] = df["distance"].cumsum()
    #calculate the gradient between two points
    df["delta_altitude"] = df["altitude"].diff()
    df["gradient"] = (df["delta_altitude"] / df["distance"]) * 100
    df["gradient"] = df["gradient"].fillna(0)
    return df

def smooth_data(df_col, window_size=5):
    return (
        df_col
        .rolling(window=window_size, center=True)
        .mean()
        .fillna(method='bfill')  # Fill the start of the DataFrame
        .fillna(method='ffill')  # Fill the end of the DataFrame
    )


