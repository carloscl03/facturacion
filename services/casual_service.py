"""
Servicio casual: primer mensaje sin registro.
Transforma el mensaje del usuario en un saludo corto contextual que invita a elegir entre
Registrar compra o Registrar venta (selección en lista/botones).
Con wa_id, id_empresa e id_plataforma devuelve payload_whatsapp_list listo para ws_send_whatsapp_list.
"""
from __future__ import annotations

from fastapi import HTTPException

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


class CasualService:
    def __init__(self, ai: AIService) -> None:
        self._ai = ai

    def ejecutar(
        self,
        mensaje: str,
        wa_id: str | None = None,
        id_empresa: int | None = None,
        id_plataforma: int = 6,
    ) -> dict:
        """
        mensaje: texto del usuario para el saludo contextual.
        wa_id, id_empresa, id_plataforma: si se envían, se devuelve payload_whatsapp_list
        listo para enviar a ws_send_whatsapp_list.php.
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
            return {
                "status": "ok",
                "destino": "casual",
                "whatsapp_output": whatsapp_output,
                "payload_whatsapp_list": payload_whatsapp_list,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
