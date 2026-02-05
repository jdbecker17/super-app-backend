import os
import requests
import google.generativeai as genai
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

# 3.1 Rota de Listagem de Ativos (GET)
@app.get("/assets")
def get_assets():
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        user_id = 'a114b418-ec3c-407e-a2f2-06c3c453b684'
        response = supabase.table("portfolios").select("*").eq("user_id", user_id).execute()
        return response.data
    except Exception as e:
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
        # A. Busca dados no Banco (Supabase)
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Carteira vazia. Adicione ativos para análise."}

        # B. Monta os dados para o Prompt
        # Formata bonitinho para a IA entender melhor
        portfolio_summary = []
        for item in portfolio_response.data:
            portfolio_summary.append(f"- {item['ticker']}: {item['quantity']} cotas a R$ {item['average_price']}")
        
        portfolio_text = "\n".join(portfolio_summary)

        # C. Prompt de Consultor de Elite
        prompt = (
            f"Atue como um Consultor de Elite de Wealth Management. "
            f"Analise esta carteira de investimentos:\n{portfolio_text}\n\n"
            f"Responda EXCLUSIVAMENTE em HTML (sem tags <html> ou <body>, apenas o conteúdo div/p/ul) "
            f"com estas 3 seções estilizadas e curtas:\n"
            f"1. <h3>Risco da Carteira</h3> (Análise objetiva)\n"
            f"2. <h3>Sugestão de Diversificação</h3> (O que falta?)\n"
            f"3. <h3>Comentário sobre o maior ativo</h3> (Destaque o principal)\n"
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
