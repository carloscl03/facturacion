"""Repositorio para ws_parametros.php (tablas maestras: centros de costo, etc.)."""
import requests


class ParametrosRepository:
    """Acceso a ws_parametros (GET OBTENER_TABLAS_MAESTRAS)."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def obtener_centros_costo(self, wa_id: str) -> list[dict]:
        """
        GET OBTENER_TABLAS_MAESTRAS con wa_id.
        Devuelve solo la tabla centros_costo: [{"id": ..., "nombre": ...}, ...].
        """
        params = {"codOpe": "OBTENER_TABLAS_MAESTRAS", "wa_id": wa_id}
        try:
            res = requests.get(self._base_url, params=params, timeout=15)
            if res.status_code != 200:
                return []
            data = res.json()
        except Exception:
            return []
        tablas = data.get("tablas_maestras") if isinstance(data, dict) else None
        if not isinstance(tablas, dict):
            return []
        centros = tablas.get("centros_costo")
        return centros if isinstance(centros, list) else []
