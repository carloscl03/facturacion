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

    def obtener_sucursales_publicas(self, id_from: int) -> list[dict]:
        """
        Obtiene la lista de sucursales públicas de la empresa.
        Retorna lista de {"id": int, "nombre": str}.
        """
        payload = {
            "codOpe": "OBTENER_SUCURSALES_PUBLICAS",
            "id_from": id_from,
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

    def obtener_sucursales(self, id_empresa: int) -> list[dict]:
        """
        Obtiene la lista de sucursales (codOpe OBTENER_SUCURSALES).
        id_empresa: empresa para jalar la tabla (como en test_opciones).
        Retorna lista de {"id": int, "nombre": str}.
        """
        payload = {"codOpe": "OBTENER_SUCURSALES", "id_empresa": id_empresa}
        try:
            res = requests.post(self._base_url, json=payload, timeout=10)
            data = res.json()
        except Exception:
            return []
        raw_list = data.get("sucursales") or data.get("data") or data.get("items") or []
        if not isinstance(raw_list, list):
            return []
        out = []
        for item in raw_list:
            s = _normalizar_sucursal(item)
            if s:
                out.append(s)
        return out

    def obtener_metodos_pago(self, id_empresa: int) -> list[dict]:
        """
        Obtiene métodos de pago (bancos, yape, plin). POST OBTENER_METODOS_PAGO con id_empresa (como test_opciones).
        Retorna lista de {"id": str, "title": str, "description": str} para listas WhatsApp.
        """
        payload = {"codOpe": "OBTENER_METODOS_PAGO", "id_empresa": id_empresa}
        try:
            res = requests.post(
                self._base_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = res.json() if res.status_code == 200 else {}
        except Exception:
            return []
        return _extraer_filas_metodos_pago(data)


def _extraer_filas_metodos_pago(respuesta: dict) -> list[dict]:
    """
    Extrae filas para lista WhatsApp desde la respuesta de OBTENER_METODOS_PAGO.
    Formato API: metodos_pago: { bancos: [...], yape: {...}|null, plin: {...}|null }.
    """
    if not isinstance(respuesta, dict):
        return []
    filas = []
    mp = respuesta.get("metodos_pago")
    if isinstance(mp, dict):
        bancos = mp.get("bancos") or []
        for b in bancos if isinstance(bancos, list) else []:
            if isinstance(b, dict):
                bid = b.get("id")
                nombre = (b.get("nombre") or "").strip() or str(bid)
                num = (b.get("numero_cuenta") or "").strip()
                cci = (b.get("cci") or "").strip()
                desc = " | ".join(x for x in [num, cci] if x)
                filas.append({"id": str(bid), "title": nombre, "description": desc})
        if mp.get("yape") and isinstance(mp["yape"], dict):
            cel = (mp["yape"].get("celular") or "").strip()
            filas.append({"id": "yape", "title": "Yape", "description": cel or "Billetera Yape"})
        if mp.get("plin") and isinstance(mp["plin"], dict):
            cel = (mp["plin"].get("celular") or "").strip()
            filas.append({"id": "plin", "title": "Plin", "description": cel or "Billetera Plin"})
    return filas
