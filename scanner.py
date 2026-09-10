import os
import csv
import requests
from datetime import datetime
from dotenv import load_dotenv

# Import shared Kelly calculator
from kelly import calculate_kalshi_kelly

load_dotenv()

# --- CONFIGURATION ---
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
KALSHI_ENV = os.getenv("KALSHI_ENV", "production").lower()
PAPER_BANKROLL = 200.00  # $200 bankroll
MIN_EV_THRESHOLD = 2.5
MAX_EV_THRESHOLD = 8.0  # Tightened ceiling to filter out stale API lag

if KALSHI_ENV == "production":
    KALSHI_BASE_URL = "https://external-api.kalshi.com"
    print("⚡ ENVIRONMENT: PRODUCTION (READ-ONLY PAPER TRADING)")
else:
    KALSHI_BASE_URL = "https://external-api.demo.kalshi.co"
    print("🧪 ENVIRONMENT: DEMO / SANDBOX")


# --- MLB TEAM ALIAS NORMALIZATION MAP ---
MLB_TEAM_ALIASES = {
    "arizona diamondbacks": ["arizona", "diamondbacks", "d-backs", "ari"],
    "atlanta braves": ["atlanta", "braves", "atl"],
    "baltimore orioles": ["baltimore", "orioles", "bal"],
    "boston red sox": ["boston", "red sox", "bos"],
    "chicago white sox": ["chicago white sox", "white sox", "cws"],
    "chicago cubs": ["chicago cubs", "cubs", "chc"],
    "cincinnati reds": ["cincinnati", "reds", "cin"],
    "cleveland guardians": ["cleveland", "guardians", "cle"],
    "colorado rockies": ["colorado", "rockies", "col"],
    "detroit tigers": ["detroit", "tigers", "det"],
    "houston astros": ["houston", "astros", "hou"],
    "kansas city royals": ["kansas city", "royals", "kc"],
    "los angeles angels": ["la angels", "angels", "laa"],
    "los angeles dodgers": ["la dodgers", "dodgers", "lad"],
    "miami marlins": ["miami", "marlins", "mia"],
    "milwaukee brewers": ["milwaukee", "brewers", "mil"],
    "minnesota twins": ["minnesota", "twins", "min"],
    "new york yankees": ["ny yankees", "yankees", "nyy"],
    "new york mets": ["ny mets", "mets", "nym"],
    "oakland athletics": ["oakland", "athletics", "a's", "oak"],
    "philadelphia phillies": ["philadelphia", "phillies", "phi"],
    "pittsburgh pirates": ["pittsburgh", "pirates", "pit"],
    "san diego padres": ["san diego", "padres", "sd"],
    "san francisco giants": ["san francisco", "giants", "sf"],
    "seattle mariners": ["seattle", "mariners", "sea"],
    "st. louis cardinals": ["st. louis", "cardinals", "stl"],
    "tampa bay rays": ["tampa bay", "rays", "tb"],
    "texas rangers": ["texas", "rangers", "tex"],
    "toronto blue jays": ["toronto", "blue jays", "tor"],
    "washington nationals": ["washington", "nationals", "was"]
}

def normalize_mlb_team(raw_name: str) -> str:
    clean = raw_name.lower().strip()
    for canonical, aliases in MLB_TEAM_ALIASES.items():
        if any(alias in clean for alias in aliases):
            return canonical
    return clean


def log_paper_trade(trade_data: dict):
    file_exists = os.path.isfile("paper_trades.csv")
    fields = [
        "timestamp", "ticker", "title", "ask_price_cents", 
        "fair_prob_pct", "ev_percent", "contracts_bought", 
        "wager_amount", "line_source"
    ]
    with open("paper_trades.csv", mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_data)


def get_existing_logged_tickers():
    if not os.path.exists("paper_trades.csv"):
        return set()
    logged = set()
    with open("paper_trades.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("ticker"):
                logged.add(row["ticker"])
    return logged


def get_kalshi_realtime_prices(ticker: str):
    url = f"{KALSHI_BASE_URL}/trade-api/v2/markets/{ticker}/orderbook"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            orderbook = response.json().get("orderbook_fp", {})
            no_bids = orderbook.get("no_dollars", [])
            best_no_bid = float(no_bids[-1][0]) * 100.0 if no_bids else None
            best_yes_ask = (100.0 - best_no_bid) if best_no_bid is not None else None
            return best_yes_ask
    except Exception as e:
        print(f"⚠️ Orderbook fetch error for {ticker}: {e}")
    return None


def get_kalshi_mlb_markets():
    url = f"{KALSHI_BASE_URL}/trade-api/v2/markets"
    params = {"limit": 200, "status": "open", "series_ticker": "KXMLBGAME"}
    mlb_markets = []
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            markets = response.json().get("markets", [])
            for m in markets:
                ticker = m.get("ticker", "").upper()
                title = m.get("title", "")
                if not any(x in ticker or x in title.upper() for x in ["WORLD", "SERIES", "PENNANT", "DIVISION"]):
                    m["_prop_type"] = "MLB Game Outcome"
                    mlb_markets.append(m)
            print(f"✅ Kalshi: Found {len(mlb_markets)} active single-game MLB markets.")
    except Exception as e:
        print(f"❌ Exception fetching Kalshi MLB markets: {e}")
    return mlb_markets


def get_sharp_mlb_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us,eu",
        "bookmakers": "pinnacle",
        "markets": "h2h",
        "oddsFormat": "american"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            events = response.json()
            print(f"✅ Pinnacle MLB: Loaded {len(events)} upcoming baseball games.")
            return events
    except Exception as e:
        print(f"❌ Connection Error: {e}")
    return []


def devig_2way_multiplicative(team_odds: float, opp_odds: float):
    def american_to_implied(odds):
        return 100.0 / (odds + 100.0) if odds > 0 else abs(odds) / (abs(odds) + 100.0)

    raw_team = american_to_implied(team_odds)
    raw_opp = american_to_implied(opp_odds)
    total_implied = raw_team + raw_opp
    return (raw_team / total_implied), (raw_opp / total_implied)


def match_mlb_odds(market: dict, odds_data: list):
    """
    Precisely matches a Kalshi MLB market dictionary strictly to Pinnacle's 2-way 
    Moneyline (h2h) and rejects spread or total juice prices.
    """
    if not odds_data or not market:
        return None, None, None

    ticker = market.get("ticker", "").upper()
    title = market.get("title", "").lower()
    sub_title = market.get("yes_sub_title", "").lower()

    for event in odds_data:
        home_team_raw = event.get("home_team", "")
        away_team_raw = event.get("away_team", "")

        home_canonical = normalize_mlb_team(home_team_raw)
        away_canonical = normalize_mlb_team(away_team_raw)

        home_aliases = MLB_TEAM_ALIASES.get(home_canonical, [home_canonical])
        away_aliases = MLB_TEAM_ALIASES.get(away_canonical, [away_canonical])

        # Verify Pinnacle event matches Kalshi title
        game_matches = any(a in title for a in home_aliases) or any(a in title for a in away_aliases)

        if game_matches:
            for book in event.get("bookmakers", []):
                for mkt in book.get("markets", []):
                    
                    # --- STRICT MARKET FILTER: MUST BE H2H (MONEYLINE) ONLY ---
                    if mkt.get("key") == "h2h":
                        outcomes = mkt.get("outcomes", [])
                        if len(outcomes) >= 2:
                            home_obj = next((o for o in outcomes if o.get("name") == home_team_raw), None)
                            away_obj = next((o for o in outcomes if o.get("name") == away_team_raw), None)

                            if home_obj and away_obj:
                                home_price = home_obj.get("price")
                                away_price = away_obj.get("price")

                                # Verify both prices exist and are non-zero
                                if home_price is not None and away_price is not None:
                                    
                                    # REJECT JUICE ANOMALIES (e.g. -105/-103 usually means total/spread)
                                    if abs(home_price) <= 108 and abs(away_price) <= 108:
                                        print(f"  ⚠️ Skipped [{ticker}]: Odds ({home_price}/{away_price}) look like total/spread juice, not true ML.")
                                        continue

                                    fair_home, fair_away = devig_2way_multiplicative(home_price, away_price)
                                    book_name = book.get("title", "Pinnacle")

                                    # Match Home Contract
                                    if any(a in sub_title for a in home_aliases) or ticker.endswith(f"-{home_canonical.upper()[:3]}"):
                                        return fair_home, f"{book_name} ML ({home_team_raw} {int(home_price):+d} / {away_team_raw} {int(away_price):+d})", "HOME"

                                    # Match Away Contract
                                    if any(a in sub_title for a in away_aliases) or ticker.endswith(f"-{away_canonical.upper()[:3]}"):
                                        return fair_away, f"{book_name} ML ({away_team_raw} {int(away_price):+d} / {home_team_raw} {int(home_price):+d})", "AWAY"

    return None, None, None

def run_mlb_scanner():
    print("\n==================================================")
    print(" ⚾ MLB 2-WAY PAPER SCANNER (MIN +2.5% EV ENFORCED) ")
    print("==================================================\n")

    print(f"💰 Simulated Bankroll: ${PAPER_BANKROLL:.2f}")
    print(f"🎯 EV Target Window: +{MIN_EV_THRESHOLD}% to +{MAX_EV_THRESHOLD}%\n")

    already_logged_tickers = get_existing_logged_tickers()
    kalshi_markets = get_kalshi_mlb_markets()
    odds_events = get_sharp_mlb_odds()

    match_groups = {}
    for m in kalshi_markets:
        ticker = m.get("ticker", "")
        base_match_id = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
        if base_match_id not in match_groups:
            match_groups[base_match_id] = []
        match_groups[base_match_id].append(m)

    ev_opportunities = []

    print("\n--------------------------------------------------")
    print("📋 EVALUATING MATCH GROUPS FOR MIN +2.5% EV EDGES")
    print("--------------------------------------------------\n")

    for base_id, markets in match_groups.items():
        best_match_opp = None
        highest_ev = -999.0

        for market in markets:
            ticker = market.get("ticker", "")
            title = market.get("title", "")

            if ticker in already_logged_tickers:
                continue

            yes_ask = get_kalshi_realtime_prices(ticker)
            if yes_ask is None or yes_ask <= 0 or yes_ask >= 100:
                continue

            fair_prob, source_label, side = match_mlb_odds(market, odds_events)

            if fair_prob is None or fair_prob <= 0.0:
                continue

            if fair_prob < 0.20 or fair_prob > 0.75:
                continue

            kelly_res = calculate_kalshi_kelly(
                fair_prob=fair_prob,
                price_cents=yes_ask,
                manual_bankroll=PAPER_BANKROLL,
                max_bankroll_pct=0.05
            )

            # --- STRICT +2.5% EV FLOOR & +30% CEILING FILTER ---
            if kelly_res["ev_percent"] < MIN_EV_THRESHOLD or kelly_res["ev_percent"] > MAX_EV_THRESHOLD:
                continue

            if kelly_res["is_ev"] and kelly_res["contracts_to_buy"] > 0:
                if kelly_res["ev_percent"] > highest_ev:
                    highest_ev = kelly_res["ev_percent"]
                    best_match_opp = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ticker": ticker,
                        "title": title,
                        "ask_price_cents": yes_ask,
                        "fair_prob_pct": round(fair_prob * 100, 1),
                        "ev_percent": kelly_res["ev_percent"],
                        "contracts_bought": kelly_res["contracts_to_buy"],
                        "wager_amount": kelly_res["wager_amount"],
                        "line_source": source_label
                    }

        if best_match_opp:
            ev_opportunities.append(best_match_opp)
            log_paper_trade(best_match_opp)
            
            for m in markets:
                already_logged_tickers.add(m.get("ticker"))

            print(f"🎯 Game [{base_id}]: Logged Best Edge -> {best_match_opp['title']}")
            print(f"   Ticker: {best_match_opp['ticker']} | Line: {best_match_opp['line_source']}")
            print(f"   Fair Prob: {best_match_opp['fair_prob_pct']}% | EV: +{best_match_opp['ev_percent']}% | Wager: ${best_match_opp['wager_amount']:.2f}\n")

    print("--------------------------------------------------")
    print(f"📊 SCAN COMPLETE: Logged {len(ev_opportunities)} High-Quality (+2.5%+ EV) MLB Games")
    print("--------------------------------------------------\n")


if __name__ == "__main__":
    run_mlb_scanner()