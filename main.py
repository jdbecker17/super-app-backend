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
    return {"status": "online", "service": "SuperAppInvest API"}

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro: Chaves de API ausentes.")

    try:
        # 1. Busca dados no Supabase
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Carteira vazia."}

        # 2. Prepara os dados
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }

       # MUDANÇA: Apontando para o Gemini 1.5 Flash (o modelo atual e rápido)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [{"text": f"Aja como um consultor financeiro. Analise esta carteira em Português: {data_packet}"}]
            }]
        }

        response = requests.post(url, json=payload)
        
        # Se der erro no Google, mostramos o motivo exato
        if response.status_code != 200:
            return {"erro_google": response.json()}

        # Extrai a resposta da IA
        ai_text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Sem resposta da IA')
        
        return {"ai_analysis": ai_text}

    except Exception as e:
        return {"erro_interno": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
