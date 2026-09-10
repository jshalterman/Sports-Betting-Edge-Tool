import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("ODDS_API_KEY")

print("--- KALSHI TITLES ---")
try:
    res1 = requests.get("https://external-api.kalshi.com/trade-api/v2/markets?series_ticker=KXMLBGAME", timeout=5).json()
    markets = res1.get("markets", [])
    if not markets:
        print("No active KXMLBGAME markets found on Kalshi right now.")
    for m in markets[:5]:
        print(f"Kalshi Title: {m.get('title')}")
except Exception as e:
    print(f"Kalshi Error: {e}")

print("\n--- ODDS-API TEAMS ---")
try:
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds?apiKey={key}&regions=us&markets=h2h"
    res2 = requests.get(url, timeout=5).json()
    if isinstance(res2, list):
        print(f"Success! Found {len(res2)} games on The-Odds-API.")
        for game in res2[:5]:
            print(f"Odds-API Game: {game.get('away_team')} @ {game.get('home_team')}")
    else:
        print("Odds-API Response:", res2)
except Exception as e:
        print(f"Odds-API Error: {e}")