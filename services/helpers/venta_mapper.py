from __future__ import annotations

from datetime import date
from typing import Any, Dict, Tuple

from services.helpers.fechas import fecha_ddmmyyyy_a_api
from services.helpers.productos import construir_detalle_desde_registro
from services.helpers.registro_domain import metodo_contado_credito_desde_registro, operacion_desde_registro


def _serie_numero_comprobante(reg: Dict[str, Any]) -> Tuple[Any, Any]:
    """
    Obtiene serie y número del comprobante desde el registro (Redis).
    El extractor guarda solo numero_documento (ej: "B005-00000008"); no guarda "serie" ni "numero".
    La API CREAR_VENTA espera serie (ej: "B005") y numero (solo dígitos del comprobante, nunca
    el documento del cliente). Así evitamos enviar "B005-00000008" como numero y que SUNAT lo
    interprete como DNI.
    Devuelve (serie, numero); numero es int si es numérico, o str de dígitos; serie es str o None.
    """
    serie = reg.get("serie")
    numero = reg.get("numero")
    num_doc = str(reg.get("numero_documento") or "").strip()
    # Si numero parece serie-numero completo (ej. B005-00000008), no usarlo como numero del comprobante
    if numero is not None and str(numero).strip():
        num_str = str(numero).strip()
        if "-" in num_str or (len(num_str) > 9 and not num_str.isdigit()):
            numero = None  # Evitar enviar "B005-00000008" como numero
    if serie is not None and str(serie).strip() and numero is not None:
        # Importante: preservar ceros a la izquierda si numero vino como string (ej: "00001").
        # Para compras (ws_compra.php) el PHP hace bind a integer igualmente.
        if isinstance(numero, str):
            num_str = numero.strip()
            if num_str.isdigit():
                numero = num_str
        return (str(serie).strip(), numero)
    if num_doc and "-" in num_doc:
        parts = num_doc.split("-", 1)
        serie_out = parts[0].strip() if parts[0].strip() else None
        num_part = (parts[1].strip() if len(parts) > 1 else "").strip()
        num_digitos = "".join(c for c in num_part if c.isdigit()) if num_part else ""
        if serie_out and num_digitos:
            # Preservar ceros a la izquierda (ej: "00001").
            return (serie_out, num_digitos)
    return (serie, numero)


def _id_medio_pago_desde_reg(reg: Dict[str, Any]) -> int | None:
    """
    id_medio_pago del catálogo LISTAR_MEDIOS (efectivo, transferencia, yape...).

    Contrato PHP (ventan8n.txt / registrarVentaN8N): `id_medio_pago` es opcional y cuando no aplica
    se espera `null` (ver test_pdf_sunat.py que envía id_medio_pago=None).
    Por eso, si no podemos determinar el medio, devolvemos None y dejamos que el PHP lo convierta en null.
    """
    v = reg.get("id_medio_pago")
    if v is not None and str(v).strip() != "":
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            return None

    # Legado: algunos registros podrían venir con id_metodo_pago
    v = reg.get("id_metodo_pago")
    if v is not None and str(v).strip() != "":
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            # Si viene como texto, intentamos mapear; si no, no forzamos default 1.
            nom_legado = str(v).strip().lower()
            if nom_legado in ("contado", "credito", ""):
                return None
            return FORMA_PAGO_MAP.get(nom_legado)

    # Texto del medio (catálogo)
    nom = str(reg.get("medio_pago") or reg.get("nombre_medio_pago") or "").strip().lower()
    if nom in ("contado", "credito", ""):
        return None

    # Como último recurso, intentar mapear desde forma_pago (compatibilidad muy limitada).
    if not nom:
        nom = str(reg.get("forma_pago") or "").strip().lower()
        if nom in ("contado", "credito", ""):
            return None

    return FORMA_PAGO_MAP.get(nom)


def nro_documento_comprobante(reg: Dict[str, Any]) -> str | None:
    """
    Devuelve el número del comprobante (serie-número) para uso en venta o compra.
    Solo valores que parecen comprobante (contienen "-"); nunca el documento de la entidad (DNI/RUC).
    """
    serie, numero = _serie_numero_comprobante(reg)
    if serie is not None and numero is not None:
        return f"{serie}-{numero}"
    num_doc = str(reg.get("numero_documento") or reg.get("nro_documento") or "").strip()
    if num_doc and "-" in num_doc:
        return num_doc
    return None


TIPO_DOCUMENTO_MAP = {
    "factura": 1,
    "boleta": 2,
    "recibo por honorarios": 3,
    "nota de venta": 7,
    "nota de compra": 7,
}

MONEDA_MAP = {
    "PEN": 1,
    "pen": 1,
    "USD": 2,
    "usd": 2,
}

MONEDA_SIMBOLO = {
    "PEN": "S/",
    "pen": "S/",
    "USD": "$",
    "usd": "$",
}

FORMA_PAGO_MAP = {
    "transferencia": 1,
    "td": 2,
    "tc": 3,
    "billetera_virtual": 4,
    "yape": 4,
    "plin": 4,
}


def construir_sintesis_actual(reg: Dict[str, Any]) -> str:
    """
    Construye un resumen visual del estado actual del registro
    para mostrarlo al usuario en mensajes de WhatsApp.
    Extraído desde FinalizarService para reutilizarlo donde sea necesario.
    """
    if not reg or not isinstance(reg, dict):
        return ""
    lineas = ["📋 *Estado actual del registro*", "━━━━━━━━━━━━━━━━━━━━"]
    op = str(reg.get("operacion") or reg.get("cod_ope") or "").strip().lower()
    operacion = "venta" if op == "ventas" else "compra" if op == "compras" else op
    if operacion == "venta":
        lineas.append("📤 *VENTA*")
    elif operacion == "compra":
        lineas.append("🛒 *COMPRA*")

    tipo_doc = str(reg.get("tipo_documento") or "").strip()
    if tipo_doc:
        lineas.append(f"📄 *Comprobante:* {tipo_doc.capitalize()}")

    num_doc = str(reg.get("numero_documento") or "").strip()
    if num_doc:
        lineas.append(f"📄 *Nro:* {num_doc}")

    if str(reg.get("entidad_nombre") or "").strip():
        lineas.append(f"👤 *Cliente/Proveedor:* {reg.get('entidad_nombre')}")
    if str(reg.get("entidad_numero") or "").strip():
        lineas.append(f"🆔 *Documento:* {reg.get('entidad_numero')}")

    monto = float(reg.get("monto_total") or 0)
    if monto > 0:
        moneda = str(reg.get("moneda") or "PEN").upper()
        simbolo = MONEDA_SIMBOLO.get(moneda, "S/")
        lineas.append(f"💰 *Total:* {simbolo} {monto:.2f}")

    prod = reg.get("productos")
    if isinstance(prod, list) and prod:
        items = ", ".join(
            f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]
        )
        lineas.append(f"📦 *Productos:* {items}")
    elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        lineas.append("📦 *Productos:* (con detalle)")

    if str(reg.get("sucursal") or "").strip():
        lineas.append(f"📍 *Sucursal:* {reg.get('sucursal')}")
    elif reg.get("id_sucursal"):
        lineas.append(f"📍 *Sucursal:* (id {reg.get('id_sucursal')})")

    metodo = metodo_contado_credito_desde_registro(reg)
    if metodo:
        lineas.append(f"💳 *Método de pago (contado/crédito):* {metodo.capitalize()}")

    moneda_str = str(reg.get("moneda") or "").strip()
    if moneda_str:
        lineas.append(f"💵 *Moneda:* {moneda_str}")
    if str(reg.get("fecha_emision") or "").strip():
        lineas.append(f"📅 *Emisión:* {reg.get('fecha_emision')}")
    if str(reg.get("fecha_pago") or "").strip():
        lineas.append(f"📅 *Pago:* {reg.get('fecha_pago')}")
    forma_pago_val = str(reg.get("forma_pago") or "").strip()
    if forma_pago_val:
        lineas.append(f"🏦 *Forma de pago:* {forma_pago_val}")
    mp_cat = str(reg.get("medio_pago") or "").strip()
    # Evitar que el texto muestre "(catálogo)" como etiqueta literal.
    mp_cat_clean = mp_cat.replace("(catálogo)", "").replace("(catalogo)", "").strip()
    if mp_cat_clean and mp_cat_clean.lower() not in ("contado", "credito"):
        lineas.append(f"💰 *Medio de pago:* {mp_cat_clean}")

    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lineas)


def traducir_registro_a_parametros(reg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Traduce un registro de cache a los parámetros básicos necesarios
    para construir el payload de venta/compra.

    Devuelve (operacion_normalizada, dict_parametros).
    """
    operacion = operacion_desde_registro(reg) or ""
    tipo_doc_str = str(reg.get("tipo_documento") or "").strip().lower()
    id_tipo_comprobante = TIPO_DOCUMENTO_MAP.get(tipo_doc_str)

    moneda_str = str(reg.get("moneda") or "").strip()
    id_moneda = MONEDA_MAP.get(moneda_str)
    moneda_simbolo = MONEDA_SIMBOLO.get(moneda_str, "S/")

    metodo = metodo_contado_credito_desde_registro(reg)
    tipo_venta = metodo.capitalize() if metodo in ("contado", "credito") else None

    id_forma_pago = None
    if reg.get("id_forma_pago") is not None:
        try:
            id_forma_pago = int(float(str(reg.get("id_forma_pago")).strip()))
        except (TypeError, ValueError):
            pass
    if id_forma_pago is None and reg.get("id_metodo_pago") is not None:
        try:
            id_forma_pago = int(float(str(reg.get("id_metodo_pago")).strip()))
        except (TypeError, ValueError):
            pass
    if id_forma_pago is None:
        forma_pago_str = str(reg.get("forma_pago") or "").strip().lower()
        try:
            id_forma_pago = int(forma_pago_str)
        except (TypeError, ValueError):
            # Sin default: si no está en el mapa (ej. "bbva"), dejamos None para no violar FK en BD.
            id_forma_pago = FORMA_PAGO_MAP.get(forma_pago_str)

    monto_total = float(reg.get("monto_total") or 0)
    monto_base = float(reg.get("monto_sin_igv") or reg.get("monto_base") or 0)
    # Compatibilidad: algunos registros guardan el IGV como `igv`, otros como `monto_impuesto`.
    monto_igv = float(reg.get("igv") or reg.get("monto_impuesto") or 0)

    entidad_numero = str(reg.get("entidad_numero") or "").strip()
    id_tipo_doc_entidad = 6 if len(entidad_numero) == 11 else 1

    id_cliente = reg.get("entidad_id") or reg.get("id_identificado")
    if id_cliente is not None and id_cliente != "":
        try:
            id_cliente = int(id_cliente)
        except (TypeError, ValueError):
            id_cliente = None

    hoy = date.today().isoformat()
    # SUNAT: fecha de emisión debe ser hoy o hasta 3 días previos; preferimos hoy si no está definida.
    fecha_emision = fecha_ddmmyyyy_a_api(reg.get("fecha_emision")) or hoy
    fecha_pago = fecha_ddmmyyyy_a_api(reg.get("fecha_pago")) or fecha_emision
    fecha_vencimiento = fecha_ddmmyyyy_a_api(reg.get("fecha_vencimiento")) or fecha_pago

    return operacion, {
        "id_tipo_comprobante": id_tipo_comprobante,
        "id_moneda": id_moneda,
        "moneda_simbolo": moneda_simbolo,
        "tipo_venta": tipo_venta,
        "id_forma_pago": id_forma_pago,
        "monto_total": monto_total,
        "monto_base": monto_base,
        "monto_igv": monto_igv,
        "entidad_numero": entidad_numero,
        "id_tipo_doc_entidad": id_tipo_doc_entidad,
        "id_cliente": id_cliente,
        "fecha_emision": fecha_emision,
        "fecha_pago": fecha_pago,
        "fecha_vencimiento": fecha_vencimiento,
    }


def construir_payload_venta(
    reg: Dict[str, Any],
    id_cliente,
    id_from: int,
    id_tipo_comprobante,
    monto_total,
    monto_base,
    monto_igv,
    moneda_simbolo: str,
    id_moneda,
    id_forma_pago,
    tipo_venta,
    fecha_emision: str,
    fecha_pago: str,
    id_usuario: int = 3,
) -> Dict[str, Any]:
    """
    Construye el payload completo CREAR_VENTA para la API externa
    a partir del registro y de los parámetros ya traducidos.
    La API solo recibe id_cliente (obtiene RUC/DNI por id). No se envía numero_documento del registro (es el comprobante); serie/numero van en None y la API asigna el comprobante.
    """
    detalle_items = construir_detalle_desde_registro(reg, monto_total, monto_base, monto_igv)
    # La API solo pide id_cliente; el RUC/DNI lo obtiene por id. No enviar numero_documento del reg (es comprobante B005-00000008).
    # No enviar serie/numero: la API asigna el siguiente comprobante.
    payload = {
        "codOpe": "CREAR_VENTA",
        "id_usuario": int(id_usuario),
        "id_cliente": int(id_cliente) if id_cliente is not None else None,
        "id_sucursal": int(reg.get("id_sucursal") or 14),
        "id_moneda": int(id_moneda) if id_moneda is not None else None,
        "id_forma_pago": int(id_forma_pago) if id_forma_pago is not None else 9,
        "id_medio_pago": _id_medio_pago_desde_reg(reg),
        "tipo_venta": tipo_venta or "Contado",
        "fecha_emision": fecha_emision,
        "fecha_pago": fecha_pago,
        "id_tipo_afectacion": int(reg.get("id_tipo_afectacion", 1)),
        "id_caja_banco": int(reg.get("id_caja_banco", 4)),
        "tipo_facturacion": "facturacion_electronica",
        "id_tipo_comprobante": int(id_tipo_comprobante) if id_tipo_comprobante is not None else None,
        "serie": None,
        "numero": None,
        "observaciones": str(reg.get("observaciones") or "").strip() or None,
        "detalle_items": detalle_items,
    }
    if payload["observaciones"] is None:
        payload.pop("observaciones", None)
    return payload


def construir_payload_venta_n8n(
    reg: Dict[str, Any],
    id_cliente: int,
    id_empresa: int,
    id_usuario: int,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Construye payload para ws_venta.php: codOpe=REGISTRAR_VENTA_N8N (sin token).
    generacion_comprobante=1 para obtener pdf_url y sunat_estado en la respuesta.
    Envía detalle_items (la API acepta detalle_items o detalles).
    """
    detalle_base = construir_detalle_desde_registro(reg, params["monto_total"], params["monto_base"], params["monto_igv"])
    detalle_items: list[Dict[str, Any]] = []
    for i, it in enumerate(detalle_base):
        concepto = str((it.get("concepto") or reg.get("observaciones") or reg.get("observacion") or f"Item {i+1}")).strip() or f"Item {i+1}"
        # No forzar id_catalogo ni id_inventario: si el registro no los tiene, enviar None (como en test_pdf_sunat).
        id_inv = it.get("id_inventario") if it.get("id_inventario") is not None else reg.get("id_inventario")
        id_cat = it.get("id_catalogo") if it.get("id_catalogo") is not None else reg.get("id_catalogo")
        detalle_items.append(
            {
                "id_inventario": id_inv,
                "id_catalogo": id_cat,
                "id_tipo_producto": it.get("id_tipo_producto", reg.get("id_tipo_producto", 2)),
                "cantidad": it.get("cantidad", 1),
                "id_unidad": it.get("id_unidad", reg.get("id_unidad", 1)),
                "precio_unitario": float(it.get("precio_unitario") or 0),
                "concepto": concepto,
                "valor_subtotal_item": float(it.get("valor_subtotal_item") or 0),
                "porcentaje_descuento": float(it.get("porcentaje_descuento") or 0),
                "valor_descuento": float(it.get("valor_descuento") or 0),
                "valor_isc": float(it.get("valor_isc") or 0),
                "valor_igv": float(it.get("valor_igv") or 0),
                "valor_icbper": float(it.get("valor_icbper") or 0),
                "valor_total_item": float(it.get("valor_total_item") or 0),
                "anticipo": float(it.get("anticipo") or 0),
                "otros_cargos": float(it.get("otros_cargos") or 0),
                "otros_tributos": float(it.get("otros_tributos") or 0),
            }
        )

    return {
        "codOpe": "REGISTRAR_VENTA_N8N",
        "empresa_id": int(id_empresa),
        "usuario_id": int(id_usuario),
        "id_cliente": int(id_cliente),
        "id_tipo_comprobante": int(params["id_tipo_comprobante"]) if params.get("id_tipo_comprobante") is not None else None,
        "fecha_emision": params["fecha_emision"],
        "fecha_pago": params["fecha_pago"],
        "id_moneda": int(params["id_moneda"]) if params.get("id_moneda") is not None else 1,
        "id_forma_pago": int(params["id_forma_pago"]) if params.get("id_forma_pago") is not None else 9,
        "id_medio_pago": _id_medio_pago_desde_reg(reg),
        "id_sucursal": int(reg.get("id_sucursal") or 14),
        "tipo_venta": params.get("tipo_venta") or "Contado",
        "observaciones": str(reg.get("observaciones") or reg.get("observacion") or "").strip() or None,
        "enlace_comprobante_pago": str(reg.get("url") or reg.get("enlace_documento") or "").strip() or None,
        "generacion_comprobante": 1,
        "detalle_items": detalle_items,
    }

