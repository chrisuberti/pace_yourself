import requests
import pandas as pd
import os
from polyline import decode  # Requires the `polyline` library for decoding
from dotenv import load_dotenv

load_dotenv()

# Replace these with your specific segment ID and access token
segment_id = "1555983"  # Insert the segment ID here
access_token = os.getenv("access_token")

# Define the endpoint and headers
url = f"https://www.strava.com/api/v3/segments/{segment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}

# Make the GET request to Strava API
response = requests.get(url, headers=headers)

# Check if the request was successful
if response.status_code == 200:
    # Parse the JSON response
    segment_data = response.json()
    
    # Extract and decode the polyline
    polyline_data = segment_data.get("map", {}).get("polyline")
    if polyline_data:
        decoded_points = decode(polyline_data)  # Decode the polyline into lat/lng points
        
        # Convert the decoded polyline points into a DataFrame
        df = pd.DataFrame(decoded_points, columns=["lat", "lng"])
        
        # Display the DataFrame
        print("Dataframe head:\n", df.head())
        print("Dataframe shape: ", df.shape)
    else:
        print("Polyline data not found in the response.")
else:
    print(f"Error: {response.status_code} - {response.text}")
