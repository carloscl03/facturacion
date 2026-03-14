from __future__ import annotations

from typing import Any, Dict


def obtener_estado(registro: Dict[str, Any] | None) -> int:
    """
    Lee el campo de estado de un registro de cache.

    Soporta tanto 'estado' como 'paso_actual' por compatibilidad.
    Devuelve 0 si no hay registro o si el valor no es convertible a int.
    """
    if not registro:
        return 0
    try:
        v = registro.get("estado") or registro.get("paso_actual")
        if v is None or v == "":
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def opciones_completas(registro: Dict[str, Any] | None) -> bool:
    """
    True si las opciones de estado 2 están completas:
    - id_sucursal
    - forma_pago no vacía
    medio_pago (contado/crédito) se pregunta en analizar, no en opciones.
    """
    if not registro:
        return False
    has_suc = bool(registro.get("id_sucursal"))
    has_fp = bool((registro.get("forma_pago") or "").strip())
    return has_suc and has_fp


def operacion_normalizada(origen: str | None) -> str | None:
    """
    Normaliza una operación textual a 'venta' o 'compra'.

    Acepta variantes como 'ventas'/'compras' y strings con mayúsculas/minúsculas.
    Devuelve None si no se puede determinar.
    """
    if not origen:
        return None
    op = origen.strip().lower()
    if op == "ventas":
        return "venta"
    if op == "compras":
        return "compra"
    if op in ("venta", "compra"):
        return op
    return None


def operacion_desde_registro(registro: Dict[str, Any] | None) -> str | None:
    """
    Obtiene la operación normalizada ('venta'/'compra') desde un registro,
    leyendo primero 'operacion' y luego 'cod_ope' por compatibilidad.
    """
    if not registro:
        return None
    raw = (
        registro.get("operacion")
        or registro.get("cod_ope")
        or ""
    )
    return operacion_normalizada(str(raw) if raw is not None else None)


def calcular_estado(datos: Dict[str, Any]) -> int:
    """
    Calcula el estado (0-3) de un registro intermedio en función de:
    - operacion (venta/compra)
    - monto/productos
    - entidad
    - tipo_documento
    - moneda
    - medio_pago (contado/credito); si credito, también dias_credito y nro_cuotas.

    Equivalente a la lógica usada en ExtraccionService._calcular_estado.
    """
    op = (datos.get("operacion") or "").strip().lower()
    if op not in ("venta", "compra"):
        return 0

    tiene_monto = float(datos.get("monto_total") or 0) > 0
    tiene_productos = False
    prod = datos.get("productos")
    if isinstance(prod, list) and len(prod) > 0:
        tiene_productos = True
    elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        tiene_productos = True

    tiene_entidad = bool(datos.get("entidad_nombre")) or bool(datos.get("entidad_id"))
    tiene_documento = bool(datos.get("tipo_documento"))
    tiene_moneda = bool(datos.get("moneda"))

    medio = (datos.get("medio_pago") or "").strip().lower()
    tiene_medio_pago = medio in ("contado", "credito")
    tiene_credito_completo = True
    if medio == "credito":
        dc = datos.get("dias_credito")
        nc = datos.get("nro_cuotas")
        tiene_credito_completo = dc is not None and nc is not None and str(dc).strip() != "" and str(nc).strip() != ""

    obligatorios = [
        tiene_monto or tiene_productos,
        tiene_entidad,
        tiene_documento,
        tiene_moneda,
        tiene_medio_pago and (tiene_credito_completo if medio == "credito" else True),
    ]
    if all(obligatorios):
        return 3
    if any(obligatorios):
        return 2
    return 1

