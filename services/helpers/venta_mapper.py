from __future__ import annotations

from typing import Any, Dict, Tuple

from services.helpers.fechas import fecha_ddmmyyyy_a_api
from services.helpers.productos import construir_detalle_desde_registro
from services.helpers.registro_domain import operacion_desde_registro


TIPO_DOCUMENTO_MAP = {
    "factura": 1,
    "boleta": 2,
    "recibo": 3,
    "nota de venta": 4,
}

MONEDA_MAP = {
    "PEN": 1,
    "pen": 1,
    "USD": 2,
    "usd": 2,
}

MONEDA_SIMBOLO = {
    "PEN": "S/",
    "pen": "S/",
    "USD": "$",
    "usd": "$",
}

FORMA_PAGO_MAP = {
    "transferencia": 1,
    "td": 2,
    "tc": 3,
    "billetera_virtual": 4,
    "yape": 4,
    "plin": 4,
}


def construir_sintesis_actual(reg: Dict[str, Any]) -> str:
    """
    Construye un resumen visual del estado actual del registro
    para mostrarlo al usuario en mensajes de WhatsApp.
    Extraído desde FinalizarService para reutilizarlo donde sea necesario.
    """
    if not reg or not isinstance(reg, dict):
        return ""
    lineas = ["📋 *Estado actual del registro*", "━━━━━━━━━━━━━━━━━━━━"]
    op = str(reg.get("operacion") or reg.get("cod_ope") or "").strip().lower()
    operacion = "venta" if op == "ventas" else "compra" if op == "compras" else op
    if operacion == "venta":
        lineas.append("📤 *VENTA*")
    elif operacion == "compra":
        lineas.append("🛒 *COMPRA*")

    tipo_doc = str(reg.get("tipo_documento") or "").strip()
    if tipo_doc:
        lineas.append(f"📄 *Comprobante:* {tipo_doc.capitalize()}")

    num_doc = str(reg.get("numero_documento") or "").strip()
    if num_doc:
        lineas.append(f"📄 *Nro:* {num_doc}")

    if str(reg.get("entidad_nombre") or "").strip():
        lineas.append(f"👤 *Cliente/Proveedor:* {reg.get('entidad_nombre')}")
    if str(reg.get("entidad_numero") or "").strip():
        lineas.append(f"🆔 *Documento:* {reg.get('entidad_numero')}")

    monto = float(reg.get("monto_total") or 0)
    if monto > 0:
        moneda = str(reg.get("moneda") or "PEN").upper()
        simbolo = MONEDA_SIMBOLO.get(moneda, "S/")
        lineas.append(f"💰 *Total:* {simbolo} {monto}")

    prod = reg.get("productos")
    if isinstance(prod, list) and prod:
        items = ", ".join(
            f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]
        )
        lineas.append(f"📦 *Productos:* {items}")
    elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        lineas.append("📦 *Productos:* (con detalle)")

    if str(reg.get("sucursal") or "").strip():
        lineas.append(f"📍 *Sucursal:* {reg.get('sucursal')}")
    elif reg.get("id_sucursal"):
        lineas.append(f"📍 *Sucursal:* (id {reg.get('id_sucursal')})")

    medio = str(reg.get("medio_pago") or "").strip().lower()
    if medio in ("contado", "credito"):
        lineas.append(f"💳 *Medio de pago:* {medio.capitalize()}")

    moneda_str = str(reg.get("moneda") or "").strip()
    if moneda_str:
        lineas.append(f"💵 *Moneda:* {moneda_str}")
    if str(reg.get("fecha_emision") or "").strip():
        lineas.append(f"📅 *Emisión:* {reg.get('fecha_emision')}")
    forma_pago_val = str(reg.get("forma_pago") or "").strip()
    if forma_pago_val:
        lineas.append(f"🏦 *Forma de pago:* {forma_pago_val}")

    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lineas)


def traducir_registro_a_parametros(reg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Traduce un registro de cache a los parámetros básicos necesarios
    para construir el payload de venta/compra.

    Devuelve (operacion_normalizada, dict_parametros).
    """
    operacion = operacion_desde_registro(reg) or ""
    tipo_doc_str = str(reg.get("tipo_documento") or "").strip().lower()
    id_tipo_comprobante = TIPO_DOCUMENTO_MAP.get(tipo_doc_str)

    moneda_str = str(reg.get("moneda") or "").strip()
    id_moneda = MONEDA_MAP.get(moneda_str)
    moneda_simbolo = MONEDA_SIMBOLO.get(moneda_str, "S/")

    medio_pago = str(reg.get("medio_pago") or "").strip().lower()
    tipo_venta = medio_pago.capitalize() if medio_pago in ("contado", "credito") else None

    # Preferir id ya guardado (p. ej. desde opciones Estado 2); si no, mapear por nombre.
    id_forma_pago = None
    if reg.get("id_metodo_pago") is not None:
        try:
            id_forma_pago = int(reg.get("id_metodo_pago"))
        except (TypeError, ValueError):
            pass
    if id_forma_pago is None:
        forma_pago_str = str(reg.get("forma_pago") or "").strip().lower()
        try:
            id_forma_pago = int(forma_pago_str)
        except (TypeError, ValueError):
            id_forma_pago = FORMA_PAGO_MAP.get(forma_pago_str, 9)

    monto_total = float(reg.get("monto_total") or 0)
    monto_base = float(reg.get("monto_sin_igv") or 0)
    monto_igv = float(reg.get("igv") or 0)

    entidad_numero = str(reg.get("entidad_numero") or "").strip()
    id_tipo_doc_entidad = 6 if len(entidad_numero) == 11 else 1

    id_cliente = reg.get("entidad_id")

    fecha_emision = fecha_ddmmyyyy_a_api(reg.get("fecha_emision")) or "2026-03-03"
    fecha_pago = fecha_ddmmyyyy_a_api(reg.get("fecha_pago")) or fecha_emision
    fecha_vencimiento = fecha_ddmmyyyy_a_api(reg.get("fecha_vencimiento")) or fecha_pago

    return operacion, {
        "id_tipo_comprobante": id_tipo_comprobante,
        "id_moneda": id_moneda,
        "moneda_simbolo": moneda_simbolo,
        "tipo_venta": tipo_venta,
        "id_forma_pago": id_forma_pago,
        "monto_total": monto_total,
        "monto_base": monto_base,
        "monto_igv": monto_igv,
        "entidad_numero": entidad_numero,
        "id_tipo_doc_entidad": id_tipo_doc_entidad,
        "id_cliente": id_cliente,
        "fecha_emision": fecha_emision,
        "fecha_pago": fecha_pago,
        "fecha_vencimiento": fecha_vencimiento,
    }


def construir_payload_venta(
    reg: Dict[str, Any],
    id_cliente,
    id_from: int,
    id_tipo_comprobante,
    monto_total,
    monto_base,
    monto_igv,
    moneda_simbolo: str,
    id_moneda,
    id_forma_pago,
    tipo_venta,
    fecha_emision: str,
    fecha_pago: str,
    id_usuario: int = 3,
) -> Dict[str, Any]:
    """
    Construye el payload completo CREAR_VENTA para la API externa
    a partir del registro y de los parámetros ya traducidos.
    """
    detalle_items = construir_detalle_desde_registro(reg, monto_total, monto_base, monto_igv)
    payload = {
        "codOpe": "CREAR_VENTA",
        "id_usuario": id_usuario,
        "id_cliente": id_cliente,
        "id_sucursal": reg.get("id_sucursal") or 14,
        "id_moneda": id_moneda,
        "id_forma_pago": id_forma_pago,
        "id_medio_pago": reg.get("id_medio_pago"),
        "tipo_venta": tipo_venta or "Contado",
        "fecha_emision": fecha_emision,
        "fecha_pago": fecha_pago,
        "id_tipo_afectacion": reg.get("id_tipo_afectacion", 1),
        "id_caja_banco": reg.get("id_caja_banco", 4),
        "tipo_facturacion": "facturacion_electronica",
        "id_tipo_comprobante": id_tipo_comprobante,
        "serie": reg.get("serie"),
        "numero": reg.get("numero"),
        "observaciones": str(reg.get("observaciones") or "").strip() or None,
        "detalle_items": detalle_items,
    }
    if payload["observaciones"] is None:
        payload.pop("observaciones", None)
    return payload

