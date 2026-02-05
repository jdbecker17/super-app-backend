# FORCE RESTART V5 - CORRECAO DO ERRO 404 YAHOO
import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Configuração
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- CONEXÃO SUPABASE (SEM LIB QUEBRADA) ---
def supabase_fetch(endpoint, method="GET", params=None, json_body=None):
    if not SUPABASE_URL or not SUPABASE_KEY: return None
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    try:
        resp = requests.request(method, url, headers=headers, params=params, json=json_body)
        if resp.status_code < 300: return resp.json() if method != "DELETE" else None
        return []
    except: return []

# --- PREÇOS BLINDADOS (CORREÇÃO DO ERRO SELIC) ---
def update_prices(assets):
    try:
        if not assets: return {}
        tickers = []
        map_t = {}
        
        # LISTA DE IGNORADOS (O que estava quebrando o app)
        IGNORE = ['SELIC', 'CDI', 'TESOURO', 'POUPANCA']

        for a in assets:
            t = a.get('ticker', '').upper()
            if not t or any(x in t for x in IGNORE): continue
            
            y_t = f"{t}.SA" if not t.endswith(".SA") and len(t) <= 5 else t
            tickers.append(y_t)
            map_t[y_t] = t
            
        if not tickers: return {}
        
        # Tenta baixar sem travar
        data = yf.download(tickers, period="1d", progress=False)
        
        prices = {}
        # Extração segura de dados
        if data is not None and not data.empty:
            if len(tickers) == 1:
                try: prices[map_t[tickers[0]]] = data['Close'].iloc[-1].item()
                except: pass
            else:
                for yt in tickers:
                    try: prices[map_t[yt]] = data['Close'][yt].iloc[-1].item()
                    except: pass
        return prices
    except Exception as e:
        print(f"Erro Yahoo ignorado: {e}")
        return {} # Se der erro, retorna vazio e o site continua funcionando

# --- ROTAS ---
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/assets")
def get_assets():
    # ID fixo para recuperar acesso
    user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
    assets = supabase_fetch("portfolios", params={"select": "*", "user_id": f"eq.{user_id}"})
    
    if not assets: return []
    
    live = update_prices(assets)
    
    for a in assets:
        avg = float(a.get('average_price') or 0)
        curr = live.get(a.get('ticker'), avg)
        
        a['average_price'] = avg
        a['current_price'] = curr
        a['profit_percent'] = ((curr - avg)/avg)*100 if avg > 0 else 0
        
    return assets

@app.post("/add-asset")
def add_asset(item: dict):
    # Endpoint simplificado
    data = {
        "user_id": 'a114b418-ec3c-407e-a2f2-06c3c453b684',
        "ticker": item.get("ticker", "").upper(),
        "quantity": int(item.get("amount", 0)),
        "average_price": float(item.get("price", 0)),
        "category": item.get("category", "Ação")
    }
    supabase_fetch("portfolios", method="POST", json_body=data)
    return {"status": "ok"}

@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int):
    supabase_fetch("portfolios", method="DELETE", params={"id": f"eq.{asset_id}"})
    return {"status": "ok"}

@app.post("/analyze")
def analyze(req: dict):
    # IA simplificada
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        return {"ai_analysis": model.generate_content("Analise financeira básica...").text}
    except: return {"ai_analysis": "IA indisponível."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)