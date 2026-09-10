import base64
import datetime
import os
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

KALSHI_KEY_ID = os.getenv("KALSHI_KEY_ID")
PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")
BASE_URL = "https://external-api.kalshi.com"


def sign_request(private_key, timestamp: str, method: str, path: str) -> str:
    """Signs request headers using your RSA private key for Kalshi API auth."""
    message = f"{timestamp}{method}{path}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def get_kalshi_balance() -> float:
    """Fetches live available balance from Kalshi in dollars."""
    path = "/trade-api/v2/portfolio/balance"
    timestamp = str(int(datetime.datetime.now().timestamp() * 1000))

    if not PRIVATE_KEY_PATH or not os.path.exists(PRIVATE_KEY_PATH):
        print(f"⚠️ Key file '{PRIVATE_KEY_PATH}' not found. Defaulting balance to $0.00.")
        return 0.0

    try:
        with open(PRIVATE_KEY_PATH, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(), password=None
            )

        signature = sign_request(private_key, timestamp, "GET", path)
        headers = {
            "KALSHI-ACCESS-KEY": KALSHI_KEY_ID,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

        res = requests.get(f"{BASE_URL}{path}", headers=headers)
        if res.status_code == 200:
            return res.json().get("balance", 0) / 100.0
        else:
            print(f"❌ Failed to fetch balance ({res.status_code}): {res.text}")
            return 0.0
    except Exception as e:
        print(f"❌ Exception retrieving balance: {e}")
        return 0.0


def calculate_kalshi_kelly(
    fair_prob: float,
    price_cents: int,
    manual_bankroll: float = None,
    max_bankroll_pct: float = 0.05,
) -> dict:
    """
    Calculates 0.5 (Half) Kelly sizing for Kalshi binary contracts.

    :param fair_prob: Devigged fair win probability (0.0 to 1.0)
    :param price_cents: Current contract purchase price in cents (1 to 99)
    :param manual_bankroll: If set, overrides live API balance query.
    :param max_bankroll_pct: Hard cap per market (default 5% = 0.05).
    :return: Dictionary containing position sizing details.
    """
    # Enforce strictly 0.5 (Half Kelly)
    KELLY_FRACTION = 0.5

    # Determine bankroll (manual override or live Kalshi balance)
    if manual_bankroll is not None:
        bankroll = manual_bankroll
    else:
        bankroll = get_kalshi_balance()

    cost = price_cents / 100.0

    # Calculate Expected Value
    ev = (fair_prob * 1.0) - cost
    ev_percent = (ev / cost) * 100 if cost > 0 else 0

    # If non-positive EV or bad pricing, return zero allocation
    if ev <= 0 or fair_prob <= cost or bankroll <= 0:
        return {
            "is_ev": False,
            "ev_percent": round(ev_percent, 2),
            "bankroll_used": round(bankroll, 2),
            "full_kelly_pct": 0.0,
            "half_kelly_pct": 0.0,
            "final_kelly_pct": 0.0,
            "wager_amount": 0.0,
            "contracts_to_buy": 0,
            "is_capped": False,
        }

    # Full Kelly for binary contracts: (p - C) / (1 - C)
    full_kelly = (fair_prob - cost) / (1.0 - cost)

    # Half Kelly (0.5 Kelly)
    half_kelly = full_kelly * KELLY_FRACTION

    # Enforce 5% maximum total bankroll cap
    is_capped = half_kelly > max_bankroll_pct
    final_kelly_pct = min(half_kelly, max_bankroll_pct)

    # Calculate exact wager amount and contract count
    max_wager_allowed = bankroll * final_kelly_pct
    contracts_to_buy = int(max_wager_allowed // cost)
    actual_wager = round(contracts_to_buy * cost, 2)

    return {
        "is_ev": True,
        "ev_percent": round(ev_percent, 2),
        "bankroll_used": round(bankroll, 2),
        "full_kelly_pct": round(full_kelly * 100, 2),
        "half_kelly_pct": round(half_kelly * 100, 2),
        "final_kelly_pct": round(final_kelly_pct * 100, 2),
        "wager_amount": actual_wager,
        "contracts_to_buy": contracts_to_buy,
        "is_capped": is_capped,
    }


# Quick Check
if __name__ == "__main__":
    # Test using a manual $1,000 bankroll
    test_result = calculate_kalshi_kelly(
        fair_prob=0.70, price_cents=55, manual_bankroll=1000.00
    )

    print("--- Half Kelly Calculation Check ---")
    print(f"+EV Trade Detected: {test_result['is_ev']}")
    print(f"Bankroll Used: ${test_result['bankroll_used']}")
    print(f"Expected Value: +{test_result['ev_percent']}%")
    print(f"Full Kelly: {test_result['full_kelly_pct']}%")
    print(f"Half Kelly (0.5): {test_result['half_kelly_pct']}%")
    print(f"Final Applied Allocation: {test_result['final_kelly_pct']}%")
    print(f"Total Wager: ${test_result['wager_amount']}")
    print(f"Contracts to Buy: {test_result['contracts_to_buy']} @ 55¢")
    print(f"Capped by 5% Limit?: {test_result['is_capped']}")