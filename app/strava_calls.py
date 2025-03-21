from app.auth import get_access_token
import requests
import datetime

def fetch_segment_data(segment_id):
    """
    Fetch latitude, longitude, and altitude data for a specific segment from Strava API.

    Args:
        segment_id (int): The ID of the segment to fetch data for.

    Returns:
        dict: A dictionary with lat/lng and altitude data if successful, else None.
    """
    access_token = get_access_token()  # Get a valid token, refreshing if necessary
    url = f"https://www.strava.com/api/v3/segments/{segment_id}/streams"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "keys": "latlng,altitude",  # Request latitude/longitude and altitude data
        "key_by_type": "true"
    }

    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        # Return the parsed JSON data, which includes 'latlng' and 'altitude' keys
        return response.json()
    else:
        print(f"Failed to fetch segment data: {response.status_code} - {response.text}")
        return None


def get_activities(days):
    access_token = get_access_token()
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    start_date_unix = int(start_date.timestamp())
    end_date_unix = int(end_date.timestamp())

    url = f"https://www.strava.com/api/v3/athlete/activities?after={start_date_unix}&before={end_date_unix}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Error fetching activities: {response.status_code}")

    return response.json()

def get_power_stream(activity_id):
    """Retrieve the power stream for a specific activity."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    params = {"keys": "watts", "key_by_type": "true"}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        # Clean the power stream by filtering out None values
        return [value for value in data.get("watts", {}).get("data", []) if value is not None]
    else:
        raise Exception(f"Error retrieving streams for activity {activity_id}: {response.text}")
    
    
def get_athlete_id():
    """
    Retrieve the athlete ID from the Strava API.

    Returns:
        int: The athlete ID if successful, else None.
    """
    access_token = get_access_token()
    url = "https://www.strava.com/api/v3/athlete"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        athlete_data = response.json()
        return athlete_data.get("id")
    else:
        print(f"Failed to fetch athlete data: {response.status_code} - {response.text}")
        return None