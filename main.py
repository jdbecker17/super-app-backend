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

        # AJUSTE: Corrigida a declaração do modelo (removido o erro de nome duplicado)
        model = genai.GenerativeModel(
          model_name="gemini-1.5-flash", 
          generation_config=generation_config,
          system_instruction="""
            Role: Você é o "Personal Broker AI". Analise os dados da carteira do usuário fornecidos em JSON.
            Capabilities: 
            1. Verifique risco de concentração (>20% em um único ativo).
            2. Sugira movimentos de eficiência tributária.
            3. Saída estritamente em Markdown. 
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
    # Verificação se os serviços foram inicializados
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Servidor mal configurado: Faltam chaves de API.")
    
    if model is None or supabase is None:
        raise HTTPException(status_code=500, detail="Erro na conexão com os serviços (Supabase/Gemini).")

    try:
        # A. Busca dados no Supabase (Mantenha o select("*") para portfolios)
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
        
        # D. Salva o Insight no Banco (Opcional - Ative se a tabela ai_insights existir)
        # supabase.table("ai_insights").insert({
        #     "user_id": request.user_id,
        #     "insight_text": response.text
        # }).execute()

        return {"ai_analysis": response.text}

    except Exception as e:
        # Retorna o erro real para ajudar no debug
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Inicia o servidor na porta 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
