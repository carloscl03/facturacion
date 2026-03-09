from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_empresa: int | None) -> dict:
        ultima_pregunta = ""
        if wa_id is not None and id_empresa is not None:
            try:
                registro = self._repo.consultar(wa_id, id_empresa)
                if registro:
                    ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
            except Exception:
                pass

        prompt = build_prompt_router(mensaje, ultima_pregunta)

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = resultado.get("intencion", "")
            resultado["necesita_extraccion"] = intencion == "actualizar"

            if not resultado.get("destino"):
                mapeo = {
                    "actualizar": "analizador",
                    "confirmacion": "registrador",
                    "resumen": "generar-resumen",
                    "finalizar": "finalizar-operacion",
                    "eliminar": "eliminar-operacion",
                    "informacion": "informador",
                    "casual": "casual",
                }
                resultado["destino"] = mapeo.get(intencion, "analizador")

            return resultado

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
