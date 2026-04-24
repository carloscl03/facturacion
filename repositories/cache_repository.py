import json
import time

import requests

from config.logging_config import get_logger
from repositories.base import CacheRepository

_log = get_logger("maravia.cache")


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
        t0 = time.perf_counter()
        res = requests.get(self._base_url, params=params)
        ms = round((time.perf_counter() - t0) * 1000)
        data = res.json().get("data", [])
        hit = bool(data)
        _log.debug("cache_consultar", extra={"wa_id": wa_id, "id_from": id_from, "hit": hit, "latency_ms": ms})
        return data[0] if data else None

    def consultar_lista(self, wa_id: str, id_from: int) -> list[dict]:
        """Retorna la lista completa (útil para determinar si el registro es nuevo)."""
        params = {
            "codOpe": "CONSULTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
        }
        t0 = time.perf_counter()
        res = requests.get(self._base_url, params=params)
        ms = round((time.perf_counter() - t0) * 1000)
        data = res.json().get("data", [])
        _log.debug("cache_consultar_lista", extra={"wa_id": wa_id, "id_from": id_from, "count": len(data), "latency_ms": ms})
        return data

    def insertar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        payload = {
            "codOpe": "INSERTAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        t0 = time.perf_counter()
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        ms = round((time.perf_counter() - t0) * 1000)
        result = res.json()
        ok = result.get("success", res.status_code == 200)
        _log.info(
            "cache_insertar",
            extra={
                "wa_id": wa_id,
                "id_from": id_from,
                "operacion": datos.get("operacion"),
                "estado": datos.get("estado"),
                "ok": ok,
                "latency_ms": ms,
            },
        )
        return result

    def actualizar(self, wa_id: str, id_from: int, datos: dict) -> dict:
        payload = {
            "codOpe": "ACTUALIZAR_CACHE",
            "ws_whatsapp": wa_id,
            "id_from": id_from,
            **datos,
        }
        headers = {"Content-Type": "application/json"}
        t0 = time.perf_counter()
        res = requests.post(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        ms = round((time.perf_counter() - t0) * 1000)
        result = res.json()
        campos = [k for k in datos if k not in ("codOpe", "ws_whatsapp", "id_from")]
        _log.debug(
            "cache_actualizar",
            extra={
                "wa_id": wa_id,
                "id_from": id_from,
                "campos_actualizados": campos,
                "n_campos": len(campos),
                "estado": datos.get("estado"),
                "operacion": datos.get("operacion"),
                "latency_ms": ms,
            },
        )
        return result

    def eliminar(self, wa_id: str, id_from: int) -> dict:
        try:
            payload = {
                "codOpe": "ELIMINAR_CACHE",
                "ws_whatsapp": wa_id,
                "id_from": id_from,
            }
            t0 = time.perf_counter()
            res = requests.post(self._base_url, json=payload, timeout=15)
            ms = round((time.perf_counter() - t0) * 1000)
            data = res.json() if res.content else {}
            ok = data.get("success", data.get("status") == "ok" or res.status_code == 200)
            _log.info("cache_eliminar", extra={"wa_id": wa_id, "id_from": id_from, "ok": bool(ok), "latency_ms": ms})
            return {"success": bool(ok)}
        except (requests.RequestException, ValueError) as e:
            _log.error("cache_eliminar_error", extra={"wa_id": wa_id, "id_from": id_from, "error": str(e)}, exc_info=True)
            return {"success": False, "error": str(e)}
