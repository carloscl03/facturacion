import json
import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

URL_CACHE = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"
WA_ID = "51994748961"
ID_EMPRESA = 2

def imprimir_bloque(titulo, registro):
    print(f"\n📦 {titulo}")
    print("=" * 70)
    print(json.dumps(registro, indent=4, ensure_ascii=False))
    print("=" * 70)

def ejecutar_flujo_contextual():
    params_leer = {"codOpe": "CONSULTAR_CACHE", "ws_whatsapp": WA_ID, "id_empresa": ID_EMPRESA}
    
    # 1. LECTURA INICIAL
    res_inicial = requests.get(URL_CACHE, params=params_leer)
    data_recibida = res_inicial.json().get('data', [])
    
    # Si está vacío, usamos una plantilla para que la IA sepa qué campos existen
    registro_actual = data_recibida[0] if data_recibida else {}
    es_registro_nuevo = len(data_recibida) == 0

    imprimir_bloque("ESTADO INICIAL RECUPERADO", registro_actual)

    # 2. INPUT DE USUARIO
    mensaje_usuario = input("\n💬 Mensaje del usuario: ")

    # 3. PROMPT CON REGLAS DE NORMALIZACIÓN
    prompt_sistema = f"""
    Eres un asistente de base de datos. Tu tarea es actualizar un registro JSON.
    
    CAMPOS IMPORTANTES:
    - 'cod_ope': Debe ser 'compras' o 'ventas'.
    - 'id_sucursal': ID numérico de la sede.
    - 'entidad_nombre': Nombre del proveedor o cliente.
    
    INSTRUCCIONES:
    1. Devuelve ÚNICAMENTE un objeto JSON con los campos a modificar.
    2. Si el usuario quiere 'comprar' o 'vender', asegúrate de incluir 'cod_ope'.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensaje_usuario}
            ],
            response_format={"type": "json_object"}
        )
        
        datos_ia = json.loads(response.choices[0].message.content)
        print(f"\n🧠 IA sugirió: {datos_ia}")

        # 4. DECISIÓN: ¿INSERTAR O ACTUALIZAR?
        # Tu PHP separa estas operaciones, así que el bot debe ser listo:
        operacion = "INSERTAR_CACHE" if es_registro_nuevo else "ACTUALIZAR_CACHE"
        
        payload = {
            "codOpe": operacion,
            "ws_whatsapp": WA_ID,
            "id_empresa": ID_EMPRESA,
            **datos_ia
        }
        
        # Validación: INSERTAR_CACHE requiere cod_ope obligatoriamente en tu PHP
        if operacion == "INSERTAR_CACHE" and "cod_ope" not in payload:
            payload["cod_ope"] = "compras" # Valor por defecto seguro

        res_upd = requests.post(URL_CACHE, json=payload)
        print(f"✅ Respuesta Servidor ({operacion}): {res_upd.json().get('message')}")

        # 5. LECTURA FINAL (CON PREVENCIÓN DE ERROR)
        res_final = requests.get(URL_CACHE, params=params_leer)
        data_final = res_final.json().get('data', [])
        
        if data_final:
            imprimir_bloque("ESTADO FINAL TRAS ACTUALIZACIÓN", data_final[0])
        else:
            print("\n⚠️ El registro aún no aparece en la base de datos. Revisa los logs del PHP.")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    ejecutar_flujo_contextual()