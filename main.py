import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

# --- Configuração Inicial ---
app = FastAPI()

# Pegamos as chaves
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Modelo de dados que vem do ReqBin/App
class AnalysisRequest(BaseModel):
    user_id: str

@app.get("/")
def health_check():
    return {"status": "online", "service": "SuperAppInvest API - Direct Mode"}

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    # 1. Validação de Segurança
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro Interno: Chaves de API não configuradas.")

    try:
        # 2. Conexão com Supabase
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        # 3. Busca os dados do Usuário
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Sua carteira está vazia no banco de dados."}

        # 4. Prepara o pacote de dados
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }

        # 5. CONEXÃO DIRETA COM A IA (Sem biblioteca quebrada)
        # Usamos a API REST oficial do Gemini 1.5 Flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GOOGLE_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [{"text": f"Você é um consultor financeiro. Analise esta carteira em PT-BR: {data_packet}"}]
            }]
        }

        # Envia o pedido (POST)
        response = requests.post(url, json=payload)
        
        # Verifica se deu certo
        if response.status_code != 200:
            raise Exception(f"Erro no Google: {response.text}")

        # Extrai o texto da resposta
        ai_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        return {"ai_analysis": ai_text}

    except Exception as e:
        print(f"Erro no processamento: {e}")
        # Mostra o erro real na tela do ReqBin para sabermos o que houve
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
