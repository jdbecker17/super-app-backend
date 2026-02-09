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
# Tenta Service Role Key primeiro (para bypass RLS), senao Anon Key
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))
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
            data = resp.json()
            print(f"DEBUG SUPABASE: Retornou {len(data) if isinstance(data, list) else 'Objeto'}. Dados: {data}")
            return data if method != "DELETE" else None
        print(f"ERRO SUPABASE: Status {resp.status_code} - {resp.text}")
        return []
    except Exception as e:
        print(f"Erro Supabase: {e}")
        return []

# --- CONFIGURAÇÃO GLOBAL DE CACHE ---
MARKET_CACHE = {
    "last_updated": 0,
    "data": {},
    "usd_rate": 5.0 # Fallback
}
import time

# --- PREÇOS CIRÚRGICOS (V8) + SUPORTE INTERNACIONAL ---
def update_prices(assets):
    print("\n--- DEBUG: INICIANDO ATUALIZACAO V8 (GLOBAL) ---")
    if not assets: return {}
    
    live_prices = {}
    tickers_to_fetch = []
    
    # Lista de Ignorados (Renda Fixa manual)
    BLOCKLIST = ['SELIC', 'CDI', 'TESOURO', 'POUPANCA', 'LCI', 'LCA', 'CDB']

    # 1. Identificar tickers e normalizar
    for item in assets:
        original_ticker = str(item.get('ticker', '')).upper().strip()
        if not original_ticker: continue
        
        # Pula Renda Fixa se estiver na blocklist
        if any(bad in original_ticker for bad in BLOCKLIST):
            continue

        # Lógica de Sufixo .SA (INTELIGENTE)
        # Se não tem ponto, tem até 6 letras e NÃO é USD/Cripto -> Assume Brasil (.SA)
        # Se for ETF americano (ex: SHV, VOO) ou stock (AAPL), o usuário deve cadastrar sem .SA, 
        # mas como saber se é BR ou US? 
        # REGRA: Se categoria for 'Stocks' ou 'REITs' ou 'ETF US', não põe .SA.
        # Por simplicidade/convenção: Se tem 3 ou 4 letras e não é padrão B3 (ex: PETR4), tenta sem .SA primeiro?
        # MELHOR: Se o usuário não botou ponto, e é "Ação", põe .SA. Se for "International", não põe.
        cat = str(item.get('category', '')).lower()
        is_intl = 'usa' in cat or 'eua' in cat or 'int' in cat or 'stock' in cat or 'reit' in cat
        
        if "." not in original_ticker and not is_intl and len(original_ticker) <= 6 and "USD" not in original_ticker:
            yahoo_ticker = f"{original_ticker}.SA"
        else:
            yahoo_ticker = original_ticker
            
        tickers_to_fetch.append((original_ticker, yahoo_ticker))

    if not tickers_to_fetch: return {}

    # 2. Buscar Cotação do Dólar (para conversão)
    try:
        usd_obj = yf.Ticker("USDBRL=X")
        # Tenta fast_info price, senão history
        usd_price = usd_obj.fast_info.last_price if hasattr(usd_obj, 'fast_info') else None
        if not usd_price:
            hist = usd_obj.history(period="1d")
            if not hist.empty: usd_price = hist['Close'].iloc[-1]
            
        if usd_price:
            MARKET_CACHE['usd_rate'] = float(usd_price)
            print(f"DEBUG: Dólar Atualizado -> R$ {usd_price:.4f}")
    except Exception as e:
        print(f"DEBUG: Erro ao buscar Dólar: {e}")

    # 3. Buscar Ativos (Fast Info Loop)
    for original, yahoo in tickers_to_fetch:
        try:
            ticker_obj = yf.Ticker(yahoo)
            price = None
            
            # Tenta fast_info
            try:
                price = ticker_obj.fast_info.last_price
            except: pass
            
            # Fallback history
            if not price:
                hist = ticker_obj.history(period="1d")
                if not hist.empty: price = hist['Close'].iloc[-1]

            if price and float(price) > 0:
                live_prices[original] = float(price)
                print(f"DEBUG: {original} ({yahoo}) -> {price:.2f}")
            else:
                print(f"DEBUG: Falha {original} ({yahoo})")
                
        except Exception as e:
            print(f"DEBUG: Erro {yahoo}: {e}")

    return live_prices

# --- ROTAS ---
@app.get("/")
def read_root():
    return FileResponse('static/index.html')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/market-data")
def get_market_data():
    # Cache de 5 minutos (300s)
    now = time.time()
    if now - MARKET_CACHE['last_updated'] < 300 and MARKET_CACHE['data']:
        return MARKET_CACHE['data']

    print("DEBUG: Atualizando Market Data (Indices)...")
    indices = {
        "IBOV": "^BVSP",
        "SP500": "^GSPC",
        "BTC": "BTC-USD",
        "USDBRL": "USDBRL=X",
        "CDI": None # CDI é difícil pegar no Yahoo, vamos mockar ou pegar taxa fixa
    }
    
    result = {}
    for name, ticker in indices.items():
        if not ticker: 
            result[name] = {"price": 13.65, "change": 0.0} # CDI Mock
            continue
            
        try:
            obj = yf.Ticker(ticker)
            # Tenta pegar preço e variação via fast_info
            # fast_info tem last_price e previous_close
            current = obj.fast_info.last_price
            prev = obj.fast_info.previous_close
            
            # Fallback
            if not current:
                hist = obj.history(period="2d")
                if not hist.empty:
                    current = hist['Close'].iloc[-1]
                    prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
            
            if current and prev:
                change_pct = ((current - prev) / prev) * 100
                result[name] = {
                    "price": current,
                    "change": change_pct
                }
        except:
            result[name] = {"price": 0.0, "change": 0.0}

    MARKET_CACHE['data'] = result
    MARKET_CACHE['last_updated'] = now
    return result

@app.get("/assets")
def get_assets():
    user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
    
    # 1. Busca Carteira
    assets = supabase_fetch("portfolios", params={"select": "*", "user_id": f"eq.{user_id}"})
    

    # 2. Busca Preços (V8)
    live_prices = update_prices(assets)
    usd_rate = MARKET_CACHE.get('usd_rate', 5.0)
    
    # 3. Processa
    for a in assets:
        ticker = a.get('ticker')
        cat = str(a.get('category', '')).lower()
        is_intl = 'usa' in cat or 'eua' in cat or 'int' in cat or 'stock' in cat or 'reit' in cat or 'cripto' in cat
        
        raw_avg = a.get('average_price')
        avg = float(raw_avg) if raw_avg is not None else 0.0
        
        # Preço Atual (Original)
        curr_original = live_prices.get(ticker, avg)
        
        # Conversão para BRL se for internacional
        if is_intl:
            a['currency'] = 'USD'
            a['price_original'] = curr_original
            a['current_price'] = curr_original * usd_rate # Valor em Reais para totalização
            a['average_price_brl'] = avg * usd_rate # Assumindo que o user cadastrou custo em USD
            # Lucro em USD
            if avg > 0:
                a['profit_percent'] = ((curr_original - avg) / avg) * 100
            else:
                a['profit_percent'] = 0.0
        else:
            a['currency'] = 'BRL'
            a['price_original'] = curr_original
            a['current_price'] = curr_original
            a['average_price_brl'] = avg
            if avg > 0:
                a['profit_percent'] = ((curr_original - avg) / avg) * 100
            else:
                a['profit_percent'] = 0.0
                
        a['average_price'] = avg # Mantém o original cadastrado
        
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

@app.get("/dividends")
def get_dividends():
    # Cache Dividends (1 hora = 3600s) - Dados demoram a mudar
    now = time.time()
    if 'dividends' in MARKET_CACHE and now - MARKET_CACHE.get('div_last_updated', 0) < 3600:
        return MARKET_CACHE['dividends']

    assets = get_assets()
    if not assets: return {"history": [], "upcoming": [], "total_12m": 0}

    history = {} # "YYYY-MM" -> val
    upcoming = []
    total_12m = 0
    
    import pandas as pd
    from datetime import datetime, timedelta
    
    today = pd.Timestamp.now().tz_localize('UTC') # YF usa timezone
    one_year_ago = today - pd.DateOffset(months=12)

    print(f"DEBUG: Buscando dividendos para {len(assets)} ativos...")

    for a in assets:
        ticker = a.get('ticker')
        qty = a.get('quantity', 0)
        if qty <= 0: continue
        
        # Ajuste Ticker V8 logic (já temos no a['ticker'] do banco, mas precisamos do Yahoo Ticker)
        # O get_assets já não retorna o yahoo ticker, ele retorna o do banco.
        # Vamos reusar a logica rapida de sufixo aqui ou confiar no cache de update_prices? 
        # Melhor re-aplicar a lógica simples de sufixo para garantir.
        
        # Logica Simplificada de Sufixo (igual update_prices)
        yticker = ticker
        cat = str(a.get('category', '')).lower()
        is_intl = 'usa' in cat or 'eua' in cat or 'int' in cat or 'stock' in cat or 'reit' in cat or 'cripto' in cat
        if "." not in ticker and not is_intl and len(ticker) <= 6 and "USD" not in ticker:
            yticker = f"{ticker}.SA"

        try:
            # Otimização: Se for Cripto, não tem dividendo (exceto alguns casos raros staking, mas YF n traz)
            if 'cripto' in cat or 'btc' in cat.lower(): continue

            obj = yf.Ticker(yticker)
            divs = obj.dividends
            
            if divs.empty: continue
            
            # Filtra últimos 12 meses (pagos)
            # YF divs index é DatetimeTZ
            # Vamos converter tudo para UTC para comparar
            if divs.index.tz is None: divs.index = divs.index.tz_localize('UTC')
            else: divs.index = divs.index.tz_convert('UTC')

            # Histórico (Ultimos 12m)
            mask_hist = (divs.index >= one_year_ago) & (divs.index <= today)
            recent_divs = divs.loc[mask_hist]
            
            for date, val in recent_divs.items():
                month_key = date.strftime("%Y-%m")
                payment = val * qty
                
                # Conversão USD se necessário (já temos rate no cache)
                if is_intl:
                    usd_rate = MARKET_CACHE.get('usd_rate', 5.0)
                    payment = payment * usd_rate
                
                history[month_key] = history.get(month_key, 0) + payment
                total_12m += payment

            # Futuros (Anunciados > Hoje)
            # YF as vezes não traz futuros em .dividends, e sim em .calendar, mas .dividends costuma ter ex-date recente.
            # Vamos checar se tem algo > today na lista de dividendos (Data Com costuma ser a key)
            # Na verdade, yfinance .dividends keys são Ex-Dividend Dates.
            # Se ex-dividend > today, ou payment date (que nao temos facil aqui) > today.
            # Vamos assumir: Se data > today, é futuro.
            mask_future = (divs.index > today)
            future_divs = divs.loc[mask_future]
            
            for date, val in future_divs.items():
                payment = val * qty
                if is_intl: payment *= MARKET_CACHE.get('usd_rate', 5.0)
                
                upcoming.append({
                    "ticker": ticker,
                    "date": date.strftime("%d/%m/%Y"),
                    "amount": payment,
                    "is_intl": is_intl
                })

        except Exception as e:
            print(f"Erro Divs {ticker}: {e}")
            continue

    # Formatar Histórico para Lista Ordenada
    sorted_hist = [{"month": k, "value": v} for k, v in sorted(history.items())]
    
    result = {
        "history": sorted_hist,
        "total_12m": total_12m,
        "upcoming": upcoming
    }
    
    MARKET_CACHE['dividends'] = result
    MARKET_CACHE['div_last_updated'] = now
    
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)