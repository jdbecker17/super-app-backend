import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from supabase import create_client, Client

import time

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

# 2. Rota para entregar o Site (Frontend)
@app.get("/")
def read_root():
    # Retorna o arquivo HTML que criamos na pasta static
    return FileResponse('static/index.html')

# Monta a pasta static para permitir arquivos futuros (CSS/JS externos)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
            "average_price": asset.price
        }
        
        supabase.table("portfolios").insert(data).execute()
        return {"message": "Ativo cadastrado com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. Rota de Análise (Backend + IA)
@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro: Chaves de API ausentes.")

    try:
        # A. Busca dados no Banco (Supabase)
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Carteira não encontrada no banco de dados."}

        # B. Modelo Hardcoded (Gemini 1.5 Flash)
        modelo_escolhido = "models/gemini-1.5-flash"

        # C. Envia para a IA com Retry
        url = f"https://generativelanguage.googleapis.com/v1beta/{modelo_escolhido}:generateContent?key={GOOGLE_API_KEY}"
        
        # Prepara o prompt financeiro profissional
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }
        
        prompt = (
            f"Atue como um Consultor Financeiro Sênior de Wealth Management. "
            f"Analise os dados abaixo (JSON). Seja direto, profissional e técnico. "
            f"Fale sobre alocação e riscos. Não use formatação Markdown complexa. "
            f"Dados: {data_packet}"
        )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        # Lógica de Retry (Tentativa Automática)
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                ai_text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Sem texto')
                return {"ai_analysis": ai_text}
            
            elif response.status_code == 429:
                # Se for erro de limite (429), espera e tenta de novo (Backoff Exponencial)
                wait_time = 2 ** attempt # 1s, 2s, 4s...
                print(f"Erro 429. Tentando novamente em {wait_time}s...")
                time.sleep(wait_time)
            
            else:
                # Outros erros não adianta tentar de novo imediatamente
                return {"erro_fatal": f"Erro Google ({modelo_escolhido}): {response.text}"}

        return {"erro_fatal": f"Falha após {max_retries} tentativas. API do Google sobrecarregada."}

    except Exception as e:
        return {"erro_interno": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
