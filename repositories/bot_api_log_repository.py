"""
Repositorio HTTP para registrar llamadas a las APIs de PHP/SUNAT en bot_api_log.

Llama a ws_bot_api_log.php con codOpe=CREAR_BOT_API_LOG. La escritura es
best-effort (fire-and-forget): si falla, NO rompe el flujo de finalización
del bot — solo loguea el error.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from config import settings
from config.logging_config import get_logger

_log = get_logger("maravia.bot_api_log")

_TIMEOUT_S = 10


def clasificar_tipo_falla(error_mensaje: str | None, http_status: int | None = None) -> str | None:
    """
    Clasifica el error en una de las categorías permitidas por el CHECK de
    bot_api_log.tipo_falla. Devuelve None si resultado=exitoso.

    Mapea errores conocidos de sp_registrar_venta y de la API SUNAT.
    """
    if not error_mensaje:
        if http_status and http_status >= 400:
            return "http_error"
        return None
    msg = str(error_mensaje).lower()
    if "timeout" in msg or "timed out" in msg or "connection" in msg:
        return "timeout"
    if "stock insuficiente" in msg or "stock disponible" in msg:
        return "stock_insuficiente"
    if "producto no encontrado" in msg:
        return "producto_no_encontrado"
    if "moneda" in msg and ("invalid" in msg or "no existe" in msg or "obligatorio" in msg or "inactiva" in msg):
        return "moneda_invalida"
    if "debe agregar al menos un producto" in msg or "al menos un detalle" in msg:
        return "sin_productos"
    if "credenciales" in msg or "api key" in msg or "no configurada" in msg:
        return "credenciales_invalidas"
    if "sunat" in msg and ("rechaz" in msg or "rechazo" in msg or "rechazada" in msg):
        return "sunat_rechazo"
    if "campo requerido" in msg or "json inválido" in msg or "formato" in msg:
        return "payload_invalido"
    if "error: " in msg or "sql" in msg or "sqlerrm" in msg:
        return "error_sql"
    if http_status and http_status >= 500:
        return "api_error"
    if http_status and http_status >= 400:
        return "http_error"
    return "error_desconocido"


def _safe(d: dict, *keys: str, default=None):
    """Obtiene el primer valor no-None de las keys."""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


def _construir_detalle(payload_enviado: dict | None) -> list[dict]:
    """
    Extrae los items del payload enviado (a venta o compra) y los normaliza
    al formato esperado por bot_api_log_detalle.
    """
    if not payload_enviado:
        return []
    items = payload_enviado.get("detalle_items") or payload_enviado.get("detalles") or []
    out: list[dict] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        out.append({
            "nombre": str(it.get("concepto") or it.get("nombre") or "Item"),
            "id_inventario": it.get("id_inventario"),
            "id_catalogo": it.get("id_catalogo"),
            "id_tipo_producto": it.get("id_tipo_producto"),
            "id_unidad": it.get("id_unidad"),
            "cantidad": float(it.get("cantidad") or 0),
            "precio_unitario": float(it.get("precio_unitario") or 0),
            "valor_subtotal_item": float(it.get("valor_subtotal_item") or 0),
            "valor_igv": float(it.get("valor_igv") or 0),
            "valor_total_item": float(it.get("valor_total_item") or 0),
            "indice": i,
        })
    return out


class BotApiLogRepository:
    """Cliente HTTP para ws_bot_api_log.php."""

    def __init__(self, url: str | None = None, timeout: int = _TIMEOUT_S) -> None:
        self._url = url or settings.URL_BOT_API_LOG
        self._timeout = timeout

    def crear(
        self,
        *,
        wa_id: str,
        id_from: int,
        api_destino: str,
        operacion: str,
        resultado: str,
        reg: dict | None = None,
        params: dict | None = None,
        payload_enviado: dict | None = None,
        respuesta_api: dict | None = None,
        http_status: int | None = None,
        latency_ms: int | None = None,
        tipo_falla: str | None = None,
        error_mensaje: str | None = None,
        id_venta: int | None = None,
        id_compra: int | None = None,
        serie_numero: str | None = None,
        pdf_url: str | None = None,
        sunat_estado: str | None = None,
        id_empresa: int | None = None,
        intento_numero: int = 1,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """
        Crea un log con su detalle en una sola llamada.

        Best-effort: si falla, retorna {"success": False, "error": "..."} pero
        nunca lanza excepción al caller.
        """
        reg = reg or {}
        params = params or {}

        body: dict[str, Any] = {
            "codOpe": "CREAR_BOT_API_LOG",
            "wa_id": wa_id,
            "id_from": id_from,
            "api_destino": api_destino,
            "operacion": operacion,
            "resultado": resultado,
            # Negocio (denormalizado)
            "tipo_documento": _safe(reg, "tipo_documento"),
            "id_tipo_comprobante": _safe(params, "id_tipo_comprobante"),
            "serie": _safe(reg, "serie"),
            "numero": _safe(reg, "numero"),
            "entidad_nombre": _safe(reg, "entidad_nombre"),
            "entidad_numero": _safe(reg, "entidad_numero"),
            "entidad_id": _safe(reg, "entidad_id"),
            "moneda": _safe(params, "moneda_simbolo") or _safe(reg, "moneda"),
            "id_moneda": _safe(params, "id_moneda"),
            "monto_base": _safe(params, "monto_base"),
            "monto_igv": _safe(params, "monto_igv"),
            "monto_total": _safe(params, "monto_total"),
            # Opciones (estado 4)
            "id_sucursal": _safe(reg, "id_sucursal"),
            "id_forma_pago": _safe(params, "id_forma_pago") or _safe(reg, "id_forma_pago"),
            "id_medio_pago": _safe(reg, "id_medio_pago"),
            "id_centro_costo": _safe(reg, "id_centro_costo"),
            "metodo_pago": _safe(reg, "metodo_pago"),
            "dias_credito": _safe(reg, "dias_credito"),
            "nro_cuotas": _safe(reg, "nro_cuotas") or _safe(reg, "cuotas"),
            # Resultado
            "http_status": http_status,
            "tipo_falla": tipo_falla,
            "error_mensaje": error_mensaje,
            "id_venta": id_venta,
            "id_compra": id_compra,
            "serie_numero": serie_numero,
            "pdf_url": pdf_url,
            "sunat_estado": sunat_estado,
            "latency_ms": latency_ms,
            "intento_numero": intento_numero,
            "payload_enviado": payload_enviado,
            "respuesta_api": respuesta_api,
            "metadata": metadata,
            "detalle": _construir_detalle(payload_enviado),
        }
        if id_empresa is not None:
            body["id_empresa"] = id_empresa

        # Eliminar claves con valor None para no sobrecargar el payload
        body = {k: v for k, v in body.items() if v is not None}

        t0 = time.perf_counter()
        try:
            r = requests.post(
                self._url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
            ms = round((time.perf_counter() - t0) * 1000)
            if r.status_code == 200 or r.status_code == 201:
                try:
                    data = r.json()
                except ValueError:
                    data = {"success": True}
                _log.info("bot_api_log_ok", extra={
                    "wa_id": wa_id, "id_from": id_from,
                    "api_destino": api_destino, "resultado": resultado,
                    "log_id": data.get("id"), "latency_ms": ms,
                })
                return data
            _log.error("bot_api_log_http_error", extra={
                "wa_id": wa_id, "id_from": id_from,
                "http": r.status_code, "body": r.text[:300], "latency_ms": ms,
            })
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except requests.RequestException as e:
            ms = round((time.perf_counter() - t0) * 1000)
            _log.error("bot_api_log_excepcion", extra={
                "wa_id": wa_id, "id_from": id_from,
                "error": str(e), "latency_ms": ms,
            })
            return {"success": False, "error": str(e)}
