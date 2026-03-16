"""
Finalizar operación (venta/compra).

Orquesta validación, traducción de campos, registro/actualización de cliente
y emisión de comprobante SUNAT delegando la lógica de dominio a helpers.
"""
from __future__ import annotations

# Límite SUNAT: boleta solo para ventas en PEN con monto < este valor (soles)
MONTO_MAX_BOLETA_PEN = 700

from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository
from services.helpers.compra_mapper import construir_payload_compra
from services.helpers.sunat_client import SunatClient
from services.helpers.venta_mapper import (
    construir_payload_venta,
    construir_sintesis_actual,
    traducir_registro_a_parametros,
)


class FinalizarService:
    def __init__(
        self,
        cache_repo: CacheRepository,
        entity_repo: EntityRepository,
        sunat_client: SunatClient | None = None,
    ) -> None:
        self._cache = cache_repo
        self._entities = entity_repo
        self._sunat = sunat_client or SunatClient()

    def _debug_tipos(self, d: dict | None) -> dict:
        """Devuelve un dict clave -> tipo del valor para diagnosticar int/str en el return."""
        if not d or not isinstance(d, dict):
            return {}
        return {k: type(v).__name__ for k, v in d.items()}

    def ejecutar(self, wa_id: str, id_from: int) -> dict:
        debug: dict = {"paso": "inicio"}

        try:
            registro = self._cache.consultar(wa_id, id_from)
            debug["paso"] = "consultar_cache"
        except Exception as e:
            return {
                "status": "error",
                "mensaje": f"Hubo un fallo técnico: {str(e)}",
                "debug": {"paso_fallo": "consultar_cache", "error": str(e), "tipo_error": type(e).__name__},
            }

        if not registro:
            return {"status": "error", "mensaje": "No hay una operación activa para finalizar.", "debug": debug}

        try:
            operacion, params = traducir_registro_a_parametros(registro)
            debug["paso"] = "traducir_registro"
            debug["operacion"] = operacion
            debug["registro_tipos"] = self._debug_tipos(registro)
            debug["params_tipos"] = self._debug_tipos(params)
        except Exception as e:
            return {
                "status": "error",
                "mensaje": f"Hubo un fallo técnico: {str(e)}",
                "debug": {
                    "paso_fallo": "traducir_registro_a_parametros",
                    "error": str(e),
                    "tipo_error": type(e).__name__,
                    "registro_tipos": self._debug_tipos(registro),
                },
            }

        try:
            errores = self._validar_campos(operacion, registro, params)
            debug["paso"] = "validar_campos"
            debug["errores"] = errores
        except Exception as e:
            return {
                "status": "error",
                "mensaje": f"Hubo un fallo técnico: {str(e)}",
                "debug": {
                    "paso_fallo": "validar_campos",
                    "error": str(e),
                    "tipo_error": type(e).__name__,
                    "registro_tipos": self._debug_tipos(registro),
                    "params_tipos": self._debug_tipos(params),
                },
            }

        if errores and not (operacion == "venta" and registro.get("entidad_nombre") and params["entidad_numero"]):
            try:
                sintesis = construir_sintesis_actual(registro)
                faltan = f"⚠️ *No se puede finalizar.*\n\nFaltan: **{', '.join(errores)}**."
                mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
                return {"status": "incompleto", "mensaje": mensaje, "sintesis_actual": sintesis, "debug": {**debug, "paso": "sintesis_incompleto"}}
            except Exception as e:
                return {
                    "status": "error",
                    "mensaje": f"Hubo un fallo técnico: {str(e)}",
                    "debug": {
                        "paso_fallo": "construir_sintesis_actual",
                        "error": str(e),
                        "tipo_error": type(e).__name__,
                        "registro_tipos": self._debug_tipos(registro),
                    },
                }

        try:
            if operacion == "venta":
                return self._finalizar_venta(wa_id, registro, id_from, params)
            return self._finalizar_compra(wa_id, registro, id_from, params, debug)
        except Exception as e:
            return {
                "status": "error",
                "mensaje": f"Hubo un fallo técnico: {str(e)}",
                "debug": {
                    "paso_fallo": "finalizar_venta_o_compra",
                    "error": str(e),
                    "tipo_error": type(e).__name__,
                    "operacion": operacion,
                    "registro_tipos": self._debug_tipos(registro),
                    "params_tipos": self._debug_tipos(params),
                },
            }

    # ------------------------------------------------------------------ #
    # Validación
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validar_campos(operacion: str, reg: dict, params: dict) -> list[str]:
        errores: list[str] = []
        if params["monto_total"] <= 0:
            errores.append("Monto total")
        if not params["id_tipo_comprobante"]:
            errores.append("Tipo de documento (Factura/Boleta)")
        if not params["id_moneda"]:
            errores.append("Moneda (PEN/USD)")
        # Regla SUNAT: boleta solo para montos < 700 soles (PEN)
        if (
            operacion == "venta"
            and params.get("id_tipo_comprobante") == 2  # boleta
            and params.get("id_moneda") == 1  # PEN
            and float(params.get("monto_total") or 0) >= MONTO_MAX_BOLETA_PEN
        ):
            errores.append(
                f"Boleta no permitida para montos >= S/ {MONTO_MAX_BOLETA_PEN}. Use Factura."
            )
        if operacion == "venta" and not params["id_cliente"]:
            tiene_datos = str(reg.get("entidad_nombre") or "").strip() and params["entidad_numero"]
            if not tiene_datos:
                errores.append("Cliente (nombre y documento) para facturar")
        if operacion == "compra" and not reg.get("entidad_id"):
            errores.append("Proveedor (debe estar seleccionado para registrar la compra)")
        return errores

    # ------------------------------------------------------------------ #
    # Flujo de venta (SUNAT)
    # ------------------------------------------------------------------ #

    def _finalizar_venta(self, wa_id: str, reg: dict, id_from: int, params: dict) -> dict:
        id_cliente = params["id_cliente"]

        if not id_cliente and str(reg.get("entidad_nombre") or "").strip() and str(reg.get("entidad_numero") or "").strip():
            resp_cli = self._entities.registrar_cliente(reg, id_from)
            if resp_cli.get("success") and resp_cli.get("cliente_id"):
                id_cliente = resp_cli["cliente_id"]
            else:
                return {
                    "status": "error",
                    "mensaje": f"❌ No se pudo registrar el cliente: {resp_cli.get('message', 'Error desconocido')}.",
                }

        if id_cliente and (reg.get("entidad_nombre") or reg.get("entidad_numero")):
            self._entities.actualizar_cliente(id_cliente, reg, id_from)

        if not id_cliente:
            sintesis = construir_sintesis_actual(reg)
            faltan = "⚠️ Falta el cliente (nombre y documento). Indica los datos para registrarlo."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {"status": "incompleto", "mensaje": mensaje, "sintesis_actual": sintesis}

        payload = construir_payload_venta(
            reg, id_cliente, id_from,
            params["id_tipo_comprobante"], params["monto_total"],
            params["monto_base"], params["monto_igv"],
            params["moneda_simbolo"], params["id_moneda"],
            params["id_forma_pago"], params["tipo_venta"],
            params["fecha_emision"], params["fecha_pago"],
        )

        resultado = self._sunat.crear_venta(payload)

        if resultado.success:
            self._marcar_completado(wa_id, id_from)
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✨ *¡VENTA REGISTRADA EN SUNAT!*\n\n"
                    f"👤 *Cliente:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Total:* {params['moneda_simbolo']} {params['monto_total']}\n"
                    f"📄 *Documento:* {resultado.serie_numero}\n\n"
                    f"🔗 *Descargar Comprobante:* {resultado.url_pdf}"
                ),
            }

        sintesis = construir_sintesis_actual(reg)
        error_sunat = f"❌ Error SUNAT: {resultado.error_mensaje}"
        mensaje = f"{sintesis}\n\n{error_sunat}" if sintesis else error_sunat
        return {"status": "error", "mensaje": mensaje, "sintesis_actual": sintesis}

    # ------------------------------------------------------------------ #
    # Flujo de compra (API ws_compra.php)
    # ------------------------------------------------------------------ #

    def _finalizar_compra(self, wa_id: str, reg: dict, id_from: int, params: dict, debug: dict) -> dict:
        """Construye payload, llama a la API de compras y devuelve resultado."""
        payload = construir_payload_compra(reg, params, id_from)
        resultado = self._entities.registrar_compra(payload)

        if resultado.get("success") is True:
            self._marcar_completado(wa_id, id_from)
            id_compra = resultado.get("id_compra", "")
            return {
                "status": "finalizado",
                "mensaje": (
                    f"✅ *COMPRA REGISTRADA EXITOSAMENTE*\n\n"
                    f"🏢 *Proveedor:* {reg.get('entidad_nombre')}\n"
                    f"💰 *Monto:* {params['moneda_simbolo']} {params['monto_total']}\n"
                    f"📝 *ID compra:* {id_compra}\n"
                    f"Estado guardado en el historial de compras."
                ),
                "debug": {**debug, "paso": "compra_ok", "id_compra": id_compra},
            }

        sintesis = construir_sintesis_actual(reg)
        error_msg = resultado.get("error") or resultado.get("message", "Error al registrar compra")
        if resultado.get("details"):
            error_msg = f"{error_msg}\nDetalles: {resultado['details']}"
        mensaje = f"{sintesis}\n\n❌ {error_msg}" if sintesis else f"❌ {error_msg}"
        return {"status": "error", "mensaje": mensaje, "sintesis_actual": sintesis, "debug": {**debug, "paso": "compra_error"}}

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #

    def _marcar_completado(self, wa_id: str, id_from: int) -> None:
        try:
            self._cache.actualizar(wa_id, id_from, {"estado": 4})
        except Exception:
            pass
