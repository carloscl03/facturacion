"""
Módulo centralizado para envío de mensajes WhatsApp.

Todas las funciones de envío (texto, PDF, lista, botones) están aquí
para evitar duplicación entre servicios y rutas.
"""
from __future__ import annotations

import time

import requests

from config import settings
from config.logging_config import get_logger

_log = get_logger("maravia.whatsapp")


# ------------------------------------------------------------------ #
# Texto (ws_send_whatsapp_oficial)
# ------------------------------------------------------------------ #

def enviar_texto(
    id_empresa: int,
    phone: str,
    mensaje: str,
    id_plataforma: int | None = None,
) -> tuple[bool, str | None]:
    """Envía mensaje de texto por ws_send_whatsapp_oficial. Retorna (éxito, error)."""
    url = settings.URL_SEND_WHATSAPP_OFICIAL
    payload: dict = {
        "id_empresa": id_empresa,
        "phone": phone,
        "type": "text",
        "message": mensaje,
    }
    if id_plataforma is not None:
        payload["id_plataforma"] = id_plataforma
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        ms = round((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            if id_plataforma is not None and r.status_code in (400, 404):
                payload.pop("id_plataforma", None)
                r2 = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if r2.status_code != 200:
                    _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r2.status_code, "latency_ms": ms})
                    return False, f"HTTP {r2.status_code}"
                data2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
                if not data2.get("success", True):
                    err2 = data2.get("error") or data2.get("message") or "API error"
                    _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err2, "latency_ms": ms})
                    return False, err2
                _log.info("wa_texto_ok", extra={"phone": phone, "id_empresa": id_empresa, "latency_ms": ms})
                return True, None
            _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r.status_code, "latency_ms": ms})
            return False, f"HTTP {r.status_code}"
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("success", True):
            err = data.get("error") or data.get("message") or "API error"
            if id_plataforma is not None and (
                "credenciales" in str(err).lower() or "plataforma" in str(err).lower()
            ):
                payload.pop("id_plataforma", None)
                r2 = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if r2.status_code != 200:
                    _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r2.status_code, "latency_ms": ms})
                    return False, f"HTTP {r2.status_code}"
                data2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
                if not data2.get("success", True):
                    err2 = data2.get("error") or data2.get("message") or "API error"
                    _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err2, "latency_ms": ms})
                    return False, err2
                _log.info("wa_texto_ok", extra={"phone": phone, "id_empresa": id_empresa, "latency_ms": ms})
                return True, None
            _log.error("wa_texto_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err, "latency_ms": ms})
            return False, err
        _log.info("wa_texto_ok", extra={"phone": phone, "id_empresa": id_empresa, "chars": len(mensaje), "latency_ms": ms})
        return True, None
    except requests.RequestException as e:
        ms = round((time.perf_counter() - t0) * 1000)
        _log.error("wa_texto_excepcion", extra={"phone": phone, "id_empresa": id_empresa, "error": str(e), "latency_ms": ms})
        return False, str(e)


# ------------------------------------------------------------------ #
# PDF / documento (ws_send_whatsapp_oficial)
# ------------------------------------------------------------------ #

def enviar_pdf(
    id_empresa: int,
    phone: str,
    document_url: str,
    filename: str,
    caption: str = "",
    id_plataforma: int | None = None,
) -> tuple[bool, str | None]:
    """Envía documento PDF por ws_send_whatsapp_oficial. Retorna (éxito, error)."""
    url = settings.URL_SEND_WHATSAPP_OFICIAL
    payload: dict = {
        "id_empresa": id_empresa,
        "phone": phone,
        "type": "document",
        "document_url": document_url,
        "filename": filename,
    }
    if id_plataforma is not None:
        payload["id_plataforma"] = id_plataforma
    if caption:
        payload["message"] = caption
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
        ms = round((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            if id_plataforma is not None and r.status_code in (400, 404):
                payload.pop("id_plataforma", None)
                r2 = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if r2.status_code != 200:
                    _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r2.status_code, "latency_ms": ms})
                    return False, f"HTTP {r2.status_code}"
                data2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
                if not data2.get("success", True):
                    err2 = data2.get("error") or data2.get("message") or "API error"
                    _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err2, "latency_ms": ms})
                    return False, err2
                _log.info("wa_pdf_ok", extra={"phone": phone, "id_empresa": id_empresa, "filename": filename, "latency_ms": ms})
                return True, None
            _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r.status_code, "latency_ms": ms})
            return False, f"HTTP {r.status_code}"
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("success", True):
            err = data.get("error") or data.get("message") or "API error"
            if id_plataforma is not None and (
                "credenciales" in str(err).lower() or "plataforma" in str(err).lower()
            ):
                payload.pop("id_plataforma", None)
                r2 = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if r2.status_code != 200:
                    _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "http": r2.status_code, "latency_ms": ms})
                    return False, f"HTTP {r2.status_code}"
                data2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
                if not data2.get("success", True):
                    err2 = data2.get("error") or data2.get("message") or "API error"
                    _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err2, "latency_ms": ms})
                    return False, err2
                _log.info("wa_pdf_ok", extra={"phone": phone, "id_empresa": id_empresa, "filename": filename, "latency_ms": ms})
                return True, None
            _log.error("wa_pdf_error", extra={"phone": phone, "id_empresa": id_empresa, "error": err, "latency_ms": ms})
            return False, err
        _log.info("wa_pdf_ok", extra={"phone": phone, "id_empresa": id_empresa, "filename": filename, "latency_ms": ms})
        return True, None
    except requests.RequestException as e:
        ms = round((time.perf_counter() - t0) * 1000)
        _log.error("wa_pdf_excepcion", extra={"phone": phone, "id_empresa": id_empresa, "error": str(e), "latency_ms": ms})
        return False, str(e)


# ------------------------------------------------------------------ #
# Lista interactiva (ws_send_whatsapp_list)
# ------------------------------------------------------------------ #

def enviar_lista(payload_list: dict) -> tuple[bool, str | None, dict]:
    """
    Envía payload a ws_send_whatsapp_list.
    Retorna (éxito, mensaje_error, debug_whatsapp).
    """
    url = settings.URL_SEND_WHATSAPP_LIST
    debug_whatsapp: dict = {
        "url_llamada": url,
        "status_code": None,
        "response_body_preview": None,
        "donde_arreglar": "Ver url_llamada: si 404, la URL no existe o cambió en el backend. Revisar config (URL_SEND_WHATSAPP_LIST) o .env.",
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(url, json=payload_list, headers={"Content-Type": "application/json"}, timeout=30)
        debug_whatsapp["status_code"] = r.status_code
        try:
            if r.text:
                preview = r.text[:500] if len(r.text) <= 500 else r.text[:500] + "..."
                debug_whatsapp["response_body_preview"] = preview
            body_lower = (r.text or "").lower()
            if r.status_code == 404:
                if "credenciales" in body_lower and "whatsapp" in body_lower:
                    debug_whatsapp["donde_arreglar"] = (
                        "404: No hay credenciales de WhatsApp para el id_empresa enviado. "
                        "Pasar id_empresa con el id de la empresa que sí tenga credenciales. "
                        "id_from se usa para cache y tablas; id_empresa solo para enviar la lista a WhatsApp."
                    )
                else:
                    debug_whatsapp["donde_arreglar"] = (
                        "404 Not Found: la URL del servicio de lista WhatsApp no existe. "
                        f"Comprobar URL_SEND_WHATSAPP_LIST en config/settings.py o variable de entorno. URL usada: {url}"
                    )
            elif r.status_code >= 500:
                debug_whatsapp["donde_arreglar"] = "Error del servidor (5xx): fallo en el backend de envío; revisar logs del servicio ws_send_whatsapp_list."
            elif r.status_code == 400:
                debug_whatsapp["donde_arreglar"] = "400 Bad Request: el payload puede tener campos incorrectos; revisar response_body_preview."
        except Exception:
            pass
        ms = round((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            _log.error("wa_lista_error", extra={"http": r.status_code, "latency_ms": ms})
            return False, f"HTTP {r.status_code}", debug_whatsapp
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("success", True):
            err = data.get("error") or data.get("message") or "API error"
            debug_whatsapp["donde_arreglar"] = f"API devolvió success=false: {err}. Revisar credenciales (id_empresa) o formato del payload."
            _log.error("wa_lista_error", extra={"error": err, "latency_ms": ms})
            return False, err, debug_whatsapp
        debug_whatsapp["donde_arreglar"] = None
        _log.info("wa_lista_ok", extra={"latency_ms": ms})
        return True, None, debug_whatsapp
    except requests.RequestException as e:
        ms = round((time.perf_counter() - t0) * 1000)
        debug_whatsapp["donde_arreglar"] = f"Error de conexión/timeout: {e}. Comprobar que la URL sea accesible desde este servidor: {url}"
        _log.error("wa_lista_excepcion", extra={"error": str(e), "latency_ms": ms})
        return False, str(e), debug_whatsapp


# ------------------------------------------------------------------ #
# Botones interactivos (ws_send_whatsapp_buttons)
# ------------------------------------------------------------------ #

def enviar_botones(payload_buttons: dict) -> tuple[bool, str | None, dict]:
    """
    Envía payload a ws_send_whatsapp_buttons.
    Retorna (éxito, mensaje_error, debug_whatsapp).
    """
    url = settings.URL_SEND_WHATSAPP_BUTTONS
    debug_whatsapp: dict = {
        "url_llamada": url,
        "status_code": None,
        "response_body_preview": None,
        "donde_arreglar": "Ver url_llamada: si 404, la URL no existe o cambió en el backend. Revisar config (URL_SEND_WHATSAPP_BUTTONS) o .env.",
    }
    try:
        r = requests.post(
            url, json=payload_buttons,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        debug_whatsapp["status_code"] = r.status_code
        try:
            if r.text:
                preview = r.text[:500] if len(r.text) <= 500 else r.text[:500] + "..."
                debug_whatsapp["response_body_preview"] = preview
            body_lower = (r.text or "").lower()
            if r.status_code == 404:
                if "credenciales" in body_lower and "whatsapp" in body_lower:
                    debug_whatsapp["donde_arreglar"] = (
                        "404: No hay credenciales de WhatsApp para el id_empresa enviado. "
                        "Revisar id_empresa o variable ID_EMPRESA_WHATSAPP."
                    )
                else:
                    debug_whatsapp["donde_arreglar"] = (
                        "404 Not Found: la URL del servicio de botones WhatsApp no existe. "
                        "Comprobar URL_SEND_WHATSAPP_BUTTONS en config/settings.py o variable de entorno. "
                        f"URL usada: {url}"
                    )
            elif r.status_code >= 500:
                debug_whatsapp["donde_arreglar"] = (
                    "Error del servidor (5xx): fallo en el backend de envío; revisar logs de ws_send_whatsapp_buttons."
                )
        except Exception:
            pass
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}", debug_whatsapp
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        err = None
        if not data.get("success", True):
            err = data.get("error") or data.get("message") or "API error"
            debug_whatsapp["donde_arreglar"] = f"API success=false: {err}."
            return False, err, debug_whatsapp
        debug_whatsapp["donde_arreglar"] = None
        return True, None, debug_whatsapp
    except requests.RequestException as e:
        debug_whatsapp["donde_arreglar"] = (
            f"Error de conexión/timeout: {e}. Comprobar que la URL sea accesible: {url}"
        )
        return False, str(e), debug_whatsapp
