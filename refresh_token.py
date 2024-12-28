import requests
import json

# Load the secret.json file
with open('secret.json', 'r') as file:
    secrets = json.load(file)

# Access the client_id and client_secret
client_id = secrets['client_id']
client_secret = secrets['client_secret']
refresh_token = secrets['refresh_token']

# Replace with your Strava client details and authorization code
authorization_code = "AUTHORIZATION_CODE"

# Define the token exchange URL
url = "https://www.strava.com/oauth/token"

# Define the payload
payload = {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": authorization_code,
    "grant_type": "authorization_code"
}

# Make the POST request
response = requests.post(url, data=payload)

# Check if the request was successful
if response.status_code == 200:
    token_data = response.json()
    print("Access Token:", token_data["access_token"])
    print("Refresh Token:", token_data["refresh_token"])
    print("Expires At:", token_data["expires_at"])
else:
    print(f"Error: {response.status_code} - {response.text}")
