import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

# 1. Configuração de Chaves
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class AnalysisRequest(BaseModel):
    user_id: str

# 2. Rota para entregar o Site (Frontend)
@app.get("/")
def read_root():
    # Retorna o arquivo HTML que criamos na pasta static
    return FileResponse('static/index.html')

# Monta a pasta static para permitir arquivos futuros (CSS/JS externos)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. Rota de Análise (Backend + IA)
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

        # B. Auto-Descoberta do Modelo Google (O segredo do sucesso)
        # Pergunta ao Google quais modelos estão liberados para esta chave
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        list_response = requests.get(list_url)
        
        modelos_google = list_response.json().get('models', [])
        # Filtra apenas modelos que geram texto
        modelos_uteis = [m['name'] for m in modelos_google if 'generateContent' in m.get('supportedGenerationMethods', [])]
        
        if not modelos_uteis:
            return {"erro_fatal": "Nenhum modelo de texto disponível na sua conta Google."}

        # Escolhe o melhor (Prioridade: Versões Flash, depois Pro)
        modelo_escolhido = modelos_uteis[0] 
        for m in modelos_uteis:
            if "flash" in m and "exp" in m: # Tenta pegar o experimental mais novo
                modelo_escolhido = m
                break
            elif "flash" in m:
                modelo_escolhido = m

        # C. Envia para a IA
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

        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            ai_text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Sem texto')
            return {"ai_analysis": ai_text}
        else:
            return {"erro_fatal": f"Erro Google ({modelo_escolhido}): {response.text}"}

    except Exception as e:
        return {"erro_interno": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
