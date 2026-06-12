"""
NIVEL 3 ROBUSTEZ: tests adversariales.

Casos diseñados deliberadamente para romper las defensas. Cubre:
  - Valores extremos: precios muy pequeños, muy grandes, cantidades raras
  - Floats problemáticos: 0.1 + 0.2, denormalizados, infinitos
  - Strings malformados: JSON inválido, productos null, campos vacíos
  - Unicode: nombres con emoji, acentos, RTL
  - Cantidades fraccionarias raras
  - Tipos de datos inesperados (None, "null", "", 0, etc.)
  - Acumulación de redondeo con cientos de items
  - Operaciones con cero en diferentes posiciones

Correr: pytest test/test_adversarial_igv.py -v
"""
from __future__ import annotations

import json
import math

import pytest

from services.helpers.compra_mapper import construir_detalles_compra
from services.helpers.igv import calcular_item, sumar_productos
from services.helpers.productos import construir_detalle_desde_registro


class TestCalcularItemEdgeCases:

    def test_precio_minimo_facturable(self):
        """S/0.01 — mínimo facturable SUNAT."""
        _, sub, igv, total = calcular_item(0.01, 1, igv_incluido=True)
        assert total >= 0
        assert abs(sub + igv - total) < 0.01

    def test_precio_maximo_practico(self):
        """S/10M (servicio caro). No debe overflow."""
        _, sub, igv, total = calcular_item(10_000_000.0, 1, igv_incluido=True)
        assert total == 10_000_000.0
        assert abs(sub + igv - total) < 0.01

    def test_cantidad_fraccion_irracional(self):
        """1/3 kg → cantidad con decimales infinitos."""
        _, sub, igv, total = calcular_item(100.0, 1/3, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01

    def test_floats_problematicos_01_02(self):
        """0.1 + 0.2 = 0.30000000000000004 en float. ¿Decimal arregla?"""
        _, sub, igv, total = calcular_item(0.1, 3, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01
        _, sub, igv, total = calcular_item(0.3, 1, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01

    def test_cantidad_muy_pequena_total_redondea_a_cero(self):
        """precio × cantidad < 0.005 → SUNAT redondea a 0. Es válido aunque raro."""
        _, sub, igv, total = calcular_item(0.01, 0.01, igv_incluido=True)
        assert total >= 0  # puede ser 0
        assert sub + igv == total  # coherencia siempre

    def test_qty_cero_no_explota(self):
        """cantidad = 0 — caso degenerado. No debe explotar."""
        _, sub, igv, total = calcular_item(100.0, 0.0, igv_incluido=True)
        assert sub == 0 and igv == 0 and total == 0

    def test_precio_con_10_decimales(self):
        """Precio base SUNAT 10dp."""
        _, sub, igv, total = calcular_item(8.4745762712, 1, igv_incluido=False)
        assert abs(sub - 8.47) < 0.01

    def test_pi_y_e(self):
        """Constantes matemáticas — coherencia robusta."""
        _, sub, igv, total = calcular_item(math.pi * 100, math.e, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01


class TestSumarProductosAdversarial:

    def test_100_items_redondeo_acumulado(self):
        """100 productos con precio variable — redondeo acumulado no debe disparar."""
        productos = [
            {"nombre": f"p{i}", "cantidad": 1, "precio_unitario": 1.18 + (i * 0.0123)}
            for i in range(100)
        ]
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        # Tolerancia razonable: 0.01 por item
        assert abs((base + igv) - total) < 1.0

    def test_mezcla_extremos(self):
        """Mezcla S/0.01 con S/100K."""
        productos = [
            {"nombre": "barato", "cantidad": 1, "precio_unitario": 0.01},
            {"nombre": "caro", "cantidad": 1, "precio_unitario": 100_000.0},
        ]
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        assert total > 100_000.0
        assert abs((base + igv) - total) < 0.1

    def test_productos_lista_vacia(self):
        """Lista vacía no debe explotar."""
        total, base, igv = sumar_productos([], igv_incluido=True)
        assert total == 0 and base == 0 and igv == 0


class TestConstruirDetalleAdversarial:

    def _reg(self, productos, td="factura", igv_incluido=True):
        return {
            "tipo_documento": td,
            "igv_incluido": igv_incluido,
            "productos": json.dumps(productos),
        }

    def test_producto_nombre_emoji(self):
        productos = [{"nombre": "🍕 pizza familiar", "cantidad": 1, "precio_unitario": 50}]
        detalle = construir_detalle_desde_registro(self._reg(productos), 0.0, 0.0, 0.0)
        assert detalle[0]["concepto"] == "🍕 pizza familiar"

    def test_producto_nombre_unicode_extremo(self):
        productos = [{"nombre": "café ñañez ó ü RTL: עברית", "cantidad": 1, "precio_unitario": 10}]
        detalle = construir_detalle_desde_registro(self._reg(productos), 0.0, 0.0, 0.0)
        assert detalle[0]["valor_total_item"] > 0

    def test_producto_sin_nombre_concepto_vacio(self):
        productos = [{"nombre": "", "cantidad": 1, "precio_unitario": 50}]
        detalle = construir_detalle_desde_registro(self._reg(productos), 0.0, 0.0, 0.0)
        # No debería explotar; concepto puede quedar vacío
        assert detalle[0]["valor_total_item"] > 0

    def test_precio_string_numerico(self):
        """Si la IA pone precio como string."""
        productos = [{"nombre": "x", "cantidad": "2", "precio_unitario": "50.5"}]
        detalle = construir_detalle_desde_registro(self._reg(productos), 0.0, 0.0, 0.0)
        assert detalle[0]["valor_total_item"] > 100

    def test_productos_string_json_invalido(self):
        """Si productos es string que no es JSON válido — pasa lista vacía."""
        reg = {"tipo_documento": "factura", "productos": "{esto no es JSON}"}
        # Sin productos válidos y sin monto_total → mapper trata como sin productos
        with pytest.raises(ValueError):
            # Llama al fallback "sin productos" con monto=0 → ValueError suma cero
            construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)

    def test_productos_es_lista_directa(self):
        """Productos llega como lista (no JSON string)."""
        productos = [{"nombre": "x", "cantidad": 1, "precio_unitario": 100}]
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": productos}
        detalle = construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)
        assert detalle[0]["valor_total_item"] > 0

    def test_50_items_consistencia(self):
        """50 productos diferentes — coherencia por item se mantiene."""
        productos = [
            {"nombre": f"prod_{i}", "cantidad": (i % 5) + 1, "precio_unitario": 10 + i * 0.7}
            for i in range(50)
        ]
        detalle = construir_detalle_desde_registro(self._reg(productos), 0.0, 0.0, 0.0)
        for item in detalle:
            assert abs(item["valor_subtotal_item"] + item["valor_igv"] - item["valor_total_item"]) < 0.01

    def test_nota_con_decimales_no_lleva_igv(self):
        productos = [{"nombre": "concepto", "cantidad": 1, "precio_unitario": 99.99}]
        detalle = construir_detalle_desde_registro(self._reg(productos, td="nota de venta"), 0.0, 0.0, 0.0)
        assert detalle[0]["valor_igv"] == 0
        assert abs(detalle[0]["valor_total_item"] - 99.99) < 0.01

    def test_caso_661_un_item_precio_cero_monto_total_distribuye(self):
        """Caso real ticket #661."""
        productos = [{"nombre": "balón gas", "cantidad": 1, "precio_unitario": 0}]
        detalle = construir_detalle_desde_registro(self._reg(productos), 34.0, 28.81, 5.19)
        assert detalle[0]["valor_total_item"] > 0
        assert abs(detalle[0]["valor_total_item"] - 34.0) < 0.01

    def test_caso_661_multi_item_un_precio_otros_cero_no_distribuye(self):
        """Si AL MENOS un producto tiene precio > 0, NO distribuir (respeta intención usuario)."""
        productos = [
            {"nombre": "a", "cantidad": 1, "precio_unitario": 100},
            {"nombre": "b", "cantidad": 1, "precio_unitario": 0},
        ]
        detalle = construir_detalle_desde_registro(self._reg(productos), 200.0, 169.49, 30.51)
        # a debe quedar con 100, b en 0 (no inventa)
        assert abs(detalle[0]["valor_total_item"] - 100) < 0.01
        assert detalle[1]["valor_total_item"] == 0

    def test_compra_balon_gas_caso_real_661(self):
        productos = [{"nombre": "balón de gas", "cantidad": 1, "precio_unitario": 0}]
        reg = {"tipo_documento": "nota de compra", "productos": json.dumps(productos)}
        detalles = construir_detalles_compra(reg, 34.0, 34.0, 0.0)
        assert abs(detalles[0]["valor_total_item"] - 34.0) < 0.01


class TestAtaquesDeliberados:
    """Casos diseñados para tratar de romper deliberadamente las defensas."""

    def test_bypass_validacion_con_precio_minusculo_no_cero(self):
        """Intentar burlar la defensa poniendo precio=0.0001 (no cero pero ≈0)."""
        productos = [{"nombre": "x", "cantidad": 1, "precio_unitario": 0.0001}]
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        # 0.0001 × 1 → redondea a 0.00. La defensa "suma cero" debe atajarlo.
        with pytest.raises(ValueError, match="suma total = 0"):
            construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)

    def test_burlar_validacion_con_descuento_negativo(self):
        """Descuento negativo no debe inflar el total artificialmente."""
        productos = [{"nombre": "x", "cantidad": 1, "precio_unitario": 100, "valor_descuento": -50}]
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        detalle = construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)
        # El descuento del input no afecta cálculo (lo hace calcular_item, no usa valor_descuento del input)
        assert detalle[0]["valor_total_item"] > 0

    def test_cantidad_negativa(self):
        """Cantidad negativa → resultado coherente pero negativo (la defensa de >0 lo atajaría arriba)."""
        productos = [{"nombre": "x", "cantidad": -1, "precio_unitario": 100}]
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        # Suma negativa → debería ser rechazada por validador suma_total ≤ 0
        with pytest.raises(ValueError, match="suma total"):
            construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)

    def test_inflar_total_con_monto_total_extremo(self):
        """Si bot pone monto_total absurdo, no debe inflar a productos."""
        productos = [{"nombre": "x", "cantidad": 1, "precio_unitario": 100}]
        reg = {"tipo_documento": "factura", "igv_incluido": True, "productos": json.dumps(productos)}
        # monto_total=999999 pero producto vale 100. mapper NO redistribuye porque precio > 0
        detalle = construir_detalle_desde_registro(reg, 999999.0, 0.0, 0.0)
        # Total debe quedar en 100, no inflado a 999999 (respeta precio explícito)
        assert abs(detalle[0]["valor_total_item"] - 100) < 0.01
