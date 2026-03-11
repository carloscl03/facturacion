import json
import requests

from repositories.base import CacheRepository


class HttpCacheRepository(CacheRepository):
    """Implementación del repositorio de caché usando la API PHP (URL_API)."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def consultar(self, wa_id: str, id_from: int) -> dict | None:
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
        }
        res = requests.get(self._base_url, params=params)
        data = res.json().get("data", [])
        return data[0] if data else None

    def consultar_lista(self, wa_id: str, id_from: int) -> list[dict]:
        """Retorna la lista completa (útil para determinar si el registro es nuevo)."""
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
        }
        res = requests.get(self._base_url, params=params)
        return res.json().get("data", [])

    def insertar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        payload = {
            "codOpe": "INSERTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        return res.json()

    def actualizar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        payload = {
            "codOpe": "ACTUALIZAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        return res.json()

    def eliminar(self, wa_id: str, id_from: int) -> dict:
        try:
            payload = {
                "codOpe": "ELIMINAR_CACHE",
                "ws_whatsapp": wa_id,
                "id_from": id_from,
            }
            res = requests.post(self._base_url, json=payload, timeout=15)
            data = res.json() if res.content else {}
            ok = data.get("success", data.get("status") == "ok" or res.status_code == 200)
            return {"success": bool(ok)}
        except (requests.RequestException, ValueError) as e:
            return {"success": False, "error": str(e)}
