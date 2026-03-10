import json

from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _obtener_paso_actual(registro: dict | None) -> int:
    if not registro:
        return 0
    return int(registro.get("paso_actual") or 0)


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_empresa: int | None) -> dict:
        ultima_pregunta = ""
        paso_actual = 0
        cod_ope = None
        if wa_id is not None and id_empresa is not None:
            try:
                registro = self._repo.consultar(wa_id, id_empresa)
                if registro:
                    ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                    paso_actual = _obtener_paso_actual(registro)
                    cod_ope = (registro.get("cod_ope") or "").strip() or None
            except Exception:
                pass

        prompt = build_prompt_router(mensaje, ultima_pregunta, paso_actual, cod_ope)

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = resultado.get("intencion", "")
            resultado["necesita_extraccion"] = intencion == "actualizar"

            if not resultado.get("destino"):
                mapeo = {
                    "actualizar": "extraccion",
                    "resumen": "generar-resumen",
                    "finalizar": "finalizar-operacion",
                    "eliminar": "eliminar-operacion",
                    "informacion": "informador",
                    "casual": "casual",
                }
                resultado["destino"] = mapeo.get(intencion, "extraccion")

            if resultado.get("destino") in ("analizador", "registrador"):
                resultado["destino"] = "extraccion"

            return resultado

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
