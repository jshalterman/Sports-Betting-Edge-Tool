import os
import requests
from dotenv import load_dotenv

# Load secret keys from .env
load_dotenv()

KALSHI_KEY_ID = os.getenv("KALSHI_KEY_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

def check_kalshi_connection():
    """Fetch public market data from Kalshi."""
    url = "https://api.elections.kalshi.com/trade-api/v2/markets?limit=3"
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("✅ Successfully connected to Kalshi API!")
            markets = data.get("markets", [])
            for m in markets[:3]:
                print(f"   - Market: {m.get('title')} (Ticker: {m.get('ticker')})")
        else:
            print(f"❌ Kalshi API Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Kalshi Connection Exception: {e}")

def check_odds_connection():
    """Fetch sports catalog from odds-api.io."""
    url = "https://api.odds-api.io/v3/sports"
    headers = {"x-api-key": ODDS_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sports = response.json()
            print("✅ Successfully connected to Odds-API.io!")
            print(f"   - Retrieved {len(sports)} sports/leagues.")
        else:
            print(f"❌ Odds API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Odds API Connection Exception: {e}")
        
if __name__ == "__main__":
    print("--- Testing API Connections ---")
    check_kalshi_connection()
    print("--------------------------------")
    check_odds_connection()