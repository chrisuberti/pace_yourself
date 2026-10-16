"""
Unit tests for strava_calls.py with mocked API responses.

These tests verify the parsing logic and error handling without hitting the real API.
For live API testing, use the notebook: notebooks/test_strava_api.ipynb
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strava_calls import (
    _parse_stream_response,
    fetch_segment_data,
    get_activities,
    get_power_stream,
    get_athlete_id,
    fetch_segment_details,
    get_activity_by_id,
)


# =============================================================================
# Test _parse_stream_response helper
# =============================================================================

class TestParseStreamResponse:
    """Test the stream response parser handles both API formats."""
    
    def test_dict_format_key_by_type_true(self):
        """When key_by_type=true, API returns dict keyed by stream type."""
        response = {
            "watts": {"data": [100, 150, 200, 180], "original_size": 4},
            "time": {"data": [0, 1, 2, 3], "original_size": 4}
        }
        
        result = _parse_stream_response(response, "watts")
        assert result == [100, 150, 200, 180]
        
        result = _parse_stream_response(response, "time")
        assert result == [0, 1, 2, 3]
    
    def test_list_format_key_by_type_false(self):
        """When key_by_type=false, API returns array of stream objects."""
        response = [
            {"type": "watts", "data": [100, 150, 200], "original_size": 3},
            {"type": "time", "data": [0, 1, 2], "original_size": 3}
        ]
        
        result = _parse_stream_response(response, "watts")
        assert result == [100, 150, 200]
    
    def test_missing_stream_type_returns_empty(self):
        """Missing stream type should return empty list."""
        response = {"watts": {"data": [100, 150]}}
        
        result = _parse_stream_response(response, "heartrate")
        assert result == []
    
    def test_empty_response(self):
        """Empty response should return empty list."""
        assert _parse_stream_response({}, "watts") == []
        assert _parse_stream_response([], "watts") == []


# =============================================================================
# Mock API Response Fixtures
# =============================================================================

@pytest.fixture
def mock_activities_response():
    """Sample response from GET /athlete/activities"""
    return [
        {
            "id": 12345678,
            "name": "Morning Ride",
            "distance": 45000.0,
            "moving_time": 5400,
            "elapsed_time": 5600,
            "type": "Ride",
            "sport_type": "Ride",
            "start_date": "2026-01-01T08:00:00Z",
            "average_watts": 185.5,
            "device_watts": True,
            "has_heartrate": True,
        },
        {
            "id": 12345679,
            "name": "Evening Spin",
            "distance": 25000.0,
            "moving_time": 3600,
            "elapsed_time": 3700,
            "type": "Ride",
            "sport_type": "VirtualRide",
            "start_date": "2026-01-01T18:00:00Z",
            "average_watts": 200.0,
            "device_watts": True,
        }
    ]


@pytest.fixture
def mock_power_stream_response():
    """Sample response from GET /activities/{id}/streams with key_by_type=true"""
    return {
        "watts": {
            "data": [150, 155, None, 160, 180, 175, None, 200, 195],
            "original_size": 9,
            "resolution": "high"
        },
        "time": {
            "data": [0, 1, 2, 3, 4, 5, 6, 7, 8],
            "original_size": 9
        }
    }


@pytest.fixture
def mock_athlete_response():
    """Sample response from GET /athlete"""
    return {
        "id": 186207,
        "username": "cyclist123",
        "firstname": "Chris",
        "lastname": "Rider",
        "city": "San Francisco",
        "state": "CA",
        "country": "USA",
        "sex": "M",
        "premium": True,
        "created_at": "2015-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_segment_details_response():
    """Sample response from GET /segments/{id}"""
    return {
        "id": 229781,
        "name": "Hawk Hill",
        "activity_type": "Ride",
        "distance": 2684.82,
        "average_grade": 5.7,
        "maximum_grade": 14.2,
        "elevation_high": 245.3,
        "elevation_low": 92.4,
        "start_latlng": [37.8331119, -122.4834356],
        "end_latlng": [37.8280722, -122.4981393],
        "climb_category": 1,
        "city": "San Francisco",
        "state": "CA",
        "country": "United States",
    }


@pytest.fixture
def mock_segment_streams_response():
    """Sample response from GET /segments/{id}/streams"""
    return {
        "latlng": {
            "data": [[37.833, -122.483], [37.832, -122.484], [37.831, -122.485]],
            "original_size": 3
        },
        "altitude": {
            "data": [92.4, 120.5, 150.2],
            "original_size": 3
        }
    }


@pytest.fixture
def mock_detailed_activity_response():
    """Sample response from GET /activities/{id}"""
    return {
        "id": 12345678,
        "name": "Morning Ride",
        "distance": 45000.0,
        "moving_time": 5400,
        "elapsed_time": 5600,
        "total_elevation_gain": 500,
        "type": "Ride",
        "sport_type": "Ride",
        "average_watts": 185.5,
        "max_watts": 650,
        "weighted_average_watts": 210,
        "device_watts": True,
        "kilojoules": 1000.5,
        "segment_efforts": [
            {
                "id": 987654321,
                "name": "Hawk Hill",
                "elapsed_time": 480,
                "moving_time": 475,
                "distance": 2685.0,
                "average_watts": 280,
            }
        ],
        "laps": [
            {"id": 111, "name": "Lap 1", "elapsed_time": 1800, "distance": 15000}
        ],
    }


# =============================================================================
# Test get_activities
# =============================================================================

class TestGetActivities:
    """Test fetching athlete activities."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activities_success(self, mock_get, mock_token, mock_activities_response):
        """Test successful activity fetch."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_activities_response
        mock_get.return_value = mock_response
        
        result = get_activities(days=30)
        
        assert len(result) == 2
        assert result[0]["id"] == 12345678
        assert result[0]["name"] == "Morning Ride"
        mock_get.assert_called_once()

    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activities_uses_requested_user(
            self, mock_get, mock_token, mock_activities_response):
        mock_token.return_value = "user_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_activities_response
        mock_get.return_value = mock_response

        get_activities(days=30, user_id='user-42')

        mock_token.assert_called_once_with('user-42')
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activities_pagination(self, mock_get, mock_token):
        """Test pagination when multiple pages of activities exist."""
        mock_token.return_value = "fake_token"
        
        # First page returns full page, second page returns less (last page)
        page1 = [{"id": i, "name": f"Activity {i}"} for i in range(100)]
        page2 = [{"id": 100 + i, "name": f"Activity {100 + i}"} for i in range(25)]
        
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = page1
        
        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = page2
        
        mock_get.side_effect = [mock_response1, mock_response2]
        
        result = get_activities(days=365, per_page=100)
        
        assert len(result) == 125
        assert mock_get.call_count == 2
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activities_unauthorized(self, mock_get, mock_token):
        """Test 401 error handling."""
        mock_token.return_value = "expired_token"
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Authorization Error", "errors": []}
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            get_activities(days=30)
        
        assert "401" in str(exc_info.value)
        assert "Authorization Error" in str(exc_info.value)


# =============================================================================
# Test get_power_stream
# =============================================================================

class TestGetPowerStream:
    """Test fetching power stream data."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_power_stream_success(self, mock_get, mock_token, mock_power_stream_response):
        """Test successful power stream fetch with None filtering."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_power_stream_response
        mock_get.return_value = mock_response
        
        result = get_power_stream(12345678)
        
        # None values should be filtered out
        assert None not in result
        assert result == [150, 155, 160, 180, 175, 200, 195]
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_power_stream_no_power_data(self, mock_get, mock_token):
        """Test activity without power data."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"time": {"data": [0, 1, 2]}}  # No watts
        mock_get.return_value = mock_response
        
        result = get_power_stream(12345678)
        assert result == []
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_power_stream_404(self, mock_get, mock_token):
        """Test activity not found."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Resource Not Found"}
        mock_get.return_value = mock_response
        
        with pytest.raises(Exception) as exc_info:
            get_power_stream(99999999)
        
        assert "404" in str(exc_info.value)


# =============================================================================
# Test get_athlete_id
# =============================================================================

class TestGetAthleteId:
    """Test fetching athlete ID."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_athlete_id_success(self, mock_get, mock_token, mock_athlete_response):
        """Test successful athlete ID fetch."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_athlete_response
        mock_get.return_value = mock_response
        
        result = get_athlete_id()
        
        assert result == 186207
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_athlete_id_unauthorized(self, mock_get, mock_token):
        """Test unauthorized returns None."""
        mock_token.return_value = "bad_token"
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Authorization Error"}
        mock_get.return_value = mock_response
        
        result = get_athlete_id()
        
        assert result is None


# =============================================================================
# Test fetch_segment_data
# =============================================================================

class TestFetchSegmentData:
    """Test fetching segment stream data."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_fetch_segment_data_success(self, mock_get, mock_token, mock_segment_streams_response):
        """Test successful segment data fetch."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_segment_streams_response
        mock_get.return_value = mock_response
        
        result = fetch_segment_data(229781)
        
        assert "latlng" in result
        assert "altitude" in result
        assert len(result["latlng"]) == 3
        assert result["altitude"] == [92.4, 120.5, 150.2]


# =============================================================================
# Test fetch_segment_details
# =============================================================================

class TestFetchSegmentDetails:
    """Test fetching segment details."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_fetch_segment_details_success(self, mock_get, mock_token, mock_segment_details_response):
        """Test successful segment details fetch."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_segment_details_response
        mock_get.return_value = mock_response
        
        result = fetch_segment_details(229781)
        
        assert result["id"] == 229781
        assert result["name"] == "Hawk Hill"
        assert result["average_grade"] == 5.7
        assert result["climb_category"] == 1


# =============================================================================
# Test get_activity_by_id
# =============================================================================

class TestGetActivityById:
    """Test fetching detailed activity by ID."""
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activity_by_id_success(self, mock_get, mock_token, mock_detailed_activity_response):
        """Test successful detailed activity fetch."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_detailed_activity_response
        mock_get.return_value = mock_response
        
        result = get_activity_by_id(12345678)
        
        assert result["id"] == 12345678
        assert "segment_efforts" in result
        assert len(result["segment_efforts"]) == 1
        assert result["segment_efforts"][0]["name"] == "Hawk Hill"
    
    @patch('app.strava_calls.get_access_token')
    @patch('app.strava_calls.requests.get')
    def test_get_activity_by_id_include_all_efforts(self, mock_get, mock_token, mock_detailed_activity_response):
        """Test include_all_efforts parameter is passed correctly."""
        mock_token.return_value = "fake_token"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_detailed_activity_response
        mock_get.return_value = mock_response
        
        get_activity_by_id(12345678, include_all_efforts=True)
        
        # Check the params passed to the request
        call_args = mock_get.call_args
        assert call_args.kwargs["params"]["include_all_efforts"] == "true"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
