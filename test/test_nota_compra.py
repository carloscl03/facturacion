"""
Test aislado: registrar una nota de compra via REGISTRAR_COMPRA (ws_compra.php).

Inspirado en test_nota_venta.py: mismo estilo de endpoint configurable,
headers, impresion de request/response y resumen final.

API base tomada de test_registro.py:
  - Endpoint: /servicio/n8n/ws_compra.php
  - codOpe: REGISTRAR_COMPRA
  - detalle en clave "detalles"

Variables de entorno utiles:
  URL_COMPRA_N8N            - override del endpoint.
  MARAVIA_TOKEN             - Bearer opcional.
  MARAVIA_FECHA_EMISION     - YYYY-MM-DD (default: hoy).
  MARAVIA_FECHA_PAGO        - YYYY-MM-DD (default: fecha_emision).
  MARAVIA_FECHA_VENCIMIENTO - YYYY-MM-DD (default: fecha_pago).
  MARAVIA_EMPRESA_ID        - default: 2
  MARAVIA_USUARIO_ID        - default: 3
  MARAVIA_ID_PROVEEDOR      - default: 5
  MARAVIA_NRO_DOCUMENTO_COMPRA       - opcional, formato SERIE-NUMERO (ej: NC01-00001).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import requests

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from config import settings

URL_COMPRA = os.environ.get("URL_COMPRA_N8N") or "https://api.maravia.pe/servicio/n8n/ws_compra.php"
if hasattr(settings, "URL_COMPRA_N8N"):
    URL_COMPRA = os.environ.get("URL_COMPRA_N8N") or getattr(settings, "URL_COMPRA_N8N")

EMPRESA_ID = int(os.environ.get("MARAVIA_EMPRESA_ID", "2"))
USUARIO_ID = int(os.environ.get("MARAVIA_USUARIO_ID", "3"))
ID_PROVEEDOR = int(os.environ.get("MARAVIA_ID_PROVEEDOR", "5"))
# Consenso funcional: para nota de compra usar id_tipo_comprobante = 7.
# Se deja hardcodeado para que el test sea determinista.
ID_TIPO_COMPROBANTE = 7

FECHA_EMISION = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()
FECHA_PAGO = os.environ.get("MARAVIA_FECHA_PAGO") or FECHA_EMISION
FECHA_VENCIMIENTO = os.environ.get("MARAVIA_FECHA_VENCIMIENTO") or FECHA_PAGO
NRO_DOCUMENTO = (os.environ.get("MARAVIA_NRO_DOCUMENTO_COMPRA") or "").strip()


def _payload_nota_compra() -> dict:
    """Un item minimo coherente con IGV 18% para registrar compra."""
    payload = {
        "codOpe": "REGISTRAR_COMPRA",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_proveedor": ID_PROVEEDOR,
        "id_tipo_comprobante": ID_TIPO_COMPROBANTE,
        "fecha_emision": FECHA_EMISION,
        "id_medio_pago": 1,
        "id_forma_pago": 1,
        "id_moneda": 1,
        "id_sucursal": 1,
        "tipo_compra": "Contado",
        "dias_credito": 0,
        "cuotas": 1,
        "porcentaje_detraccion": 0,
        "fecha_pago": FECHA_PAGO,
        "fecha_vencimiento": FECHA_VENCIMIENTO,
        "id_tipo_afectacion": 1,
        "observacion": "Prueba nota de compra (test_nota_compra.py)",
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
                "precio_unitario": 118.0,
                "concepto": "Item prueba nota de compra",
                "valor_subtotal_item": 100.0,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_isc": 0,
                "valor_igv": 18.0,
                "valor_icbper": 0,
                "valor_total_item": 118.0,
                "anticipo": 0,
                "otros_cargos": 0,
                "otros_tributos": 0,
            }
        ],
    }
    if NRO_DOCUMENTO:
        payload["nro_documento"] = NRO_DOCUMENTO
    return payload


def run() -> None:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = _payload_nota_compra()
    print("--- REQUEST (REGISTRAR_COMPRA — nota de compra) ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n--- POST", URL_COMPRA, "---\n")

    try:
        res = requests.post(URL_COMPRA, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        print("Error de conexion:", e)
        return

    print("--- RESPUESTA (raw) ---")
    print(res.text)

    if res.status_code in (502, 503, 504):
        print(f"\nServidor no disponible (HTTP {res.status_code}).")
        return

    try:
        data = res.json()
    except ValueError:
        print("\nRespuesta no es JSON.")
        return

    print("\n--- RESPUESTA (JSON formateado) ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if data.get("success"):
        print("\n--- RESUMEN ---")
        print("success:", data.get("success"))
        print("id_compra:", data.get("id_compra"))
        if data.get("message"):
            print("message:", data.get("message"))
        if data.get("serie") or data.get("numero") is not None:
            print("Comprobante:", data.get("serie"), "-", data.get("numero"))
    else:
        err = data.get("message") or data.get("error") or data.get("details") or res.text[:300]
        print("\nError:", err)


if __name__ == "__main__":
    run()
