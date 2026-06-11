"""
Test: enviar sub, igv y total precalculados (no 0) para que PHP los use directamente.
"""
import json
import os
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

import requests
from config import settings

URL_VENTA = getattr(settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php")
FECHA = date.today().isoformat()

D2 = Decimal("0.01")
F = Decimal("1.18")
T = Decimal("0.18")

# Precios CON IGV
PRODUCTOS = [
    {"nombre": "laptop",  "precio_con_igv": Decimal("111.00"),   "qty": 1},
    {"nombre": "camara",  "precio_con_igv": Decimal("1199.99"),  "qty": 1},
    {"nombre": "pan",     "precio_con_igv": Decimal("10.00"),    "qty": 10},
]


def _build_item(nombre, precio_con_igv, qty):
    # Base con alta precision
    pu_base = precio_con_igv / F
    # Subtotal = base * qty, redondeado a 2dp
    subtotal = (pu_base * qty).quantize(D2, ROUND_HALF_UP)
    # IGV = subtotal * 18%
    igv = (subtotal * T).quantize(D2, ROUND_HALF_UP)
    # Total = subtotal + igv
    total = subtotal + igv

    print(f"  {nombre}: pu_base={float(pu_base):.10f}, sub={subtotal}, igv={igv}, total={total}")

    return {
        "id_inventario": None,
        "id_catalogo": None,
        "id_tipo_producto": 2,
        "cantidad": int(qty),
        "id_unidad": 1,
        "precio_unitario": float(pu_base.quantize(Decimal("0.0000000001"), ROUND_HALF_UP)),
        "concepto": nombre,
        "valor_subtotal_item": float(subtotal),
        "porcentaje_descuento": 0,
        "valor_descuento": 0,
        "valor_isc": 0,
        "valor_igv": float(igv),
        "valor_icbper": 0,
        "valor_total_item": float(total),
        "anticipo": 0,
        "otros_cargos": 0,
        "otros_tributos": 0,
    }


def run():
    items = []
    total_sum = Decimal(0)
    print("Items precalculados:")
    for p in PRODUCTOS:
        it = _build_item(p["nombre"], p["precio_con_igv"], p["qty"])
        items.append(it)
        total_sum += Decimal(str(it["valor_total_item"]))

    print(f"\nSuma total items (con IGV): {total_sum}")

    payload = {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": 2,
        "usuario_id": 3,
        "id_cliente": 5,
        "id_tipo_comprobante": 1,  # Factura
        "fecha_emision": FECHA,
        "fecha_pago": FECHA,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "observaciones": "Test precalculado",
        "generacion_comprobante": 1,
        "detalle_items": items,
    }

    print(f"\n--- PAYLOAD ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

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
        print(f"No JSON: {res.text[:300]}")
        return

    print(json.dumps(data, indent=2, ensure_ascii=False))

    if data.get("success"):
        print(f"\nOK - id_venta={data.get('id_venta')}")
    else:
        print(f"\nFALLO - {data.get('details') or data.get('message') or data.get('error')}")


if __name__ == "__main__":
    run()
