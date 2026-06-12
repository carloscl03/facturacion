"""
NIVEL 2 ROBUSTEZ: property-based tests con Hypothesis.

Genera miles de inputs aleatorios y verifica invariantes que SIEMPRE deben
cumplirse después de los fixes IGV. Si alguno falla, Hypothesis reduce el
caso al mínimo reproducible.

Invariantes cubiertas:
  I1: calcular_item(pu, qty, igv_incluido=True).total ≈ round(pu × qty, 2)
  I2: calcular_item siempre: subtotal + igv = total (con tolerancia 0.01)
  I3: sumar_productos siempre: total + base + igv coherentes
  I4: construir_detalle_desde_registro siempre: sum(valor_total_item) > 0
      cuando hay productos con precio > 0 o monto_total > 0
  I5: construir_detalle_desde_registro SIEMPRE lanza ValueError si suma = 0
  I6: distribución de monto_total cuando precio=0: sum_total ≈ monto_total
  I7: notas sin IGV: valor_igv = 0 siempre

Correr: pytest test/test_property_based_igv.py -v
"""
from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck

from services.helpers.compra_mapper import construir_detalles_compra
from services.helpers.igv import calcular_item, sumar_productos
from services.helpers.productos import construir_detalle_desde_registro


# ============================================================
# Estrategias para generar inputs realistas
# ============================================================

# Precios entre S/0.01 y S/100,000 con hasta 4 decimales
precio_strategy = st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False, allow_infinity=False)
precio_o_cero_strategy = st.one_of(st.just(0.0), precio_strategy)
qty_strategy = st.floats(min_value=0.01, max_value=10_000.0, allow_nan=False, allow_infinity=False)

# Nombres de productos arbitrarios (no vacíos)
nombre_strategy = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())


@st.composite
def producto_strategy(draw, allow_zero_price=True):
    """Genera un producto con nombre, cantidad y precio.

    Cuando allow_zero_price=False, garantiza que el producto sea facturable:
    precio × cantidad ≥ S/0.01 (mínimo redondeable SUNAT).
    """
    nombre = draw(nombre_strategy)
    if allow_zero_price:
        return {
            "nombre": nombre,
            "cantidad": draw(qty_strategy),
            "precio_unitario": draw(precio_o_cero_strategy),
        }
    # Garantizar que pu × qty ≥ 0.01 (facturable real)
    pu = draw(precio_strategy)
    qty = draw(qty_strategy)
    assume(pu * qty >= 0.01)
    return {"nombre": nombre, "cantidad": qty, "precio_unitario": pu}


@st.composite
def productos_list_strategy(draw, min_size=1, max_size=10, allow_zero_price=True):
    """Lista de productos."""
    return draw(st.lists(producto_strategy(allow_zero_price=allow_zero_price), min_size=min_size, max_size=max_size))


# ============================================================
# I1, I2: calcular_item invariantes
# ============================================================

class TestCalcularItemInvariantes:

    @given(pu=precio_strategy, qty=qty_strategy)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_total_preserva_precision_cuando_igv_incluido(self, pu, qty):
        """I1: total = ROUND_HALF_UP(pu × qty, 2). Sin pérdida de 1 céntimo.
        Usa Decimal porque Python round() usa banker's rounding, mientras SUNAT
        y nuestro código usan ROUND_HALF_UP (siempre 0.5 sube)."""
        from decimal import Decimal, ROUND_HALF_UP
        _, sub, igv, total = calcular_item(pu, qty, igv_incluido=True)
        esperado = float((Decimal(str(pu)) * Decimal(str(qty))).quantize(Decimal("0.01"), ROUND_HALF_UP))
        assert abs(total - esperado) < 0.005

    @given(pu=precio_strategy, qty=qty_strategy, igv_incl=st.booleans())
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_coherencia_sub_igv_total(self, pu, qty, igv_incl):
        """I2: subtotal + igv = total siempre."""
        _, sub, igv, total = calcular_item(pu, qty, igv_incluido=igv_incl)
        assert abs((sub + igv) - total) < 0.01, f"pu={pu}, qty={qty}, sub={sub}, igv={igv}, total={total}"

    @given(pu=precio_strategy, qty=qty_strategy)
    @settings(max_examples=300)
    def test_sin_igv_total_igual_subtotal(self, pu, qty):
        """I7: sin_igv → valor_igv = 0 y subtotal = total."""
        _, sub, igv, total = calcular_item(pu, qty, sin_igv=True)
        assert igv == 0.0
        assert sub == total

    @given(pu=precio_strategy, qty=qty_strategy)
    @settings(max_examples=300)
    def test_no_negativos(self, pu, qty):
        """Subtotal, IGV, total siempre ≥ 0."""
        _, sub, igv, total = calcular_item(pu, qty, igv_incluido=True)
        assert sub >= 0
        assert igv >= 0
        assert total >= 0


# ============================================================
# I3: sumar_productos coherencia agregada
# ============================================================

class TestSumarProductosInvariantes:

    @given(productos=productos_list_strategy(min_size=1, max_size=10, allow_zero_price=False))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_total_base_igv_coherentes(self, productos):
        """sum(base) + sum(igv) ≈ sum(total) (con tolerancia por redondeo acumulado)."""
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        # Tolerancia mayor por redondeo de múltiples items
        assert abs((base + igv) - total) < 0.05 + 0.01 * len(productos)

    @given(productos=productos_list_strategy(min_size=1, max_size=5, allow_zero_price=False))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_resultado_no_negativo(self, productos):
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        assert total >= 0 and base >= 0 and igv >= 0


# ============================================================
# I4, I5: construir_detalle_desde_registro defensa
# ============================================================

class TestConstruirDetalleDefensa:

    @given(productos=productos_list_strategy(min_size=1, max_size=5, allow_zero_price=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_con_productos_validos_no_lanza(self, productos):
        """I4: con productos con precio > 0, NUNCA lanza error y suma > 0."""
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        detalle = construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)
        assert len(detalle) == len(productos)
        suma = sum(d["valor_total_item"] for d in detalle)
        assert suma > 0

    @given(monto_total=st.floats(min_value=1.0, max_value=10_000.0))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_precio_cero_con_monto_total_distribuye(self, monto_total):
        """I6: si precio=0 pero monto_total>0, el mapper distribuye y suma ≈ monto_total."""
        reg = {
            "tipo_documento": "factura",
            "igv_incluido": True,
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 0}]),
        }
        detalle = construir_detalle_desde_registro(reg, monto_total, monto_total * 0.847, monto_total * 0.153)
        suma = sum(d["valor_total_item"] for d in detalle)
        assert abs(suma - monto_total) < monto_total * 0.01  # tolerancia 1%

    def test_precio_cero_sin_monto_total_lanza_error(self):
        """I5: si todo precio=0 Y monto_total=0, ValueError SIEMPRE."""
        reg = {
            "tipo_documento": "factura",
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 0}]),
        }
        with pytest.raises(ValueError, match="suma total = 0"):
            construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)

    @given(productos=productos_list_strategy(min_size=1, max_size=5, allow_zero_price=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_coherencia_por_item_siempre(self, productos):
        """Cada item del detalle: sub + igv = total (post-fix coherencia)."""
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        detalle = construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)
        for item in detalle:
            assert abs(item["valor_subtotal_item"] + item["valor_igv"] - item["valor_total_item"]) < 0.01


# ============================================================
# Mismas defensas en compra_mapper
# ============================================================

class TestConstruirDetallesCompraDefensa:

    @given(productos=productos_list_strategy(min_size=1, max_size=5, allow_zero_price=False))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_compra_con_productos_validos_no_lanza(self, productos):
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        detalles = construir_detalles_compra(reg, 0.0, 0.0, 0.0)
        suma = sum(d["valor_total_item"] for d in detalles)
        assert suma > 0

    def test_compra_todos_cero_lanza_error(self):
        reg = {
            "tipo_documento": "factura",
            "productos": json.dumps([{"nombre": "balón", "cantidad": 1, "precio": 0}]),
        }
        with pytest.raises(ValueError, match="suma total = 0"):
            construir_detalles_compra(reg, 0.0, 0.0, 0.0)

    @given(monto_total=st.floats(min_value=1.0, max_value=10_000.0))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_compra_precio_cero_con_monto_distribuye(self, monto_total):
        reg = {
            "tipo_documento": "factura",
            "igv_incluido": True,
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 0}]),
        }
        detalles = construir_detalles_compra(reg, monto_total, monto_total * 0.847, monto_total * 0.153)
        suma = sum(d["valor_total_item"] for d in detalles)
        assert abs(suma - monto_total) < monto_total * 0.01
