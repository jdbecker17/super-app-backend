
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_market():
    print("1. Testing GET /market-data...")
    try:
        res = requests.get(BASE_URL + "/market-data")
        if res.status_code == 200:
            data = res.json()
            print("SUCCESS: Market Data received")
            # print(json.dumps(data, indent=2))
        else:
            print(f"FAIL: Status {res.status_code} - {res.text}")
            
    except Exception as e:
        print(f"FAIL: Connection error: {e}")

def test_assets_debug():
    print("\n2. Testing POST/GET Assets DEBUG...")
    intl_asset = {
        "ticker": "AAPL",
        "amount": 1,
        "price": 150.00,
        "category": "Stocks" 
    }
    
    try:
        print("Adding AAPL...")
        r = requests.post(BASE_URL + "/add-asset", json=intl_asset)
        print(f"POST Status: {r.status_code}")
        print(f"POST Response: {r.text}")
        
        time.sleep(2)
        
        print("Fetching Assets...")
        res = requests.get(BASE_URL + "/assets")
        if res.status_code == 200:
            data = res.json()
            print(f"Got {len(data)} assets.")
            found = False
            for a in data:
                print(f" - Found: {a.get('ticker')} | Cat: {a.get('category')} | Currency: {a.get('currency')}")
                if a.get('ticker') == 'AAPL':
                    found = True
                    # Cleanup
                    requests.delete(f"{BASE_URL}/assets/{a.get('id')}")
            
            if not found:
                print("FAIL: AAPL still not found in list.")
        else:
            print(f"FAIL GET: {res.text}")
            
    except Exception as e:
         print(f"FAIL: Error {e}")

if __name__ == "__main__":
    test_market()
    test_assets_debug()
