import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CacheManager:
    def __init__(self, url_api: str):
        self.url = url_api

    def consultar(self, whatsapp: str, id_empresa: int):
        """Busca si el usuario tiene una sesión activa."""
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": whatsapp,
            "id_empresa": id_empresa
        }
        try:
            response = requests.get(self.url, params=params, verify=False, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                return res_json['data'][0] if res_json.get('total', 0) > 0 else None
            return None
        except Exception as e:
            print(f"Error en CacheManager.consultar: {e}")
            return None

    def guardar(self, payload: dict):
        """Inserta o Actualiza según el codOpe enviado."""
        # Aseguramos que los booleanos viajen como 0/1 para PostgreSQL
        for key in ['is_ready', 'verificado_erp']:
            if key in payload:
                payload[key] = 1 if payload[key] is True or payload[key] == 1 else 0
        
        try:
            response = requests.post(self.url, json=payload, verify=False, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error en CacheManager.guardar: {e}")
            return {"success": False, "error": str(e)}

    def eliminar(self, whatsapp: str, id_empresa: int):
        """Limpia la caché al finalizar la venta/compra."""
        payload = {
            "codOpe": "ELIMINAR_CACHE",
            "ws_whatsapp": whatsapp,
            "id_empresa": id_empresa
        }
        try:
            response = requests.post(self.url, json=payload, verify=False)
            return response.json()
        except Exception as e:
            print(f"Error en CacheManager.eliminar: {e}")
            return {"success": False}