import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))


def update_asset(asset_id, updates):
    url = f"{SUPABASE_URL}/rest/v1/portfolios?id=eq.{asset_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    response = requests.patch(url, headers=headers, json=updates)
    print(f"Updated {asset_id}: {response.status_code}")


def get_assets():
    url = f"{SUPABASE_URL}/rest/v1/portfolios?select=*"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    return requests.get(url, headers=headers).json()


if __name__ == "__main__":
    assets = get_assets()
    for a in assets:
        ticker = a.get("ticker")
        cat = a.get("category")

        # 1. Fix AAPL (Ação -> Stocks)
        if ticker == "AAPL" and cat == "Ação":
            print(f"Propagating Fix for AAPL ({a.get('id')})...")
            update_asset(a.get("id"), {"category": "Stocks"})

        # 2. Fix SELIC (Ação -> Renda Fixa)
        if ticker == "SELIC" and cat == "Ação":
            print(f"Fixing SELIC ({a.get('id')})...")
            update_asset(a.get("id"), {"category": "Renda Fixa"})

        # 3. Fix NVDA (Ação -> Stocks) - Generic Check
        if (
            ticker in ["NVDA", "MSFT", "GOOGL", "AMZN", "TSLA", "META"]
            and cat == "Ação"
        ):
            print(f"Fixing US Stock {ticker}...")
            update_asset(a.get("id"), {"category": "Stocks"})

    print("Correction Complete.")
