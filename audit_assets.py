import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))


def get_assets():
    url = f"{SUPABASE_URL}/rest/v1/portfolios?select=*"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers)
    return response.json()


if __name__ == "__main__":
    assets = get_assets()
    print(f"{'TICKER':<10} | {'CATEGORY':<15} | {'TYPE (Suggested)':<15} | {'ID'}")
    print("-" * 60)
    for a in assets:
        print(
            f"{a.get('ticker'):<10} | {a.get('category'):<15} | {'?':<15} | {a.get('id')}"
        )
