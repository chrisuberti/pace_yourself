import streamlit as st
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = "http://localhost:8502/callback"  # Update to match your Streamlit app

# Step 1: Generate the authorization URL and display it to the user
auth_url = (
    "https://www.strava.com/oauth/authorize?"
    + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "read,activity:read_all"
    })
)

st.title("Strava OAuth Example with Streamlit")

if st.button("Authorize with Strava"):
    st.write("Please authorize the application by following this link:")
    st.markdown(f"[Authorize Strava]({auth_url})")

# Step 2: Capture the authorization code from the redirected URL
query_params = st.experimental_get_query_params()
authorization_code = query_params.get("code", [None])[0]  # Extract 'code' if present

# Step 3: Exchange authorization code for tokens if code is available
if authorization_code:
    st.write("Authorization Code:", authorization_code)

    # Prepare the token request
    token_url = "https://www.strava.com/oauth/token"
    token_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": authorization_code,
        "grant_type": "authorization_code"
    }

    # Make the POST request to get the tokens
    response = requests.post(token_url, data=token_payload)

    # Handle the response
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = token_data["expires_at"]

        st.success("Authorization successful! Tokens acquired.")
        st.write("Access Token:", access_token)
        st.write("Refresh Token:", refresh_token)

        # Step 4: Save tokens to .env for reuse
        def update_env_file(key, value):
            with open(".env", "r") as file:
                lines = file.readlines()
            with open(".env", "w") as file:
                for line in lines:
                    if line.startswith(f"{key}="):
                        file.write(f"{key}={value}\n")
                    else:
                        file.write(line)
        
        # Update .env with new tokens and expiration
        update_env_file("access_token", access_token)
        update_env_file("refresh_token", refresh_token)
        update_env_file("expires_at", str(expires_at))

        st.write("Tokens saved to .env file for future use.")
    else:
        st.error(f"Failed to acquire tokens: {response.text}")
else:
    st.info("Awaiting authorization... Once you authorize, the page will capture the authorization code.")
