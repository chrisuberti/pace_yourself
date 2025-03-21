import unittest
from unittest.mock import patch, MagicMock
from strava_calls import fetch_segment_data, get_activities, get_power_stream

class TestStravaCalls(unittest.TestCase):

    @patch('strava_calls.get_access_token')
    @patch('strava_calls.requests.get')
    def test_fetch_segment_data(self, mock_get, mock_get_access_token):
        mock_get_access_token.return_value = 'fake_access_token'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'latlng': {'data': [[37.7749, -122.4194], [37.7750, -122.4195]]},
            'altitude': {'data': [10, 20]}
        }
        mock_get.return_value = mock_response

        segment_id = 123456
        result = fetch_segment_data(segment_id)
        self.assertIsNotNone(result)
        self.assertIn('latlng', result)
        self.assertIn('altitude', result)
        print("fetch_segment_data result:", result)

    @patch('strava_calls.get_access_token')
    @patch('strava_calls.requests.get')
    def test_get_activities(self, mock_get, mock_get_access_token):
        mock_get_access_token.return_value = 'fake_access_token'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 1, 'name': 'Activity 1'},
            {'id': 2, 'name': 'Activity 2'}
        ]
        mock_get.return_value = mock_response

        result = get_activities()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        print("get_activities result:", result)

    @patch('strava_calls.get_access_token')
    @patch('strava_calls.requests.get')
    def test_get_power_stream(self, mock_get, mock_get_access_token):
        mock_get_access_token.return_value = 'fake_access_token'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'watts': {'data': [100, 200, 150, None, 250]}
        }
        mock_get.return_value = mock_response

        activity_id = 123456
        result = get_power_stream(activity_id)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertNotIn(None, result)
        print("get_power_stream result:", result)

if __name__ == '__main__':
    unittest.main()