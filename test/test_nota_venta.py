"""
Test aislado: registrar una nota de venta vía REGISTRAR_VENTA_N8N (ws_venta.php).

Inspirado en test_pdf_sunat.py: mismo endpoint, headers y forma de imprimir la respuesta.

Contrato (php/ventan8n.txt, función registrarVentaN8N):
  - id_tipo_comprobante para este test se fija en 7 por consenso funcional del equipo.
  - generacion_comprobante debe ser 0: el flujo SUNAT en registrarVentaN8N solo aplica a tipos 1 (factura) y 2 (boleta).
  - Sin SUNAT: si envías serie y no número, PHP autogenera el correlativo con MAX+1 para esa serie.

Variables de entorno útiles:
  URL_VENTA_SUNAT — override del endpoint (igual que test_pdf_sunat).
  MARAVIA_TOKEN — Bearer opcional.
  MARAVIA_FECHA_EMISION — YYYY-MM-DD (default: hoy).
  MARAVIA_ID_CLIENTE — override del id_cliente (default: 5, como en test_pdf_sunat).
  MARAVIA_SERIE_NOTA_VENTA — serie interna (default: NV01); sin MARAVIA_NUMERO_NOTA_VENTA se autogenera el número.
  MARAVIA_NUMERO_NOTA_VENTA — si quieres fijar el correlativo (entero).
"""
from __future__ import annotations

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

EMPRESA_ID = int(os.environ.get("MARAVIA_EMPRESA_ID", "2"))
USUARIO_ID = int(os.environ.get("MARAVIA_USUARIO_ID", "3"))
ID_CLIENTE = int(os.environ.get("MARAVIA_ID_CLIENTE", "5"))

FECHA_EMISION = os.environ.get("MARAVIA_FECHA_EMISION") or date.today().isoformat()

# Consenso funcional: para nota de venta usar id_tipo_comprobante = 7.
# Se deja hardcodeado para evitar ambigüedad entre catálogos/mapeos históricos.
ID_TIPO_NOTA_VENTA = 7

SERIE_NV = os.environ.get("MARAVIA_SERIE_NOTA_VENTA", "NV01")
_num_env = os.environ.get("MARAVIA_NUMERO_NOTA_VENTA", "").strip()
NUMERO_NV: int | None = int(_num_env) if _num_env.isdigit() else None


def _payload_nota_venta() -> dict:
    """Un ítem mínimo coherente con IGV 18% (mismas ideas que test_pdf_sunat)."""
    return {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_cliente": ID_CLIENTE,
        "id_tipo_comprobante": ID_TIPO_NOTA_VENTA,
        "fecha_emision": FECHA_EMISION,
        "fecha_pago": FECHA_EMISION,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Prueba nota de venta (test_nota_venta.py)",
        "generacion_comprobante": 0,
        "serie": SERIE_NV,
        **({"numero": NUMERO_NV} if NUMERO_NV is not None else {}),
        "detalle_items": [
            {
                "id_inventario": None,
                "id_catalogo": None,
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": 1,
                "precio_unitario": 118.0,
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


def run() -> None:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = _payload_nota_venta()
    print("--- REQUEST (REGISTRAR_VENTA_N8N — nota de venta, id_tipo_comprobante=7) ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\n--- POST", URL_VENTA, "---\n")

    try:
        res = requests.post(URL_VENTA, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        print("❌ Error de conexión:", e)
        return

    print("--- RESPUESTA (raw) ---")
    print(res.text)

    if res.status_code in (502, 503, 504):
        print(f"\n⚠ Servidor no disponible (HTTP {res.status_code}).")
        return

    try:
        data = res.json()
    except ValueError:
        print("\n⚠ Respuesta no es JSON.")
        return

    print("\n--- RESPUESTA (JSON formateado) ---")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if data.get("success"):
        print("\n--- RESUMEN ---")
        print("✅ success:", data.get("success"))
        print("🆔 id_venta:", data.get("id_venta"))
        if data.get("message"):
            print("📋 message:", data.get("message"))
        if data.get("serie") or data.get("numero") is not None:
            print("📄 Comprobante:", data.get("serie"), "-", data.get("numero"))
        crono = data.get("cronograma")
        if crono is not None:
            print("📅 cronograma:", crono.get("generado"), "| cuotas:", crono.get("cuotas_insertadas"))
    else:
        err = data.get("message") or data.get("error") or data.get("details") or res.text[:300]
        print("\n❌ Error:", err)


if __name__ == "__main__":
    run()
