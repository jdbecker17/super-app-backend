import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from supabase import create_client, Client

import time

import yfinance as yf

app = FastAPI()

# 1. Configuração de Chaves
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class AnalysisRequest(BaseModel):
    user_id: str

class AssetRequest(BaseModel):
    ticker: str
    amount: int
    price: float
    category: str

# 2. Rota para entregar o Site (Frontend)
@app.get("/")
def read_root():
    # Retorna o arquivo HTML que criamos na pasta static
    return FileResponse('static/index.html')

# Monta a pasta static para permitir arquivos futuros (CSS/JS externos)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Helper: Atualizador de Preços (Yahoo Finance)
def update_prices(assets_data):
    """
    Recebe a lista de ativos do Supabase, busca preços no Yahoo Finance
    e retorna um dicionário {ticker: current_price}.
    BLINDAGEM: Se falhar, retorna vazio (o frontend usa preço médio).
    """
    if not assets_data:
        return {}

    # 1. Identificar Tickers (adicionar .SA se for necessário para B3)
    tickers_map = {} # {ticker_yahoo: ticker_original}
    tickers_to_fetch = []
    
    # Lista de ignorados (exóticos que travam o YFinance)
    IGNORE_KEYWORDS = ['SELIC', 'CDI', 'TESOURO', 'POUPANÇA', 'VISTA']

    for item in assets_data:
        original = item['ticker']
        upper_ticker = original.upper()
        
        # A. Checagem de Segurança: Pula ativos exóticos
        if any(keyword in upper_ticker for keyword in IGNORE_KEYWORDS):
            continue

        # Lógica simples: Se não tem ponto e parece ação BR (geralmente 5/6 chars), tenta .SA
        # Mas vamos forçar tentativa.
        # Se for Cripto (BTC, ETH), o yfinance geralmente precisa de sufixo -USD ou -BRL (ex: BTC-USD)
        # Assumindo que o usuário digite "PETR4" -> "PETR4.SA"
        
        yahoo_ticker = original
        if "category" in item and item['category']:
            cat = item['category'].lower()
            if "cripto" in cat:
                if not "-" in original: yahoo_ticker = f"{original}-USD"
            elif "ação" in cat or "fii" in cat or "renda" in cat:
                if not original.endswith(".SA") and len(original) <= 6:
                    yahoo_ticker = f"{original}.SA"

        tickers_map[yahoo_ticker] = original
        tickers_to_fetch.append(yahoo_ticker)

    if not tickers_to_fetch:
        return {}

    # 2. Buscar no Yahoo Finance (Batch)
    try:
        # download returns a DataFrame
        # period='1d' is enough for latest price
        # threads=False para evitar conflitos em alguns ambientes
        data = yf.download(tickers_to_fetch, period="1d", progress=False, threads=False)
        
        current_prices = {}
        
        # Se veio vazio ou deu erro
        if data.empty:
             return {}

        # Se for apenas 1 ticker, a estrutura do DF é diferente (Series ou DataFrame simples)
        if len(tickers_to_fetch) == 1:
            ticker = tickers_to_fetch[0]
            try:
                # Tenta pegar 'Close', se falhar ('Adj Close' ou outro), ignora
                if 'Close' in data.columns:
                     # Pega o último válido
                    price = data['Close'].iloc[-1].item() 
                    current_prices[tickers_map[ticker]] = price
            except:
                pass
        else:
            # Multi-index columns: ('Close', 'PETR4.SA')
            # Às vezes o download falha parcialmente. Iteramos o que foi pedido.
            for yahoo_ticker in tickers_to_fetch:
                try:
                    if yahoo_ticker in data['Close']:
                        series = data['Close'][yahoo_ticker]
                        # Remove NaNs
                        last_valid = series.dropna().iloc[-1]
                        price = last_valid.item()
                        current_prices[tickers_map[yahoo_ticker]] = price
                except:
                    # Fallback logic check next
                    pass
        
        return current_prices

    except Exception as e:
        print(f"Erro no YFinance (Ignorado para não travar API): {e}")
        return {}

# 3. Rota de Cadastro de Ativos
@app.post("/add-asset")
def add_asset(asset: AssetRequest):
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # ID fixo solicitado
        user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
        
        data = {
            "user_id": user_id,
            "ticker": asset.ticker.upper(),
            "quantity": asset.amount,
            "average_price": asset.price,
            "category": asset.category
        }
        
        supabase.table("portfolios").insert(data).execute()
        return {"message": "Ativo cadastrado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3.1 Rota de Listagem de Ativos (GET) - COM LIVE DATA
@app.get("/assets")
def get_assets():
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
        response = supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
        assets = response.data

        # Busca Preços Atualizados
        live_prices = update_prices(assets)

        # Enriquece os dados
        for asset in assets:
            ticker = asset['ticker']
            avg_price = asset['average_price']
            
            # Se achou preço, usa. Senão, usa o preço médio como fallback (rentabilidade 0%)
            current_price = live_prices.get(ticker, avg_price)
            
            asset['current_price'] = current_price
            
            if avg_price > 0:
                asset['profit_percent'] = ((current_price - avg_price) / avg_price) * 100
            else:
                asset['profit_percent'] = 0.0

        return assets
    except Exception as e:
        # Em caso de erro grave, retorna erro 500. 
        # (Idealmente logaríamos o erro e retornaríamos os dados sem live price)
        print(f"Erro GET /assets: {e}") 
        raise HTTPException(status_code=500, detail=str(e))

# 3.2 Rota de Exclusão de Ativos (DELETE)
@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int):
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Verifica se o ativo pertence ao usuário (seria ideal, mas por enquanto simplificamos deletando pelo ID)
        response = supabase.table("portfolios").delete().eq("id", asset_id).execute()
        return {"message": "Ativo deletado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Rota de Análise (Backend + IA)
# Helper: Lógica de Fallback de Modelos
def get_gemini_response(prompt_text):
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # Lista de prioridade (Flash é mais rápido/barato, Pro é backup)
    # Tenta nomes com e sem prefixo 'models/' se necessário, mas geralmente o lib resolve.
    models_priority = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-flash-latest',
        'models/gemini-2.0-flash', 
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-pro',
        'gemini-1.0-pro',
    ]

    errors = []

    for model_name in models_priority:
        try:
            print(f"Tentando modelo: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            
            if response.text:
                return response.text
        except Exception as e:
            print(f"Erro no {model_name}: {str(e)}")
            errors.append(f"{model_name}: {str(e)}")
            continue # Tenta o próximo
    
    # Se chegou aqui, todos falharam. Tenta listar o que EXISTE.
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        available_str = ", ".join(available_models)
        raise Exception(f"Falha em todos os modelos. ERRO 404 pode indicar chave sem permissão ou nome errado. Modelos DISPONÍVEIS na sua chave: [{available_str}]. Detalhes técnicos: {'; '.join(errors)}")
    except Exception as list_error:
         raise Exception(f"Falha total e falha ao listar modelos ({str(list_error)}). Detalhes: {'; '.join(errors)}")

# 4. Rota de Análise (Backend + IA)
@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro: Chaves de API ausentes.")

    try:
        # A. Busca dados usando a nossa própria função interna (para já pegar os Live Prices!)
        # Pequeno hack: chamamos a lógica da get_assets internamente
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        assets = response.data
        
        if not assets:
            return {"ai_analysis": "Carteira vazia. Adicione ativos para análise."}
            
        # Busca preços para enriquecer o prompt
        live_prices = update_prices(assets)

        # B. Monta os dados para o Prompt com Rentabilidade
        portfolio_summary = []
        for item in assets:
            cur_price = live_prices.get(item['ticker'], item['average_price'])
            profit = 0.0
            if item['average_price'] > 0:
                profit = ((cur_price - item['average_price']) / item['average_price']) * 100
            
            portfolio_summary.append(
                f"- {item['ticker']} ({item.get('category', 'Ativo')}): "
                f"{item['quantity']} cotas. "
                f"Comprado a R$ {item['average_price']:.2f}, Hoje vale R$ {cur_price:.2f}. "
                f"Resultado: {profit:+.2f}%"
            )
        
        portfolio_text = "\n".join(portfolio_summary)

        # C. Prompt de Consultor de Elite
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

        # D. Chama a IA com Fallback
        ai_analysis = get_gemini_response(prompt)
        
        return {"ai_analysis": ai_analysis}

    except Exception as e:
        return {"erro_fatal": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
