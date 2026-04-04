"""
Test: ¿La API de ventas (ws_venta.php) recalcula IGV o usa nuestros valores?

Envía 4 variantes de payload como Nota de Venta (id_tipo_comprobante=7,
generacion_comprobante=0) para no tocar SUNAT y poder comparar lo que
la BD registra.

Variantes:
  A. Monto directo (1 ítem, sin productos): con sub/igv/total precalculados.
  B. Monto directo: sub=0, igv=0, total=monto → ¿la API calcula sub/igv?
  C. Productos (3 ítems): con sub/igv/total precalculados por calcular_item.
  D. Productos (3 ítems): sub=0, igv=0, total=qty*pu → ¿la API calcula?

Resultado esperado:
  - Si la API ACEPTA A, B, C, D sin error → usa nuestros valores tal cual.
  - Si B o D fallan → la API valida que sub+igv==total (necesitamos precalcular).
  - El test imprime la respuesta para diagnóstico; no hace asserts duros.

USO: python test/test_api_calculo_igv.py
NOTA: Crea registros reales en BD con id_tipo_comprobante=7 (nota de venta).
"""
import json
import os
import sys
from datetime import date

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

# Windows: forzar UTF-8 en stdout para emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from config import settings
from services.helpers.igv import calcular_item

URL_VENTA = getattr(settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php")
EMPRESA_ID = 2
USUARIO_ID = 3
ID_CLIENTE = 5
FECHA = date.today().isoformat()


def _base_payload(**overrides):
    payload = {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_cliente": ID_CLIENTE,
        "id_tipo_comprobante": 7,       # Nota de venta (sin SUNAT)
        "fecha_emision": FECHA,
        "fecha_pago": FECHA,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "generacion_comprobante": 0,    # Sin SUNAT
    }
    payload.update(overrides)
    return payload


def _enviar(label: str, payload: dict) -> dict | None:
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()

    try:
        res = requests.post(URL_VENTA, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
    except requests.RequestException as e:
        print(f"  ❌ Error conexión: {e}")
        return None

    try:
        data = res.json()
    except ValueError:
        print(f"  ❌ Respuesta no JSON (HTTP {res.status_code}): {res.text[:200]}")
        return None

    ok = data.get("success", False)
    icono = "✅" if ok else "❌"
    print(f"  {icono} HTTP {res.status_code} | success={ok}")
    if ok:
        print(f"  id_venta={data.get('id_venta')} | message={data.get('message')}")
    else:
        err = data.get("details") or data.get("error") or data.get("message") or ""
        print(f"  error: {err}")

    return data


def test_a_monto_directo_precalculado():
    """A. Un ítem, monto=1000, sub/igv/total precalculados."""
    item = calcular_item(1000.0, 1.0, igv_incluido=True, sin_igv=True)
    return _enviar("A) Monto directo — sub/igv/total PRECALCULADOS (nota, sin IGV)", _base_payload(
        observaciones="Test A: monto directo precalculado",
        detalle_items=[{
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": 1,
            "id_unidad": 1,
            "precio_unitario": item["precio_unitario"],
            "valor_subtotal_item": item["valor_subtotal_item"],
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": item["valor_igv"],
            "valor_icbper": 0,
            "valor_total_item": item["valor_total_item"],
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        }],
    ))


def test_b_monto_directo_sin_desglose():
    """B. Un ítem, monto=1000, sub=0, igv=0 → ¿la API calcula?"""
    return _enviar("B) Monto directo — sub=0, igv=0, total=1000 (¿API calcula?)", _base_payload(
        observaciones="Test B: monto directo sin desglose",
        detalle_items=[{
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": 1,
            "id_unidad": 1,
            "precio_unitario": 1000.00,
            "valor_subtotal_item": 0,
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": 0,
            "valor_icbper": 0,
            "valor_total_item": 1000.00,
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        }],
    ))


def test_c_productos_precalculados():
    """C. 3 productos, sub/igv/total precalculados con calcular_item."""
    productos = [
        ("laptop", 7, 111.00),
        ("cámara", 3, 80.00),
        ("pan", 2, 20.00),
    ]
    items = []
    for nombre, qty, pu in productos:
        vals = calcular_item(pu, qty, igv_incluido=True, sin_igv=True)  # nota = sin IGV
        items.append({
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": qty,
            "id_unidad": 1,
            "precio_unitario": vals["precio_unitario"],
            "concepto": nombre,
            "valor_subtotal_item": vals["valor_subtotal_item"],
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": vals["valor_igv"],
            "valor_icbper": 0,
            "valor_total_item": vals["valor_total_item"],
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        })
    return _enviar("C) 3 productos — sub/igv/total PRECALCULADOS (nota)", _base_payload(
        observaciones="Test C: productos precalculados",
        detalle_items=items,
    ))


def test_d_productos_sin_desglose():
    """D. 3 productos, sub=0, igv=0, total=qty*pu → ¿API calcula?"""
    productos = [
        ("laptop", 7, 111.00),
        ("cámara", 3, 80.00),
        ("pan", 2, 20.00),
    ]
    items = []
    for nombre, qty, pu in productos:
        items.append({
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": qty,
            "id_unidad": 1,
            "precio_unitario": pu,
            "concepto": nombre,
            "valor_subtotal_item": 0,
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": 0,
            "valor_icbper": 0,
            "valor_total_item": round(qty * pu, 2),
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        })
    return _enviar("D) 3 productos — sub=0, igv=0, total=qty*pu (¿API calcula?)", _base_payload(
        observaciones="Test D: productos sin desglose",
        detalle_items=items,
    ))


def test_e_factura_precalculado_con_sunat():
    """E. Factura real con SUNAT (generacion_comprobante=1), precalculado con base→igv→total."""
    productos = [
        ("laptop", 7, 111.00),
        ("cámara", 3, 80.00),
        ("pan", 2, 20.00),
    ]
    items = []
    for nombre, qty, pu in productos:
        vals = calcular_item(pu, qty, igv_incluido=True, sin_igv=False)  # factura = con IGV
        items.append({
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": qty,
            "id_unidad": 1,
            "precio_unitario": vals["precio_unitario"],
            "concepto": nombre,
            "valor_subtotal_item": vals["valor_subtotal_item"],
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": vals["valor_igv"],
            "valor_icbper": 0,
            "valor_total_item": vals["valor_total_item"],
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        })
    return _enviar("E) Factura SUNAT — 3 productos precalculados base→igv→total", _base_payload(
        id_tipo_comprobante=1,          # Factura
        generacion_comprobante=1,       # Generar en SUNAT
        observaciones="Test E: factura SUNAT precalculada",
        detalle_items=items,
    ))


def test_f_factura_sin_desglose_con_sunat():
    """F. Factura real SUNAT, sub=0, igv=0 → ¿SUNAT recalcula o rechaza?"""
    productos = [
        ("laptop", 7, 111.00),
        ("cámara", 3, 80.00),
        ("pan", 2, 20.00),
    ]
    items = []
    for nombre, qty, pu in productos:
        items.append({
            "id_inventario": None,
            "id_catalogo": None,
            "id_tipo_producto": 2,
            "cantidad": qty,
            "id_unidad": 1,
            "precio_unitario": round(pu / 1.18, 2),  # precio base como si fuera sin IGV
            "concepto": nombre,
            "valor_subtotal_item": 0,
            "porcentaje_descuento": 0,
            "valor_descuento": 0,
            "valor_isc": 0,
            "valor_igv": 0,
            "valor_icbper": 0,
            "valor_total_item": round(qty * pu, 2),
            "anticipo": 0,
            "otros_cargos": 0,
            "otros_tributos": 0,
        })
    return _enviar("F) Factura SUNAT — sub=0, igv=0 (¿SUNAT recalcula o rechaza?)", _base_payload(
        id_tipo_comprobante=1,
        generacion_comprobante=1,
        observaciones="Test F: factura SUNAT sin desglose",
        detalle_items=items,
    ))


def main():
    print("=" * 70)
    print("  TEST: ¿La API recalcula IGV o usa nuestros valores?")
    print(f"  Endpoint: {URL_VENTA}")
    print(f"  Fecha: {FECHA}")
    print("=" * 70)

    resultados = {}

    # Tests sin SUNAT (notas de venta — seguros)
    resultados["A"] = test_a_monto_directo_precalculado()
    resultados["B"] = test_b_monto_directo_sin_desglose()
    resultados["C"] = test_c_productos_precalculados()
    resultados["D"] = test_d_productos_sin_desglose()

    # Tests con SUNAT (facturas — emiten comprobante real)
    print(f"\n{'#'*70}")
    print("  TESTS CON SUNAT (generan factura real)")
    print(f"{'#'*70}")
    resultados["E"] = test_e_factura_precalculado_con_sunat()
    resultados["F"] = test_f_factura_sin_desglose_con_sunat()

    # Resumen
    print(f"\n{'='*70}")
    print("  RESUMEN FINAL")
    print(f"{'='*70}")
    for k, v in resultados.items():
        if v is None:
            print(f"  {k}: ⚠ Sin respuesta (error conexión)")
        elif v.get("success"):
            print(f"  {k}: ✅ Aceptado (id_venta={v.get('id_venta')})")
        else:
            err = v.get("details") or v.get("error") or v.get("message") or "?"
            err_short = str(err)[:80]
            print(f"  {k}: ❌ Rechazado — {err_short}")

    print()
    print("INTERPRETACIÓN:")
    print("  - Si A y B pasan → la API acepta sub=0/igv=0 (no valida desglose para notas)")
    print("  - Si C y D pasan → la API acepta items sin desglose IGV para notas")
    print("  - Si E pasa y F falla → SUNAT requiere desglose correcto (nuestro cálculo es necesario)")
    print("  - Si E y F pasan → SUNAT/PHP recalcula IGV internamente (nuestro cálculo es redundante)")


if __name__ == "__main__":
    main()
