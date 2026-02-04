import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI()

# Pegamos as chaves
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class AnalysisRequest(BaseModel):
    user_id: str

@app.get("/")
def health_check():
    return {"status": "online", "service": "SuperAppInvest Auto-Discovery"}

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro: Chaves de API ausentes.")

    try:
        # 1. Conecta no Supabase e busca os dados
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Carteira vazia no banco de dados."}

        # 2. AUTO-DESCOBERTA: Pergunta ao Google quais modelos existem para sua chave
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
        list_response = requests.get(list_url)
        
        if list_response.status_code != 200:
            return {"erro_fatal": "Chave do Google recusada ao listar modelos.", "detalhe": list_response.text}
            
        # Filtra apenas modelos que geram texto (ignora modelos de apenas imagem/som)
        modelos_google = list_response.json().get('models', [])
        modelos_uteis = [m['name'] for m in modelos_google if 'generateContent' in m.get('supportedGenerationMethods', [])]
        
        if not modelos_uteis:
            return {"erro_fatal": "Sua conta Google não tem nenhum modelo de texto liberado. Verifique o Google AI Studio."}

        # Escolhe o melhor modelo automaticamente (prefere Flash, senão pega o primeiro da lista)
        modelo_escolhido = modelos_uteis[0] # Pega o primeiro que aparecer
        for m in modelos_uteis:
            if "flash" in m:
                modelo_escolhido = m
                break

        # 3. ENVIA PARA A IA (Usando o modelo que sabemos que existe)
        url = f"https://generativelanguage.googleapis.com/v1beta/{modelo_escolhido}:generateContent?key={GOOGLE_API_KEY}"
        
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }
        
        payload = {
            "contents": [{
                "parts": [{"text": f"Aja como um consultor financeiro. Analise esta carteira em Português: {data_packet}"}]
            }]
        }

        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            ai_text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Sem texto')
            return {
                "modelo_descoberto_e_usado": modelo_escolhido,
                "ai_analysis": ai_text
            }
        else:
            return {"erro_final": response.text}

    except Exception as e:
        return {"erro_interno": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
