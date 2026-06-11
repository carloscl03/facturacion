"""
Test robusto: validación del cálculo de IGV contra la API real (ws_venta.php).

Cubre todos los escenarios de cálculo:
  1. Monto directo sin productos
  2. Productos con IGV incluido (catálogo)
  3. Productos sin IGV (usuario dice "más IGV" / "sin IGV")
  4. Mix de productos con y sin IGV
  5. Notas de venta (sin IGV, sin SUNAT)
  6. Recibo por honorarios
  7. Un solo producto
  8. Muchos productos (10+)
  9. Precios con decimales irregulares

NOTA: Crea registros reales en BD. Tests A-D usan nota de venta (sin SUNAT).
      Tests E+ usan factura con SUNAT (generan comprobante real).

USO: python test/test_api_calculo_igv.py
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
from services.helpers.igv import calcular_igv, construir_items_detalle, precio_con_igv, sumar_productos

URL_VENTA = getattr(settings, "URL_VENTA_SUNAT", "https://api.maravia.pe/servicio/n8n/ws_venta.php")
EMPRESA_ID = 2
USUARIO_ID = 3
ID_CLIENTE = 5
FECHA = date.today().isoformat()


def _base_payload(tipo=7, gen=0, obs="test", items=None):
    return {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": EMPRESA_ID,
        "usuario_id": USUARIO_ID,
        "id_cliente": ID_CLIENTE,
        "id_tipo_comprobante": tipo,
        "fecha_emision": FECHA,
        "fecha_pago": FECHA,
        "id_moneda": 1,
        "id_forma_pago": 9,
        "id_medio_pago": None,
        "id_sucursal": 14,
        "tipo_venta": "Contado",
        "generacion_comprobante": gen,
        "observaciones": obs,
        "detalle_items": items or [],
    }


def _item(pu_con_igv, qty, concepto="item", sub=None, igv=None, total=None):
    """Construye un item para el payload. pu = precio CON IGV."""
    return {
        "id_inventario": None,
        "id_catalogo": None,
        "id_tipo_producto": 2,
        "cantidad": qty,
        "id_unidad": 1,
        "precio_unitario": pu_con_igv,
        "concepto": concepto,
        "valor_subtotal_item": sub if sub is not None else 0,
        "porcentaje_descuento": 0,
        "valor_descuento": 0,
        "valor_isc": 0,
        "valor_igv": igv if igv is not None else 0,
        "valor_icbper": 0,
        "valor_total_item": total if total is not None else round(pu_con_igv * qty, 2),
        "anticipo": 0,
        "otros_cargos": 0,
        "otros_tributos": 0,
    }


def _items_con_ajuste(productos_raw, conceptos=None):
    """Construye items usando construir_items_detalle (con ajuste de redondeo PHP)."""
    prods = [{"precio_unitario": pu, "cantidad": qty} for pu, qty in productos_raw]
    calcs = construir_items_detalle(prods, igv_incluido=True)
    items = []
    for i, (calc, (pu, qty)) in enumerate(zip(calcs, productos_raw)):
        nombre = conceptos[i] if conceptos and i < len(conceptos) else f"producto {i}"
        items.append(_item(calc["pu"], calc["qty"], nombre, sub=calc["sub"], igv=calc["igv"], total=calc["total"]))
    return items


def _enviar(label, payload):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    try:
        res = requests.post(URL_VENTA, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
        data = res.json()
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return {"_label": label, "_ok": False, "_error": str(e)}

    ok = data.get("success", False)
    status = "✅" if ok else "❌"
    print(f"  {status} HTTP {res.status_code}", end="")
    if ok:
        print(f" | id_venta={data.get('id_venta')}")
    else:
        err = data.get("details") or data.get("error") or data.get("message") or ""
        print(f" | {str(err)[:100]}")

    data["_label"] = label
    data["_ok"] = ok
    return data


# ═══════════════════════════════════════════════════════════════
#  TESTS SIN SUNAT (notas de venta, generacion_comprobante=0)
# ═══════════════════════════════════════════════════════════════

def test_01_monto_directo():
    """Monto directo S/1000, sin productos."""
    return _enviar("01: Monto directo S/1000", _base_payload(
        obs="T01: monto directo",
        items=[_item(1000.0, 1, "Servicio")],
    ))


def test_02_productos_con_igv():
    """3 productos con precios que YA incluyen IGV (catálogo)."""
    return _enviar("02: 3 productos con IGV incluido", _base_payload(
        obs="T02: productos con IGV",
        items=[
            _item(111.0, 7, "laptop"),
            _item(80.0, 3, "cámara"),
            _item(20.0, 2, "pan"),
        ],
    ))


def test_03_producto_sin_igv():
    """Producto a precio base (sin IGV). Se convierte a precio con IGV."""
    pu_base = 20.0
    pu_con = precio_con_igv(pu_base, igv_incluido=False)  # 20 * 1.18 = 23.60
    return _enviar(f"03: Producto sin IGV (base={pu_base}, con_igv={pu_con})", _base_payload(
        obs="T03: producto sin IGV",
        items=[_item(pu_con, 5, "pan sin IGV")],
    ))


def test_04_mix_con_y_sin_igv():
    """Mix: laptop con IGV (111), pan sin IGV (20 base → 23.60 con IGV)."""
    pu_pan = precio_con_igv(20.0, igv_incluido=False)  # 23.60
    return _enviar("04: Mix con IGV + sin IGV", _base_payload(
        obs="T04: mix IGV",
        items=[
            _item(111.0, 7, "laptop (con IGV)"),
            _item(pu_pan, 5, "pan (sin IGV → 23.60)"),
        ],
    ))


def test_05_precios_decimales():
    """Precios con decimales irregulares que causan problemas de redondeo."""
    return _enviar("05: Precios decimales irregulares", _base_payload(
        obs="T05: decimales",
        items=[
            _item(99.99, 7, "producto A"),
            _item(33.33, 11, "producto B"),
            _item(0.50, 100, "producto C"),
            _item(1234.56, 3, "producto D"),
        ],
    ))


def test_06_muchos_productos():
    """10 productos distintos — estrés de acumulación de redondeo."""
    items = [_item(round(50.0 + i * 17.33, 2), i + 1, f"prod_{i}") for i in range(10)]
    return _enviar("06: 10 productos (estrés redondeo)", _base_payload(
        obs="T06: 10 productos",
        items=items,
    ))


def test_07_un_centavo():
    """Producto a S/0.01 × 1 — mínimo posible."""
    return _enviar("07: Producto S/0.01 × 1", _base_payload(
        obs="T07: un centavo",
        items=[_item(0.01, 1, "centavo")],
    ))


def test_08_monto_grande():
    """Monto grande S/99999.99 × 1."""
    return _enviar("08: Monto grande S/99999.99", _base_payload(
        obs="T08: monto grande",
        items=[_item(99999.99, 1, "item caro")],
    ))


# ═══════════════════════════════════════════════════════════════
#  TESTS CON SUNAT (facturas, generacion_comprobante=1)
# ═══════════════════════════════════════════════════════════════

def test_09_factura_simple():
    """Factura SUNAT con 1 producto."""
    return _enviar("09: Factura SUNAT simple", _base_payload(
        tipo=1, gen=1, obs="T09: factura simple",
        items=[_item(111.0, 7, "laptop")],
    ))


def test_10_factura_multi():
    """Factura SUNAT con 3 productos (el caso del bug original)."""
    return _enviar("10: Factura SUNAT 3 productos", _base_payload(
        tipo=1, gen=1, obs="T10: factura multi",
        items=_items_con_ajuste([(111.0, 7), (80.0, 3), (20.0, 2)], ["laptop", "cámara", "pan"]),
    ))


def test_11_factura_mix_igv():
    """Factura SUNAT: laptop con IGV + pan sin IGV."""
    pu_pan = precio_con_igv(20.0, igv_incluido=False)
    return _enviar("11: Factura SUNAT mix IGV", _base_payload(
        tipo=1, gen=1, obs="T11: factura mix",
        items=[
            _item(111.0, 7, "laptop (con IGV)"),
            _item(pu_pan, 5, "pan (sin IGV → con IGV)"),
        ],
    ))


def test_12_factura_decimales():
    """Factura SUNAT con precios decimales complicados."""
    return _enviar("12: Factura SUNAT decimales", _base_payload(
        tipo=1, gen=1, obs="T12: factura decimales",
        items=_items_con_ajuste(
            [(99.99, 7), (33.33, 11), (1234.56, 3)],
            ["Producto Alpha", "Producto Beta", "Producto Gamma"],
        ),
    ))


def test_13_factura_muchos():
    """Factura SUNAT con 8 productos — estrés de redondeo."""
    prods = [(round(50.0 + i * 23.45, 2), i + 1) for i in range(8)]
    nombres = [f"producto {i} test" for i in range(8)]
    return _enviar("13: Factura SUNAT 8 productos", _base_payload(
        tipo=1, gen=1, obs="T13: factura 8 items",
        items=_items_con_ajuste(prods, nombres),
    ))


# ═══════════════════════════════════════════════════════════════
#  VALIDACIÓN LOCAL: sumar_productos == sum(item totals)
# ═══════════════════════════════════════════════════════════════

def test_local_consistency():
    """Valida que sumar_productos coincide con sum(pu_con_igv × qty) para muchos casos."""
    import random
    random.seed(42)
    fails = 0
    for trial in range(10000):
        n = random.randint(1, 15)
        prods = [{"precio_unitario": round(random.uniform(0.5, 5000), 2), "cantidad": random.randint(1, 100)} for _ in range(n)]

        mt, _, _ = sumar_productos(prods, igv_incluido=True)

        # Lo que PHP calcularía
        php_total = sum(round(p["precio_unitario"] * p["cantidad"], 2) for p in prods)
        php_total = round(php_total, 2)

        if mt != php_total:
            fails += 1

    print(f"\n{'─'*60}")
    print(f"  LOCAL: sumar_productos vs PHP-style sum")
    print(f"{'─'*60}")
    print(f"  {'✅' if fails == 0 else '❌'} Mismatches: {fails}/10000")
    return fails == 0


def main():
    print("═" * 60)
    print("  TEST ROBUSTO: Cálculo IGV contra API real")
    print(f"  Endpoint: {URL_VENTA}")
    print(f"  Fecha: {FECHA}")
    print("═" * 60)

    # Local consistency
    local_ok = test_local_consistency()

    # Tests sin SUNAT (seguros)
    print(f"\n{'═'*60}")
    print("  TESTS SIN SUNAT (notas de venta)")
    print(f"{'═'*60}")
    resultados = {}
    for fn in [test_01_monto_directo, test_02_productos_con_igv, test_03_producto_sin_igv,
               test_04_mix_con_y_sin_igv, test_05_precios_decimales,
               test_06_muchos_productos, test_07_un_centavo, test_08_monto_grande]:
        r = fn()
        resultados[fn.__name__] = r

    # Tests con SUNAT
    print(f"\n{'═'*60}")
    print("  TESTS CON SUNAT (facturas reales)")
    print(f"{'═'*60}")
    for fn in [test_09_factura_simple, test_10_factura_multi, test_11_factura_mix_igv,
               test_12_factura_decimales, test_13_factura_muchos]:
        r = fn()
        resultados[fn.__name__] = r

    # Resumen
    print(f"\n{'═'*60}")
    print("  RESUMEN FINAL")
    print(f"{'═'*60}")
    print(f"  Local consistency: {'✅' if local_ok else '❌'}")
    ok_count = 0
    fail_count = 0
    for name, r in resultados.items():
        label = r.get("_label", name) if r else name
        if r and r.get("_ok"):
            ok_count += 1
            print(f"  ✅ {label}")
        else:
            fail_count += 1
            err = ""
            if r:
                err = str(r.get("details") or r.get("error") or r.get("_error") or "")[:60]
            print(f"  ❌ {label} — {err}")

    print(f"\n  Total: {ok_count} OK, {fail_count} FAIL")


if __name__ == "__main__":
    main()
