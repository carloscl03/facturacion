import json

from fastapi import HTTPException

from config.estados import PENDIENTE_IDENTIFICACION, VALIDOS
from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _parsear_metadata(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    s = str(raw).strip()
    if not s:
        return {}
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _obtener_estado_flujo(registro: dict | None) -> str:
    if not registro:
        return "inicial"
    metadata_ia = _parsear_metadata(registro.get("metadata_ia"))
    estado = (metadata_ia.get("estado_flujo") or "").strip()
    if estado in VALIDOS:
        return estado
    ultima = (registro.get("ultima_pregunta") or "").strip()
    if "IDENTIFICACION PENDIENTE" in ultima.upper():
        return PENDIENTE_IDENTIFICACION
    return "inicial"


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_empresa: int | None) -> dict:
        ultima_pregunta = ""
        estado_flujo = "inicial"
        cod_ope = None
        if wa_id is not None and id_empresa is not None:
            try:
                registro = self._repo.consultar(wa_id, id_empresa)
                if registro:
                    ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                    estado_flujo = _obtener_estado_flujo(registro)
                    cod_ope = (registro.get("cod_ope") or "").strip() or None
            except Exception:
                pass

        prompt = build_prompt_router(mensaje, ultima_pregunta, estado_flujo, cod_ope)

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
