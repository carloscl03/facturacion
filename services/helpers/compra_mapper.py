"""
Mapper para el payload de registro de compras (API ws_compra.php).

Construye el JSON REGISTRAR_COMPRA a partir del registro de caché y parámetros
traducidos, alineado con la estructura probada en test_registro.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from services.helpers.productos import normalizar_productos_raw
from services.helpers.venta_mapper import nro_documento_comprobante


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
    Formato esperado por la API: concepto, valor_subtotal_item, valor_igv, valor_total_item, etc.
    """
    productos = normalizar_productos_raw(reg.get("productos"))
    id_unidad = reg.get("id_unidad", id_unidad_default)

    if not productos:
        mt = float(monto_total)
        mb = float(monto_base or mt / 1.18)
        mi = float(monto_igv or mt - mb)
        return [
            {
                "id_inventario": None,
                "id_catalogo": reg.get("id_catalogo", 10),
                "id_tipo_producto": reg.get("id_tipo_producto", 1),
                "cantidad": 1,
                "id_unidad": id_unidad,
                "precio_unitario": round(mt, 2),
                "concepto": str(reg.get("observacion") or "Compra").strip() or "Item compra",
                "valor_subtotal_item": round(mb, 2),
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": round(mi, 2),
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
        total_item = float(p.get("total_item", qty * pu))
        subtotal = total_item / 1.18
        igv = total_item - subtotal
        concepto = str(p.get("nombre") or p.get("concepto") or "Item").strip() or "Producto"
        detalles.append(
            {
                "id_inventario": p.get("id_inventario"),
                "id_catalogo": p.get("id_catalogo", reg.get("id_catalogo", 10)),
                "id_tipo_producto": p.get("id_tipo_producto", reg.get("id_tipo_producto", 1)),
                "cantidad": qty,
                "id_unidad": p.get("id_unidad", id_unidad),
                "precio_unitario": round(pu, 2),
                "concepto": concepto,
                "valor_subtotal_item": round(subtotal, 2),
                "porcentaje_descuento": float(p.get("porcentaje_descuento", 0)),
                "valor_descuento": float(p.get("valor_descuento", 0)),
                "valor_isc": 0,
                "valor_igv": round(igv, 2),
                "valor_icbper": 0,
                "valor_total_item": round(total_item, 2),
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

    tipo_compra = (params.get("tipo_venta") or "Contado").strip()
    dias_credito = int(reg.get("dias_credito", 30))
    cuotas = int(reg.get("cuotas", 1))
    # Número del comprobante (factura/boleta del proveedor): solo serie-número, nunca RUC/DNI del proveedor
    nro_documento = nro_documento_comprobante(reg) or "S/N"

    id_proveedor = reg.get("entidad_id")
    if id_proveedor is not None:
        id_proveedor = int(id_proveedor)
    id_forma_pago = params.get("id_forma_pago")
    if id_forma_pago is not None:
        id_forma_pago = int(id_forma_pago)
    else:
        id_forma_pago = 1
    payload: Dict[str, Any] = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": int(id_from),
        "usuario_id": int(id_usuario),
        "id_proveedor": id_proveedor,
        "id_tipo_comprobante": int(params["id_tipo_comprobante"]) if params.get("id_tipo_comprobante") is not None else 1,
        "fecha_emision": params["fecha_emision"],
        "nro_documento": nro_documento or "S/N",
        "id_medio_pago": int(reg.get("id_medio_pago") or 1),
        "id_forma_pago": id_forma_pago,
        "id_moneda": int(params["id_moneda"]) if params.get("id_moneda") is not None else 1,
        "id_sucursal": int(reg.get("id_sucursal") or 1),
        "tipo_compra": tipo_compra,
        "dias_credito": dias_credito,
        "cuotas": cuotas,
        "porcentaje_detraccion": float(reg.get("porcentaje_detraccion", 0)),
        "fecha_pago": params["fecha_pago"],
        "fecha_vencimiento": params.get("fecha_vencimiento") or params["fecha_pago"],
        "enlace_documento": str(reg.get("enlace_documento") or "").strip() or None,
        "id_tipo_afectacion": int(reg.get("id_tipo_afectacion", 1)),
        "observacion": str(reg.get("observacion") or "").strip() or None,
        "id_caja_banco": int(reg.get("id_caja_banco") or 1),
        "id_centro_costo": int(reg.get("id_centro_costo") or 1),
        "id_tipo_compra_gasto": int(reg.get("id_tipo_compra_gasto") or 1),
        "detalles": detalles,
    }
    if payload["enlace_documento"] is None:
        payload.pop("enlace_documento", None)
    if payload["observacion"] is None:
        payload.pop("observacion", None)
    return payload
