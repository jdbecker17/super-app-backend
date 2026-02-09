import requests

BASE_URL = "http://localhost:8000"


def test_api():
    print("1. Testing GET / (Frontend)...")
    try:
        res = requests.get(BASE_URL + "/")
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print("SUCCESS: Frontend loaded")
        else:
            print("FAIL: Frontend not 200")
    except Exception as e:
        print(f"FAIL: Could not connect to server: {e}")
        return

    print("\n2. Testing POST /add-asset...")
    new_asset = {
        "ticker": "TEST-FIX",
        "amount": 10,
        "price": 100.50,
        "category": "Ação",
    }
    try:
        res = requests.post(BASE_URL + "/add-asset", json=new_asset)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print("SUCCESS: Asset added")
            print(res.json())
        else:
            print(f"FAIL: {res.text}")
    except Exception as e:
        print(f"FAIL: POST Error {e}")

    print("\n3. Testing GET /assets...")
    try:
        res = requests.get(BASE_URL + "/assets")
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            print(f"SUCCESS: Retrieved {len(data)} assets")
            # Verify if TEST-FIX is there
            found = False
            for item in data:
                if item.get("ticker") == "TEST-FIX":
                    found = True
                    # Clean up
                    print(f"Cleaning up asset ID: {item.get('id')}")
                    requests.delete(f"{BASE_URL}/assets/{item.get('id')}")

            if found:
                print("VERIFIED: Newly added asset was found in list.")
            else:
                print("FAIL: Newly added asset NOT found.")

        else:
            print(f"FAIL: {res.text}")
    except Exception as e:
        print(f"FAIL: GET Error {e}")


if __name__ == "__main__":
    test_api()
