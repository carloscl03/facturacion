"""
Test: registrar nota de venta y nota de compra SIN id de persona/empresa (id_cliente/id_proveedor).
Monto menor a 700 soles. Verifica si las APIs aceptan el registro sin entidad identificada.
"""
import json
import os
import sys
from datetime import date

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests

from config import settings

URL_VENTA = os.environ.get("URL_VENTA_SUNAT") or getattr(
    settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php"
)
URL_COMPRA = "https://api.maravia.pe/servicio/n8n/ws_compra.php"

EMPRESA_ID = 2
USUARIO_ID = 3
FECHA_EMISION = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()

# Monto menor a 700 soles (sin IGV para notas)
MONTO_TOTAL = 500.00


def nota_venta_sin_cliente():
    """Nota de venta sin id_cliente, monto < 700."""
    payload = {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_cliente": None,
        "id_tipo_comprobante": 7,  # Nota de venta
        "fecha_emision": FECHA_EMISION,
        "fecha_pago": FECHA_EMISION,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Test nota de venta sin cliente - monto < 700",
        "generacion_comprobante": 0,
        "detalle_items": [
            {
                "id_inventario": None,
                "id_catalogo": None,
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": MONTO_TOTAL,
                "valor_subtotal_item": MONTO_TOTAL,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 0,
                "valor_icbper": 0,
                "valor_total_item": MONTO_TOTAL,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    return requests.post(URL_VENTA, json=payload, headers=headers, timeout=30)


def nota_compra_sin_proveedor():
    """Nota de compra sin id_proveedor, monto < 700."""
    payload = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_proveedor": None,
        "id_tipo_comprobante": 7,  # Nota de compra
        "fecha_emision": FECHA_EMISION,
        "id_medio_pago": None,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": 1,
        "tipo_compra": "Contado",
        "dias_credito": 0,
        "cuotas": 0,
        "porcentaje_detraccion": 0,
        "fecha_pago": FECHA_EMISION,
        "fecha_vencimiento": FECHA_EMISION,
        "id_tipo_afectacion": 1,
        "observacion": "Test nota de compra sin proveedor - monto < 700",
        "id_caja_banco": 1,
        "id_centro_costo": 1,
        "id_tipo_compra_gasto": 1,
        "detalles": [
            {
                "id_inventario": None,
                "id_catalogo": None,
                "id_tipo_producto": 1,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": MONTO_TOTAL,
                "concepto": "Gasto menor sin proveedor",
                "valor_subtotal_item": MONTO_TOTAL,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 0,
                "valor_icbper": 0,
                "valor_total_item": MONTO_TOTAL,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    return requests.post(URL_COMPRA, json=payload, headers=headers, timeout=30)


def _imprimir_resultado(nombre: str, resp):
    print(f"\n{'=' * 60}")
    print(f"{nombre}")
    print(f"{'=' * 60}")
    print("Status code:", resp.status_code)
    try:
        data = resp.json()
    except ValueError:
        print("Respuesta no es JSON:")
        print(resp.text[:500])
        return
    print("Respuesta:", json.dumps(data, indent=2, ensure_ascii=False))
    if data.get("success") is True:
        id_registro = data.get("id_venta") or data.get("id_compra") or data.get("id")
        print(f"\nRegistro exitoso. ID: {id_registro}")
    else:
        err = data.get("error") or data.get("message") or "Error desconocido"
        print(f"\nError: {err}")
        if data.get("details"):
            print("Detalles:", data["details"])


def run():
    print(f"Monto: S/ {MONTO_TOTAL} (menor a 700)")
    print("id_cliente / id_proveedor: None (sin entidad)")

    # Test 1: Nota de venta sin cliente
    try:
        resp = nota_venta_sin_cliente()
        _imprimir_resultado("NOTA DE VENTA sin id_cliente", resp)
    except Exception as e:
        print(f"\nError al llamar ws_venta: {e}")

    # Test 2: Nota de compra sin proveedor
    try:
        resp = nota_compra_sin_proveedor()
        _imprimir_resultado("NOTA DE COMPRA sin id_proveedor", resp)
    except Exception as e:
        print(f"\nError al llamar ws_compra: {e}")


if __name__ == "__main__":
    run()
