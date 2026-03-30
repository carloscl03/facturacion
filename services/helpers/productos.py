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


MAX_ROW_TITLE = 24


def enriquecer_producto_con_catalogo(producto: Dict[str, Any], catalogo_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriquece un producto extraído por la IA con datos del catálogo.
    Si el usuario dio precio explícito, se respeta; si no, se usa el del catálogo.
    """
    enriched = {**producto}
    enriched["id_catalogo"] = catalogo_item["id_catalogo"]
    enriched["id_unidad"] = catalogo_item.get("id_unidad_medida", 1)
    enriched["sku"] = catalogo_item.get("sku", "")
    enriched["nombre"] = catalogo_item.get("nombre") or producto.get("nombre", "")
    # Precio: respetar el del usuario si lo indicó; si no, usar catálogo
    precio_usuario = float(producto.get("precio_unitario") or producto.get("precio") or 0)
    if precio_usuario > 0:
        enriched["precio_unitario"] = precio_usuario
    else:
        enriched["precio_unitario"] = catalogo_item.get("precio_unitario", 0)
    # Recalcular total_item
    qty = float(enriched.get("cantidad", 1))
    enriched["total_item"] = round(qty * enriched["precio_unitario"], 2)
    return enriched


def catalogo_a_filas_whatsapp(candidatos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Convierte candidatos de catálogo en filas para WhatsApp list message."""
    filas: List[Dict[str, str]] = []
    for c in candidatos:
        nombre = (c.get("nombre") or "").strip()
        titulo = nombre[:MAX_ROW_TITLE] if len(nombre) > MAX_ROW_TITLE else nombre
        precio = c.get("precio_unitario", 0)
        stock = c.get("stock_total", 0)
        desc = f"S/ {precio:.2f}" if precio else ""
        if stock:
            desc += f" | Stock: {int(stock)}" if desc else f"Stock: {int(stock)}"
        filas.append({
            "id": str(c.get("id_catalogo", "0")),
            "title": titulo,
            "description": desc,
        })
    return filas


def build_payload_lista_productos(
    id_empresa: int,
    phone: str,
    id_plataforma: int,
    candidatos: List[Dict[str, Any]],
    nombre_buscado: str,
) -> Dict[str, Any]:
    """Construye el payload para ws_send_whatsapp_list con candidatos de catálogo."""
    filas = catalogo_a_filas_whatsapp(candidatos)
    return {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": f"Encontré {len(candidatos)} productos para \"{nombre_buscado}\". ¿Cuál es?",
        "button_text": "Ver productos",
        "header_text": "Selecciona el producto",
        "footer_text": "Elige una opción",
        "sections": [{"title": "Productos", "rows": filas}],
    }


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
    tipo_doc = str(reg.get("tipo_documento") or "").strip().lower()
    es_nota = tipo_doc in ("nota de venta", "nota de compra")
    if not productos:
        mt = float(monto_total)
        if es_nota:
            mb = float(monto_base or mt)
            mi = 0.0
        else:
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
        if es_nota:
            subtotal = total_item
            igv = 0.0
        else:
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

