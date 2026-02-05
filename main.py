# FORCE UPDATE V8 - SURGICAL MODE (FAST INFO + DEBUG LOGS)
import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# --- CONFIGURAÇÃO ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- CONEXÃO BANCO (MANTIDA) ---
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
        if resp.status_code < 300: 
            return resp.json() if method != "DELETE" else None
        return []
    except Exception as e:
        print(f"Erro Supabase: {e}")
        return []

# --- PREÇOS CIRÚRGICOS (V8) ---
def update_prices(assets):
    print("\n--- DEBUG: INICIANDO ATUALIZACAO V8 ---")
    if not assets: return {}
    
    live_prices = {}
    
    # Lista de Ignorados (Renda Fixa manual)
    BLOCKLIST = ['SELIC', 'CDI', 'TESOURO', 'POUPANCA', 'LCI', 'LCA', 'CDB']

    for item in assets:
        original_ticker = str(item.get('ticker', '')).upper().strip()
        if not original_ticker: continue
        
        # Pula Renda Fixa
        if any(bad in original_ticker for bad in BLOCKLIST):
            print(f"DEBUG: Ignorando {original_ticker} (Renda Fixa)")
            continue

        # Formata para Yahoo (Ex: PETR4 -> PETR4.SA)
        if "." not in original_ticker and len(original_ticker) <= 6 and "USD" not in original_ticker:
            yahoo_ticker = f"{original_ticker}.SA"
        else:
            yahoo_ticker = original_ticker
            
        try:
            # MÉTODO NOVO: FAST INFO (Mais rápido e robusto que download)
            ticker_obj = yf.Ticker(yahoo_ticker)
            
            # Tenta pegar preço atual ou último fechamento
            price = None
            
            # Tenta fast_info (Endpoint 1)
            try:
                price = ticker_obj.fast_info.last_price
            except: pass
            
            # Fallback para history (Endpoint 2 - se o 1 falhar)
            if not price:
                hist = ticker_obj.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]

            if price and float(price) > 0:
                live_prices[original_ticker] = float(price)
                print(f"DEBUG: Sucesso {original_ticker} ({yahoo_ticker}) -> R$ {price:.2f}")
            else:
                print(f"DEBUG: Falha {original_ticker} ({yahoo_ticker}) -> Preço vazio ou zero.")
                
        except Exception as e:
            print(f"DEBUG: Erro ao baixar {original_ticker}: {e}")

    print("--- DEBUG: FIM DA ATUALIZACAO ---\n")
    return live_prices

# --- ROTAS ---
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/assets")
def get_assets():
    # ID fixo
    user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
    
    # 1. Busca Carteira
    assets = supabase_fetch("portfolios", params={"select": "*", "user_id": f"eq.{user_id}"})
    if not assets: return []
    
    # 2. Busca Preços (V8)
    live_prices = update_prices(assets)
    
    # 3. Processa
    for a in assets:
        ticker = a.get('ticker')
        raw_avg = a.get('average_price')
        avg = float(raw_avg) if raw_avg is not None else 0.0
        
        # Se achou preço live, usa. Se não, usa o médio.
        curr = live_prices.get(ticker, avg)
        
        a['average_price'] = avg
        a['current_price'] = curr
        
        if avg > 0:
            a['profit_percent'] = ((curr - avg) / avg) * 100
        else:
            a['profit_percent'] = 0.0
        
    return assets

@app.post("/add-asset")
def add_asset(item: dict):
    data = {
        "user_id": 'a114b418-ec3c-407e-a2f2-06c3c453b684',
        "ticker": str(item.get("ticker", "")).upper(),
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
        assets = get_assets()
        
        # Resumo detalhado para a IA
        resumo = ""
        total_patrimonio = 0
        for a in assets:
            val = a['quantity'] * a['current_price']
            total_patrimonio += val
            resumo += f"- {a['ticker']} ({a['category']}): {a['quantity']} un. Pago R$ {a['average_price']:.2f}, Hoje R$ {a['current_price']:.2f} (Lucro: {a['profit_percent']:.2f}%)\n"

        prompt = (
            f"Analise esta carteira de R$ {total_patrimonio:.2f} como um Wealth Advisor Sênior.\n"
            f"Dados:\n{resumo}\n"
            "Gere HTML puro (sem markdown ```html) com 3 seções curtas e diretas:\n"
            "1. <h3>Diagnóstico de Risco</h3>\n"
            "2. <h3>Destaques de Performance</h3> (Cite quem lucrou mais)\n"
            "3. <h3>Ação Recomendada</h3> (Comprar/Vender/Manter)"
        )
        
        # Tenta modelos
        for m in ['gemini-2.0-flash', 'gemini-1.5-flash']:
            try:
                model = genai.GenerativeModel(m)
                return {"ai_analysis": model.generate_content(prompt).text}
            except: continue
        return {"ai_analysis": "IA indisponível."}
        
    except Exception as e:
        return {"ai_analysis": f"Erro IA: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)