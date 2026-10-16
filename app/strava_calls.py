from app.auth import get_access_token
import requests
import datetime

def _parse_stream_response(response_json, stream_type):
    """
    Parse stream response from Strava API.
    
    The API returns different formats depending on key_by_type parameter:
    - key_by_type=true: Returns dict keyed by stream type (e.g., {"watts": {"data": [...]}})
    - key_by_type=false/omitted: Returns array of stream objects (e.g., [{"type": "watts", "data": [...]}])
    
    This helper handles both formats.
    """
    if isinstance(response_json, dict):
        # key_by_type=true format: {"watts": {"data": [...]}, "time": {"data": [...]}}
        stream_data = response_json.get(stream_type, {})
        return stream_data.get("data", [])
    elif isinstance(response_json, list):
        # key_by_type=false format: [{"type": "watts", "data": [...]}, ...]
        for stream in response_json:
            if stream.get("type") == stream_type:
                return stream.get("data", [])
    return []


def fetch_segment_data(segment_id, user_id=None):
    """
    Fetch latitude, longitude, and altitude data for a specific segment from Strava API.

    Args:
        segment_id (int): The ID of the segment to fetch data for.

    Returns:
        dict: A dictionary with 'latlng' and 'altitude' keys containing data arrays,
              or None if request fails.
    """
    access_token = get_access_token(user_id)
    url = f"https://www.strava.com/api/v3/segments/{segment_id}/streams"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "keys": "latlng,altitude",
        "key_by_type": "true"  # Returns dict format: {"latlng": {...}, "altitude": {...}}
    }

    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        # Return normalized structure with just the data arrays
        return {
            "latlng": _parse_stream_response(data, "latlng"),
            "altitude": _parse_stream_response(data, "altitude")
        }
    else:
        print(f"Failed to fetch segment data: {response.status_code} - {response.text}")
        return None


def get_activities(days, per_page=100, user_id=None):
    """
    Fetch activities from Strava API for the specified number of days.
    
    Args:
        days: Number of days to look back for activities.
        per_page: Number of activities per page (max 200, default 100).
    
    Returns:
        list: List of activity objects (SummaryActivity format).
    
    Raises:
        Exception: If the API request fails.
    
    Note:
        Requires `activity:read` scope. Only Me activities will be filtered out
        unless token has `activity:read_all` scope.
    """
    access_token = get_access_token(user_id)
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=days)
    
    # Strava uses epoch timestamps (seconds since 1970)
    after = int(start_date.timestamp())
    before = int(end_date.timestamp())

    headers = {"Authorization": f"Bearer {access_token}"}
    all_activities = []
    page = 1
    
    while True:
        params = {
            "after": after,
            "before": before,
            "page": page,
            "per_page": min(per_page, 200)  # API max is 200
        }
        
        response = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers=headers,
            params=params
        )

        if response.status_code != 200:
            error_msg = f"Error fetching activities: {response.status_code}"
            try:
                error_detail = response.json()
                if "message" in error_detail:
                    error_msg += f" - {error_detail['message']}"
                if "errors" in error_detail:
                    error_msg += f" - {error_detail['errors']}"
            except:
                error_msg += f" - {response.text}"
            raise Exception(error_msg)

        activities = response.json()
        
        if not activities:
            break  # No more activities
            
        all_activities.extend(activities)
        
        if len(activities) < per_page:
            break  # Last page
            
        page += 1
    
    return all_activities


def get_power_stream(activity_id, user_id=None):
    """
    Retrieve the power stream for a specific activity.
    
    Args:
        activity_id: The Strava activity ID.
    
    Returns:
        list: Power values in watts (None values filtered out).
    
    Raises:
        Exception: If the API request fails.
    
    Note:
        Requires `activity:read` scope. Requires `activity:read_all` for Only Me activities.
    """
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    headers = {"Authorization": f"Bearer {get_access_token(user_id)}"}
    params = {
        "keys": "watts",
        "key_by_type": "true"  # Returns dict format: {"watts": {"data": [...]}}
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        power_data = _parse_stream_response(data, "watts")
        # Filter out None values (gaps in power recording)
        return [value for value in power_data if value is not None]
    else:
        error_msg = f"Error retrieving streams for activity {activity_id}: {response.status_code}"
        try:
            error_detail = response.json()
            if "message" in error_detail:
                error_msg += f" - {error_detail['message']}"
        except:
            error_msg += f" - {response.text}"
        raise Exception(error_msg)
    
    
def get_athlete_profile(user_id=None):
    """Return the authenticated Strava athlete profile."""
    access_token = get_access_token(user_id)
    url = "https://www.strava.com/api/v3/athlete"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()

    error_msg = f"Failed to fetch athlete data: {response.status_code}"
    try:
        error_detail = response.json()
        if "message" in error_detail:
            error_msg += f" - {error_detail['message']}"
    except Exception:
        error_msg += f" - {response.text}"
    raise Exception(error_msg)


def get_athlete_id(user_id=None):
    """
    Retrieve the authenticated athlete's ID from the Strava API.
    
    Returns:
        int: The athlete ID if successful, else None.
    
    Note:
        Uses GET /athlete endpoint. Tokens with `profile:read_all` scope will receive
        a detailed athlete representation; all others receive a summary representation.
    """
    try:
        return get_athlete_profile(user_id=user_id).get("id")
    except Exception as error:
        print(error)
        return None


def fetch_segment_details(segment_id, user_id=None):
    """
    Fetch segment details including name, distance, elevation, etc. from Strava API.

    Args:
        segment_id (int): The ID of the segment to fetch details for.

    Returns:
        dict: A dictionary with segment details (DetailedSegment) if successful, else None.
              Includes: id, name, activity_type, distance, average_grade, maximum_grade,
              elevation_high, elevation_low, start_latlng, end_latlng, climb_category, etc.
    
    Note:
        Requires `read_all` scope to retrieve athlete-specific segment info or private segments.
    """
    access_token = get_access_token(user_id)
    url = f"https://www.strava.com/api/v3/segments/{segment_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        error_msg = f"Failed to fetch segment details: {response.status_code}"
        try:
            error_detail = response.json()
            if "message" in error_detail:
                error_msg += f" - {error_detail['message']}"
        except:
            error_msg += f" - {response.text}"
        print(error_msg)
        return None


def get_activity_by_id(activity_id, include_all_efforts=False, user_id=None):
    """
    Fetch a single activity by ID with full details.
    
    Args:
        activity_id: The Strava activity ID.
        include_all_efforts: Whether to include all segment efforts (default False).
    
    Returns:
        dict: DetailedActivity object if successful, else None.
              Includes: best_efforts (for running), segment_efforts, laps, splits, etc.
    
    Note:
        Requires `activity:read` for Everyone and Followers activities.
        Requires `activity:read_all` for Only Me activities.
    """
    access_token = get_access_token(user_id)
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"include_all_efforts": str(include_all_efforts).lower()}
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        error_msg = f"Failed to fetch activity {activity_id}: {response.status_code}"
        try:
            error_detail = response.json()
            if "message" in error_detail:
                error_msg += f" - {error_detail['message']}"
        except:
            error_msg += f" - {response.text}"
        print(error_msg)
        return None