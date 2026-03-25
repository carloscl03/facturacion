"""
Test: enviar enlace_documento (URL de PDF) a ws_venta.php y ws_compra.php
para verificar que el campo se acepta correctamente en ambas APIs.
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

ENLACE_DOCUMENTO = "https://maravia-uploads.s3.us-east-1.amazonaws.com/uploads/whatsapp/1/documentos/PDF-BOLETAEB01-410728842496__1_.pdf"


def registrar_venta_con_url():
    """Llama a ws_venta.php con enlace_documento en el payload."""
    payload = {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_cliente": 5,
        "id_tipo_comprobante": 7,
        "fecha_emision": FECHA_EMISION,
        "fecha_pago": FECHA_EMISION,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Test URL - venta con enlace_documento",
        "generacion_comprobante": 0,
        "enlace_documento": ENLACE_DOCUMENTO,
        "detalle_items": [
            {
                "id_inventario": None,
                "id_catalogo": None,
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 100.00,
                "valor_subtotal_item": 84.75,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 15.25,
                "valor_icbper": 0,
                "valor_total_item": 100.00,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    return requests.post(URL_VENTA, json=payload, headers=headers, timeout=30)


def registrar_compra_con_url():
    """Llama a ws_compra.php con enlace_documento en el payload."""
    payload = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_proveedor": 5,
        "id_tipo_comprobante": 1,
        "fecha_emision": FECHA_EMISION,
        "nro_documento": "F001-00001",
        "id_medio_pago": 1,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": 1,
        "tipo_compra": "Contado",
        "dias_credito": 0,
        "cuotas": 0,
        "porcentaje_detraccion": 0,
        "fecha_pago": FECHA_EMISION,
        "fecha_vencimiento": FECHA_EMISION,
        "enlace_documento": ENLACE_DOCUMENTO,
        "id_tipo_afectacion": 1,
        "observacion": "Test URL - compra con enlace_documento",
        "id_caja_banco": 1,
        "id_centro_costo": 1,
        "id_tipo_compra_gasto": 1,
        "detalles": [
            {
                "id_inventario": None,
                "id_catalogo": 10,
                "id_tipo_producto": 1,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 100,
                "concepto": "Producto test URL",
                "valor_subtotal_item": 100,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 18,
                "valor_icbper": 0,
                "valor_total_item": 118,
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
        print(f"enlace_documento enviado: {ENLACE_DOCUMENTO}")
    else:
        err = data.get("error") or data.get("message") or "Error desconocido"
        print(f"\nError: {err}")
        if data.get("details"):
            print("Detalles:", data["details"])


def run():
    print(f"URL a probar: {ENLACE_DOCUMENTO}")

    # Test 1: Venta
    try:
        resp_venta = registrar_venta_con_url()
        _imprimir_resultado("VENTA con enlace_documento", resp_venta)
    except Exception as e:
        print(f"\nError al llamar ws_venta: {e}")

    # Test 2: Compra
    try:
        resp_compra = registrar_compra_con_url()
        _imprimir_resultado("COMPRA con enlace_documento", resp_compra)
    except Exception as e:
        print(f"\nError al llamar ws_compra: {e}")


if __name__ == "__main__":
    run()
