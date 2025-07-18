import os
import requests
from dotenv import load_dotenv
import time

load_dotenv()  # Load environment variables

# Retrieve initial values from .env
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
refresh_token = os.getenv("refresh_token")
expires_at = int(os.getenv("expires_at"))
access_token = os.getenv("access_token")


# Token refresh function
def refresh_access_token():
    global access_token, refresh_token, expires_at

    # Define the token refresh endpoint and payload
    url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    # Make the POST request to refresh the token
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = token_data["expires_at"]
        
        # Update the .env file with new tokens
        update_env_file("access_token", access_token)
        update_env_file("refresh_token", refresh_token)
        update_env_file("expires_at", str(expires_at))
        print(response.json())
        print("Access token refreshed.")
    else:
        raise Exception("Failed to refresh token: ", response.text)

# Update .env file with new token values
def update_env_file(key, value):
    with open(".env", "r") as file:
        lines = file.readlines()
    with open(".env", "w") as file:
        for line in lines:
            if line.startswith(f"{key}="):
                file.write(f"{key}={value}\n")
            else:
                file.write(line)

# Get a valid token (refresh if needed)
def get_access_token():
    global expires_at
    if time.time() > expires_at - 300:
        refresh_access_token()
    return access_token