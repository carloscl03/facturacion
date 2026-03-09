"""Repositorio para la API de información (sucursales, etc.)."""
import requests


def _normalizar_sucursal(item: dict) -> dict | None:
    """Extrae id y nombre de un ítem de sucursal (admite varias formas de la API)."""
    if not isinstance(item, dict):
        return None
    sid = item.get("id") or item.get("id_sucursal") or item.get("sucursal_id") or item.get("sucursalId")
    if sid is None:
        return None
    try:
        sid = int(sid)
    except (TypeError, ValueError):
        return None
    nombre = (item.get("nombre") or item.get("nombre_sucursal") or item.get("sucursal_nombre") or item.get("name") or "").strip()
    return {"id": sid, "nombre": nombre or str(sid)}


class InformacionRepository:
    """Acceso a ws_informacion_ia.php (sucursales públicas, etc.)."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def obtener_sucursales_publicas(self, id_empresa: int) -> list[dict]:
        """
        Obtiene la lista de sucursales públicas de la empresa.
        Retorna lista de {"id": int, "nombre": str}.
        """
        payload = {
            "codOpe": "OBTENER_SUCURSALES_PUBLICAS",
            "id_empresa": id_empresa,
        }
        try:
            res = requests.post(self._base_url, json=payload, timeout=10)
            data = res.json()
        except Exception:
            return []
        # Aceptar data, sucursales o items como clave de la lista
        raw_list = data.get("data") or data.get("sucursales") or data.get("items") or []
        if not isinstance(raw_list, list):
            return []
        out = []
        for item in raw_list:
            s = _normalizar_sucursal(item)
            if s:
                out.append(s)
        return out
