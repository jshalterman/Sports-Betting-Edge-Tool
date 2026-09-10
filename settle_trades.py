import os
import csv
import requests
from dotenv import load_dotenv

load_dotenv()

KALSHI_ENV = os.getenv("KALSHI_ENV", "production").lower()
KALSHI_BASE_URL = (
    "https://external-api.kalshi.com"
    if KALSHI_ENV == "production"
    else "https://external-api.demo.kalshi.co"
)


def check_market_result(ticker: str):
    """
    Queries Kalshi for the market's final settlement status and outcome.
    Returns: ('finalized' | 'open', 'yes' | 'no' | None)
    """
    url = f"{KALSHI_BASE_URL}/trade-api/v2/markets/{ticker}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            market = response.json().get("market", {})
            status = market.get("status", "open")
            result = market.get("result", None)  # 'yes' or 'no'
            return status, result
    except Exception as e:
        print(f"⚠️ Error checking ticker {ticker}: {e}")

    return "open", None


def settle_paper_trades():
    csv_file = "paper_trades.csv"

    if not os.path.exists(csv_file):
        print("❌ No paper_trades.csv file found!")
        return

    # Read existing trades
    trades = []
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            trades.append(row)

    # Ensure settlement columns exist
    for col in ["status", "result", "pnl"]:
        if col not in fieldnames:
            fieldnames.append(col)

    updated = 0
    total_pnl = 0.0

    print("\n==================================================")
    print(" ⚖️ GRADING PAPER TRADES VIA KALSHI SETTLEMENT API ")
    print("==================================================\n")

    for trade in trades:
        # Skip trades that are already graded
        if trade.get("status") == "finalized":
            pnl_val = float(trade.get("pnl", 0.0))
            total_pnl += pnl_val
            continue

        ticker = trade["ticker"]
        status, result = check_market_result(ticker)

        if status == "finalized" and result in ["yes", "no"]:
            contracts = int(trade["contracts_bought"])
            cost = float(trade["wager_amount"])

            if result == "yes":
                # Won: Every contract pays $1.00 (100¢)
                payout = contracts * 1.00
                pnl = payout - cost
                print(f"✅ WON:  {trade['title']} | Profit: +${pnl:.2f}")
            else:
                # Lost: Contract expires at $0.00
                pnl = -cost
                print(f"❌ LOST: {trade['title']} | Loss: -${abs(pnl):.2f}")

            trade["status"] = "finalized"
            trade["result"] = result.upper()
            trade["pnl"] = f"{pnl:.2f}"
            total_pnl += pnl
            updated += 1
        else:
            trade["status"] = "PENDING"
            trade["result"] = "PENDING"
            trade["pnl"] = "0.00"
            print(f"⏳ PENDING: {trade['title']} (Game not finalized yet)")

    # Write back updated trade records
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trades)

    print("\n--------------------------------------------------")
    print(f"📊 SUMMARY: Graded {updated} new trades | Total Paper PnL: ${total_pnl:+.2f}")
    print("--------------------------------------------------\n")


if __name__ == "__main__":
    settle_paper_trades()