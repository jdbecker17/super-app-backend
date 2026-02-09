# Mock imports
try:
    import yfinance as yf

    print("yfinance imported successfully")
except ImportError as e:
    print(f"FAILED to import yfinance: {e}")


# Copying the logic from main.py to test it
def update_prices(assets_data):
    try:
        if not assets_data:
            return {}

        tickers_map = {}
        tickers_to_fetch = []
        IGNORE_KEYWORDS = ["SELIC", "CDI", "TESOURO", "POUPANÇA", "VISTA"]

        for item in assets_data:
            if not item:
                continue
            original = item.get("ticker")
            if not original:
                continue
            upper_ticker = str(original).upper()
            if any(keyword in upper_ticker for keyword in IGNORE_KEYWORDS):
                continue
            yahoo_ticker = original
            category = item.get("category")
            if category:
                cat = str(category).lower()
                if "cripto" in cat:
                    if "-" not in original:
                        yahoo_ticker = f"{original}-USD"
                elif "ação" in cat or "fii" in cat or "renda" in cat:
                    if not original.endswith(".SA") and len(original) <= 6:
                        yahoo_ticker = f"{original}.SA"
            tickers_map[yahoo_ticker] = original
            tickers_to_fetch.append(yahoo_ticker)
            print(f"Added to fetch: {yahoo_ticker}")

        if not tickers_to_fetch:
            print("No tickers to fetch")
            return {}

        print(f"Fetching from YFinance: {tickers_to_fetch}")

        # Test yf.download
        data = yf.download(tickers_to_fetch, period="1d", progress=False, threads=False)
        print("Download complete")
        print(f"Data empty? {data.empty if data is not None else 'None'}")

        # Parsing logic... safely skipping for this test, mostly interested if download crashes or data access fails
        return {"TEST": 10.0}

    except Exception as e:
        print(f"CRITICAL ERROR in update_prices: {e}")
        import traceback

        traceback.print_exc()
        return {}


def test_logic():
    print("Starting Test Logic...")

    # Mock Data
    assets = [
        {"ticker": "PETR4", "average_price": 30.5, "category": "Ação", "quantity": 10},
        {
            "ticker": "BTC",
            "average_price": 40000.0,
            "category": "Cripto",
            "quantity": 0.1,
        },
        {
            "ticker": "SELIC",
            "average_price": 1.0,
            "category": "Renda Fixa",
            "quantity": 100,
        },
        {
            "ticker": "BAD_DATA",
            "average_price": None,
            "category": None,
            "quantity": 5,
        },  # Testing bad data
    ]

    print("Calling update_prices...")
    prices = update_prices(assets)
    print(f"Prices returned: {prices}")

    print("Simulating Enrichment Loop...")
    for asset in assets:
        try:
            ticker = asset.get("ticker")
            avg_price = asset.get("average_price")

            # THE DANGEROUS PART
            # Converting to float safely
            avg_price_safe = float(avg_price) if avg_price is not None else 0.0

            print(f"Processing {ticker}, Avg: {avg_price_safe}")

            # Simulate math
            current_price = prices.get(ticker, avg_price_safe)
            if avg_price_safe > 0:
                profit = ((current_price - avg_price_safe) / avg_price_safe) * 100
                print(f"Profit: {profit}%")
            else:
                print("Avg price 0 or None")

        except Exception as e:
            print(f"ERROR processing asset {asset}: {e}")


if __name__ == "__main__":
    test_logic()
