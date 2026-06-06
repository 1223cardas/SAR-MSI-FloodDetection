from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
import requests
import os

from .aquisition_config import TOKEN_URL

load_dotenv()


def getSHCredentials():
	client_id = os.getenv('SH_CLIENT_ID', '')
	client_secret = os.getenv('SH_CLIENT_SECRET', '')

	if not client_id or not client_secret:
		raise ValueError("Client ID and Client Secret must be set in environment variables.")
	
	return client_id, client_secret

def getCDSECredentials():
	username = os.getenv("CDSE_USERNAME", "")
	password = os.getenv("CDSE_PASSWORD", "")

	if not username or not password:
		raise ValueError("CDSE_USERNAME and CDSE_PASSWORD must be set in environment variables.")

	return username, password


def getCDSEToken() -> dict:
	username, password = getCDSECredentials()
	payload = {
		"username": username,
		"password": password,
		"grant_type": "password",
		"client_id": "cdse-public",
	}

	response = requests.post(TOKEN_URL, data=payload)
	response.raise_for_status()
	return response.json()

def initCDSESession() -> OAuth2Session:
	try:
		token = getCDSEToken()
		oauth = OAuth2Session()

		oauth.token = token
		access_token = token.get("access_token")

		if access_token:
			oauth.headers.update({"Authorization": f"Bearer {access_token}"})

		return oauth
	except Exception as e:
		print(f"Error initializing CDSE session: {e}")
		raise

def initSHSession():
	try:
		client_id, client_secret = getSHCredentials()

		client = BackendApplicationClient(client_id=client_id)
		oauth = OAuth2Session(client=client)

		token = oauth.fetch_token(
			token_url=TOKEN_URL, 
			client_id=client_id, 
			client_secret=client_secret
			)

		oauth.token = token
		access_token = token.get("access_token")
		if access_token:
			oauth.headers.update({"Authorization": f"Bearer {access_token}"})

		return oauth
	except Exception as e:
		print(f"Error initializing Sentinel Hub session: {e}")
		raise
