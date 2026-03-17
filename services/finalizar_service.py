"""
Finalizar operación (venta/compra).

Orquesta validación, traducción de campos, registro/actualización de cliente
y emisión de comprobante SUNAT delegando la lógica de dominio a helpers.
"""
from __future__ import annotations

# Límite 700 PEN: si monto < 700 → identificación por documento (DNI/RUC) opcional (nota de venta).
# Si monto >= 700 → documento obligatorio. No es restricción estricta sobre tipo de comprobante.
MONTO_LIMITE_DOC_OPCIONAL_PEN = 700

# Usuario con el que se registran ventas y compras (temporal; informado por Maravia).
ID_USUARIO_REGISTRO = 3

# Mapeo de errores conocidos de las APIs de registro (ws_compra.php, ws_cliente) a mensajes claros.
MAPEO_ERRORES_API_COMPRA = {
    "Campo requerido: id_proveedor": "Falta indicar el proveedor.",
    "Campo requerido: fecha_emision": "Falta la fecha de emisión.",
    "Campo requerido: id_moneda": "Falta la moneda.",
    "Campo requerido: tipo_compra": "Falta el tipo de compra (Contado o Crédito).",
    "Debe incluir al menos un detalle de compra": "Debe incluir al menos un detalle (producto o concepto).",
    "Formato de nro_documento inválido": "El número de comprobante del proveedor debe ser SERIE-NÚMERO (ej: F001-00001).",
    "JSON inválido o vacío": "Datos enviados inválidos. Reintente.",
    "No se pudo conectar a la base de datos": "Servicio temporalmente no disponible. Reintente más tarde.",
}
MAPEO_ERRORES_API_CLIENTE = {
    "duplicate": "Ya existe un cliente con ese documento.",
    "ya existe": "Ya existe un cliente con ese documento.",
    "documento": "Revise el número de documento (DNI 8 dígitos, RUC 11 dígitos).",
}

from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository
from services.helpers.compra_mapper import construir_payload_compra
from services.helpers.sunat_client import SunatClient
from services.helpers.venta_mapper import (
    construir_payload_venta,
    construir_payload_venta_n8n,
    construir_sintesis_actual,
    traducir_registro_a_parametros,
)


def _mensaje_error_mapeado(mensaje: str, mapeo: dict) -> str:
    """Sustituye mensajes conocidos de la API por textos más claros para el usuario."""
    if not mensaje or not isinstance(mensaje, str):
        return mensaje or "Error desconocido"
    mensaje = mensaje.strip()
    for clave, reemplazo in mapeo.items():
        if clave.lower() in mensaje.lower():
            return reemplazo
    return mensaje


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
        # Regla 700 PEN solo afecta si exigimos documento: >= 700 → nombre + documento; < 700 → solo nombre (documento opcional).
        if operacion == "venta" and not params["id_cliente"]:
            monto_pen = float(params.get("monto_total") or 0)
            id_moneda_pen = params.get("id_moneda") == 1
            if id_moneda_pen and monto_pen >= MONTO_LIMITE_DOC_OPCIONAL_PEN:
                tiene_datos = str(reg.get("entidad_nombre") or "").strip() and params.get("entidad_numero")
                if not tiene_datos:
                    errores.append("Cliente (nombre y documento) para facturar")
            else:
                tiene_datos = str(reg.get("entidad_nombre") or "").strip()
                if not tiene_datos:
                    errores.append("Cliente (nombre) para el comprobante")
        if operacion == "compra" and not reg.get("entidad_id"):
            errores.append("Proveedor (debe estar seleccionado para registrar la compra)")
        return errores

    # ------------------------------------------------------------------ #
    # Flujo de venta (SUNAT) — ws_venta.php REGISTRAR_VENTA_N8N (sin token)
    # generacion_comprobante=1; respuesta: pdf_url, sunat_estado en raíz.
    # ------------------------------------------------------------------ #

    def _finalizar_venta(self, wa_id: str, reg: dict, id_from: int, params: dict) -> dict:
        id_cliente = params["id_cliente"]

        if not id_cliente and str(reg.get("entidad_nombre") or "").strip() and str(reg.get("entidad_numero") or "").strip():
            resp_cli = self._entities.registrar_cliente(reg, id_from)
            id_cliente = resp_cli.get("cliente_id") or (resp_cli.get("data") or {}).get("cliente_id") or resp_cli.get("id")
            if resp_cli.get("success") and id_cliente:
                id_cliente = int(id_cliente) if id_cliente else None
            else:
                id_cliente = None
            if not id_cliente:
                msg = (
                    resp_cli.get("message")
                    or resp_cli.get("mensaje")
                    or resp_cli.get("error")
                    or resp_cli.get("msg")
                    or resp_cli.get("detail")
                    or "Error desconocido"
                )
                msg = _mensaje_error_mapeado(str(msg), MAPEO_ERRORES_API_CLIENTE)
                # Si sigue siendo genérico, añadir pista con status o respuesta
                if msg == "Error desconocido" and resp_cli:
                    extra = []
                    if resp_cli.get("success") is True:
                        extra.append("API devolvió success=true pero sin cliente_id")
                    if isinstance(resp_cli.get("data"), dict):
                        extra.append(str(resp_cli.get("data"))[:150])
                    if extra:
                        msg = f"{msg} ({'; '.join(extra)})"
                return {
                    "status": "error",
                    "mensaje": f"❌ No se pudo registrar el cliente: {msg}.",
                }

        if id_cliente and (reg.get("entidad_nombre") or reg.get("entidad_numero")):
            self._entities.actualizar_cliente(id_cliente, reg, id_from)

        if not id_cliente:
            sintesis = construir_sintesis_actual(reg)
            faltan = "⚠️ Falta el cliente (nombre y documento). Indica los datos para registrarlo."
            mensaje = f"{sintesis}\n\n{faltan}" if sintesis else faltan
            return {"status": "incompleto", "mensaje": mensaje, "sintesis_actual": sintesis}

        # Usar el mismo flujo que el test: ws_venta.php REGISTRAR_VENTA_N8N (sin token),
        # generacion_comprobante=1 para devolver PDF y estado SUNAT.
        payload = construir_payload_venta_n8n(
            reg=reg,
            id_cliente=int(id_cliente),
            id_empresa=int(id_from),
            id_usuario=int(ID_USUARIO_REGISTRO),
            params=params,
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
        out = {"status": "error", "mensaje": mensaje, "sintesis_actual": sintesis}
        if getattr(resultado, "error_debug", None):
            out["debug"] = resultado.error_debug
        return out

    # ------------------------------------------------------------------ #
    # Flujo de compra — ws_compra.php REGISTRAR_COMPRA
    # Payload: codOpe, empresa_id, usuario_id, id_proveedor, fecha_emision, detalles; nro_documento SERIE-NUMERO opcional.
    # ------------------------------------------------------------------ #

    def _finalizar_compra(self, wa_id: str, reg: dict, id_from: int, params: dict, debug: dict) -> dict:
        """Construye payload REGISTRAR_COMPRA para ws_compra.php y devuelve resultado."""
        payload = construir_payload_compra(reg, params, id_from, id_usuario=ID_USUARIO_REGISTRO)
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
        error_msg = _mensaje_error_mapeado(str(error_msg), MAPEO_ERRORES_API_COMPRA)
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
