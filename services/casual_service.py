"""
Servicio casual: primer mensaje sin registro.
Transforma el mensaje del usuario en un saludo corto contextual que invita a elegir entre
Registrar compra o Registrar venta (botones interactivos en WhatsApp).
Con wa_id, id_empresa e id_plataforma construye payload para ws_send_whatsapp_buttons
(mismo contrato que test/test_whatsapp_buttons.py).
"""
from __future__ import annotations

import os

import requests
from fastapi import HTTPException

from config import settings
from prompts.casual import build_prompt_casual
from services.ai_service import AIService

# Opciones: dos botones (id/título; WhatsApp limita títulos cortos)
OPCIONES_REGISTRO = [
    {"id": "compra", "title": "Registrar compra", "description": ""},
    {"id": "venta", "title": "Registrar venta", "description": ""},
]

FOOTER_BOTONES = "Selecciona una opción"


def _buttons_payload_rows() -> list[dict]:
    """Solo id y title para ws_send_whatsapp_buttons.php."""
    return [{"id": o["id"], "title": o["title"]} for o in OPCIONES_REGISTRO]


def _build_payload_whatsapp_buttons(
    id_empresa: int,
    phone: str,
    id_plataforma: int,
    body_text: str,
    footer_text: str = FOOTER_BOTONES,
) -> dict:
    """Payload para ws_send_whatsapp_buttons.php (test_whatsapp_buttons.py)."""
    return {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": body_text,
        "footer_text": footer_text,
        "buttons": _buttons_payload_rows(),
    }


def _headers_whatsapp() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = os.environ.get("MARAVIA_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _enviar_botones_whatsapp(payload_buttons: dict) -> tuple[bool, str | None, dict]:
    """
    Envía payload a ws_send_whatsapp_buttons.
    Retorna (éxito, mensaje_error, debug_whatsapp).
    """
    url = settings.URL_SEND_WHATSAPP_BUTTONS
    debug_whatsapp = {
        "url_llamada": url,
        "status_code": None,
        "response_body_preview": None,
        "donde_arreglar": "Ver url_llamada: si 404, la URL no existe o cambió en el backend. Revisar config (URL_SEND_WHATSAPP_BUTTONS) o .env.",
    }
    try:
        r = requests.post(
            url,
            json=payload_buttons,
            headers=_headers_whatsapp(),
            timeout=60,
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
                        "Pasar id_empresa (query o body) con el id de la empresa que sí tenga credenciales (ej. 1)."
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
            elif r.status_code == 400:
                debug_whatsapp["donde_arreglar"] = (
                    "400 Bad Request: el payload puede tener campos incorrectos; revisar response_body_preview."
                )
        except Exception:
            pass
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}", debug_whatsapp
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("success", True):
            err = data.get("error") or data.get("message") or "API error"
            debug_whatsapp["donde_arreglar"] = (
                f"API devolvió success=false: {err}. Revisar credenciales (id_empresa) o formato del payload."
            )
            return False, err, debug_whatsapp
        debug_whatsapp["donde_arreglar"] = None
        return True, None, debug_whatsapp
    except requests.RequestException as e:
        debug_whatsapp["donde_arreglar"] = (
            f"Error de conexión/timeout: {e}. Comprobar que la URL sea accesible desde este servidor: {url}"
        )
        return False, str(e), debug_whatsapp


class CasualService:
    def __init__(self, ai: AIService) -> None:
        self._ai = ai

    def ejecutar(
        self,
        mensaje: str,
        wa_id: str | None = None,
        id_empresa: int | None = None,
        *,
        id_plataforma: int,
    ) -> dict:
        """
        mensaje: texto del usuario para el saludo contextual.
        wa_id, id_empresa, id_plataforma: si se envían wa_id e id_empresa, se construye
        payload_whatsapp_buttons y se envía por POST a URL_SEND_WHATSAPP_BUTTONS.
        """
        prompt = build_prompt_casual(mensaje or "")
        try:
            texto = (self._ai.completar_texto(prompt) or "").strip()
            if not texto:
                texto = "Hola, para empezar con el registro primero elige entre las dos opciones:"
            whatsapp_output = {
                "texto": texto,
                "opciones_lista": OPCIONES_REGISTRO,
                "opciones_botones": _buttons_payload_rows(),
            }
            payload_whatsapp_buttons = None
            if wa_id is not None and id_empresa is not None:
                payload_whatsapp_buttons = _build_payload_whatsapp_buttons(
                    id_empresa=id_empresa,
                    phone=wa_id,
                    id_plataforma=id_plataforma,
                    body_text=texto,
                )
            out: dict = {
                "status": "ok",
                "destino": "casual",
                "whatsapp_output": whatsapp_output,
                "payload_whatsapp_buttons": payload_whatsapp_buttons,
            }
            if payload_whatsapp_buttons:
                enviado, error, debug_wa = _enviar_botones_whatsapp(payload_whatsapp_buttons)
                out["whatsapp_buttons_enviado"] = enviado
                if error:
                    out["whatsapp_buttons_error"] = error
                out["whatsapp_buttons_debug"] = debug_wa
                out["whatsapp_buttons_debug"]["id_empresa_usado_en_envio"] = payload_whatsapp_buttons["id_empresa"]
            return out
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
