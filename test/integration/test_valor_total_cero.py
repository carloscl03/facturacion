"""
Test: enviar valor_total_item=0 para verificar que PHP lo recalcula.

Caso 1: Factura con 3 productos (laptop, cámara, 10 pan) — generacion_comprobante=1 (SUNAT).
Caso 2: Nota de venta con los mismos productos — generacion_comprobante=0 (sin SUNAT).

Si PHP recalcula valor_total_item, ambos deben dar success=True.
Si NO lo recalcula, SUNAT rechazará con total=0.
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
from services.helpers.igv import precio_base, valor_total_item as vti

URL_VENTA = getattr(settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php")
FECHA = date.today().isoformat()

# Precios CON IGV (como vienen del usuario/catálogo)
PRODUCTOS = [
    {"nombre": "laptop",  "precio_con_igv": 111.00,   "qty": 1},
    {"nombre": "cámara",  "precio_con_igv": 1199.99,  "qty": 1},
    {"nombre": "pan",     "precio_con_igv": 10.00,    "qty": 10},
]


def _build_item(nombre, precio_con_igv, qty):
    pu_base = precio_base(precio_con_igv, igv_incluido=True, sin_igv=False)
    return {
        "id_inventario": None,
        "id_catalogo": None,
        "id_tipo_producto": 2,
        "cantidad": qty,
        "id_unidad": 1,
        "precio_unitario": pu_base,
        "concepto": nombre,
        "valor_subtotal_item": 0,
        "porcentaje_descuento": 0,
        "valor_descuento": 0,
        "valor_isc": 0,
        "valor_igv": 0,
        "valor_icbper": 0,
        "valor_total_item": vti(pu_base, qty),
        "anticipo": 0,
        "otros_cargos": 0,
        "otros_tributos": 0,
    }


def _build_payload(id_tipo_comprobante, generacion_comprobante):
    items = [_build_item(p["nombre"], p["precio_con_igv"], p["qty"]) for p in PRODUCTOS]
    return {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": 2,
        "usuario_id": 3,
        "id_cliente": 5,
        "id_tipo_comprobante": id_tipo_comprobante,
        "fecha_emision": FECHA,
        "fecha_pago": FECHA,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Test valor_total_item=0",
        "generacion_comprobante": generacion_comprobante,
        "detalle_items": items,
    }


def _send(label, payload):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    print("\n--- ITEMS enviados ---")
    for it in payload["detalle_items"]:
        print(f"  {it['concepto']}: pu_base={it['precio_unitario']}, qty={it['cantidad']}, valor_total_item={it['valor_total_item']}")

    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post(URL_VENTA, json=payload, headers=headers, timeout=90)
    except requests.RequestException as e:
        print(f"\nError conexion: {e}")
        return

    print(f"\nHTTP {res.status_code}")
    try:
        data = res.json()
    except ValueError:
        print(f"Respuesta no JSON: {res.text[:300]}")
        return

    print(json.dumps(data, indent=2, ensure_ascii=False))

    if data.get("success"):
        print(f"\nOK PASO - id_venta={data.get('id_venta')}, serie={data.get('serie')}, numero={data.get('numero')}")
        if data.get("pdf_url"):
            print(f"PDF: {data.get('pdf_url')}")
    else:
        err = data.get("details") or data.get("message") or data.get("error") or "?"
        print(f"\nFALLO - {err}")


def run():
    print("Precios base enviados:")
    for p in PRODUCTOS:
        pb = precio_base(p["precio_con_igv"], igv_incluido=True, sin_igv=False)
        print(f"  {p['nombre']}: {p['precio_con_igv']} con IGV -> {pb} base x {p['qty']}")

    # Test 1: Nota de venta (sin SUNAT) — más seguro
    _send("Nota de venta (sin SUNAT) - valor_total_item=0",
          _build_payload(id_tipo_comprobante=7, generacion_comprobante=0))

    # Test 2: Factura (con SUNAT) — valida redondeo
    _send("Factura (con SUNAT) - valor_total_item=0",
          _build_payload(id_tipo_comprobante=1, generacion_comprobante=1))


if __name__ == "__main__":
    run()
