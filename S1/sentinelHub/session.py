from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
from config import TOKEN_URL
import os
import requests

load_dotenv()


def getCredentials():
	client_id = os.getenv('SH_CLIENT_ID', '')
	client_secret = os.getenv('SH_CLIENT_SECRET', '')

	if not client_id or not client_secret:
		raise ValueError("Client ID and Client Secret must be set in environment variables.")
	
	return client_id, client_secret


def getUserCredentials():
	username = os.getenv("CDSE_USERNAME", "")
	password = os.getenv("CDSE_PASSWORD", "")

	if not username or not password:
		raise ValueError("CDSE_USERNAME and CDSE_PASSWORD must be set in environment variables.")

	return username, password


def get_password_token() -> dict:
	username, password = getUserCredentials()
	payload = {
		"username": username,
		"password": password,
		"grant_type": "password",
		"client_id": "cdse-public",
	}

	response = requests.post(TOKEN_URL, data=payload)
	response.raise_for_status()
	return response.json()


def initializeSessionPasswordGrant() -> OAuth2Session:
	token = get_password_token()
	oauth = OAuth2Session()
	oauth.token = token
	access_token = token.get("access_token")
	if access_token:
		oauth.headers.update({"Authorization": f"Bearer {access_token}"})
	return oauth


def initializeSession():
	client_id, client_secret = getCredentials()

	# Create a session
	client = BackendApplicationClient(client_id=client_id)
	oauth = OAuth2Session(client=client)

	try:
		
		def sentinelhub_compliance_hook(response):
			response.raise_for_status()
			return response

		oauth.register_compliance_hook("access_token_response", sentinelhub_compliance_hook)

		# Get token for the session
		token = oauth.fetch_token(
			token_url=TOKEN_URL,
			client_secret=client_secret,
			include_client_id=True,
		)

		# ensure the session knows the token and set explicit Authorization header
		oauth.token = token
		access_token = token.get("access_token")
		if access_token:
			oauth.headers.update({"Authorization": f"Bearer {access_token}"})

		print("Token fetched successfully.")

		return oauth
	except Exception as e:
		print("Error fetching token:", str(e))
		exit(1)