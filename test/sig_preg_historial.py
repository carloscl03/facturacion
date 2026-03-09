import os
import requests
from fastapi import FastAPI, Query, HTTPException
from openai import OpenAI
from dotenv import load_dotenv

# Cargar las llaves del archivo .env
load_dotenv()

app = FastAPI(title="MaravIA - Generador de Siguiente Pregunta")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.get("/analizar-historial")
async def analizar_historial(
    ws_whatsapp: str = Query(..., description="Número de WhatsApp del cliente"),
    user_prompt: str = Query(..., description="El mensaje o instrucción para la IA")
):
    # 1. Consultar la API de tu amigo para traer el JSON del historial
    url_api = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
    
    try:
        response_api = requests.get(url_api, params={'ws_whatsapp': ws_whatsapp}, timeout=10)
        response_api.raise_for_status()
        data_json = response_api.json()
        
        # Extraemos el registro más reciente
        historial_data = data_json.get('data', [])[0] if data_json.get('data') else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al conectar con la API de historial: {str(e)}")

    # 2. Preparar el envío a ChatGPT (gpt-4o-mini)
    # Concatenamos tu prompt con el JSON que obtuvimos
    contexto_ia = f"""
    DATOS ACTUALES EN BASE DE DATOS (JSON):
    {historial_data}

    MENSAJE DEL USUARIO / INSTRUCCIÓN:
    {user_prompt}
    """

    try:
        chat_completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "Eres el asistente inteligente de MaravIA. Tu función es analizar el JSON y responder a la instrucción del usuario. Si te piden detalles de campos vacíos, lístalos. Si te piden la siguiente pregunta, genérala para completar el registro."
                },
                {"role": "user", "content": contexto_ia}
            ],
            temperature=0  # Para que sea preciso y no invente datos
        )
        
        respuesta_final = chat_completion.choices[0].message.content
        
        return {
            "ws_whatsapp": ws_whatsapp,
            "status": "success",
            "respuesta_ia": respuesta_final
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en OpenAI: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Cambiamos a 3000 para que coincida con tu ngrok
    uvicorn.run(app, host="0.0.0.0", port=3000)