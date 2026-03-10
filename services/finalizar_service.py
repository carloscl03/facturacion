"""
Finalizar operación (venta/compra) y, en ventas, enviar CREAR_VENTA a la API para emitir comprobante SUNAT.

Contrato mínimo API (referencia: test/run_factura_minima.py, doc CREAR_VENTA ws_ventas.php):
- Raíz: id_cliente, id_sucursal, tipo_venta, id_forma_pago, id_moneda, tipo_facturacion, detalle_items.
- Condicional facturado: id_tipo_afectacion, id_tipo_comprobante.
- Fechas: fecha_emision, fecha_pago.
- Caja (pago): id_caja_banco.
- Por ítem: id_inventario, id_tipo_producto, cantidad, id_unidad, precio_unitario,
  valor_subtotal_item, valor_igv, valor_total_item; backend suele exigir porcentaje_descuento/valor_descuento.

Las validaciones de este servicio (monto_total, tipo_comprobante, cliente, tipo_operacion, plazo si crédito)
aseguran que el registro tenga lo necesario para construir ese payload. id_sucursal se asume 14 por defecto
y de momento no se pregunta (en el futuro se podrá solicitar). El preguntador debe pedir solo los datos
obligatorios listados arriba (sin sucursal).
"""
import json

import requests

from config import settings
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository


def _construir_sintesis_actual(reg: dict) -> str:
    """Construye una síntesis de lo que ya está registrado (solo campos con valor)."""
    if not reg or not isinstance(reg, dict):
        return ""
    lineas = ["📋 *Estado actual del registro*", "━━━━━━━━━━━━━━━━━━━━"]
    cod_ope = (reg.get("cod_ope") or "").strip().lower()
    if cod_ope == "ventas":
        lineas.append("📤 *VENTA*")
    elif cod_ope == "compras":
        lineas.append("🛒 *COMPRA*")
    comp = reg.get("comprobante_tipo_nombre") or (
        "Factura" if reg.get("id_comprobante_tipo") == 1 else
        "Boleta" if reg.get("id_comprobante_tipo") == 2 else
        "Recibo" if reg.get("id_comprobante_tipo") == 3 else None
    )
    if comp:
        lineas.append(f"📄 *Comprobante:* {comp}")
    if (reg.get("entidad_nombre") or "").strip():
        lineas.append(f"👤 *Cliente/Proveedor:* {reg.get('entidad_nombre')}")
    if (reg.get("entidad_numero_documento") or "").strip():
        lineas.append(f"🆔 *Documento:* {reg.get('entidad_numero_documento')}")
    if reg.get("monto_total") is not None and float(reg.get("monto_total") or 0) > 0:
        mon = reg.get("moneda_simbolo", "S/")
        lineas.append(f"💰 *Total:* {mon} {reg.get('monto_total')}")
    prod = reg.get("productos_json")
    if isinstance(prod, list) and prod:
        lineas.append("📦 *Productos:* " + ", ".join(
            f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]
        ))
    if isinstance(prod, str) and prod.strip():
        lineas.append("📦 *Productos:* (con detalle)")
    if (reg.get("sucursal_nombre") or "").strip():
        lineas.append(f"📍 *Sucursal:* {reg.get('sucursal_nombre')}")
    elif reg.get("id_sucursal"):
        lineas.append(f"📍 *Sucursal:* (id {reg.get('id_sucursal')})")
    tipo_op = (reg.get("tipo_operacion") or "").strip().lower()
    if tipo_op in ("contado", "credito"):
        lineas.append(f"💳 *Pago:* {tipo_op.capitalize()}")
    if tipo_op == "credito" and (reg.get("plazo_dias") or (reg.get("fecha_vencimiento") or "").strip()):
        if reg.get("plazo_dias"):
            lineas.append(f"🔄 *Plazo:* {reg.get('plazo_dias')} días")
        if (reg.get("fecha_vencimiento") or "").strip():
            lineas.append(f"📅 *Vencimiento:* {reg.get('fecha_vencimiento')}")
    if (reg.get("moneda_nombre") or "").strip():
        lineas.append(f"💵 *Moneda:* {reg.get('moneda_nombre')}")
    if (reg.get("fecha_emision") or "").strip():
        lineas.append(f"📅 *Emisión:* {reg.get('fecha_emision')}")
    lineas.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lineas)


class FinalizarService:
    def __init__(self, cache_repo: CacheRepository, entity_repo: EntityRepository) -> None:
        self._cache = cache_repo
        self._entities = entity_repo

    def ejecutar(self, wa_id: str, id_empresa: int) -> dict:
        registro = self._cache.consultar(wa_id, id_empresa)

        if not registro:
            return {"status": "error", "mensaje": "No hay una operación activa para finalizar."}

        reg = registro
        tipo_ope = str(reg.get("cod_ope", "VENTAS")).upper()
        monto_total = reg.get("monto_total")
        monto_base = reg.get("monto_base")
        monto_igv = reg.get("monto_impuesto")
        tipo_comp = reg.get("id_comprobante_tipo")
        moneda_simbolo = reg.get("moneda_simbolo", "S/")
        id_cliente = reg.get("cliente_id") or reg.get("entidad_id_maestro")

        tipo_operacion = (reg.get("tipo_operacion") or "").strip().lower()
        es_credito = tipo_operacion == "credito"
        tiene_plazo_o_vencimiento = bool(
            reg.get("plazo_dias") or (reg.get("fecha_vencimiento") or "").strip()
        )

        errores = []
        if not monto_total or float(monto_total) <= 0:
            errores.append("Monto total")
        if not tipo_comp:
            errores.append("Tipo de Comprobante (Boleta/Factura)")
        if not reg.get("id_moneda"):
            errores.append("Moneda (Soles/Dólares)")
        if "VENTA" in tipo_ope and not id_cliente:
            tiene_datos_registro = (reg.get("entidad_nombre") or "").strip() and (reg.get("entidad_numero_documento") or "").strip()
            if not tiene_datos_registro:
                errores.append("Cliente (RUC/DNI y nombre) para facturar")
        if not tipo_operacion or tipo_operacion not in ("contado", "credito"):
            errores.append("Tipo de pago (Contado o Crédito)")
        if es_credito and not tiene_plazo_o_vencimiento:
            errores.append("Plazo en días o fecha de vencimiento (operación a crédito)")
        # id_sucursal: por defecto 14; no se pregunta de momento (ver payload más abajo)

        if errores and not ("VENTA" in tipo_ope and (reg.get("entidad_nombre") and reg.get("entidad_numero_documento"))):
            sintesis = _construir_sintesis_actual(reg)
            faltan = f"⚠️ *No se puede finalizar.*\n\nFaltan: **{', '.join(errores)}**."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {
                "status": "incompleto",
                "mensaje": mensaje,
                "sintesis_actual": sintesis,
            }

        try:
            if "VENTA" in tipo_ope:
                return self._finalizar_venta(wa_id, reg, id_cliente, id_empresa, tipo_comp, monto_total, monto_base, monto_igv, moneda_simbolo)

            self._marcar_completado(wa_id, id_empresa)
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✅ *COMPRA REGISTRADA EXITOSAMENTE*\n\n"
                    f"🏢 *Proveedor:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Monto:* {moneda_simbolo} {monto_total}\n"
                    f"📝 *Estado:* Guardado en el historial de {tipo_ope.lower()}."
                ),
            }

        except Exception as e:
            return {"status": "error", "mensaje": f"Hubo un fallo técnico: {str(e)}"}

    def _marcar_completado(self, wa_id: str, id_empresa: int) -> None:
        try:
            self._cache.actualizar(wa_id, id_empresa, {"paso_actual": 4, "is_ready": 1})
        except Exception:
            pass

    def _finalizar_venta(
        self,
        wa_id: str,
        reg: dict,
        id_cliente,
        id_empresa: int,
        tipo_comp,
        monto_total,
        monto_base,
        monto_igv,
        moneda_simbolo: str,
    ) -> dict:
        if not id_cliente and (reg.get("entidad_nombre") or "").strip() and (reg.get("entidad_numero_documento") or "").strip():
            resp_cli = self._entities.registrar_cliente(reg, id_empresa)
            if resp_cli.get("success") and resp_cli.get("cliente_id"):
                id_cliente = resp_cli["cliente_id"]
            else:
                return {
                    "status": "error",
                    "mensaje": f"❌ No se pudo registrar el cliente: {resp_cli.get('message', 'Error desconocido')}.",
                }

        if id_cliente and (reg.get("entidad_nombre") or reg.get("entidad_numero_documento")):
            self._entities.actualizar_cliente(id_cliente, reg, id_empresa)

        if not id_cliente:
            sintesis = _construir_sintesis_actual(reg)
            faltan = "⚠️ Falta el cliente (RUC/DNI y nombre). Indica los datos para registrarlo o búscalos en la base."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {
                "status": "incompleto",
                "mensaje": mensaje,
                "sintesis_actual": sintesis,
            }

        detalle_items = self._construir_detalle(reg, monto_total, monto_base, monto_igv)

        # Payload alineado al mínimo que acepta la API (test/run_factura_minima.py)
        fecha_emision = reg.get("fecha_emision") or "2026-03-03"
        fecha_pago = reg.get("fecha_pago") or fecha_emision
        payload_venta = {
            "codOpe": "CREAR_VENTA",
            "id_usuario": reg.get("id_usuario", 3),
            "id_cliente": id_cliente,
            "id_sucursal": reg.get("id_sucursal") or 14,  # por defecto 14; en el futuro se preguntará
            "id_moneda": reg.get("id_moneda"),
            "id_forma_pago": reg.get("id_forma_pago", 9),
            "tipo_venta": (reg.get("tipo_operacion") or "").strip().lower().capitalize(),  # "contado"|"credito" -> "Contado"|"Credito"
            "fecha_emision": fecha_emision,
            "fecha_pago": fecha_pago,
            "id_tipo_afectacion": reg.get("id_tipo_afectacion", 1),
            "id_caja_banco": reg.get("id_caja_banco", 4),
            "tipo_facturacion": "facturacion_electronica",
            "id_tipo_comprobante": tipo_comp,
            "detalle_items": detalle_items,
        }

        headers = {"Authorization": f"Bearer {settings.TOKEN_SUNAT}", "Content-Type": "application/json"}
        res_sunat = requests.post(settings.URL_VENTA_SUNAT, json=payload_venta, headers=headers)
        res_json = res_sunat.json()

        # Extraer URL del PDF: sunat.sunat_data primero; luego sunat.data.payload.pdf; luego data.url_pdf
        sunat_obj = res_json.get("sunat") or {}
        sunat_data = sunat_obj.get("sunat_data") or {}
        payload = (sunat_obj.get("data") or {}).get("payload") or {}
        payload_pdf = payload.get("pdf") if isinstance(payload.get("pdf"), dict) else {}
        url_pdf = (
            sunat_data.get("sunat_pdf")
            or sunat_data.get("enlace_documento")
            or payload_pdf.get("ticket")
            or payload_pdf.get("a4")
            or res_json.get("data", {}).get("url_pdf")
        )
        if url_pdf and res_json.get("success"):
            self._marcar_completado(wa_id, id_empresa)
            serie_num = f"{sunat_data.get('serie', reg.get('comprobante_serie', 'F001'))}-{sunat_data.get('numero', reg.get('comprobante_numero', '000'))}"
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✨ *¡VENTA REGISTRADA EN SUNAT!*\n\n"
                    f"👤 *Cliente:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Total:* {moneda_simbolo} {monto_total}\n"
                    f"📄 *Documento:* {serie_num}\n\n"
                    f"🔗 *Descargar Comprobante:* {url_pdf}"
                ),
            }

        sintesis = _construir_sintesis_actual(reg)
        error_sunat = f"❌ Error SUNAT: {res_json.get('message') or res_json.get('error') or 'No se pudo generar el PDF.'}"
        mensaje = f"{sintesis}\n\n{error_sunat}" if sintesis else error_sunat
        return {
            "status": "error",
            "mensaje": mensaje,
            "sintesis_actual": sintesis,
        }

    def _construir_detalle(self, reg: dict, monto_total, monto_base, monto_igv) -> list:
        productos = []
        try:
            pj = reg.get("productos_json")
            if isinstance(pj, str):
                productos = json.loads(pj) if pj.strip() else []
            elif isinstance(pj, list):
                productos = pj
        except Exception:
            productos = []

        # Campos por ítem según contrato mínimo API (id_unidad, descuentos; ver run_factura_minima)
        id_unidad = reg.get("id_unidad", 1)
        if not productos:
            mt = float(monto_total)
            mb = float(monto_base or mt / 1.18)
            mi = float(monto_igv or mt - mb)
            return [{
                "id_inventario": reg.get("id_inventario", 7),
                "id_tipo_producto": 2,
                "cantidad": 1,
                "id_unidad": id_unidad,
                "precio_unitario": mt,
                "porcentaje_descuento": 0,
                "valor_descuento": 0,
                "valor_subtotal_item": round(mb, 2),
                "valor_igv": round(mi, 2),
                "valor_total_item": mt,
            }]

        detalle = []
        for p in productos:
            qty = float(p.get("cantidad", 1))
            pu = float(p.get("precio_unitario") or p.get("precio", 0))
            total_item = float(p.get("total_item", qty * pu))
            subtotal = total_item / 1.18
            igv = total_item - subtotal
            detalle.append({
                "id_inventario": reg.get("id_inventario", 7),
                "id_tipo_producto": 2,
                "cantidad": qty,
                "id_unidad": p.get("id_unidad", id_unidad),
                "precio_unitario": pu,
                "porcentaje_descuento": float(p.get("porcentaje_descuento", 0)),
                "valor_descuento": float(p.get("valor_descuento", 0)),
                "valor_subtotal_item": round(subtotal, 2),
                "valor_igv": round(igv, 2),
                "valor_total_item": round(total_item, 2),
            })
        return detalle
