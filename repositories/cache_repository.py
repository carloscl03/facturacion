import json
import requests

from repositories.base import CacheRepository


class HttpCacheRepository(CacheRepository):
    """Implementación del repositorio de caché usando la API PHP (URL_API)."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def consultar(self, wa_id: str, id_empresa: int) -> dict | None:
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
        }
        res = requests.get(self._base_url, params=params)
        data = res.json().get("data", [])
        return data[0] if data else None

    def consultar_lista(self, wa_id: str, id_empresa: int) -> list[dict]:
        """Retorna la lista completa (útil para determinar si el registro es nuevo)."""
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
        }
        res = requests.get(self._base_url, params=params)
        return res.json().get("data", [])

    def insertar(self, wa_id: str, id_empresa: int, datos: dict) -> dict:
        payload = {
            "codOpe": "INSERTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        return res.json()

    def actualizar(self, wa_id: str, id_empresa: int, datos: dict) -> dict:
        payload = {
            "codOpe": "ACTUALIZAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        return res.json()

    def eliminar(self, wa_id: str, id_empresa: int) -> dict:
        payload = {
            "codOpe": "ELIMINAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_empresa": id_empresa,
        }
        res = requests.post(self._base_url, json=payload)
        return res.json()
