from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


CAMPOS_ESTADO2: Tuple[str, str, str, str] = ("sucursal", "centro_costo", "forma_pago", "medio_pago")


def siguiente_campo_pendiente(registro: Dict[str, Any] | None, tiene_parametros: bool) -> str | None:
    """
    Determina el siguiente campo de opciones pendiente para Estado 2.

    Respeta el orden: sucursal → centro_costo → forma_pago → medio_pago.
    El flag tiene_parametros indica si hay repositorio de parámetros disponible
    para centros de costo.
    """
    if not registro:
        return "sucursal"
    if not registro.get("id_sucursal"):
        return "sucursal"
    if tiene_parametros and not registro.get("id_centro_costo"):
        return "centro_costo"
    if not (registro.get("forma_pago") or "").strip():
        return "forma_pago"
    if (registro.get("medio_pago") or "").strip().lower() not in ("contado", "credito"):
        return "medio_pago"
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
    string JSON o None) a una lista de dicts estándar.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            return []
    return []

