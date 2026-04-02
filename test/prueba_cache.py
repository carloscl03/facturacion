import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_API = "https://api.maravia.pe/servicio/n8n/ws_historial_cache.php"
WS_WHATSAPP = "51999999999"
ID_FROM = 2

def probar_actualizacion():
    print(f"--- Probando ACTUALIZAR_CACHE ---")

    # Payload para actualizar el registro existente
    # Importante: Mantener 0/1 para campos booleanos
    payload_update = {
        "codOpe": "ACTUALIZAR_CACHE",
        "ws_whatsapp": WS_WHATSAPP,
        "id_from": ID_FROM,
        "cod_ope": "ventas",
        "entidad_numero_documento": "20601234567",
        "entidad_razon_social": "MARAVIA SAC",
        "is_ready": 1,              # Marcamos como listo
        "ultima_pregunta": "Registro completado con éxito",
        "metadata_ia": {
            "confianza": 0.98,
            "intencion": "finalizar_registro"
        }
    }
    
    try:
        print("\n1. Enviando actualización...")
        res_act = requests.post(URL_API, json=payload_update, verify=False)
        print(f"Respuesta Update: {res_act.text}")

        # 2. Verificar los cambios con un GET final
        print("\n2. Consultando estado final en la DB...")
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": WS_WHATSAPP,
            "id_from": ID_FROM
        }
        res_get = requests.get(URL_API, params=params, verify=False)
        
        if res_get.status_code == 200:
            datos = res_get.json()
            print(json.dumps(datos, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probar_actualizacion()