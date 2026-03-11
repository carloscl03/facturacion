"""
Servicio casual: primer mensaje sin registro.
Transforma el mensaje del usuario en un saludo corto contextual que invita a elegir entre Compra o Venta (botones en otro centro).
"""
from __future__ import annotations

from fastapi import HTTPException

from prompts.casual import build_prompt_casual
from services.ai_service import AIService


class CasualService:
    def __init__(self, ai: AIService) -> None:
        self._ai = ai

    def ejecutar(self, mensaje: str) -> dict:
        prompt = build_prompt_casual(mensaje or "")
        try:
            texto = (self._ai.completar_texto(prompt) or "").strip()
            if not texto:
                texto = "Hola, para empezar con el registro primero elige entre las dos opciones:"
            return {
                "status": "ok",
                "destino": "casual",
                "whatsapp_output": {"texto": texto},
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
