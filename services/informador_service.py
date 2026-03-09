import json

from fastapi import HTTPException

from prompts.informador import build_prompt_info
from repositories.base import CacheRepository
from services.ai_service import AIService


class InformadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_empresa: int | None) -> dict:
        estado_registro = self._obtener_estado(wa_id, id_empresa)
        prompt = build_prompt_info(mensaje, estado_registro)

        try:
            texto = self._ai.completar_texto(prompt)
            return {
                "status": "ok",
                "destino": "informador",
                "whatsapp_output": {
                    "texto": texto or "Puedes indicarme, por ejemplo: cliente con RUC o DNI, productos con cantidad y precio, tipo de comprobante (Factura/Boleta) y si el pago es al contado o crédito."
                },
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def _obtener_estado(self, wa_id: str | None, id_empresa: int | None) -> str:
        if wa_id is None or id_empresa is None:
            return "(No se proporcionó wa_id/id_empresa; no hay contexto de registro.)"
        try:
            registro = self._repo.consultar(wa_id, id_empresa)
            if registro:
                return json.dumps(registro, ensure_ascii=False, indent=0)
            return "(No hay registro activo; el usuario puede estar por iniciar una operación.)"
        except Exception:
            return "(No se pudo leer el estado actual del registro.)"
