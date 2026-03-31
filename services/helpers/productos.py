from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def normalizar_productos_raw(productos_raw: Any) -> List[Dict[str, Any]]:
    """
    Normaliza una representación de productos que puede venir como:
    - lista de dicts
    - string JSON
    - string libre (ej: "1 x laptop", "laptop")

    a una lista de dicts. Si no se puede parsear como JSON, intenta
    extraer nombre y cantidad del texto libre.
    """
    if isinstance(productos_raw, list):
        return [p for p in productos_raw if isinstance(p, dict)]
    if isinstance(productos_raw, str):
        s = productos_raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, dict)]
        except Exception:
            pass
        # Texto libre: intentar extraer "cantidad x nombre" o solo "nombre"
        return _parsear_texto_libre_productos(s)
    return []


def _parsear_texto_libre_productos(texto: str) -> List[Dict[str, Any]]:
    """Parsea texto libre como '2 x laptop' o 'laptop, monitor' a lista de dicts."""
    import re
    productos: List[Dict[str, Any]] = []
    # Separar por comas o saltos de línea
    partes = re.split(r"[,\n]+", texto)
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        # Intentar "N x nombre" o "N nombre"
        m = re.match(r"^(\d+(?:\.\d+)?)\s*[xX×]\s*(.+)$", parte)
        if m:
            productos.append({"cantidad": float(m.group(1)), "nombre": m.group(2).strip()})
            continue
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(.+)$", parte)
        if m:
            productos.append({"cantidad": float(m.group(1)), "nombre": m.group(2).strip()})
            continue
        # Solo nombre
        productos.append({"cantidad": 1, "nombre": parte})
    return productos


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
        precio = c.get("precio_unitario", 0)
        stock = c.get("stock_total", 0)
        # Title: nombre + precio (lo que recibe el bot al seleccionar)
        titulo_raw = f"{nombre} S/{precio:.2f}" if precio else nombre
        titulo = titulo_raw[:MAX_ROW_TITLE] if len(titulo_raw) > MAX_ROW_TITLE else titulo_raw
        # Description: solo stock (info secundaria)
        desc = f"Stock: {int(stock)}" if stock else ""
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
    sin_igv = tipo_doc in ("nota de venta", "nota de compra", "recibo por honorarios")
    if not productos:
        mt = float(monto_total)
        if sin_igv:
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
        if sin_igv:
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

