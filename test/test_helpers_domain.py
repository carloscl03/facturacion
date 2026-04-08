from services.helpers.registro_domain import (
    calcular_estado,
    normalizar_documento_entidad,
    obtener_estado,
    operacion_desde_registro,
    operacion_normalizada,
    opciones_completas,
)
from services.helpers.opciones_domain import (
    CAMPOS_ESTADO2,
    lista_para_redis,
    normalizar_opciones_actuales,
    siguiente_campo_pendiente,
)
from services.helpers.productos import construir_detalle_desde_registro, productos_a_str
from services.helpers.venta_mapper import (
    FORMA_PAGO_MAP,
    MONEDA_MAP,
    TIPO_DOCUMENTO_MAP,
    construir_sintesis_actual,
    construir_payload_venta,
    traducir_registro_a_parametros,
)


def test_operacion_normalizada_variantes():
    assert operacion_normalizada("ventas") == "venta"
    assert operacion_normalizada("compras") == "compra"
    assert operacion_normalizada("venta") == "venta"
    assert operacion_normalizada("compra") == "compra"
    assert operacion_normalizada("otra") is None
    assert operacion_normalizada(None) is None


def test_normalizar_documento_entidad_rechaza_serie_comprobante():
    assert normalizar_documento_entidad("EB01-4") == ""
    assert normalizar_documento_entidad("F001-00005678") == ""
    assert normalizar_documento_entidad("20999999993") == "20999999993"
    assert normalizar_documento_entidad("12345678") == "12345678"
    assert normalizar_documento_entidad("") == ""


def test_operacion_desde_registro_prioriza_operacion_y_cod_ope():
    reg = {"operacion": "venta"}
    assert operacion_desde_registro(reg) == "venta"

    reg = {"cod_ope": "compras"}
    assert operacion_desde_registro(reg) == "compra"

    reg = {}
    assert operacion_desde_registro(reg) is None


def test_obtener_estado_y_opciones_completas():
    assert obtener_estado(None) == 0
    assert obtener_estado({"estado": "3"}) == 3
    assert obtener_estado({"paso_actual": 2}) == 2
    assert obtener_estado({"estado": "x"}) == 0

    reg = {}
    assert opciones_completas(reg) is False
    reg = {"id_sucursal": 1, "forma_pago": "Contado", "id_medio_pago": 1}
    assert opciones_completas(reg) is True
    reg_compra = {
        "operacion": "compra",
        "id_sucursal": 1,
        "id_centro_costo": 9,
        "forma_pago": "Contado",
        "id_medio_pago": 2,
    }
    assert opciones_completas(reg_compra) is True
    assert opciones_completas({"operacion": "compra", "id_sucursal": 1, "forma_pago": "x", "id_medio_pago": 1}) is False


def test_calcular_estado_sin_operacion_es_cero():
    datos = {}
    assert calcular_estado(datos) == 0

    datos["operacion"] = "venta"
    assert calcular_estado(datos) == 1


def test_calcular_estado_con_campos_obligatorios():
    datos = {
        "operacion": "compra",
        "monto_total": 100,
        "entidad_nombre": "Cliente",
        "tipo_documento": "factura",
        "moneda": "PEN",
        "metodo_pago": "contado",
    }
    assert calcular_estado(datos) == 3

    datos["monto_total"] = 0
    assert calcular_estado(datos) == 2

    # Sin metodo_pago no llega a estado 3
    datos["monto_total"] = 100
    datos.pop("metodo_pago", None)
    assert calcular_estado(datos) == 2

    # Con crédito exige dias_credito y nro_cuotas para estado 3
    datos["metodo_pago"] = "credito"
    assert calcular_estado(datos) == 2
    datos["dias_credito"] = 30
    datos["nro_cuotas"] = 3
    assert calcular_estado(datos) == 3


def test_siguiente_campo_pendiente_respeta_orden_y_parametros():
    reg = {}
    assert siguiente_campo_pendiente(reg, tiene_parametros=True) == "sucursal"

    # Sin operación o compra: tras sucursal sigue centro_costo (si hay parámetros)
    reg = {"id_sucursal": 1}
    assert siguiente_campo_pendiente(reg, tiene_parametros=True) == "centro_costo"
    assert siguiente_campo_pendiente(reg, tiene_parametros=False) == "forma_pago"

    # Venta: no se pide centro de costo; tras sucursal sigue forma_pago
    reg = {"id_sucursal": 1, "operacion": "venta"}
    assert siguiente_campo_pendiente(reg, tiene_parametros=True) == "forma_pago"

    reg = {"id_sucursal": 1, "operacion": "venta", "forma_pago": "Contado", "id_forma_pago": 1}
    assert siguiente_campo_pendiente(reg, tiene_parametros=True) == "medio_catalogo"

    reg = {"id_sucursal": 1, "id_centro_costo": 2, "forma_pago": "Contado", "id_forma_pago": 1, "id_medio_pago": 10}
    assert siguiente_campo_pendiente(reg, tiene_parametros=True) is None


def test_lista_para_redis_y_normalizar_opciones_actuales():
    raw = [{"id": 1, "nombre": "Uno"}, 2, "tres"]
    lista = lista_para_redis(raw)
    assert lista == [
        {"id": 1, "nombre": "Uno"},
        {"id": 2, "nombre": "2"},
        {"id": "tres", "nombre": "tres"},
    ]

    json_str = '[{"id": 1, "nombre": "Uno"}]'
    norm = normalizar_opciones_actuales(json_str)
    assert norm == [{"id": 1, "nombre": "Uno"}]
    assert normalizar_opciones_actuales(None) == []


def test_productos_a_str_y_construir_detalle_desde_registro_sin_productos():
    assert productos_a_str([]) == "[]"

    reg = {"id_unidad": 1, "id_inventario": 7}
    detalle = construir_detalle_desde_registro(reg, monto_total=118, monto_base=100, monto_igv=18)
    assert len(detalle) == 1
    item = detalle[0]
    assert item["cantidad"] == 1
    # precio_unitario es BASE (sin IGV) — PHP recalcula sub, igv y total
    assert item["precio_unitario"] == 100.0
    assert item["valor_total_item"] == 100.0


def test_traducir_registro_a_parametros_y_payload_venta_basico():
    reg = {
        "operacion": "venta",
        "tipo_documento": "factura",
        "moneda": "PEN",
        "metodo_pago": "contado",
        "forma_pago": "transferencia",
        "monto_total": 118,
        "monto_sin_igv": 100,
        "igv": 18,
        "entidad_numero": "20123456789",
        "entidad_id": 10,
        "fecha_emision": "01-01-2026",
        "fecha_pago": "02-01-2026",
        "id_sucursal": 14,
    }

    operacion, params = traducir_registro_a_parametros(reg)
    assert operacion == "venta"
    assert params["id_tipo_comprobante"] == TIPO_DOCUMENTO_MAP["factura"]
    assert params["id_moneda"] == MONEDA_MAP["PEN"]
    assert params["id_forma_pago"] == FORMA_PAGO_MAP["transferencia"]
    assert params["id_tipo_doc_entidad"] == 6  # RUC

    payload = construir_payload_venta(
        reg,
        id_cliente=10,
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
    assert payload["id_cliente"] == 10
    assert payload["id_sucursal"] == 14
    assert payload["detalle_items"]


def test_construir_sintesis_actual_minimo():
    reg = {
        "operacion": "venta",
        "tipo_documento": "factura",
        "numero_documento": "F001-123",
        "entidad_nombre": "Cliente X",
        "entidad_numero": "20123456789",
        "monto_total": 100,
        "moneda": "PEN",
    }
    texto = construir_sintesis_actual(reg)
    assert "VENTA" in texto
    assert "Cliente X" in texto
    assert "S/" in texto

