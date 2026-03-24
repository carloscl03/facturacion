from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from services.helpers.registro_domain import operacion_desde_registro


CAMPOS_ESTADO2: Tuple[str, ...] = ("sucursal", "centro_costo", "forma_pago")


def _forma_pago_completa(registro: Dict[str, Any]) -> bool:
    return bool((registro.get("forma_pago") or "").strip() or registro.get("id_forma_pago"))


def siguiente_campo_pendiente(registro: Dict[str, Any] | None, tiene_parametros: bool) -> str | None:
    """
    Orden Estado 2:
    sucursal → centro_costo (solo compra) → forma_pago (LISTAR_FORMAS).
    En venta se omite centro de costo.
    """
    if not registro:
        return "sucursal"
    if not registro.get("id_sucursal"):
        return "sucursal"
    operacion = operacion_desde_registro(registro)
    if operacion != "venta" and tiene_parametros and not registro.get("id_centro_costo"):
        return "centro_costo"
    if not _forma_pago_completa(registro):
        return "forma_pago"
    return None


def lista_para_redis(raw: Iterable[Any]) -> List[Dict[str, Any]]:
    """
    Convierte una lista heterogénea (dicts, str, int) en una lista estándar
    de opciones con forma: [{\"id\": ..., \"nombre\": ...}, ...]
    adecuada para guardar en Redis y mostrar al usuario.
    """
    out: List[Dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, dict):
            id_v = item.get("id")
            nom = (item.get("nombre") or item.get("title") or "").strip() or str(id_v)
            out.append({"id": id_v, "nombre": nom})
        elif isinstance(item, (str, int)):
            out.append({"id": item, "nombre": str(item)})
    return out


def normalizar_opciones_actuales(raw: Any) -> List[Dict[str, Any]]:
    """
    Normaliza el valor crudo de opciones_actuales (puede venir como lista,
    string JSON, bytes o None) a una lista de dicts estándar.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            return []
    return []
