import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRO: Configure SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no .env")
    exit(1)


def supabase_post(table, data):
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # Upsert basic
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code < 300:
        print(f"{table}: Inserido/Atualizado {len(data)} registros.")
    else:
        print(f"{table} Erro {resp.status_code}: {resp.text}")


def seed_institutions():
    institutions = [
        {
            "name": "XP Investimentos",
            "code": "102",
            "country": "BR",
            "logo_url": "https://logodownload.org/wp-content/uploads/2019/11/xp-investimentos-logo.png",
        },
        {
            "name": "BTG Pactual",
            "code": "199",
            "country": "BR",
            "logo_url": "https://logodownload.org/wp-content/uploads/2017/09/btg-pactual-logo.png",
        },
        {
            "name": "Avenue Securities",
            "code": "AVE",
            "country": "US",
            "logo_url": "https://avenue.us/wp-content/uploads/2021/01/logo-avenue.svg",
        },
        {
            "name": "Binance",
            "code": "BIN",
            "country": "Global",
            "logo_url": "https://public.bnbstatic.com/20190405/eb2349c3-b2f8-4a93-a286-8f86a62ea9d8.png",
        },
        {
            "name": "NuInvest",
            "code": "260",
            "country": "BR",
            "logo_url": "https://logodownload.org/wp-content/uploads/2021/08/nu-invest-logo.png",
        },
        {
            "name": "Inter",
            "code": "109",
            "country": "BR",
            "logo_url": "https://logodownload.org/wp-content/uploads/2017/11/banco-inter-logo.png",
        },
    ]
    supabase_post("institutions", institutions)


def seed_assets_master():
    assets = [
        # B3 Stocks
        {
            "ticker": "PETR4",
            "name": "Petrobras PN",
            "type": "stock_br",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "VALE3",
            "name": "Vale ON",
            "type": "stock_br",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "WEGE3",
            "name": "Weg ON",
            "type": "stock_br",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "ITUB4",
            "name": "Itaú Unibanco PN",
            "type": "stock_br",
            "currency": "BRL",
            "exchange": "B3",
        },
        # FIIs
        {
            "ticker": "KNIP11",
            "name": "Kinea Índices de Preços",
            "type": "fii",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "HGLG11",
            "name": "CSHG Logística",
            "type": "fii",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "MXRF11",
            "name": "Maxi Renda",
            "type": "fii",
            "currency": "BRL",
            "exchange": "B3",
        },
        # US Stocks
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "type": "stock_us",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        {
            "ticker": "NVDA",
            "name": "NVIDIA Corp.",
            "type": "stock_us",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        {
            "ticker": "MSFT",
            "name": "Microsoft Corp.",
            "type": "stock_us",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        {
            "ticker": "TSLA",
            "name": "Tesla Inc.",
            "type": "stock_us",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        # ETFs
        {
            "ticker": "IVVB11",
            "name": "iShares S&P 500 BHD",
            "type": "etf_br",
            "currency": "BRL",
            "exchange": "B3",
        },
        {
            "ticker": "VOO",
            "name": "Vanguard S&P 500",
            "type": "etf_us",
            "currency": "USD",
            "exchange": "NYSE",
        },
        {
            "ticker": "VNQ",
            "name": "Vanguard Real Estate",
            "type": "reit",
            "currency": "USD",
            "exchange": "NYSE",
        },
        # Crypto
        {
            "ticker": "BTC",
            "name": "Bitcoin",
            "type": "crypto",
            "currency": "USD",
            "exchange": "CRYPTO",
        },
        {
            "ticker": "ETH",
            "name": "Ethereum",
            "type": "crypto",
            "currency": "USD",
            "exchange": "CRYPTO",
        },
    ]
    supabase_post("assets_master", assets)


if __name__ == "__main__":
    print("Iniciando Seed da V9...")

    # 1. Institutions
    try:
        seed_institutions()
    except Exception as e:
        print(f"Erro seeding institutions: {e}")

    # 2. Assets Master
    try:
        seed_assets_master()
    except Exception as e:
        print(f"Erro seeding assets_master: {e}")

    print("Seed Finalizado.")
