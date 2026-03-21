"""
Servicio casual: primer mensaje sin registro.
Transforma el mensaje del usuario en un saludo corto contextual que invita a elegir entre
Registrar compra o Registrar venta (selección en lista/botones).
Con wa_id, id_empresa e id_plataforma construye payload_whatsapp_list y lo envía a
ws_send_whatsapp_list (mismo flujo que /opciones).
"""
from __future__ import annotations

import requests
from fastapi import HTTPException

from config import settings
from prompts.casual import build_prompt_casual
from services.ai_service import AIService

# Opciones para la lista/botones: registrar compra y registrar venta
OPCIONES_REGISTRO = [
    {"id": "compra", "title": "Registrar compra", "description": ""},
    {"id": "venta", "title": "Registrar venta", "description": ""},
]

SECTION_TITLE = "Tipo de operación"


def _build_payload_whatsapp_list(
    id_empresa: int,
    phone: str,
    id_plataforma: int,
    body_text: str,
) -> dict:
    """Payload para ws_send_whatsapp_list.php (mismo formato que opciones/inventario)."""
    return {
        "id_empresa": id_empresa,
        "id_plataforma": id_plataforma,
        "phone": phone,
        "body_text": body_text,
        "button_text": "Ver opciones",
        "header_text": SECTION_TITLE,
        "footer_text": "Selecciona Registrar compra o Registrar venta",
        "sections": [{"title": SECTION_TITLE, "rows": OPCIONES_REGISTRO}],
    }


def _enviar_lista_whatsapp(payload_list: dict) -> tuple[bool, str | None, dict]:
    """
    Envía payload_whatsapp_list a ws_send_whatsapp_list.
    Retorna (éxito, mensaje_error, debug_whatsapp) con datos para diagnosticar fallos.
    (Misma lógica que api.routes.opciones._enviar_lista_whatsapp.)
    """
    url = settings.URL_SEND_WHATSAPP_LIST
    debug_whatsapp = {
        "url_llamada": url,
        "status_code": None,
        "response_body_preview": None,
        "donde_arreglar": "Ver url_llamada: si 404, la URL no existe o cambió en el backend. Revisar config (URL_SEND_WHATSAPP_LIST) o .env.",
    }
    try:
        r = requests.post(
            url,
            json=payload_list,
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
                        "Pasar id_empresa (query o body) con el id de la empresa que sí tenga credenciales (ej. 1). "
                        "id_from se usa para contexto; id_empresa solo para enviar la lista a WhatsApp."
                    )
                else:
                    debug_whatsapp["donde_arreglar"] = (
                        "404 Not Found: la URL del servicio de lista WhatsApp no existe. "
                        "Comprobar URL_SEND_WHATSAPP_LIST en config/settings.py o variable de entorno. "
                        f"URL usada: {url}"
                    )
            elif r.status_code >= 500:
                debug_whatsapp["donde_arreglar"] = (
                    "Error del servidor (5xx): fallo en el backend de envío; revisar logs del servicio ws_send_whatsapp_list."
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
        payload_whatsapp_list y se envía por POST a URL_SEND_WHATSAPP_LIST (como /opciones).
        id_plataforma lo resuelve la ruta (query/body; fallback 6 solo allí).
        """
        prompt = build_prompt_casual(mensaje or "")
        try:
            texto = (self._ai.completar_texto(prompt) or "").strip()
            if not texto:
                texto = "Hola, para empezar con el registro primero elige entre las dos opciones:"
            whatsapp_output = {
                "texto": texto,
                "opciones_lista": OPCIONES_REGISTRO,
            }
            payload_whatsapp_list = None
            if wa_id is not None and id_empresa is not None:
                payload_whatsapp_list = _build_payload_whatsapp_list(
                    id_empresa=id_empresa,
                    phone=wa_id,
                    id_plataforma=id_plataforma,
                    body_text=texto,
                )
            out: dict = {
                "status": "ok",
                "destino": "casual",
                "whatsapp_output": whatsapp_output,
                "payload_whatsapp_list": payload_whatsapp_list,
            }
            if payload_whatsapp_list:
                enviado, error, debug_wa = _enviar_lista_whatsapp(payload_whatsapp_list)
                out["whatsapp_list_enviado"] = enviado
                if error:
                    out["whatsapp_list_error"] = error
                out["whatsapp_list_debug"] = debug_wa
                out["whatsapp_list_debug"]["id_empresa_usado_en_envio"] = payload_whatsapp_list["id_empresa"]
            return out
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
