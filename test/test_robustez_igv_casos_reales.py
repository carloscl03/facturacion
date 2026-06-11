"""
Tests de robustez para fixes IGV — cubre casos reales que dispararon tickets:

- #232 TAMBO: factura chip claro S/10 que el bot infló a S/11.80
- #339 ARAUCO: boleta EB01-75 servicio incubadora S/2100 que el bot dejó en S/1779.66

Valida:
1. calcular_item produce subtotal+igv=total siempre
2. _extraer_hint_desde_json_visión detecta JSON visión y emite hint correcto
3. construir_detalle_desde_registro maneja correctamente igv_incluido en ambas direcciones
4. sumar_productos cuadra con suma de calcular_item por item

Correr: pytest test/test_robustez_igv_casos_reales.py -v
"""
import json
import sys
import os
from decimal import Decimal

_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from services.helpers.igv import calcular_item, sumar_productos, calcular_igv, es_tipo_sin_igv
from services.helpers.productos import construir_detalle_desde_registro
from services.helpers.compra_mapper import construir_detalles_compra


# ============================================================
# 1. calcular_item — coherencia base→IGV→total
# ============================================================

class TestCalcularItemRobustez:
    def test_caso_tambo_chip_10_soles_con_igv(self):
        """Usuario dice 'chip 10 soles' y el precio incluye IGV (caso #232)."""
        pu_b, sub, igv, total = calcular_item(10.0, 1, igv_incluido=True)
        assert abs(total - 10.0) < 0.01, f"total esperado 10, recibido {total}"
        assert abs(sub - 8.47) < 0.01
        assert abs(igv - 1.53) < 0.01
        assert abs(sub + igv - total) < 0.01, "incoherencia sub+igv != total"

    def test_caso_tambo_chip_10_soles_sin_igv_explicito(self):
        """Usuario dice '10 soles sin IGV' → precio es base, total=11.80."""
        pu_b, sub, igv, total = calcular_item(10.0, 1, igv_incluido=False)
        assert abs(total - 11.80) < 0.01
        assert abs(sub - 10.0) < 0.01
        assert abs(igv - 1.80) < 0.01

    def test_caso_arauco_boleta_2100_con_igv(self):
        """Boleta EB01-75: total comprobante 2100 (caso #339)."""
        pu_b, sub, igv, total = calcular_item(2100.0, 1, igv_incluido=True)
        assert abs(total - 2100.0) < 0.01
        assert abs(sub - 1779.66) < 0.01
        assert abs(igv - 320.34) < 0.01

    def test_nota_de_venta_sin_igv(self):
        """Nota de venta nunca lleva IGV."""
        pu_b, sub, igv, total = calcular_item(100.0, 5, sin_igv=True)
        assert igv == 0.0
        assert sub == total == 500.0

    def test_alta_cantidad_redondeo(self):
        """30 panes a S/0.50 con IGV — verifica que el redondeo acumulado no rompe coherencia."""
        pu_b, sub, igv, total = calcular_item(0.50, 30, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01

    def test_cantidad_decimal(self):
        """1.5 kg a S/12.30 con IGV."""
        pu_b, sub, igv, total = calcular_item(12.30, 1.5, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01

    def test_precio_muy_pequeno(self):
        """Producto S/0.10 (centavos)."""
        pu_b, sub, igv, total = calcular_item(0.10, 1, igv_incluido=True)
        assert abs(sub + igv - total) < 0.01

    def test_precio_alto(self):
        """Servicio S/50,000 con IGV."""
        pu_b, sub, igv, total = calcular_item(50000.0, 1, igv_incluido=True)
        assert abs(total - 50000.0) < 0.01
        assert abs(sub + igv - total) < 0.01


# ============================================================
# 2. sumar_productos — agregada multi-item
# ============================================================

class TestSumarProductosRobustez:
    def test_caso_arauco_un_item(self):
        productos = [{"nombre": "servicio", "cantidad": 1, "precio_unitario": 2100.0, "igv_incluido": True}]
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        assert abs(total - 2100.0) < 0.01
        assert abs(base - 1779.66) < 0.01

    def test_multi_item_coherencia(self):
        productos = [
            {"nombre": "a", "cantidad": 1, "precio_unitario": 118.0},
            {"nombre": "b", "cantidad": 2, "precio_unitario": 59.0},
            {"nombre": "c", "cantidad": 3, "precio_unitario": 23.6},
        ]
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        assert abs(total - (118.0 + 118.0 + 70.8)) < 0.01
        assert abs(base + igv - total) < 0.02

    def test_mezcla_igv_incluido_por_producto(self):
        """Un producto incluye IGV, otro es base."""
        productos = [
            {"nombre": "incluido", "cantidad": 1, "precio_unitario": 118.0, "igv_incluido": True},
            {"nombre": "base", "cantidad": 1, "precio_unitario": 100.0, "igv_incluido": False},
        ]
        total, base, igv = sumar_productos(productos, igv_incluido=True)
        # incluido: total=118, base=100. base: total=118, base=100. → 236, 200
        assert abs(total - 236.0) < 0.02
        assert abs(base - 200.0) < 0.02


# ============================================================
# 3. construir_detalle_desde_registro — formato payload SUNAT
# ============================================================

class TestConstruirDetalleRobustez:
    def test_caso_tambo_genera_detalle_correcto(self):
        """Registro Redis caso TAMBO debe generar detalle con sub+igv=total."""
        reg = {
            "tipo_documento": "factura",
            "igv_incluido": True,
            "productos": json.dumps([{"nombre": "chip claro", "cantidad": 1, "precio_unitario": 10.0}]),
        }
        detalle = construir_detalle_desde_registro(reg, 10.0, 8.47, 1.53)
        assert len(detalle) == 1
        item = detalle[0]
        assert abs(item["valor_subtotal_item"] + item["valor_igv"] - item["valor_total_item"]) < 0.01
        assert abs(item["valor_total_item"] - 10.0) < 0.01

    def test_caso_arauco_genera_detalle_correcto(self):
        """Registro Redis caso ARAUCO."""
        reg = {
            "tipo_documento": "boleta",
            "igv_incluido": True,
            "productos": json.dumps([{"nombre": "servicio incubadora", "cantidad": 1, "precio_unitario": 2100.0}]),
        }
        detalle = construir_detalle_desde_registro(reg, 2100.0, 1779.66, 320.34)
        assert len(detalle) == 1
        item = detalle[0]
        assert abs(item["valor_total_item"] - 2100.0) < 0.01
        assert abs(item["valor_subtotal_item"] - 1779.66) < 0.01

    def test_nota_de_venta_sin_igv_en_detalle(self):
        reg = {
            "tipo_documento": "nota de venta",
            "productos": json.dumps([{"nombre": "concepto", "cantidad": 1, "precio_unitario": 200.0}]),
        }
        detalle = construir_detalle_desde_registro(reg, 200.0, 200.0, 0.0)
        assert detalle[0]["valor_igv"] == 0.0
        assert abs(detalle[0]["valor_total_item"] - 200.0) < 0.01

    def test_caso_661_compra_balon_gas_distribuye_monto_total(self):
        """Ticket #661 Bug A: usuario dice 'balón de gas total 34', IA pone precio=0.
        Mapper debe distribuir monto_total entre items."""
        reg = {
            "tipo_documento": "nota de compra",
            "productos": json.dumps([{"nombre": "balón de gas", "cantidad": 1, "precio": 0}]),
        }
        detalles = construir_detalles_compra(reg, 34.0, 34.0, 0.0)
        assert detalles[0]["valor_total_item"] > 0, "FIX: total no debe quedar en cero"
        assert abs(detalles[0]["valor_total_item"] - 34.0) < 0.01

    def test_caso_661_venta_filtros_distribuye_monto_total(self):
        """Ticket #661 Bug B: '3 filtros total 83.76', IA pone precio=0.
        Mapper debe distribuir 83.76 entre 3 unidades."""
        reg = {
            "tipo_documento": "boleta",
            "igv_incluido": True,
            "productos": json.dumps([{"nombre": "filtro magic", "cantidad": 3, "precio": 0}]),
        }
        detalle = construir_detalle_desde_registro(reg, 83.76, 70.98, 12.78)
        assert detalle[0]["valor_total_item"] > 0, "FIX: total no debe quedar en cero"
        # Cada filtro debió quedar a ~27.92 con IGV → total item = 83.76
        assert abs(detalle[0]["valor_total_item"] - 83.76) < 0.05

    def test_precio_cero_sin_monto_total_lanza_error(self):
        """Si precio=0 Y monto_total=0, lanzar ValueError (fix #661):
        nunca enviar payload con suma cero a SUNAT/PHP."""
        import pytest
        reg = {
            "tipo_documento": "factura",
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 0}]),
        }
        with pytest.raises(ValueError, match="suma total = 0"):
            construir_detalle_desde_registro(reg, 0.0, 0.0, 0.0)

    def test_compra_precio_cero_sin_monto_total_lanza_error(self):
        """Fix D2 compra: si precio=0 y monto_total=0, ValueError."""
        import pytest
        reg = {
            "tipo_documento": "factura",
            "productos": json.dumps([{"nombre": "balón gas", "cantidad": 1, "precio": 0}]),
        }
        with pytest.raises(ValueError, match="suma total = 0"):
            construir_detalles_compra(reg, 0.0, 0.0, 0.0)


# ============================================================
# 5. FinalizarService._validar_campos — coherencia monto_total vs productos (fix E)
# ============================================================

class TestValidarCamposCoherencia:
    @staticmethod
    def _validar(operacion, reg, params):
        from services.finalizar_service import FinalizarService
        return FinalizarService._validar_campos(operacion, reg, params)

    def _params_base(self, monto=100.0, op="venta"):
        return {
            "monto_total": monto,
            "id_tipo_comprobante": 1,
            "id_moneda": 1,
            "id_cliente": 5,
            "moneda_simbolo": "PEN",
        }

    def test_coherente_no_error(self):
        """monto_total=100, productos suma=100 → ratio 1.0 → OK."""
        reg = {
            "entidad_id": 5,
            "productos": json.dumps([{"nombre": "a", "cantidad": 1, "precio": 100}]),
        }
        errores = self._validar("venta", reg, self._params_base(100.0))
        assert "Inconsistencia" not in " ".join(errores)

    def test_incoherente_error(self):
        """monto_total=100, productos suma=500 → ratio 5 → error."""
        reg = {
            "entidad_id": 5,
            "productos": json.dumps([{"nombre": "a", "cantidad": 1, "precio": 500}]),
        }
        errores = self._validar("venta", reg, self._params_base(100.0))
        assert any("Inconsistencia" in e for e in errores)

    def test_productos_precio_cero_no_bloquea(self):
        """Si productos tienen precio=0 (caso #661), no bloquear acá —
        el mapper redistribuirá monto_total. Solo bloquear si ratio fuera de rango."""
        reg = {
            "entidad_id": 5,
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 0}]),
        }
        errores = self._validar("venta", reg, self._params_base(100.0))
        assert "Inconsistencia" not in " ".join(errores)

    def test_ratio_borde_tolerancia(self):
        """ratio entre 0.5 y 2.0 es OK (tolerancia razonable)."""
        # Productos suma = 60, monto_total = 100 → ratio 0.6 → OK
        reg = {
            "entidad_id": 5,
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 60}]),
        }
        errores = self._validar("venta", reg, self._params_base(100.0))
        assert "Inconsistencia" not in " ".join(errores)
        # Productos suma = 150, monto_total = 100 → ratio 1.5 → OK
        reg["productos"] = json.dumps([{"nombre": "x", "cantidad": 1, "precio": 150}])
        errores = self._validar("venta", reg, self._params_base(100.0))
        assert "Inconsistencia" not in " ".join(errores)

    def test_monto_total_cero_no_evalua_ratio(self):
        """Si monto_total=0, el error 'Monto total' aparece pero no el de Inconsistencia."""
        reg = {
            "entidad_id": 5,
            "productos": json.dumps([{"nombre": "x", "cantidad": 1, "precio": 100}]),
        }
        errores = self._validar("venta", reg, self._params_base(0.0))
        assert "Monto total" in errores
        assert "Inconsistencia" not in " ".join(errores)

    def test_un_item_con_precio_otros_sin_no_redistribuye(self):
        """Si algún producto ya tiene precio, no redistribuir (respeta intención)."""
        reg = {
            "tipo_documento": "factura",
            "igv_incluido": True,
            "productos": json.dumps([
                {"nombre": "a", "cantidad": 1, "precio": 118},
                {"nombre": "b", "cantidad": 1, "precio": 0},
            ]),
        }
        detalle = construir_detalle_desde_registro(reg, 200.0, 169.49, 30.51)
        # No redistribuye porque uno tiene precio. b queda en 0 (es bug del usuario, no del mapper).
        assert abs(detalle[0]["valor_total_item"] - 118.0) < 0.01
        assert detalle[1]["valor_total_item"] == 0.0

    def test_compra_con_3_items(self):
        reg = {
            "tipo_documento": "factura",
            "igv_incluido": True,
            "productos": json.dumps([
                {"nombre": "a", "cantidad": 1, "precio_unitario": 118.0},
                {"nombre": "b", "cantidad": 2, "precio_unitario": 59.0},
                {"nombre": "c", "cantidad": 3, "precio_unitario": 23.6},
            ]),
        }
        detalles = construir_detalles_compra(reg, 306.80, 260.00, 46.80)
        assert len(detalles) == 3
        total_sum = sum(d["valor_total_item"] for d in detalles)
        sub_sum = sum(d["valor_subtotal_item"] for d in detalles)
        igv_sum = sum(d["valor_igv"] for d in detalles)
        # SUNAT validará esto:
        assert abs(sub_sum + igv_sum - total_sum) < 0.02


# ============================================================
# 4. _extraer_hint_desde_json_visión — pre-procesador
# ============================================================

class TestExtraerHintRobustez:
    """Importa la función del extraccion_service. Si no se puede (deps OpenAI),
    los tests se saltan con skip."""

    @staticmethod
    def _import_hint():
        try:
            from services.extraccion_service import _extraer_hint_desde_json_visión
            return _extraer_hint_desde_json_visión
        except (ImportError, ModuleNotFoundError):
            return None

    def test_caso_tambo_json_visión_emite_hint(self):
        fn = self._import_hint()
        if fn is None:
            return  # skip si no se puede importar
        msg = json.dumps({
            "monto_sin_impuesto": 8.47, "impuesto": 1.53, "monto_total": 10,
            "datos_generales": {"serie_comprobante": "F377"},
            "productos": [{"precio_unitario": 10}],
        })
        hint = fn(msg)
        assert hint is not None
        assert "igv_incluido=true" in hint.lower() or "igv_incluido=true" in hint
        assert "factura" in hint.lower()

    def test_texto_plano_usuario_no_genera_hint(self):
        fn = self._import_hint()
        if fn is None:
            return
        assert fn("vendi 5 panes a 3 soles") is None
        assert fn("registrar compra de chip a TAMBO por 10 soles") is None
        assert fn("") is None
        assert fn(None) is None

    def test_json_sin_campos_relevantes_no_genera_hint(self):
        fn = self._import_hint()
        if fn is None:
            return
        assert fn('{"foo": "bar"}') is None
        assert fn('{"productos": []}') is None

    def test_json_visión_solo_serie_B_emite_boleta(self):
        fn = self._import_hint()
        if fn is None:
            return
        msg = json.dumps({
            "monto_sin_impuesto": 100, "impuesto": 18, "monto_total": 118,
            "datos_generales": {"serie_comprobante": "B001"},
        })
        hint = fn(msg)
        assert hint is not None
        assert "boleta" in hint.lower()

    def test_json_invalido_no_rompe(self):
        fn = self._import_hint()
        if fn is None:
            return
        assert fn("{esto no es json valido}") is None
        assert fn("{") is None
