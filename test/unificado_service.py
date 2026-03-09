from prompts.unificado import build_prompt_unico
from repositories.base import CacheRepository
from services.ai_service import AIService


class UnificadoService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, mensaje: str, id_empresa: int) -> dict:
        lista = self._repo.consultar_lista(wa_id, id_empresa)
        estado_actual = lista[0] if lista else {}
        es_registro_nuevo = len(lista) == 0

        contexto_operacion = estado_actual.get("cod_ope", "compras")
        ultima_pregunta_bot = estado_actual.get("ultima_pregunta", "")

        prompt = build_prompt_unico(
            contexto_operacion=contexto_operacion,
            estado_actual=estado_actual,
            ultima_pregunta_bot=ultima_pregunta_bot,
            mensaje=mensaje,
        )
        output = self._ai.completar_json(prompt)
        cambios_db = output["datos_db"]
        guiado = output["respuesta_usuario"]

        datos = {k: v for k, v in cambios_db.items() if v is not None}
        self._repo.upsert(wa_id, id_empresa, datos, es_registro_nuevo)

        return {
            "status": "sincronizado",
            "requiere_identificacion": cambios_db.get("requiere_identificacion", False),
            "datos_entidad": {
                "termino": cambios_db.get("entidad_numero_documento") or cambios_db.get("entidad_nombre") or "",
                "tipo_ope": cambios_db.get("cod_ope"),
                "tipo_doc": cambios_db.get("entidad_id_tipo_documento"),
            },
            "whatsapp_output": {
                "texto": guiado["resumen_y_guia"],
                "botones": {
                    "activar": guiado["requiere_botones"],
                    "b1": {"id": guiado.get("btn1_id"), "title": guiado.get("btn1_title")},
                    "b2": {"id": guiado.get("btn2_id"), "title": guiado.get("btn2_title")},
                },
            },
        }
