# FORCE UPDATE V9 - CONFIRM DEPLOYMENT
import os
import requests
import shutil
import time
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# --- SAFE IMPORTS (Try/Except for debugging) ---
IMPORT_ERRORS = []

try:
    import google.generativeai as genai
except Exception as e:
    genai = None
    IMPORT_ERRORS.append(f"genai: {e}")

try:
    import yfinance as yf
except Exception as e:
    yf = None
    IMPORT_ERRORS.append(f"yfinance: {e}")

try:
    from ocr_parser import BrokerageNoteParser
except Exception as e:
    BrokerageNoteParser = None
    IMPORT_ERRORS.append(f"ocr_parser: {e}")

load_dotenv()

app = FastAPI()

# --- LOGGING INIT ---
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 APLICAÇÃO INICIANDO...")
    logger.info(f"Import Errors: {IMPORT_ERRORS}")
    logger.info(f"Supabase Configured: {'SIM' if SUPABASE_URL and SUPABASE_KEY else 'NÃO'}")
    logger.info("✅ Startup concluído com sucesso!")

@app.get("/")
def read_root():
    return {"status": "online", "version": "v10-debug"}

@app.get("/health")
def health_check():
    return {
        "status": "ok" if not IMPORT_ERRORS else "partial",
        "import_errors": IMPORT_ERRORS,
        "env_check": {
            "supabase": bool(SUPABASE_URL and SUPABASE_KEY),
            "google_ai": bool(GOOGLE_API_KEY)
        }
    }

# --- CONFIGURAÇÃO ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Tenta Service Role Key primeiro (para bypass RLS), senao Anon Key
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# --- CONEXÃO BANCO (MANTIDA) ---
def supabase_fetch(endpoint, method="GET", params=None, json_body=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{endpoint}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        resp = requests.request(
            method, url, headers=headers, params=params, json=json_body
        )
        if resp.status_code < 300:
            data = resp.json()
            print(
                f"DEBUG SUPABASE: Retornou {len(data) if isinstance(data, list) else 'Objeto'}. Dados: {data}"
            )
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
    "usd_rate": 5.0,  # Fallback
}


# --- PREÇOS CIRÚRGICOS (V8) + SUPORTE INTERNACIONAL ---
def update_prices(assets):
    print("\n--- DEBUG: INICIANDO ATUALIZACAO V8 (GLOBAL) ---")
    if not assets:
        return {}

    live_prices = {}
    prev_closes = {}
    tickers_to_fetch = []

    # Lista de Ignorados (Renda Fixa manual)
    BLOCKLIST = ["SELIC", "CDI", "TESOURO", "POUPANCA", "LCI", "LCA", "CDB"]

    # 1. Identificar tickers e normalizar
    for item in assets:
        original_ticker = str(item.get("ticker", "")).upper().strip()
        if not original_ticker:
            continue

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
        cat = str(item.get("category", "")).lower()
        is_intl = (
            "usa" in cat
            or "eua" in cat
            or "int" in cat
            or "stock" in cat
            or "reit" in cat
        )

        if (
            "." not in original_ticker
            and not is_intl
            and len(original_ticker) <= 6
            and "USD" not in original_ticker
        ):
            yahoo_ticker = f"{original_ticker}.SA"
        else:
            yahoo_ticker = original_ticker

        tickers_to_fetch.append((original_ticker, yahoo_ticker))

    if not tickers_to_fetch:
        return {}

    # 2. Buscar Cotação do Dólar (para conversão)
    try:
        usd_obj = yf.Ticker("USDBRL=X")
        # Tenta fast_info price, senão history
        usd_price = (
            usd_obj.fast_info.last_price if hasattr(usd_obj, "fast_info") else None
        )
        if not usd_price:
            hist = usd_obj.history(period="1d")
            if not hist.empty:
                usd_price = hist["Close"].iloc[-1]

        if usd_price:
            MARKET_CACHE["usd_rate"] = float(usd_price)
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
            except Exception:
                pass

            # Fallback history
            if not price:
                hist = ticker_obj.history(period="2d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]
                    # Tenta pegar previous_close do histórico se não tiver fast_info
                    if len(hist) > 1:
                        prev_closes[original] = hist["Close"].iloc[-2]

            # Tenta pegar previous_close do fast_info se não pegou do histórico
            if original not in prev_closes:
                 try:
                     prev_closes[original] = ticker_obj.fast_info.previous_close
                 except:
                     pass

            if price and float(price) > 0:
                live_prices[original] = float(price)
                print(f"DEBUG: {original} ({yahoo}) -> {price:.2f}")
            else:
                print(f"DEBUG: Falha {original} ({yahoo})")

        except Exception as e:
            print(f"DEBUG: Erro {yahoo}: {e}")

    return live_prices, prev_closes


# --- ROTAS ---
@app.get("/")
def read_root():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/market-data")
def get_market_data():
    # Cache de 5 minutos (300s)
    now = time.time()
    if now - MARKET_CACHE["last_updated"] < 300 and MARKET_CACHE["data"]:
        return MARKET_CACHE["data"]

    print("DEBUG: Atualizando Market Data (Indices)...")
    indices = {
        "IBOV": "^BVSP",
        "SP500": "^GSPC",
        "BTC": "BTC-USD",
        "USDBRL": "USDBRL=X",
        "CDI": None,  # CDI é difícil pegar no Yahoo, vamos mockar ou pegar taxa fixa
    }

    result = {}
    for name, ticker in indices.items():
        if not ticker:
            result[name] = {"price": 13.65, "change": 0.0}  # CDI Mock
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
                    current = hist["Close"].iloc[-1]
                    prev = hist["Close"].iloc[-2] if len(hist) > 1 else current

            if current and prev:
                change_pct = ((current - prev) / prev) * 100
                result[name] = {"price": current, "change": change_pct}
        except Exception:
            result[name] = {"price": 0.0, "change": 0.0}

    MARKET_CACHE["data"] = result
    MARKET_CACHE["last_updated"] = now
    return result


@app.get("/assets")
def get_assets():
    user_id = "a114b418-ec3c-407e-a2f2-06c3c453b684"

    # 1. Busca Carteira
    assets = supabase_fetch(
        "portfolios", params={"select": "*", "user_id": f"eq.{user_id}"}
    )

    # 2. Busca Preços (V8)
    live_prices, prev_closes = update_prices(assets)
    usd_rate = MARKET_CACHE.get("usd_rate", 5.0)

    # 3. Processa
    for a in assets:
        ticker = a.get("ticker")
        cat = str(a.get("category", "")).lower()
        is_intl = (
            "usa" in cat
            or "eua" in cat
            or "int" in cat
            or "stock" in cat
            or "reit" in cat
            or "cripto" in cat
        )

        raw_avg = a.get("average_price")
        avg = float(raw_avg) if raw_avg is not None else 0.0

        # Preço Atual (Original) e Fechamento Anterior
        curr_original = live_prices.get(ticker, avg)
        prev_close_original = prev_closes.get(ticker, curr_original)

        # Conversão para BRL se for internacional
        if is_intl:
            a["currency"] = "USD"
            a["price_original"] = curr_original
            a["current_price"] = (
                curr_original * usd_rate
            )  # Valor em Reais para totalização
            a["average_price_brl"] = (
                avg * usd_rate
            )  # Assumindo que o user cadastrou custo em USD
            # Lucro em USD
            if avg > 0:
                a["profit_percent"] = ((curr_original - avg) / avg) * 100
            else:
                a["profit_percent"] = 0.0
            
            # Daily Change USD
            a["daily_change"] = (curr_original - prev_close_original) * a["quantity"] * usd_rate
            a["daily_change_pct"] = ((curr_original - prev_close_original) / prev_close_original) * 100 if prev_close_original > 0 else 0.0
        else:
            a["currency"] = "BRL"
            a["price_original"] = curr_original
            a["current_price"] = curr_original
            a["average_price_brl"] = avg
            if avg > 0:
                a["profit_percent"] = ((curr_original - avg) / avg) * 100
            else:
                a["profit_percent"] = 0.0

            # Daily Change BRL
            a["daily_change"] = (curr_original - prev_close_original) * a["quantity"]
            a["daily_change_pct"] = ((curr_original - prev_close_original) / prev_close_original) * 100 if prev_close_original > 0 else 0.0

        a["average_price"] = avg  # Mantém o original cadastrado

    return assets


@app.post("/add-asset")
def add_asset(item: dict):
    data = {
        "user_id": "a114b418-ec3c-407e-a2f2-06c3c453b684",
        "ticker": str(item.get("ticker", "")).upper(),
        "quantity": int(item.get("amount", 0)),
        "average_price": float(item.get("price", 0)),
        "category": item.get("category", "Ação"),
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
        
        # Agrupamento por Categoria
        alloc = {}
        
        for a in assets:
            val = a["quantity"] * a["current_price"]
            total_patrimonio += val
            cat = a["category"]
            alloc[cat] = alloc.get(cat, 0) + val
            
            p_l_pct = a.get("profit_percent", 0)
            resumo += f"- {a['ticker']} ({a['category']}): {a['quantity']} un. Total R$ {val:.2f}. Rentab. {p_l_pct:.2f}%\n"

        prompt = (
            f"Atue como um Consultor de Wealth Management de Elite (CFA Nível 3).\n"
            f"Analise esta carteira de R$ {total_patrimonio:.2f}.\n"
            f"Alocação Atual: {alloc}\n"
            f"Ativos:\n{resumo}\n\n"
            "Objetivo: Maximizar retorno ajustado ao risco e garantir diversificação inteligente.\n"
            "Gere uma resposta em HTML PURO (sem tags html, head, body, sem markdown ```html). "
            "Use classes CSS do Tailwind se achar pertinente, mas foque na estrutura.\n\n"
            "Estrutura da Resposta:\n"
            "<div class='space-y-6'>\n"
            "  <div class='bg-gray-800 p-4 rounded-lg border-l-4 border-yellow-500'>\n"
            "    <h3 class='text-lg font-bold text-white mb-2'>🛡️ Diagnóstico de Risco & Concentração</h3>\n"
            "    <p class='text-gray-300'>[Análise crítica da alocação. Identifique ativos que ultrapassam 15% da carteira ou setores expostos demais. Seja direto.]</p>\n"
            "  </div>\n\n"
            "  <div class='bg-gray-800 p-4 rounded-lg border-l-4 border-green-500'>\n"
            "    <h3 class='text-lg font-bold text-white mb-2'>🚀 Destaques & Oportunidades</h3>\n"
            "    <p class='text-gray-300'>[Cite o melhor ativo e por que ele performou bem. Identifique oportunidades de entrada em classes sub-alocadas (ex: FIIs, Renda Fixa) para equilibrar.]</p>\n"
            "  </div>\n\n"
            "  <div class='bg-gray-800 p-4 rounded-lg border-l-4 border-blue-500'>\n"
            "    <h3 class='text-lg font-bold text-white mb-2'>⚖️ Plano de Ação (Rebalanceamento)</h3>\n"
            "    <ul class='list-disc list-inside text-gray-300 space-y-1'>\n"
            "      <li>[Sugestão Prática 1: Ex: 'Reduzir exposição em VALE3 em 5%...']</li>\n"
            "      <li>[Sugestão Prática 2]</li>\n"
            "      <li>[Sugestão Prática 3]</li>\n"
            "    </ul>\n"
            "  </div>\n"
            "</div>"
        )

        # Tenta modelos
        for m in ["gemini-2.0-pro-exp", "gemini-1.5-pro", "gemini-1.5-flash"]:
            try:
                model = genai.GenerativeModel(m)
                response = model.generate_content(prompt)
                return {"ai_analysis": response.text}
            except Exception as e:
                print(f"Erro Model {m}: {e}")
                continue
        return {"ai_analysis": "Sistema de IA temporariamente indisponível. Tente novamente em instantes."}

    except Exception as e:
        return {"ai_analysis": f"Erro Interno IA: {str(e)}"}


@app.get("/dividends")
def get_dividends():
    # Cache Dividends (1 hora = 3600s) - Dados demoram a mudar
    now = time.time()
    if (
        "dividends" in MARKET_CACHE
        and now - MARKET_CACHE.get("div_last_updated", 0) < 3600
    ):
        return MARKET_CACHE["dividends"]

    assets = get_assets()
    if not assets:
        return {"history": [], "upcoming": [], "total_12m": 0}

    history = {}  # "YYYY-MM" -> val
    upcoming = []
    total_12m = 0

    import pandas as pd

    today = pd.Timestamp.now().tz_localize("UTC")  # YF usa timezone
    one_year_ago = today - pd.DateOffset(months=12)

    print(f"DEBUG: Buscando dividendos para {len(assets)} ativos...")

    for a in assets:
        ticker = a.get("ticker")
        qty = a.get("quantity", 0)
        if qty <= 0:
            continue

        # Logica Simplificada de Sufixo (igual update_prices)
        yticker = ticker
        if a.get("category") == "Ação" or a.get("category") == "FII":
            if not (ticker.endswith(".SA") or ticker.endswith(".SAO")):
                yticker = f"{ticker}.SA"
        elif a.get("category") == "Cripto":
            yticker = f"{ticker}-USD"

        # Pular se for "Cripto" genérico ou não tiver sufixo correto
        # (Melhorar essa lógica depois)

        try:
            # Otimização: Se for Cripto, não tem dividendo (exceto alguns casos raros staking, mas YF n traz)
            if (
                "cripto" in str(a.get("category")).lower()
                or "btc" in str(a.get("category")).lower()
            ):
                continue

            obj = yf.Ticker(yticker)
            divs = obj.dividends

            if divs.empty:
                continue

            # Filtra últimos 12 meses (pagos)
            # YF divs index é DatetimeTZ
            # Vamos converter tudo para UTC para comparar
            if divs.index.tz is None:
                divs.index = divs.index.tz_localize("UTC")
            else:
                divs.index = divs.index.tz_convert("UTC")

            # Histórico (Ultimos 12m)
            mask_hist = (divs.index >= one_year_ago) & (divs.index <= today)
            recent_divs = divs.loc[mask_hist]

            for date, val in recent_divs.items():
                month_key = date.strftime("%Y-%m")
                payment = val * qty

                # Conversão USD se necessário (já temos rate no cache)
                is_intl = (
                    "usa" in str(a.get("category")).lower()
                    or "eua" in str(a.get("category")).lower()
                    or "int" in str(a.get("category")).lower()
                    or "stock" in str(a.get("category")).lower()
                    or "reit" in str(a.get("category")).lower()
                    or "cripto" in str(a.get("category")).lower()
                )
                if is_intl:
                    usd_rate = MARKET_CACHE.get("usd_rate", 5.0)
                    payment = payment * usd_rate

                history[month_key] = history.get(month_key, 0) + payment
                total_12m += payment

            # Futuros (Anunciados > Hoje)
            # YF as vezes não traz futuros em .dividends, e sim em .calendar, mas .dividends costuma ter ex-date recente.
            # Vamos checar se tem algo > today na lista de dividendos (Data Com costuma ser a key)
            # Na verdade, yfinance .dividends keys são Ex-Dividend Dates.
            # Se ex-dividend > today, ou payment date (que nao temos facil aqui) > today.
            # Vamos assumir: Se data > today, é futuro.
            mask_future = divs.index > today
            future_divs = divs.loc[mask_future]

            for date, val in future_divs.items():
                payment = val * qty
                if is_intl:
                    payment *= MARKET_CACHE.get("usd_rate", 5.0)

                upcoming.append(
                    {
                        "ticker": ticker,
                        "date": date.strftime("%d/%m/%Y"),
                        "amount": payment,
                        "is_intl": is_intl,
                    }
                )

        except Exception as e:
            print(f"Erro Divs {ticker}: {e}")
            continue

    # Formatar Histórico para Lista Ordenada
    sorted_hist = [{"month": k, "value": v} for k, v in sorted(history.items())]

    result = {"history": sorted_hist, "total_12m": total_12m, "upcoming": upcoming}

    MARKET_CACHE["dividends"] = result
    MARKET_CACHE["div_last_updated"] = now

    return result


@app.get("/history")
def get_history():
    """
    Returns simulated historical performance vs benchmarks (IBOV, CDI).
    Since we don't have full transaction history, we simulate:
    "If I held this current portfolio for the last 12 months..."
    """
    # Cache
    now = time.time()
    if now - MARKET_CACHE.get("hist_last_updated", 0) < 3600 and "history" in MARKET_CACHE:
         return MARKET_CACHE["history"]

    assets = get_assets()
    if not assets:
        return {"portfolio": [], "ibov": [], "cdi": []}
    
    import pandas as pd
    import numpy as np
    
    # 1. Download Benchmarks (1y)
    tickers = {"IBOV": "^BVSP", "CDI": "CDI"} # CDI is tricky, usually we use a constant rate or mock
    
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.DateOffset(months=12)
    
    # IBOV
    ibov_df = yf.download("^BVSP", start=start_date, end=end_date, progress=False)
    # Normalize IBOV to start at 100
    if not ibov_df.empty:
        ibov_norm = (ibov_df["Close"] / ibov_df["Close"].iloc[0]) * 100
        ibov_data = [{"date": d.strftime("%Y-%m-%d"), "value": v} for d, v in ibov_norm.items()]
    else:
        ibov_data = []

    # CDI Mock (Constante 13.65% a.a -> ~0.05% ao dia util)
    # Simulator linear growth
    cdi_data = []
    days = len(ibov_data)
    if days > 0:
        daily_rate = (1 + 0.1365)**(1/252) - 1
        curr = 100.0
        for item in ibov_data:
            cdi_data.append({"date": item["date"], "value": curr})
            curr *= (1 + daily_rate)
            
    # Portfolio Simulation
    # We take current weights and apply to individual asset histories
    # This is expensive. We will do a simplified version: 
    # Get history for top 5 assets and assume they represent the move.
    
    # For now, let's just use IBOV + Alpha (Random/Mock) or just return IBOV/CDI for frontend dev
    # Real implementation would require fetching history for ALL assets.
    # Let's try fetching history for the portfolio items.
    
    portfolio_series = pd.Series(0.0, index=ibov_df.index)
    total_current_value = sum(a["current_price"] * a["quantity"] for a in assets)
    
    if total_current_value > 0:
        # Fetch history for each asset
        for a in assets:
            qty = a["quantity"]
            if qty <= 0: continue
            
            ticker = a["ticker"]
            # Suffix logic again...
            yticker = ticker
            cat = str(a.get("category", "")).lower()
            is_intl = "usa" in cat or "stock" in cat
            
            if not is_intl and not ticker.endswith(".SA") and len(ticker) <= 6:
                yticker = f"{ticker}.SA"
                
            try:
                hist = yf.download(yticker, start=start_date, end=end_date, progress=False)
                if not hist.empty:
                    # Reindex to match IBOV dates (fill fwd)
                    hist = hist["Close"].reindex(ibov_df.index, method="ffill").fillna(0)
                    
                    # Convert to BRL if intl
                    val_series = hist * qty
                    if is_intl:
                         val_series *= MARKET_CACHE.get("usd_rate", 5.0)
                         
                    portfolio_series = portfolio_series.add(val_series, fill_value=0)
            except:
                pass
        
        # Normalize Portfolio
        if not portfolio_series.empty and portfolio_series.iloc[0] > 0:
            port_norm = (portfolio_series / portfolio_series.iloc[0]) * 100
            port_data = [{"date": d.strftime("%Y-%m-%d"), "value": v} for d, v in port_norm.items()]
        else:
            port_data = []
    else:
        port_data = []

    result = {
        "portfolio": port_data,
        "ibov": ibov_data,
        "cdi": cdi_data
    }
    
    MARKET_CACHE["history"] = result
    MARKET_CACHE["hist_last_updated"] = now
    return result


@app.get("/news")
def get_news():
    """
    Returns personalized news feed based on portfolio assets.
    Uses Google News RSS.
    """
    # Cache
    now = time.time()
    if now - MARKET_CACHE.get("news_last_updated", 0) < 1800 and "news" in MARKET_CACHE:
         return MARKET_CACHE["news"]

    assets = get_assets()
    if not assets:
        return []

    # Extract unique tickers/names
    # Limit to top 5 holdings to avoid huge query
    sorted_assets = sorted(assets, key=lambda x: x["current_price"] * x["quantity"], reverse=True)
    top_assets = sorted_assets[:5]
    
    query_terms = [a["ticker"] for a in top_assets]
    # Add some general terms
    query_terms.append("Mercado Financeiro")
    
    query_str = " OR ".join(query_terms)
    rss_url = f"https://news.google.com/rss/search?q={query_str}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    
    try:
        import xml.etree.ElementTree as ET
        resp = requests.get(rss_url, timeout=5)
        root = ET.fromstring(resp.content)
        
        items = []
        for item in root.findall(".//item")[:10]:
            title = item.find("title").text
            link = item.find("link").text
            pubDate = item.find("pubDate").text
            source = item.find("source").text if item.find("source") is not None else "Google News"
            
            items.append({
                "title": title,
                "link": link,
                "date": pubDate,
                "source": source
            })
            
        MARKET_CACHE["news"] = items
        MARKET_CACHE["news_last_updated"] = now
        return items
    except Exception as e:
        print(f"Erro News: {e}")
        return []


@app.get("/taxes")
def get_taxes():
    """
    Calculadora DARF (MVP) - Placeholder
    In a real app, this would iterate over 'sales' history table.
    """
    return {
        "swing_trade": {
            "accumulated_loss": 0.0,
            "current_month_profit": 0.0,
            "tax_due": 0.0
        },
        "day_trade": {
            "accumulated_loss": 0.0,
            "current_month_profit": 0.0,
            "tax_due": 0.0
        },
        "fii": {
             "accumulated_loss": 0.0,
            "current_month_profit": 0.0,
            "tax_due": 0.0
        }
    }


@app.get("/assets/search")
def search_assets(q: str):
    """
    Autocomplete endpoint for Assets Master DB
    """
    if not q or len(q) < 2:
        return []

    q = q.upper()
    try:
        # Search by Ticker OR Name (Client-side usually sends just text)
        # Using Supabase 'or' syntax: ticker.ilike.%Q%,name.ilike.%Q%
        # Note: wildcards in Supabase usually need * or % depending on exact lib,
        # but postgrest-js uses .ilike('col', '%val%').
        # Here we are using requests. GET /table?select=*&or=(ticker.ilike.*VAL*,name.ilike.*VAL*)
        # Correct PostgREST syntax for OR with ILIKE is tricky in URL params.
        # Let's try simple filter first. Search by ticker only for MVP if OR fails.

        # SINTAXE CORRETA DO SUPABASE/POSTGREST PARA 'OR':
        # or=(ticker.ilike.*PETR*,name.ilike.*PETR*)

        params = {
            "select": "*",
            "or": f"(ticker.ilike.*{q}*,name.ilike.*{q}*)",
            "limit": "10",
        }

        # Debug URL construction if needed
        # print(f"DEBUG SEARCH: {q}")

        data = supabase_fetch("assets_master", params=params)
        return data
    except Exception as e:
        print(f"Erro Search: {e}")
        return []


@app.post("/upload-note")
async def upload_note(file: UploadFile = File(...)):
    """
    Receives a PDF brokerage note, saves it momentarily, parses it with OCR, and returns JSON data.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Apenas arquivos PDF são permitidos.")

    os.makedirs("temp_notes", exist_ok=True)
    # Sanitize filename avoiding directory traversal is good practice but for now simple
    safe_filename = os.path.basename(file.filename)
    file_path = f"temp_notes/{safe_filename}"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Parse
        parser = BrokerageNoteParser(file_path)
        data = parser.parse()

        # Clean up
        if os.path.exists(file_path):
            os.remove(file_path)

        if not data:
            raise HTTPException(
                400, "Falha ao ler nota. Verifique se é um PDF SINACUR/B3 válido."
            )

        return data

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Erro Upload: {e}")
        raise HTTPException(500, f"Erro ao processar nota: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
