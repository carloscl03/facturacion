import json

import requests

from config import settings
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository


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

        errores = []
        if not monto_total or float(monto_total) <= 0:
            errores.append("Monto total")
        if not tipo_comp:
            errores.append("Tipo de Comprobante (Boleta/Factura)")
        if "VENTA" in tipo_ope and not id_cliente:
            tiene_datos_registro = (reg.get("entidad_nombre") or "").strip() and (reg.get("entidad_numero_documento") or "").strip()
            if not tiene_datos_registro:
                errores.append("Cliente (RUC/DNI y nombre) para facturar")

        if errores and not ("VENTA" in tipo_ope and (reg.get("entidad_nombre") and reg.get("entidad_numero_documento"))):
            return {
                "status": "incompleto",
                "mensaje": f"⚠️ *No se puede finalizar.*\n\nFaltan: **{', '.join(errores)}**.",
            }

        try:
            if "VENTA" in tipo_ope:
                return self._finalizar_venta(reg, id_cliente, id_empresa, tipo_comp, monto_total, monto_base, monto_igv, moneda_simbolo)

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

    def _finalizar_venta(
        self,
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
            return {
                "status": "incompleto",
                "mensaje": "⚠️ Falta el cliente (RUC/DNI y nombre). Indica los datos para registrarlo o búscalos en la base.",
            }

        detalle_items = self._construir_detalle(reg, monto_total, monto_base, monto_igv)

        payload_venta = {
            "codOpe": "CREAR_VENTA",
            "id_usuario": reg.get("id_usuario", 3),
            "id_cliente": id_cliente,
            "id_sucursal": reg.get("id_sucursal", 14),
            "id_moneda": reg.get("id_moneda", 1),
            "id_forma_pago": reg.get("id_forma_pago", 9),
            "tipo_venta": (reg.get("tipo_operacion") or "Contado").capitalize(),
            "fecha_emision": reg.get("fecha_emision") or "2026-03-03",
            "tipo_facturacion": "facturacion_electronica",
            "id_tipo_comprobante": tipo_comp,
            "detalle_items": detalle_items,
        }

        headers = {"Authorization": f"Bearer {settings.TOKEN_SUNAT}", "Content-Type": "application/json"}
        res_sunat = requests.post(settings.URL_VENTA_SUNAT, json=payload_venta, headers=headers)
        res_json = res_sunat.json()

        url_pdf = res_json.get("data", {}).get("url_pdf")
        if url_pdf:
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✨ *¡VENTA REGISTRADA EN SUNAT!*\n\n"
                    f"👤 *Cliente:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Total:* {moneda_simbolo} {monto_total}\n"
                    f"📄 *Documento:* {reg.get('comprobante_serie', 'F001')}-{reg.get('comprobante_numero', '000')}\n\n"
                    f"🔗 *Descargar Comprobante:* {url_pdf}"
                ),
            }

        return {
            "status": "error",
            "mensaje": f"❌ Error SUNAT: {res_json.get('message', 'No se pudo generar el PDF.')}",
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

        if not productos:
            mt = float(monto_total)
            mb = float(monto_base or mt / 1.18)
            mi = float(monto_igv or mt - mb)
            return [{
                "id_inventario": reg.get("id_inventario", 7),
                "cantidad": 1,
                "precio_unitario": mt,
                "valor_subtotal_item": round(mb, 2),
                "valor_igv": round(mi, 2),
                "valor_total_item": mt,
                "id_tipo_producto": 2,
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
                "cantidad": qty,
                "precio_unitario": pu,
                "valor_subtotal_item": round(subtotal, 2),
                "valor_igv": round(igv, 2),
                "valor_total_item": round(total_item, 2),
                "id_tipo_producto": 2,
            })
        return detalle
