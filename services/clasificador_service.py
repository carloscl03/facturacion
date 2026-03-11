from fastapi import HTTPException

from prompts.clasificador import build_prompt_router
from repositories.base import CacheRepository
from services.ai_service import AIService


def _obtener_estado(registro: dict | None) -> int:
    if not registro:
        return 0
    return int(registro.get("estado") or 0)


class ClasificadorService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, mensaje: str, wa_id: str | None, id_from: int | None) -> dict:
        ultima_pregunta = ""
        estado = 0
        operacion = None
        if wa_id is not None and id_from is not None:
            try:
                registro = self._repo.consultar(wa_id, id_from)
                if not registro:
                    # Sin registro: siempre a casual (sistema de botones en otro centro; POST /casual genera el mensaje contextual).
                    return {
                        "intencion": "casual",
                        "destino": "casual",
                        "confianza": 1.0,
                        "urgencia": "baja",
                        "necesita_extraccion": False,
                        "campo_detectado": "ninguno",
                        "explicacion_soporte": "",
                    }
                else:
                    ultima_pregunta = (registro.get("ultima_pregunta") or "").strip()
                    estado = _obtener_estado(registro)
                    operacion = (registro.get("operacion") or "").strip() or None
            except Exception:
                pass

        prompt = build_prompt_router(mensaje, ultima_pregunta, estado, operacion)

        try:
            resultado = self._ai.completar_json(prompt)

            intencion = resultado.get("intencion", "")
            resultado["necesita_extraccion"] = intencion == "actualizar"

            if not resultado.get("destino"):
                mapeo = {
                    "actualizar": "extraccion",
                    "opciones": "opciones",
                    "resumen": "generar-resumen",
                    "finalizar": "finalizar-operacion",
                    "eliminar": "eliminar-operacion",
                    "informacion": "informador",
                    "casual": "casual",
                }
                resultado["destino"] = mapeo.get(intencion, "extraccion")

            if resultado.get("destino") in ("analizador", "registrador"):
                resultado["destino"] = "extraccion"

            # Opciones solo aplica con estado >= 3; si no, forzar a extraccion o casual
            if resultado.get("destino") == "opciones" and estado < 3:
                resultado["destino"] = "extraccion"
                resultado["intencion"] = intencion if intencion != "opciones" else "actualizar"

            return resultado

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
