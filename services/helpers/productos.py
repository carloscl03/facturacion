from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def normalizar_productos_raw(productos_raw: Any) -> List[Dict[str, Any]]:
    """
    Normaliza una representación de productos que puede venir como:
    - lista de dicts
    - string JSON
    - string libre

    a una lista de dicts. Si no se puede parsear, devuelve lista vacía.
    """
    if isinstance(productos_raw, list):
        return [p for p in productos_raw if isinstance(p, dict)]
    if isinstance(productos_raw, str):
        s = productos_raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return [p for p in parsed] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def productos_a_str(productos: Any) -> str:
    """
    Convierte productos (lista o string) a una representación de texto estable,
    preferentemente JSON, lista para ser almacenada en cache/BD.
    """
    if isinstance(productos, str):
        return productos
    if isinstance(productos, list):
        try:
            return json.dumps(productos, ensure_ascii=False)
        except Exception:
            return "[]"
    return "[]"


def construir_detalle_desde_registro(
    reg: Dict[str, Any],
    monto_total: float,
    monto_base: float,
    monto_igv: float,
    id_unidad_default: int = 1,
) -> List[Dict[str, Any]]:
    """
    Construye la lista de 'detalle_items' para el payload de venta
    a partir de los productos del registro y los montos agregados.

    Replica la lógica de FinalizarService._construir_detalle.
    """
    productos: List[Dict[str, Any]] = []
    try:
        pj = reg.get("productos")
        if isinstance(pj, str):
            productos = json.loads(pj) if pj.strip() else []
        elif isinstance(pj, list):
            productos = pj
    except Exception:
        productos = []

    id_unidad = reg.get("id_unidad", id_unidad_default)
    if not productos:
        mt = float(monto_total)
        mb = float(monto_base or mt / 1.18)
        mi = float(monto_igv or mt - mb)
        # Sin catálogo ni inventario (como en test_pdf_sunat): la API acepta null y funciona con normalidad.
        return [
            {
                "id_inventario": reg.get("id_inventario"),
                "id_catalogo": reg.get("id_catalogo"),
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": id_unidad,
                "precio_unitario": mt,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_subtotal_item": round(mb, 2),
                "valor_igv": round(mi, 2),
                "valor_total_item": mt,
            }
        ]

    detalle = []
    for p in productos:
        qty = float(p.get("cantidad", 1))
        pu = float(p.get("precio_unitario") or p.get("precio", 0))
        total_item = float(p.get("total_item", qty * pu))
        subtotal = total_item / 1.18
        igv = total_item - subtotal
        detalle.append(
            {
                "id_inventario": p.get("id_inventario") or reg.get("id_inventario"),
                "id_catalogo": p.get("id_catalogo") or reg.get("id_catalogo"),
                "id_tipo_producto": p.get("id_tipo_producto", 2),
                "cantidad": qty,
                "id_unidad": p.get("id_unidad", id_unidad),
                "precio_unitario": pu,
                "porcentaje_descuento": float(p.get("porcentaje_descuento", 0)),
                "valor_descuento": float(p.get("valor_descuento", 0)),
                "valor_subtotal_item": round(subtotal, 2),
                "valor_igv": round(igv, 2),
                "valor_total_item": round(total_item, 2),
            }
        )
    return detalle

