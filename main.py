# FORCE UPDATE V6 - NO YAHOO (VERSAO LEVE)
import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# --- CONFIGURAÇÃO ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- CONEXÃO BANCO DE DADOS ---
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

# --- ROTAS (SEM COTAÇÃO ONLINE) ---
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/assets")
def get_assets():
    # ID fixo para garantir que carrega
    user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
    
    # Busca apenas dados do banco
    assets = supabase_fetch("portfolios", params={"select": "*", "user_id": f"eq.{user_id}"})
    
    if not assets: return []
    
    # Processamento básico (Preço Atual = Preço de Compra)
    for a in assets:
        avg = float(a.get('average_price') or 0)
        a['average_price'] = avg
        a['current_price'] = avg # Sem atualização online por enquanto
        a['profit_percent'] = 0.0
        
    return assets

@app.post("/add-asset")
def add_asset(item: dict):
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
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        return {"ai_analysis": model.generate_content("Analise financeira simples...").text}
    except: return {"ai_analysis": "IA Indisponivel."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)