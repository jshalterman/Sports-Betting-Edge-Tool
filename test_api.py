import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("ODDS_API_KEY")

url = "https://api.odds-api.io/v3/odds"
params = {
    "apiKey": key,
    "sport": "baseball",
    "market": "player_pitcher_strikeouts"
}

try:
    res = requests.get(url, params=params, timeout=10)
    print(f"Status Code: {res.status_code}")
    print("Response Preview:", res.text[:400])
except Exception as e:
    print(f"Error: {e}")