"""
Finalizar operación (venta/compra) y, en ventas, enviar CREAR_VENTA a la API para emitir comprobante SUNAT.

Lee campos con nombres naturales desde Redis y los traduce a los IDs que espera la API backend:
- operacion "venta"/"compra" → lógica de flujo
- tipo_documento "factura"→1, "boleta"→2, "nota de venta"→4 → id_tipo_comprobante
- moneda "PEN"→1, "USD"→2 → id_moneda
- medio_pago "contado"/"credito" → tipo_venta "Contado"/"Credito"
- forma_pago "transferencia"→1, "td"→2, "tc"→3, "billetera_virtual"→4 → id_forma_pago
- entidad_numero → inferir tipo: len 8 = DNI (1), len 11 = RUC (6)
- monto_sin_igv → monto_base, igv → monto_impuesto
- fecha_emision / fecha_pago DD-MM-YYYY → YYYY-MM-DD
- banco → id_caja_banco (texto libre por ahora)
- entidad_id → id_cliente
"""
import json

import requests

from config import settings
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository

# --------------- Mapeos de traducción --------------- #

TIPO_DOCUMENTO_MAP = {
    "factura": 1,
    "boleta": 2,
    "recibo": 3,
    "nota de venta": 4,
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
}


def _fecha_a_api(fecha_ddmmyyyy: str | None) -> str | None:
    """DD-MM-YYYY → YYYY-MM-DD. Si no puede convertir, devuelve tal cual."""
    if not fecha_ddmmyyyy or not isinstance(fecha_ddmmyyyy, str):
        return fecha_ddmmyyyy
    f = fecha_ddmmyyyy.strip()
    if len(f) == 10 and f[2] == "-" and f[5] == "-":
        dd, mm, yyyy = f[:2], f[3:5], f[6:]
        return f"{yyyy}-{mm}-{dd}"
    return f


def _construir_sintesis_actual(reg: dict) -> str:
    if not reg or not isinstance(reg, dict):
        return ""
    lineas = ["📋 *Estado actual del registro*", "━━━━━━━━━━━━━━━━━━━━"]
    operacion = (reg.get("operacion") or "").strip().lower()
    if operacion == "venta":
        lineas.append("📤 *VENTA*")
    elif operacion == "compra":
        lineas.append("🛒 *COMPRA*")

    tipo_doc = (reg.get("tipo_documento") or "").strip()
    if tipo_doc:
        lineas.append(f"📄 *Comprobante:* {tipo_doc.capitalize()}")

    num_doc = (reg.get("numero_documento") or "").strip()
    if num_doc:
        lineas.append(f"📄 *Nro:* {num_doc}")

    if (reg.get("entidad_nombre") or "").strip():
        lineas.append(f"👤 *Cliente/Proveedor:* {reg.get('entidad_nombre')}")
    if (reg.get("entidad_numero") or "").strip():
        lineas.append(f"🆔 *Documento:* {reg.get('entidad_numero')}")

    monto = float(reg.get("monto_total") or 0)
    if monto > 0:
        moneda = (reg.get("moneda") or "PEN").upper()
        simbolo = MONEDA_SIMBOLO.get(moneda, "S/")
        lineas.append(f"💰 *Total:* {simbolo} {monto}")

    prod = reg.get("productos")
    if isinstance(prod, list) and prod:
        lineas.append("📦 *Productos:* " + ", ".join(
            f"{p.get('cantidad', 1)} x {p.get('nombre', '')}" for p in prod[:5]
        ))
    elif isinstance(prod, str) and prod.strip() and prod.strip() != "[]":
        lineas.append("📦 *Productos:* (con detalle)")

    if (reg.get("sucursal") or "").strip():
        lineas.append(f"📍 *Sucursal:* {reg.get('sucursal')}")
    elif reg.get("id_sucursal"):
        lineas.append(f"📍 *Sucursal:* (id {reg.get('id_sucursal')})")

    medio = (reg.get("medio_pago") or "").strip().lower()
    if medio in ("contado", "credito"):
        lineas.append(f"💳 *Pago:* {medio.capitalize()}")

    moneda_str = (reg.get("moneda") or "").strip()
    if moneda_str:
        lineas.append(f"💵 *Moneda:* {moneda_str}")
    if (reg.get("fecha_emision") or "").strip():
        lineas.append(f"📅 *Emisión:* {reg.get('fecha_emision')}")
    if (reg.get("banco") or "").strip():
        lineas.append(f"🏦 *Banco:* {reg.get('banco')}")

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

        # --- Traducir campos naturales a IDs --- #
        operacion = (reg.get("operacion") or "").strip().lower()
        tipo_ope_upper = "VENTAS" if operacion == "venta" else "COMPRAS"

        tipo_doc_str = (reg.get("tipo_documento") or "").strip().lower()
        id_tipo_comprobante = TIPO_DOCUMENTO_MAP.get(tipo_doc_str)

        moneda_str = (reg.get("moneda") or "").strip()
        id_moneda = MONEDA_MAP.get(moneda_str)
        moneda_simbolo = MONEDA_SIMBOLO.get(moneda_str, "S/")

        medio_pago = (reg.get("medio_pago") or "").strip().lower()
        tipo_venta = medio_pago.capitalize() if medio_pago in ("contado", "credito") else None

        forma_pago_str = (reg.get("forma_pago") or "").strip().lower()
        id_forma_pago = FORMA_PAGO_MAP.get(forma_pago_str, 9)

        monto_total = float(reg.get("monto_total") or 0)
        monto_base = float(reg.get("monto_sin_igv") or 0)
        monto_igv = float(reg.get("igv") or 0)

        entidad_numero = (reg.get("entidad_numero") or "").strip()
        id_tipo_doc_entidad = 6 if len(entidad_numero) == 11 else 1

        id_cliente = reg.get("entidad_id")

        fecha_emision = _fecha_a_api(reg.get("fecha_emision")) or "2026-03-03"
        fecha_pago = _fecha_a_api(reg.get("fecha_pago")) or fecha_emision

        # --- Validaciones --- #
        errores = []
        if monto_total <= 0:
            errores.append("Monto total")
        if not id_tipo_comprobante:
            errores.append("Tipo de documento (Factura/Boleta)")
        if not id_moneda:
            errores.append("Moneda (PEN/USD)")
        if operacion == "venta" and not id_cliente:
            tiene_datos = (reg.get("entidad_nombre") or "").strip() and entidad_numero
            if not tiene_datos:
                errores.append("Cliente (nombre y documento) para facturar")

        if errores and not (operacion == "venta" and reg.get("entidad_nombre") and entidad_numero):
            sintesis = _construir_sintesis_actual(reg)
            faltan = f"⚠️ *No se puede finalizar.*\n\nFaltan: **{', '.join(errores)}**."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {
                "status": "incompleto",
                "mensaje": mensaje,
                "sintesis_actual": sintesis,
            }

        try:
            if operacion == "venta":
                return self._finalizar_venta(
                    wa_id, reg, id_cliente, id_empresa,
                    id_tipo_comprobante, monto_total, monto_base, monto_igv,
                    moneda_simbolo, id_moneda, id_forma_pago, tipo_venta,
                    fecha_emision, fecha_pago, id_tipo_doc_entidad,
                )

            self._marcar_completado(wa_id, id_empresa)
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✅ *COMPRA REGISTRADA EXITOSAMENTE*\n\n"
                    f"🏢 *Proveedor:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Monto:* {moneda_simbolo} {monto_total}\n"
                    f"📝 *Estado:* Guardado en el historial de compras."
                ),
            }

        except Exception as e:
            return {"status": "error", "mensaje": f"Hubo un fallo técnico: {str(e)}"}

    def _marcar_completado(self, wa_id: str, id_empresa: int) -> None:
        try:
            self._cache.actualizar(wa_id, id_empresa, {"estado": 4})
        except Exception:
            pass

    def _finalizar_venta(
        self,
        wa_id: str,
        reg: dict,
        id_cliente,
        id_empresa: int,
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
        id_tipo_doc_entidad: int,
    ) -> dict:
        if not id_cliente and (reg.get("entidad_nombre") or "").strip() and (reg.get("entidad_numero") or "").strip():
            resp_cli = self._entities.registrar_cliente(reg, id_empresa)
            if resp_cli.get("success") and resp_cli.get("cliente_id"):
                id_cliente = resp_cli["cliente_id"]
            else:
                return {
                    "status": "error",
                    "mensaje": f"❌ No se pudo registrar el cliente: {resp_cli.get('message', 'Error desconocido')}.",
                }

        if id_cliente and (reg.get("entidad_nombre") or reg.get("entidad_numero")):
            self._entities.actualizar_cliente(id_cliente, reg, id_empresa)

        if not id_cliente:
            sintesis = _construir_sintesis_actual(reg)
            faltan = "⚠️ Falta el cliente (nombre y documento). Indica los datos para registrarlo."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {
                "status": "incompleto",
                "mensaje": mensaje,
                "sintesis_actual": sintesis,
            }

        detalle_items = self._construir_detalle(reg, monto_total, monto_base, monto_igv)

        payload_venta = {
            "codOpe": "CREAR_VENTA",
            "id_usuario": reg.get("id_usuario", 3),
            "id_cliente": id_cliente,
            "id_sucursal": reg.get("id_sucursal") or 14,
            "id_moneda": id_moneda,
            "id_forma_pago": id_forma_pago,
            "tipo_venta": tipo_venta or "Contado",
            "fecha_emision": fecha_emision,
            "fecha_pago": fecha_pago,
            "id_tipo_afectacion": reg.get("id_tipo_afectacion", 1),
            "id_caja_banco": reg.get("id_caja_banco", 4),
            "tipo_facturacion": "facturacion_electronica",
            "id_tipo_comprobante": id_tipo_comprobante,
            "detalle_items": detalle_items,
        }

        headers = {"Authorization": f"Bearer {settings.TOKEN_SUNAT}", "Content-Type": "application/json"}
        res_sunat = requests.post(settings.URL_VENTA_SUNAT, json=payload_venta, headers=headers)
        res_json = res_sunat.json()

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
            serie_num = f"{sunat_data.get('serie', 'F001')}-{sunat_data.get('numero', '000')}"
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
            pj = reg.get("productos")
            if isinstance(pj, str):
                productos = json.loads(pj) if pj.strip() else []
            elif isinstance(pj, list):
                productos = pj
        except Exception:
            productos = []

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
