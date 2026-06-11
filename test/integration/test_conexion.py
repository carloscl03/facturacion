import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analizar_datos_faltantes(numero_whatsapp):
    # 1. Obtenemos el JSON real de tu API
    url_api = "https://api.maravia.pe/servicio/n8n_asistente/ws_informacion_historial.php"
    res = requests.get(url_api, params={'ws_whatsapp': numero_whatsapp})
    data_json = res.json()

    # Extraemos solo la parte de 'data' para no gastar tokens innecesarios
    historial_data = data_json.get('data', [])[0] if data_json.get('data') else {}

    # 2. Tu instrucción específica concatenada con el JSON
    instruccion_usuario = "quiero que me detalles los datos que no están llenados"
    
    prompt_completo = f"""
    JSON DE LA BASE DE DATOS:
    {historial_data}

    INSTRUCCIÓN:
    {instruccion_usuario}
    """

    # 3. Mandamos a ChatGPT (gpt-4.1-mini)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system", 
                "content": "Eres un auditor de datos contables. Tu función es revisar el JSON proporcionado y listar únicamente los campos que tienen valor 'null' o están vacíos, explicando brevemente por qué son importantes para un registro de GASTO, VENTA o COMPRA según el 'cod_ope'."
            },
            {"role": "user", "content": prompt_completo}
        ],
        temperature=0
    )

    return response.choices[0].message.content

# Ejecución
print("🔍 Analizando huecos de información en el ID 142...")
resultado = analizar_datos_faltantes("51999999999")
print("\n--- REPORTE DE LA IA ---")
print(resultado)