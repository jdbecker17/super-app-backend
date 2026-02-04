import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai

# 1. Configuração de Segurança
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Inicialização global das variáveis
supabase: Client = None
model = None

# 2. Conexões e Inicialização
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        generation_config = {
          "temperature": 0.5,
          "top_p": 0.95,
          "max_output_tokens": 8192,
          "response_mime_type": "text/plain",
        }

        # No main.py, substitua a linha do model por esta:
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest", # Adicionamos o "-latest"
    generation_config=generation_config,
    system_instruction="Você é o Personal Broker AI. Analise a carteira em português."
)
except Exception as e:
    print(f"Erro na inicialização dos clientes: {e}")

app = FastAPI()

class AnalysisRequest(BaseModel):
    user_id: str

@app.get("/")
def health_check():
    return {"status": "online", "service": "AI Financial Core"}

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Servidor mal configurado: Faltam chaves de API.")
    
    if model is None or supabase is None:
        raise HTTPException(status_code=500, detail="Erro na conexão com os serviços (Supabase/Gemini).")

    try:
        # A. Busca dados no Supabase
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Sua carteira está vazia. Comece adicionando ativos."}

        # B. Prepara o pacote para a IA
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }

        # C. Envia para o Google Gemini
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(f"Analise esta carteira atual: {data_packet}")
        
        return {"ai_analysis": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
