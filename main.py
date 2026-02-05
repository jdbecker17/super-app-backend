# FORCE UPDATE V3.5
import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf
from dotenv import load_dotenv

# ==========================================
# CONFIGURAÇÃO E CONSTANTES
# ==========================================
load_dotenv()

app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Verifica chaves críticas na inicialização
if not SUPABASE_URL or not SUPABASE_KEY:
    print("CRITICAL WARNING: SUPABASE_URL or SUPABASE_KEY not set!")

# ==========================================
# MODELS
# ==========================================
class AnalysisRequest(BaseModel):
    user_id: str

class AssetRequest(BaseModel):
    ticker: str
    amount: int
    price: float
    category: str

# ==========================================
# FRONTEND ROUTING
# ==========================================
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# HELPERS
# ==========================================

def supabase_fetch(endpoint: str, method="GET", params=None, json_body=None):
    """
    Realiza chamadas HTTP diretas à API REST do Supabase.
    Substitui o cliente oficial que estava falhando (pyroaring error).
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Exception("Supabase credentials missing")

    # Garante que a URL base termine sem barra e o endpoint comece com barra
    base_url = SUPABASE_URL.rstrip('/') + "/rest/v1"
    url = f"{base_url}/{endpoint.lstrip('/')}"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation" # Importante para receber o dado criado/deletado de volta
    }

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_body
        )
        response.raise_for_status()
        
        # Para DELETE ou POST com return=representation, o supabase retorna o objeto.
        # Se for lista vazia ou 204 No Content, lida adequadamente.
        if response.status_code == 204:
            return None
            
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Supabase HTTP Error: {e.response.text}")
        raise e
    except Exception as e:
        print(f"Supabase Generic Error: {str(e)}")
        raise e

def update_prices(assets_data):
    """
    Fetches live prices from Yahoo Finance.
    Returns {ticker: current_price}.
    """
    try:
        if not assets_data:
            return {}

        tickers_map = {}
        tickers_to_fetch = []
        IGNORE_KEYWORDS = ['SELIC', 'CDI', 'TESOURO', 'POUPANÇA', 'VISTA']

        for item in assets_data:
            if not item: continue
            original = item.get('ticker')
            if not original: continue
            
            upper_ticker = str(original).upper()
            if any(keyword in upper_ticker for keyword in IGNORE_KEYWORDS):
                continue

            yahoo_ticker = original
            category = item.get('category')
            if category:
                cat = str(category).lower()
                if "cripto" in cat:
                    if not "-" in original: yahoo_ticker = f"{original}-USD"
                elif "ação" in cat or "fii" in cat or "renda" in cat:
                    if not original.endswith(".SA") and len(original) <= 6:
                        yahoo_ticker = f"{original}.SA"

            tickers_map[yahoo_ticker] = original
            tickers_to_fetch.append(yahoo_ticker)

        if not tickers_to_fetch:
            return {}

        # Fetch data
        data = yf.download(tickers_to_fetch, period="1d", progress=False, threads=False)
        
        current_prices = {}
        if data is None or data.empty:
             return {}

        # Single ticker case
        if len(tickers_to_fetch) == 1:
            ticker = tickers_to_fetch[0]
            try:
                if 'Close' in data.columns:
                    price = data['Close'].iloc[-1].item() 
                    current_prices[tickers_map[ticker]] = price
            except: pass
        else:
            # Multi-index
            for yahoo_ticker in tickers_to_fetch:
                try:
                    if 'Close' in data and yahoo_ticker in data['Close']:
                        series = data['Close'][yahoo_ticker]
                        last_valid = series.dropna().iloc[-1]
                        price = last_valid.item()
                        current_prices[tickers_map[yahoo_ticker]] = price
                except: pass
        
        return current_prices

    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}

def get_gemini_response(prompt_text):
    genai.configure(api_key=GOOGLE_API_KEY)
    models_priority = [
        'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-pro'
    ]
    
    errors = []
    for model_name in models_priority:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            if response.text:
                return response.text
        except Exception as e:
            errors.append(str(e))
            continue
            
    # Fallback message
    return f"Não foi possível gerar análise. Detalhes: {'; '.join(errors)}"

# ==========================================
# ENDPOINTS
# ==========================================

@app.get("/assets")
def get_assets():
    try:
        user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
        
        # REST API Call: GET /portfolios?select=*&user_id=eq.{user_id}
        assets = supabase_fetch(
            endpoint="portfolios",
            method="GET",
            params={"select": "*", "user_id": f"eq.{user_id}"}
        )
        
        # Live Data Enrichment
        live_prices = update_prices(assets)

        # Logic Enrichment
        for asset in assets:
            try:
                ticker = asset.get('ticker')
                avg_price_raw = asset.get('average_price')
                avg_price = float(avg_price_raw) if avg_price_raw is not None else 0.0
                asset['average_price'] = avg_price

                current_price = live_prices.get(ticker, avg_price)
                if current_price is None: current_price = avg_price
                asset['current_price'] = current_price
                
                if avg_price > 0:
                    asset['profit_percent'] = ((current_price - avg_price) / avg_price) * 100
                else:
                    asset['profit_percent'] = 0.0
            except:
                asset['current_price'] = asset.get('average_price', 0)
                asset['profit_percent'] = 0.0

        return assets
    except Exception as e:
        print(f"Fatal GET /assets: {e}") 
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/add-asset")
def add_asset(asset: AssetRequest):
    try:
        user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
        
        data = {
            "user_id": user_id,
            "ticker": asset.ticker.upper(),
            "quantity": asset.amount,
            "average_price": asset.price,
            "category": asset.category
        }
        
        # REST API Call: POST /portfolios
        supabase_fetch(
            endpoint="portfolios",
            method="POST",
            json_body=data
        )
        
        return {"message": "Ativo cadastrado com sucesso!"}
    except Exception as e:
        print(f"Fatal POST /add-asset: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int):
    try:
        # REST API Call: DELETE /portfolios?id=eq.{asset_id}
        supabase_fetch(
            endpoint="portfolios",
            method="DELETE",
            params={"id": f"eq.{asset_id}"}
        )
        return {"message": "Ativo deletado com sucesso!"}
    except Exception as e:
        print(f"Fatal DELETE /assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Chaves de API ausentes.")

    try:
        # Re-use logic (internal call approach)
        # Fetch directly from Supabase via REST
        assets = supabase_fetch(
            endpoint="portfolios",
            method="GET",
            params={"select": "*", "user_id": f"eq.{request.user_id}"}
        )
        
        if not assets:
            return {"ai_analysis": "Carteira vazia."}
        
        live_prices = update_prices(assets)
        
        portfolio_summary = []
        for item in assets:
            # Safe parsing
            ticker = item.get('ticker', 'UNKNOWN')
            raw_avg = item.get('average_price', 0)
            avg = float(raw_avg) if raw_avg is not None else 0.0
            
            curr = live_prices.get(ticker, avg)
            
            profit = 0.0
            if avg > 0: profit = ((curr - avg) / avg) * 100
            
            portfolio_summary.append(
                f"- {ticker} ({item.get('category')}): {item.get('quantity')} un. "
                f"Médio: R$ {avg:.2f}, Atual: R$ {curr:.2f} ({profit:+.2f}%)"
            )

        portfolio_text = "\n".join(portfolio_summary)
        
        prompt = (
            f"Atue como um Consultor de Elite de Wealth Management. "
            f"Analise esta carteira de investimentos (Dados ATUALIZADOS de mercado):\n{portfolio_text}\n\n"
            f"Responda EXCLUSIVAMENTE em HTML (sem tags <html> ou <body>, apenas o conteúdo div/p/ul) "
            f"com estas 3 seções estilizadas e curtas:\n"
            f"1. <h3>Risco da Carteira</h3> (Análise objetiva baseada nas classes de ativos)\n"
            f"2. <h3>Performance Atual</h3> (Elogie os lucros e alerte sobre os prejuízos)\n"
            f"3. <h3>Sugestão de Rebalanceamento</h3> (O que comprar/vender?)\n"
            f"Seja direto e profissional."
        )
        
        analysis = get_gemini_response(prompt)
        return {"ai_analysis": analysis}

    except Exception as e:
        return {"erro_fatal": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
