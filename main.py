# FORCE UPDATE V7 - SMART LIVE MODE (COM FILTRO ANTI-CRASH)
import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yfinance as yf # A biblioteca volta, mas controlada!
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# --- CONFIGURAÇÃO ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- CONEXÃO BANCO (MANTIDA IGUAL - VIA REQUESTS) ---
def supabase_fetch(endpoint, method="GET", params=None, json_body=None):
    if not SUPABASE_URL or not SUPABASE_KEY: return None
    # Garante URL correta removendo barras extras
    base = SUPABASE_URL.rstrip('/')
    url = f"{base}/rest/v1/{endpoint}"
    
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    try:
        resp = requests.request(method, url, headers=headers, params=params, json=json_body)
        # Sucesso (200-299)
        if resp.status_code < 300: 
            return resp.json() if method != "DELETE" else None
        return []
    except: return []

# --- PREÇOS INTELIGENTES (O SEGREDO ANTI-CRASH) ---
def update_prices(assets):
    if not assets: return {}
    
    tickers_map = {}
    tickers_to_fetch = []
    
    # 1. LISTA NEGRA: Tickers que sabemos que travam o Yahoo ou não existem lá
    BLOCKLIST = ['SELIC', 'CDI', 'TESOURO', 'POUPANCA', 'LCI', 'LCA', 'CDB']

    for item in assets:
        raw_ticker = str(item.get('ticker', '')).upper().strip()
        if not raw_ticker: continue
        
        # 2. Se for proibido, ignora silenciosamente
        if any(bad in raw_ticker for bad in BLOCKLIST):
            continue

        # 3. Formata para o Yahoo (Adiciona .SA se for ação BR padrão)
        # Lógica: Se não tem ponto, tem menos de 6 letras e não é Cripto (USD), deve ser B3.
        if not "." in raw_ticker and len(raw_ticker) <= 6 and not "USD" in raw_ticker:
            yahoo_ticker = f"{raw_ticker}.SA"
        else:
            yahoo_ticker = raw_ticker
            
        tickers_map[yahoo_ticker] = raw_ticker
        tickers_to_fetch.append(yahoo_ticker)
    
    if not tickers_to_fetch: return {}

    try:
        # 4. Busca em Lote (Batch Download)
        # 'threads=False' é crucial para estabilidade em servidores python pequenos
        data = yf.download(tickers_to_fetch, period="1d", progress=False, threads=False)
        
        current_prices = {}
        
        # Lógica de extração segura do Pandas DataFrame (Multi-index vs Single-index)
        if data is not None and not data.empty:
            # Caso A: Apenas um ativo solicitado
            if len(tickers_to_fetch) == 1:
                t = tickers_to_fetch[0]
                try:
                    # Tenta pegar o último 'Close' disponível
                    val = data['Close'].iloc[-1]
                    # Converte de numpy para float nativo do Python
                    current_prices[tickers_map[t]] = float(val.item())
                except: pass
            
            # Caso B: Vários ativos
            else:
                for yt in tickers_to_fetch:
                    try:
                        if yt in data['Close']:
                            val = data['Close'][yt].iloc[-1]
                            current_prices[tickers_map[yt]] = float(val.item())
                    except: pass
                    
        return current_prices

    except Exception as e:
        print(f"Erro Yahoo Finance (Sistema continua rodando): {e}")
        return {} # Retorna vazio, o site usa o preço de compra como fallback

# --- ROTAS ---
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/assets")
def get_assets():
    # ID fixo do usuário (Hardcoded para MVP)
    user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
    
    # 1. Busca Carteira no Banco
    assets = supabase_fetch("portfolios", params={"select": "*", "user_id": f"eq.{user_id}"})
    
    if not assets: return []
    
    # 2. Busca Preços Online (Smart Mode)
    live_prices = update_prices(assets)
    
    # 3. Mescla os dados
    for a in assets:
        ticker = a.get('ticker')
        # Garante que seja float
        raw_avg = a.get('average_price')
        avg = float(raw_avg) if raw_avg is not None else 0.0
        
        # Se achou preço online, usa. Se não (ex: SELIC), usa o preço de compra.
        curr = live_prices.get(ticker, avg)
        
        a['average_price'] = avg
        a['current_price'] = curr
        
        # Calcula rentabilidade
        if avg > 0:
            a['profit_percent'] = ((curr - avg) / avg) * 100
        else:
            a['profit_percent'] = 0.0
        
    return assets

@app.post("/add-asset")
def add_asset(item: dict):
    # Endpoint recebe JSON direto do frontend
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
        
        # Recupera carteira atualizada (com preços live) para contexto da IA
        assets = get_assets()
        
        # Monta um resumo de texto para a IA ler
        resumo_texto = ""
        total_val = 0
        for a in assets:
            total = a['quantity'] * a['current_price']
            total_val += total
            resumo_texto += f"- {a['ticker']} ({a['category']}): {a['quantity']} un. @ R$ {a['current_price']:.2f} (Rentab: {a['profit_percent']:.2f}%)\n"
            
        prompt = (
            f"Atue como Advisor Financeiro Sênior de Wealth Management.\n"
            f"Analise esta carteira (Valor Total: R$ {total_val:.2f}):\n{resumo_texto}\n"
            "Gere uma resposta EXCLUSIVAMENTE em HTML (sem tags html/body/head, apenas divs e conteúdo) contendo:\n"
            "1. Um <h3>Risco da Carteira</h3> (análise crítica de concentração).\n"
            "2. Um <h3>Oportunidades</h3> (o que está performando bem).\n"
            "3. Um <h3>Rebalanceamento</h3> (sugestões práticas de compra/venda).\n"
            "Use classes CSS do Tailwind se quiser, mas mantenha o HTML limpo."
        )
        
        # Tenta modelos em ordem de inteligência
        modelos = ['gemini-2.0-flash', 'gemini-1.5-flash']
        for m in modelos:
            try:
                model = genai.GenerativeModel(m)
                response = model.generate_content(prompt)
                return {"ai_analysis": response.text}
            except: continue
            
        return {"ai_analysis": "<p>IA temporariamente indisponível.</p>"}
        
    except Exception as e:
        return {"ai_analysis": f"<p>Erro na análise: {str(e)}</p>"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)