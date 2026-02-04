import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai

# --- Configuração Inicial ---
app = FastAPI()

# Pegamos as chaves
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Validamos se as chaves existem (apenas aviso no log)
if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
    print("⚠️ AVISO: Variáveis de ambiente faltando. Verifique o Dokploy.")

# Configuração da IA (Global)
genai.configure(api_key=GOOGLE_API_KEY)

# Modelo de dados que vem do ReqBin/App
class AnalysisRequest(BaseModel):
    user_id: str

@app.get("/")
def health_check():
    return {"status": "online", "service": "SuperAppInvest API"}

@app.post("/analyze")
def analyze_portfolio(request: AnalysisRequest):
    # 1. Validação de Segurança
    if not all([SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY]):
        raise HTTPException(status_code=500, detail="Erro Interno: Chaves de API não configuradas no servidor.")

    try:
        # 2. Conexão com Supabase (Cria na hora, evita queda de conexão)
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        # 3. Definição do Modelo (Cria na hora para garantir a versão correta)
        # Usamos o nome padrão 'gemini-1.5-flash' que é o mais compatível
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.5,
                "max_output_tokens": 4096,
                "response_mime_type": "text/plain",
            },
            system_instruction="Você é o Personal Broker AI. Responda em Português do Brasil com formatação Markdown."
        )

        # 4. Busca os dados do Usuário
        portfolio_response = supabase.table("portfolios").select("*").eq("user_id", request.user_id).execute()
        profile_response = supabase.table("profiles").select("*").eq("id", request.user_id).execute()
        
        if not portfolio_response.data:
            return {"ai_analysis": "Sua carteira está vazia no banco de dados."}

        # 5. Prepara o pacote e envia para a IA
        data_packet = {
            "profile": profile_response.data,
            "portfolio": portfolio_response.data
        }

        # Gera a resposta
        response = model.generate_content(f"Analise esta carteira de investimentos: {data_packet}")
        
        return {"ai_analysis": response.text}

    except Exception as e:
        # Se der erro, mostra o detalhe exato ao invés de derrubar o servidor
        print(f"Erro no processamento: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no servidor: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
