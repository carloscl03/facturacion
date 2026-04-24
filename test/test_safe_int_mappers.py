"""
Test robusto de conversiones int en mappers.

Verifica que ningún valor proveniente de Redis (string vacío, None, texto,
float como string, etc.) cause un ValueError/TypeError al construir payloads.

Uso:
  python -m pytest test/test_safe_int_mappers.py -v
  python test/test_safe_int_mappers.py
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import json
from datetime import date

from services.helpers.venta_mapper import (
    _safe_int,
    traducir_registro_a_parametros,
    construir_payload_venta,
    construir_payload_venta_n8n,
    construir_sintesis_actual,
    TIPO_DOCUMENTO_MAP,
)
from services.helpers.compra_mapper import (
    _safe_int as _safe_int_compra,
    construir_payload_compra,
    construir_detalles_compra,
)


# ================================================================
# _safe_int
# ================================================================

class TestSafeInt:
    """Verifica _safe_int con todos los tipos de basura que Redis puede devolver."""

    def test_none(self):
        assert _safe_int(None) is None
        assert _safe_int(None, 5) == 5

    def test_empty_string(self):
        assert _safe_int("") is None
        assert _safe_int("", 10) == 10

    def test_whitespace(self):
        assert _safe_int("  ") is None
        assert _safe_int("  ", 7) == 7

    def test_valid_int(self):
        assert _safe_int(42) == 42
        assert _safe_int("42") == 42

    def test_valid_float_string(self):
        assert _safe_int("3.0") == 3
        assert _safe_int("14.5") == 14

    def test_valid_float(self):
        assert _safe_int(3.0) == 3
        assert _safe_int(14.9) == 14

    def test_negative(self):
        assert _safe_int("-1") == -1
        assert _safe_int(-5) == -5

    def test_text_garbage(self):
        assert _safe_int("abc") is None
        assert _safe_int("abc", 99) == 99

    def test_null_string(self):
        assert _safe_int("null") is None
        assert _safe_int("None") is None

    def test_zero(self):
        assert _safe_int(0) == 0
        assert _safe_int("0") == 0

    def test_bool(self):
        # Redis no devuelve booleans (todo es string), así que "True"/"False"
        # no son convertibles a int. _safe_int devuelve default.
        assert _safe_int("True") is None
        assert _safe_int("False") is None

    def test_both_implementations_match(self):
        """_safe_int de venta_mapper y compra_mapper deben comportarse igual."""
        cases = [None, "", "  ", 42, "42", "3.0", "abc", 0, True, False]
        for val in cases:
            assert _safe_int(val) == _safe_int_compra(val), f"Mismatch for {val!r}"


# ================================================================
# Registro simulado de Redis con campos problemáticos
# ================================================================

def _build_registro_redis_venta_sucio():
    """Simula un registro de Redis con campos vacíos/problemáticos como los que causan int('')."""
    return {
        "operacion": "venta",
        "tipo_documento": "factura",
        "entidad_nombre": "Empresa Test SAC",
        "entidad_numero": "20123456789",
        "entidad_id": "573",
        "id_identificado": "573",
        "identificado": "True",
        "monto_total": "1500.0",
        "monto_sin_igv": "0.0",
        "monto_base": "0.0",
        "monto_impuesto": "0.0",
        "igv": "0.0",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "fecha_emision": "01-04-2026",
        "fecha_pago": "01-04-2026",
        "estado": "5",
        # --- Campos problemáticos (string vacío desde Redis) ---
        "dias_credito": "",
        "nro_cuotas": "",
        "id_sucursal": "14",
        "id_forma_pago": "9",
        "id_medio_pago": "",
        "id_tipo_afectacion": "",
        "id_caja_banco": "",
        "productos": json.dumps([
            {"nombre": "Laptop", "cantidad": 1, "precio_unitario": 1500, "total_item": 1500}
        ]),
        "url": "",
        "observacion": "",
        "numero_documento": "",
        "producto_pendiente": "",
    }


def _build_registro_redis_compra_sucio():
    """Simula un registro de compra con todos los campos vacíos problemáticos."""
    return {
        "operacion": "compra",
        "tipo_documento": "recibo por honorarios",
        "entidad_nombre": "Proveedor Test SAC",
        "entidad_numero": "20999999994",
        "entidad_id": "233",
        "id_identificado": "233",
        "identificado": "True",
        "monto_total": "2000.0",
        "monto_sin_igv": "0.0",
        "monto_base": "0.0",
        "monto_impuesto": "0.0",
        "igv": "0.0",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "fecha_emision": "31-03-2026",
        "fecha_pago": "31-03-2026",
        "estado": "5",
        "numero_documento": "E001-00018",
        # --- Campos problemáticos ---
        "dias_credito": "",
        "nro_cuotas": "",
        "id_sucursal": "2",
        "id_forma_pago": "",
        "id_medio_pago": "",
        "id_centro_costo": "3",
        "id_tipo_afectacion": "",
        "id_caja_banco": "",
        "id_tipo_compra_gasto": "",
        "forma_pago": "Transferencia Bancaria",
        "centro_costo": "Recursos Humanos",
        "sucursal": "Oficina Principal",
        "productos": json.dumps([
            {"nombre": "Desarrollo de Software", "cantidad": 1, "precio_unitario": 2000, "total_item": 2000}
        ]),
        "url": "https://example.com/doc.pdf",
        "observacion": "",
        "producto_pendiente": "",
    }


def _build_registro_todos_none():
    """Registro con valores None y vacíos en todos los campos opcionales."""
    return {
        "operacion": "venta",
        "tipo_documento": "boleta",
        "entidad_nombre": "Juan Perez",
        "entidad_numero": "12345678",
        "entidad_id": None,
        "monto_total": "100",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "fecha_emision": "01-04-2026",
        "fecha_pago": "01-04-2026",
        "estado": "5",
        "dias_credito": None,
        "nro_cuotas": None,
        "id_sucursal": None,
        "id_forma_pago": None,
        "id_medio_pago": None,
        "productos": "[]",
    }


def _build_registro_credito():
    """Registro con crédito y cuotas válidos."""
    return {
        "operacion": "compra",
        "tipo_documento": "factura",
        "entidad_nombre": "Proveedor XYZ",
        "entidad_numero": "20987654321",
        "entidad_id": "100",
        "monto_total": "5000.0",
        "moneda": "USD",
        "metodo_pago": "credito",
        "dias_credito": "30",
        "nro_cuotas": "3",
        "fecha_emision": "01-04-2026",
        "fecha_pago": "01-05-2026",
        "estado": "5",
        "id_sucursal": "2",
        "id_forma_pago": "9",
        "id_medio_pago": "1",
        "id_centro_costo": "3",
        "productos": json.dumps([
            {"nombre": "Servicio", "cantidad": 1, "precio_unitario": 5000, "total_item": 5000}
        ]),
    }


# ================================================================
# traducir_registro_a_parametros
# ================================================================

class TestTraducirRegistro:
    """Verifica que traducir_registro_a_parametros no explote con datos sucios."""

    def test_venta_con_campos_vacios(self):
        reg = _build_registro_redis_venta_sucio()
        operacion, params = traducir_registro_a_parametros(reg)
        assert operacion == "venta"
        assert params["id_tipo_comprobante"] == 1  # factura
        assert params["id_moneda"] == 1  # PEN
        assert params["monto_total"] == 1500.0
        assert isinstance(params["id_cliente"], int)
        assert params["id_cliente"] == 573

    def test_compra_honorarios_con_campos_vacios(self):
        reg = _build_registro_redis_compra_sucio()
        operacion, params = traducir_registro_a_parametros(reg)
        assert operacion == "compra"
        assert params["id_tipo_comprobante"] == 3  # recibo por honorarios
        assert params["monto_total"] == 2000.0

    def test_registro_con_nones(self):
        reg = _build_registro_todos_none()
        operacion, params = traducir_registro_a_parametros(reg)
        assert operacion == "venta"
        assert params["id_tipo_comprobante"] == 2  # boleta
        assert params["id_cliente"] is None  # entidad_id=None

    def test_registro_credito(self):
        reg = _build_registro_credito()
        operacion, params = traducir_registro_a_parametros(reg)
        assert operacion == "compra"
        assert params["tipo_venta"] == "Credito"


# ================================================================
# construir_payload_venta (CREAR_VENTA)
# ================================================================

class TestPayloadVenta:
    def test_no_explota_con_campos_vacios(self):
        reg = _build_registro_redis_venta_sucio()
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_venta(
            reg=reg,
            id_cliente=573,
            id_from=1,
            id_tipo_comprobante=params["id_tipo_comprobante"],
            monto_total=params["monto_total"],
            monto_base=params["monto_base"],
            monto_igv=params["monto_igv"],
            moneda_simbolo=params["moneda_simbolo"],
            id_moneda=params["id_moneda"],
            id_forma_pago=params["id_forma_pago"],
            tipo_venta=params["tipo_venta"],
            fecha_emision=params["fecha_emision"],
            fecha_pago=params["fecha_pago"],
        )
        assert payload["codOpe"] == "CREAR_VENTA"
        assert payload["id_cliente"] == 573
        assert payload["id_sucursal"] == 14
        assert isinstance(payload["detalle_items"], list)
        assert len(payload["detalle_items"]) > 0


# ================================================================
# construir_payload_venta_n8n (REGISTRAR_VENTA_N8N)
# ================================================================

class TestPayloadVentaN8N:
    def test_no_explota_con_campos_vacios(self):
        reg = _build_registro_redis_venta_sucio()
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_venta_n8n(
            reg=reg,
            id_cliente=573,
            id_empresa=1,
            id_usuario=3,
            params=params,
        )
        assert payload["codOpe"] == "REGISTRAR_VENTA_N8N"
        assert payload["id_cliente"] == 573
        assert isinstance(payload["detalle_items"], list)

    def test_con_nones(self):
        reg = _build_registro_todos_none()
        _, params = traducir_registro_a_parametros(reg)
        # id_cliente None: no debería explotar int(None)
        payload = construir_payload_venta_n8n(
            reg=reg,
            id_cliente=1,
            id_empresa=1,
            id_usuario=3,
            params=params,
        )
        assert payload["codOpe"] == "REGISTRAR_VENTA_N8N"


# ================================================================
# construir_payload_compra (REGISTRAR_COMPRA)
# ================================================================

class TestPayloadCompra:
    def test_no_explota_con_campos_vacios(self):
        """El bug original: dias_credito='' y nro_cuotas='' causaban int('')."""
        reg = _build_registro_redis_compra_sucio()
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_compra(reg, params, id_from=1)
        assert payload["codOpe"] == "REGISTRAR_COMPRA"
        assert payload["id_proveedor"] == 233
        assert payload["dias_credito"] == 30  # default cuando es string vacío
        assert payload["cuotas"] == 1  # default cuando es string vacío
        assert payload["id_centro_costo"] == 3
        assert isinstance(payload["detalles"], list)
        assert len(payload["detalles"]) > 0

    def test_credito_con_valores_validos(self):
        reg = _build_registro_credito()
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_compra(reg, params, id_from=1)
        assert payload["tipo_compra"] == "Crédito"
        assert payload["dias_credito"] == 30
        assert payload["cuotas"] == 3

    def test_campos_opcionales_none(self):
        reg = _build_registro_redis_compra_sucio()
        reg["id_tipo_afectacion"] = None
        reg["id_caja_banco"] = None
        reg["id_tipo_compra_gasto"] = None
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_compra(reg, params, id_from=1)
        # Campos opcionales con None no deben estar en el payload
        assert "id_tipo_afectacion" not in payload or payload.get("id_tipo_afectacion") is None
        assert "id_caja_banco" not in payload or payload.get("id_caja_banco") is None

    def test_campos_opcionales_string_vacio(self):
        """String vacío debe tratarse como None, no explotar."""
        reg = _build_registro_redis_compra_sucio()
        reg["id_tipo_afectacion"] = ""
        reg["id_caja_banco"] = ""
        reg["id_centro_costo"] = ""
        reg["id_tipo_compra_gasto"] = ""
        _, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_compra(reg, params, id_from=1)
        assert payload["codOpe"] == "REGISTRAR_COMPRA"  # No explotó


# ================================================================
# construir_detalles_compra (sin IGV para honorarios)
# ================================================================

class TestDetallesCompra:
    def test_honorarios_sin_igv(self):
        reg = _build_registro_redis_compra_sucio()
        detalles = construir_detalles_compra(reg, 2000.0, 0.0, 0.0)
        assert len(detalles) == 1
        d = detalles[0]
        assert d["valor_igv"] == 0.0
        assert d["valor_total_item"] == 2000.0

    def test_factura_con_igv(self):
        reg = _build_registro_credito()  # factura
        detalles = construir_detalles_compra(reg, 5000.0, 4237.29, 762.71)
        d = detalles[0]
        # precio_unitario es BASE (sin IGV) con alta precisión; sub/igv/total precalculados
        assert abs(d["precio_unitario"] - 4237.29) < 0.01
        assert d["valor_subtotal_item"] == 4237.29
        assert d["valor_igv"] == 762.71
        assert d["valor_total_item"] == 5000.0


# ================================================================
# construir_sintesis_actual
# ================================================================

class TestSintesisActual:
    def test_no_explota_con_registro_sucio(self):
        reg = _build_registro_redis_venta_sucio()
        texto = construir_sintesis_actual(reg)
        assert "VENTA" in texto
        assert "1,500" in texto or "1500" in texto

    def test_registro_vacio(self):
        texto = construir_sintesis_actual({})
        assert texto == ""

    def test_registro_none(self):
        texto = construir_sintesis_actual(None)
        assert texto == ""


# ================================================================
# TIPO_DOCUMENTO_MAP
# ================================================================

class TestTipoDocumentoMap:
    def test_todos_los_tipos(self):
        assert TIPO_DOCUMENTO_MAP["factura"] == 1
        assert TIPO_DOCUMENTO_MAP["boleta"] == 2
        assert TIPO_DOCUMENTO_MAP["recibo por honorarios"] == 3
        assert TIPO_DOCUMENTO_MAP["nota de venta"] == 7
        assert TIPO_DOCUMENTO_MAP["nota de compra"] == 7


# ================================================================
# Caso real: el bug original de producción
# ================================================================

class TestBugOriginalProduccion:
    """Reproduce exactamente el error que ocurrió en producción:
    POST /finalizar-operacion con dias_credito="" y nro_cuotas="" en Redis.
    """

    def test_compra_honorarios_redis_real(self):
        """Datos exactos del HGETALL que causó el crash."""
        reg = {
            "monto_total": 2000.0,
            "fecha_emision": "31-03-2026",
            "url": "https://maravia-uploads.s3.us-east-1.amazonaws.com/uploads/whatsapp/1/documentos/rhe-marzo.pdf",
            "entidad_id": 233,
            "forma_pago": "Transferencia Bancaria",
            "centro_costo": "Recursos Humanos",
            "sucursal": "Oficina Principal",
            "opciones_actuales": [],
            "ultima_pregunta": "datos_confirmados",
            "tipo_documento": "recibo por honorarios",
            "fecha_pago": "31-03-2026",
            "numero_documento": "E001-00018",
            "monto_base": 0.0,
            "id_sucursal": 2,
            "moneda": "PEN",
            "nro_cuotas": "",       # <-- el campo problemático
            "entidad_nombre": "Proveedor Test SAC",
            "id_centro_costo": 3,
            "operacion": "compra",
            "estado": 5,
            "id_forma_pago": 9,
            "id_identificado": 233,
            "monto_impuesto": 0.0,
            "metodo_pago": "contado",
            "igv": 0.0,
            "identificado": "True",
            "monto_sin_igv": 0.0,
            "dias_credito": "",     # <-- el campo problemático
            "productos": [
                {"nombre": "Desarrollo de Software", "cantidad": 1, "precio": 2000.0,
                 "id_catalogo": 3088, "id_unidad": 1, "sku": "", "precio_unitario": 2000.0,
                 "total_item": 2000.0}
            ],
            "entidad_numero": 20999999994,
        }
        # Antes del fix esto lanzaba: ValueError: invalid literal for int() with base 10: ''
        operacion, params = traducir_registro_a_parametros(reg)
        payload = construir_payload_compra(reg, params, id_from=1)

        assert payload["codOpe"] == "REGISTRAR_COMPRA"
        assert payload["dias_credito"] == 30    # default seguro, no crash
        assert payload["cuotas"] == 1           # default seguro, no crash
        assert payload["id_proveedor"] == 233
        assert payload["id_tipo_comprobante"] == 3  # recibo por honorarios
        assert payload["id_centro_costo"] == 3
        assert payload["id_sucursal"] == 2
        assert isinstance(payload["detalles"], list)
        assert payload["detalles"][0]["valor_igv"] == 0.0  # sin IGV para honorarios
        assert payload["detalles"][0]["valor_total_item"] == 2000.0


# ================================================================
# Ejecución directa
# ================================================================

def _run_all():
    """Ejecuta todos los tests sin pytest."""
    clases = [
        TestSafeInt, TestTraducirRegistro, TestPayloadVenta,
        TestPayloadVentaN8N, TestPayloadCompra, TestDetallesCompra,
        TestSintesisActual, TestTipoDocumentoMap, TestBugOriginalProduccion,
    ]
    total = 0
    ok = 0
    fail = 0
    for cls in clases:
        instance = cls()
        metodos = [m for m in dir(instance) if m.startswith("test_")]
        for m in metodos:
            total += 1
            nombre = f"{cls.__name__}.{m}"
            try:
                getattr(instance, m)()
                print(f"  PASS  {nombre}")
                ok += 1
            except Exception as e:
                print(f"  FAIL  {nombre}: {e}")
                fail += 1
    print(f"\n{'='*50}")
    print(f"Total: {total} | Pass: {ok} | Fail: {fail}")
    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(_run_all())
