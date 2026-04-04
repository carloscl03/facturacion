"""
Mapper para el payload de registro de compras (ws_compra.php).

Construye el JSON REGISTRAR_COMPRA: codOpe, empresa_id, usuario_id, id_proveedor,
fecha_emision, nro_documento (SERIE-NUMERO opcional), detalles.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from services.helpers.productos import normalizar_productos_raw
from services.helpers.venta_mapper import nro_documento_comprobante


def _safe_int(val, default=None):
    """Convierte a int de forma segura. Devuelve default si no se puede."""
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def construir_detalles_compra(
    reg: Dict[str, Any],
    monto_total: float,
    monto_base: float,
    monto_igv: float,
    id_unidad_default: int = 1,
) -> List[Dict[str, Any]]:
    """
    Construye la lista 'detalles' para el payload de compra (API ws_compra.php)
    a partir de los productos del registro y montos agregados.

    Usa el módulo igv.py para cálculos consistentes con Decimal.
    Respeta el flag igv_incluido del registro.
    """
    from services.helpers.igv import calcular_igv, calcular_item, es_tipo_sin_igv

    productos = normalizar_productos_raw(reg.get("productos"))
    id_unidad = reg.get("id_unidad", id_unidad_default)
    tipo_doc = str(reg.get("tipo_documento") or "").strip().lower()
    sin_igv = es_tipo_sin_igv(tipo_doc)

    # Leer flag igv_incluido del registro (default True)
    igv_incluido_raw = reg.get("igv_incluido")
    if igv_incluido_raw is None:
        igv_incluido = True
    else:
        igv_incluido = igv_incluido_raw is True or str(igv_incluido_raw).strip().lower() == "true"

    if not productos:
        mt = float(monto_total)
        mt_calc, mb_calc, mi_calc = calcular_igv(
            mt, igv_incluido=True, sin_igv=sin_igv,
        )
        mb_final = float(monto_base) if monto_base > 0 else mb_calc
        mi_final = float(monto_igv) if monto_igv > 0 else mi_calc
        return [
            {
                "id_inventario": reg.get("id_inventario"),
                "id_catalogo": reg.get("id_catalogo"),
                "id_tipo_producto": reg.get("id_tipo_producto", 1),
                "cantidad": 1,
                "id_unidad": id_unidad,
                "precio_unitario": round(mt, 2),
                "concepto": str(reg.get("observacion") or "Compra").strip() or "Item compra",
                "valor_subtotal_item": round(mb_final, 2),
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": round(mi_final, 2),
                "valor_icbper": 0,
                "valor_total_item": round(mt, 2),
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ]

    detalles: List[Dict[str, Any]] = []
    for p in productos:
        qty = float(p.get("cantidad", 1))
        pu = float(p.get("precio_unitario") or p.get("precio", 0))
        item_vals = calcular_item(
            pu, qty, igv_incluido=igv_incluido, sin_igv=sin_igv,
        )
        concepto = str(p.get("nombre") or p.get("concepto") or "Item").strip() or "Producto"
        detalles.append(
            {
                "id_inventario": p.get("id_inventario") or reg.get("id_inventario"),
                "id_catalogo": p.get("id_catalogo") or reg.get("id_catalogo"),
                "id_tipo_producto": p.get("id_tipo_producto", reg.get("id_tipo_producto", 1)),
                "cantidad": qty,
                "id_unidad": p.get("id_unidad", id_unidad),
                "precio_unitario": item_vals["precio_unitario"],
                "concepto": concepto,
                "valor_subtotal_item": item_vals["valor_subtotal_item"],
                "porcentaje_descuento": float(p.get("porcentaje_descuento", 0)),
                "valor_descuento": float(p.get("valor_descuento", 0)),
                "valor_isc": 0,
                "valor_igv": item_vals["valor_igv"],
                "valor_icbper": 0,
                "valor_total_item": item_vals["valor_total_item"],
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        )
    return detalles


def construir_payload_compra(
    reg: Dict[str, Any],
    params: Dict[str, Any],
    id_from: int,
    id_usuario: int = 3,
) -> Dict[str, Any]:
    """
    Construye el payload completo REGISTRAR_COMPRA para ws_compra.php
    a partir del registro y los parámetros ya traducidos (venta_mapper).
    """
    detalles = construir_detalles_compra(
        reg,
        params["monto_total"],
        params["monto_base"],
        params["monto_igv"],
    )

    tipo_compra_raw = (params.get("tipo_venta") or "Contado").strip()
    tipo_compra = "Crédito" if tipo_compra_raw.lower() == "credito" else "Contado"
    dias_credito_raw = reg.get("dias_credito") or reg.get("dias_credito", "")
    try:
        dias_credito = int(dias_credito_raw) if str(dias_credito_raw).strip() else 30
    except (ValueError, TypeError):
        dias_credito = 30
    cuotas_raw = reg.get("nro_cuotas") or reg.get("cuotas") or ""
    try:
        cuotas = int(cuotas_raw) if str(cuotas_raw).strip() else 1
    except (ValueError, TypeError):
        cuotas = 1
    # Número del comprobante: solo enviar si es SERIE-NUMERO válido (ws_compra exige formato "F001-00001").
    # Si no hay comprobante, no enviar la clave para que la API deje serie/numero en null.
    nro_raw = nro_documento_comprobante(reg)
    nro_documento = None
    if nro_raw and isinstance(nro_raw, str):
        nro_raw = nro_raw.strip()
        if nro_raw and "-" in nro_raw and len(nro_raw.split("-")) == 2 and nro_raw.upper() != "S/N":
            nro_documento = nro_raw

    id_proveedor = _safe_int(reg.get("entidad_id"))
    id_forma_pago = _safe_int(params.get("id_forma_pago"))
    id_medio_pago = _safe_int(reg.get("id_medio_pago"))
    id_sucursal = _safe_int(reg.get("id_sucursal"))
    payload: Dict[str, Any] = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": int(id_from),
        "usuario_id": int(id_usuario),
        "id_proveedor": id_proveedor,
        "id_tipo_comprobante": _safe_int(params.get("id_tipo_comprobante"), 1),
        "fecha_emision": params["fecha_emision"],
        "id_medio_pago": id_medio_pago,
        "id_forma_pago": id_forma_pago,
        "id_moneda": _safe_int(params.get("id_moneda"), 1),
        "id_sucursal": id_sucursal,
        "tipo_compra": tipo_compra,
        "dias_credito": dias_credito,
        "cuotas": cuotas,
        "porcentaje_detraccion": float(reg.get("porcentaje_detraccion") or 0),
        "fecha_pago": params["fecha_pago"],
        "fecha_vencimiento": params.get("fecha_vencimiento") or params["fecha_pago"],
        "enlace_documento": str(reg.get("url") or reg.get("enlace_documento") or "").strip() or None,
        "id_tipo_afectacion": _safe_int(reg.get("id_tipo_afectacion")),
        "observacion": str(reg.get("observacion") or "").strip() or None,
        "id_caja_banco": _safe_int(reg.get("id_caja_banco")),
        "id_centro_costo": _safe_int(reg.get("id_centro_costo")),
        "id_tipo_compra_gasto": _safe_int(reg.get("id_tipo_compra_gasto")),
        "detalles": detalles,
    }
    if payload["enlace_documento"] is None:
        payload.pop("enlace_documento", None)
    if payload["observacion"] is None:
        payload.pop("observacion", None)
    # Quitar opcionales null para que el PHP los trate como no enviados (acepta null en bind)
    for key in ("id_forma_pago", "id_medio_pago", "id_sucursal", "id_tipo_afectacion", "id_caja_banco", "id_centro_costo", "id_tipo_compra_gasto"):
        if payload.get(key) is None:
            payload.pop(key, None)
    if nro_documento is not None:
        payload["nro_documento"] = nro_documento
    return payload
