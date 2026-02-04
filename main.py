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
            return {"ai_analysis": "Carteira vazia no banco de dados."}

        # 2. Prepara os dados
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }

        # 3. ESTRATÉGIA INTELIGENTE: Tenta vários modelos até um funcionar
        # Lista de tentativas: O mais novo, o específico 001, e o clássico Pro
        modelos_para_tentar = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-001",
            "gemini-1.0-pro",
            "gemini-pro"
        ]

        last_error = ""

        for modelo in modelos_para_tentar:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GOOGLE_API_KEY}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": f"Aja como um consultor financeiro. Analise esta carteira em Português: {data_packet}"}]
                    }]
                }

                # Tenta conectar
                response = requests.post(url, json=payload)
                
                # Se der certo (200), pega o texto e PARA de tentar
                if response.status_code == 200:
                    ai_text = response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Sem texto')
                    return {
                        "modelo_usado": modelo, # Mostra qual funcionou
                        "ai_analysis": ai_text
                    }
                else:
                    # Se der erro, guarda o motivo e tenta o próximo da lista
                    last_error = response.text
                    continue 

            except Exception as e:
                print(f"Erro ao tentar {modelo}: {e}")
                continue

        # Se chegar aqui, nenhum funcionou. Retorna o erro do último.
        return {
            "erro_fatal": "Nenhum modelo do Google funcionou.",
            "ultimo_erro_google": last_error
        }

    except Exception as e:
        return {"erro_interno": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
