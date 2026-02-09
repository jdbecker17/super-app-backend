import requests
import time

BASE_URL = "http://localhost:8000"

print("Testing /dividends endpoint...")
try:
    start = time.time()
    res = requests.get(f"{BASE_URL}/dividends")
    elapsed = time.time() - start
    
    print(f"Status: {res.status_code}")
    print(f"Time: {elapsed:.2f}s")
    
    if res.status_code == 200:
        data = res.json()
        print(f"Total 12m: R$ {data.get('total_12m', 0):.2f}")
        print(f"History Entries: {len(data.get('history', []))}")
        print(f"Upcoming Entries: {len(data.get('upcoming', []))}")
        
        if data.get('history'):
            print("Last 3 History:", data['history'][-3:])
    else:
        print("Error:", res.text)

except Exception as e:
    print(f"Connection failed: {e}")
