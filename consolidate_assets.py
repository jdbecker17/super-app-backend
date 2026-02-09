import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))

def sb_fetch(endpoint, method="GET", params=None, json_body=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    if method == "GET":
        return requests.get(url, headers=headers, params=params).json()
    elif method == "POST":
        return requests.post(url, headers=headers, json=json_body).json()
    elif method == "DELETE":
        return requests.delete(url, headers=headers, params=params)
    elif method == "PATCH":
        return requests.patch(url, headers=headers, params=params, json=json_body).json()

def consolidate():
    assets = sb_fetch("portfolios", params={"select": "*"})
    
    # Group by Ticker
    grouped = {}
    for a in assets:
        ticker = a['ticker']
        if ticker not in grouped: grouped[ticker] = []
        grouped[ticker].append(a)
    
    for ticker, items in grouped.items():
        if len(items) > 1:
            print(f"Consolidating {ticker} ({len(items)} entries)...")
            
            total_qty = 0
            total_invested = 0.0
            cat = items[0]['category'] 
            user_id = items[0]['user_id']
            
            for i in items:
                q = float(i['quantity'])
                p = float(i['average_price'])
                total_qty += q
                total_invested += (q * p)
                
                # Use latest valid category if mixed
                if i['category'] and i['category'] != 'Ação':
                    cat = i['category']
            
            avg_price = total_invested / total_qty if total_qty > 0 else 0.0
            
            print(f" -> New Total: {total_qty} @ {avg_price:.2f} ({cat})")
            
            # 1. Update First Item
            first_id = items[0]['id']
            sb_fetch("portfolios", method="PATCH", params={"id": f"eq.{first_id}"}, 
                     json_body={
                         "quantity": total_qty, 
                         "average_price": avg_price,
                         "category": cat
                     })
            
            # 2. Delete Others
            for i in items[1:]:
                sb_fetch("portfolios", method="DELETE", params={"id": f"eq.{i['id']}"})
                print(f" -> Deleted duplicate {i['id']}")

if __name__ == "__main__":
    consolidate()
