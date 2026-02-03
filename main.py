import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai

# 1. Configuração de Segurança (Lê as senhas do Servidor)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Validação Inicial
if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
    # Imprime aviso no log para ajudar a depurar, mas não trava o start imediato do Uvicorn
    print("AVISO: Variáveis de ambiente incompletas. Verifique o Dokploy.")

# 2. Conexões (Inicializa apenas se tiver chaves, senão aguarda configuração)
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    if GOOGLE_API_KEY:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # Configuração do Modelo
        generation_config = {
          "temperature": 0.5,
          "top_p": 0.95,
          "max_output_tokens": 8192,
          "response_mime_type": "text/plain",
        }

        model = genai.GenerativeModel(
          model_name="gemini-1.5-pro", 
          generation_config=generation_config,
          system_instruction="""
            Role: You are the "Personal Broker AI". Analyze the user's portfolio data provided in JSON.
            Capabilities: 
            1. Check for concentration risk (>20% in one asset).
            2. Suggest tax efficiency moves.
            3. Output strictly in Markdown. 
            Language: Portuguese (Brazil).
          """
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

    try:
        # A. Busca dados no Supabase
        portfolio_response = supabase.table("portfolios").select("*, assets(*)").eq("user_id", request.user_id).execute()
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
        
        # D. Salva o Insight no Banco
        supabase.table("ai_insights").insert({
            "user_id": request.user_id,
            "context": "General Analysis",
            "ai_response": response.text,
            "sentiment_score": 0.0 
        }).execute()

        return {"ai_analysis": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
if __name__ == "__main__":
    import uvicorn
    # A mágica acontece aqui: segura o servidor ligado na porta 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
