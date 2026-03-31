"""
Servicio casual: primer mensaje sin registro.
Transforma el mensaje del usuario en un saludo corto contextual que invita a elegir entre
Registrar compra o Registrar venta (botones interactivos en WhatsApp).
Con wa_id, id_empresa e id_plataforma construye payload para ws_send_whatsapp_buttons
(mismo contrato que test/test_whatsapp_buttons.py).
"""
from __future__ import annotations

from fastapi import HTTPException

from prompts.casual import build_prompt_casual
from services.ai_service import AIService
from services.whatsapp_sender import enviar_botones as _enviar_botones_whatsapp

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
