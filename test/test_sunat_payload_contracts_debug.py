"""
Debug para validar contratos de payload con los PHP de N8N.

Incluye 2 validaciones:
- Ventas: usa `services/helpers/venta_mapper.py` (REGISTRAR_VENTA_N8N) y compara con
  `test/test_pdf_sunat.py` + `php/ventan8n.txt`.
- Compras: usa `services/helpers/compra_mapper.py` (REGISTRAR_COMPRA) y compara con
  `test/test_registro.py` + `php/compras.txt`.

Este script NO hace asserts duros: si falta algún campo o hay diferencias,
imprime un reporte para que revises manualmente.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import date
from typing import Any

# Asegurar importaciones desde la raíz del proyecto
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.helpers.compra_mapper import construir_payload_compra
from services.helpers.venta_mapper import construir_payload_venta_n8n

def _build_expected_venta_like_test_pdf_sunat() -> dict:
    """
    Replica PAYLOAD_REGISTRAR_VENTA_N8N de `test/test_pdf_sunat.py` (sin importar el módulo).
    Así evitamos dependencias de `config/settings.py` (dotenv) en este entorno.
    """
    fecha_emision = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()
    return {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": 2,
        "usuario_id": 3,
        "id_cliente": 5,
        "id_tipo_comprobante": 1,
        "fecha_emision": fecha_emision,
        "fecha_pago": fecha_emision,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Prueba Factura Postman",
        "generacion_comprobante": 1,
        "detalle_items": [
            {
                "id_inventario": None,
                "id_catalogo": None,
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 1111.00,
                "valor_subtotal_item": 941.53,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 169.47,
                "valor_icbper": 0,
                "valor_total_item": 1111.00,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }


def _pretty(d: Any) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False, sort_keys=True, default=str)


def _compare_payloads(label: str, actual: dict, expected: dict) -> None:
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)

    actual_keys = set(actual.keys())
    expected_keys = set(expected.keys())
    extra = sorted(actual_keys - expected_keys)
    faltan = sorted(expected_keys - actual_keys)

    print("Claves esperadas:", len(expected_keys))
    print("Claves actuales:  ", len(actual_keys))
    if faltan:
        print("FALTAN (en actual):", faltan)
    if extra:
        print("EXTRA (en actual):  ", extra)

    claves_criticas = [
        "codOpe",
        "empresa_id",
        "usuario_id",
        "id_cliente",
        "id_proveedor",
        "id_tipo_comprobante",
        "id_moneda",
        "id_forma_pago",
        "id_medio_pago",
        "id_sucursal",
        "tipo_venta",
        "tipo_compra",
        "generacion_comprobante",
        "fecha_emision",
        "fecha_pago",
        "fecha_vencimiento",
        "nro_documento",
    ]
    for k in claves_criticas:
        if k in expected or k in actual:
            av = actual.get(k)
            ev = expected.get(k)
            if av != ev:
                print(f"- {k}: actual={av!r} | esperado={ev!r}")

    # Comparar a nivel de detalle: claves del primer ítem
    if "detalle_items" in expected or "detalles" in expected:
        a_items = actual.get("detalle_items") or actual.get("detalles") or []
        e_items = expected.get("detalle_items") or expected.get("detalles") or []
        if isinstance(a_items, list) and a_items and isinstance(e_items, list) and e_items:
            ak = set(a_items[0].keys())
            ek = set(e_items[0].keys())
            extra_i = sorted(ak - ek)
            faltan_i = sorted(ek - ak)
            if faltan_i:
                print("Detalle: faltan claves esperadas:", faltan_i)
            if extra_i:
                print("Detalle: claves extra en actual:  ", extra_i)


def _iso_to_ddmmyyyy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def _build_reg_venta_like_test() -> tuple[dict, dict, dict]:
    """
    Construye reg+params para generar un payload similar al de `PAYLOAD_REGISTRAR_VENTA_N8N`.
    Nota: el contrato PHP acepta `detalle_items` con más campos de los que trae el test,
    por eso aquí hacemos comparación superficial.
    """
    # Seguir la misma fecha del test
    fecha_iso = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()

    params = {
        "id_tipo_comprobante": 1,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "monto_total": 1111.00,
        "monto_base": 941.53,
        "monto_igv": 169.47,
        "moneda_simbolo": "S/",
        "tipo_venta": "Contado",
        "fecha_emision": fecha_iso,
        "fecha_pago": fecha_iso,
        "fecha_vencimiento": fecha_iso,
    }

    reg = {
        "operacion": "venta",
        "tipo_documento": "factura",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "id_sucursal": 14,
        "id_unidad": 1,
        "id_inventario": None,
        "id_catalogo": None,
        "id_medio_pago": None,  # importante: el contrato considera id_medio_pago opcional (null)
        "observaciones": "Prueba Factura Postman",
        # Montos usados por construir_detalle_desde_registro cuando no hay productos
        "monto_total": 1111.00,
        "monto_sin_igv": 941.53,
        "igv": 169.47,
        "productos": [],  # fuerza detalle "sin catálogo/inventario" como en el test
    }

    extra = {"id_cliente": 5}
    return reg, params, extra


def _build_reg_compra_like_test() -> tuple[dict, dict, dict]:
    """
    Construye reg+params para generar un payload similar al de `test/test_registro.py`.
    """
    reg = {
        "operacion": "compra",
        "tipo_documento": "factura",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "entidad_id": 5,  # id_proveedor
        "numero_documento": "F001-00001",
        "id_sucursal": 1,
        "id_centro_costo": 1,
        "id_tipo_afectacion": 1,
        "id_caja_banco": 1,
        "id_tipo_compra_gasto": 1,
        "id_forma_pago": 1,
        "id_medio_pago": 1,
        "dias_credito": 30,
        "cuotas": 3,
        "porcentaje_detraccion": 0,
        "fecha_emision": _iso_to_ddmmyyyy("2025-10-31"),
        "fecha_pago": _iso_to_ddmmyyyy("2025-11-15"),
        "fecha_vencimiento": _iso_to_ddmmyyyy("2025-11-30"),
        "enlace_documento": "https://storage.maravia.pe/compras/doc123.pdf",
        "observacion": "Compra de productos para stock",
        # Montos
        "monto_total": 590.0,
        "monto_sin_igv": 500.0,
        "igv": 90.0,
        # Productos: para que la construcción genere los mismos valores que el test
        "productos": [
            {
                "nombre": "Producto X",
                "cantidad": 5,
                "precio_unitario": 100,
                "total_item": 590,
                "id_tipo_producto": 1,
                "id_unidad": 1,
                "id_catalogo": 10,
                "id_inventario": None,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
            }
        ],
    }

    params = {
        "id_tipo_comprobante": 1,
        "id_moneda": 1,
        "id_forma_pago": 1,
        "monto_total": 590.0,
        "monto_base": 500.0,
        "monto_igv": 90.0,
        "moneda_simbolo": "S/",
        "tipo_venta": "Contado",
        "fecha_emision": "2025-10-31",
        "fecha_pago": "2025-11-15",
        "fecha_vencimiento": "2025-11-30",
    }

    extra = {"id_from": 2}
    return reg, params, extra


def main() -> None:
    # -------------------- VENTAS --------------------
    expected_venta = _build_expected_venta_like_test_pdf_sunat()
    reg_v, params_v, extra_v = _build_reg_venta_like_test()
    actual_venta = construir_payload_venta_n8n(
        reg=reg_v,
        id_cliente=int(extra_v["id_cliente"]),
        id_empresa=int(expected_venta["empresa_id"]),
        id_usuario=int(expected_venta["usuario_id"]),
        params=params_v,
    )

    _compare_payloads("VENTAS - Payload REGISTRAR_VENTA_N8N", actual_venta, expected_venta)

    # -------------------- COMPRAS --------------------
    expected_compra = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": 2,
        "usuario_id": 3,
        "id_proveedor": 5,
        "id_tipo_comprobante": 1,
        "fecha_emision": "2025-10-31",
        "nro_documento": "F001-00001",
        "id_medio_pago": 1,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": 1,
        "tipo_compra": "Contado",
        "dias_credito": 30,
        "cuotas": 3,
        "porcentaje_detraccion": 0,
        "fecha_pago": "2025-11-15",
        "fecha_vencimiento": "2025-11-30",
        "enlace_documento": "https://storage.maravia.pe/compras/doc123.pdf",
        "id_tipo_afectacion": 1,
        "observacion": "Compra de productos para stock",
        "id_caja_banco": 1,
        "id_centro_costo": 1,
        "id_tipo_compra_gasto": 1,
        "detalles": [
            {
                "id_inventario": None,
                "id_catalogo": 10,
                "id_tipo_producto": 1,
                "cantidad": 5,
                "id_unidad": 1,
                "precio_unitario": 100,
                "concepto": "Producto X",
                "valor_subtotal_item": 500,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 90,
                "valor_icbper": 0,
                "valor_total_item": 590,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }

    reg_c, params_c, extra_c = _build_reg_compra_like_test()
    actual_compra = construir_payload_compra(
        reg=reg_c,
        params=params_c,
        id_from=int(extra_c["id_from"]),
        id_usuario=3,
    )

    _compare_payloads("COMPRAS - Payload REGISTRAR_COMPRA", actual_compra, expected_compra)

    print("\nRevisa los reportes si hay diferencias. En especial: nulos en id_medio_pago / ids opcionales.")


if __name__ == "__main__":
    main()

