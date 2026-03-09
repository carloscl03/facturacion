import json

from prompts.extraccion import build_prompt_extractor
from repositories.base import CacheRepository
from services.ai_service import AIService


class ExtraccionService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, mensaje: str, id_empresa: int) -> dict:
        registro = self._repo.consultar(wa_id, id_empresa)
        estado_actual = registro or {}
        es_registro_nuevo = registro is None

        contexto_operacion = estado_actual.get("cod_ope", "ventas")
        ultima_pregunta_bot = estado_actual.get("ultima_pregunta", "")

        prompt = build_prompt_extractor(
            contexto_operacion=contexto_operacion,
            estado_actual=estado_actual,
            ultima_pregunta_bot=ultima_pregunta_bot,
            mensaje=mensaje,
        )
        cambios_ia = self._ai.completar_json(prompt)

        nuevo_contexto = cambios_ia.get("cod_ope") or contexto_operacion
        datos = {
            k: v
            for k, v in cambios_ia.items()
            if k not in ("requiere_identificacion", "cod_ope") and v is not None
        }
        datos["cod_ope"] = nuevo_contexto

        self._repo.upsert(wa_id, id_empresa, datos, es_registro_nuevo)

        return {
            "status": "sincronizado",
            "requiere_identificacion": cambios_ia.get("requiere_identificacion", False),
            "datos_entidad": {
                "termino": cambios_ia.get("entidad_numero_documento") or cambios_ia.get("entidad_nombre") or "",
                "tipo_ope": contexto_operacion,
                "tipo_doc": cambios_ia.get("id_comprobante_tipo"),
            },
            "bitacora_ia": cambios_ia.get("ultima_pregunta"),
        }
