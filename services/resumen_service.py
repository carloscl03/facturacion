from prompts.resumen import build_prompt_resumen
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.whatsapp_sender import enviar_texto as _enviar_texto


class ResumenService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, id_from: int, *, id_empresa: int | None = None, id_plataforma: int | None = None) -> dict:
        registro = self._repo.consultar(wa_id, id_from)

        if not registro:
            texto = "No tienes ninguna operación activa en este momento."
            if id_empresa is not None:
                _enviar_texto(id_empresa, wa_id, texto, id_plataforma)
            return {"resumen": texto}

        prompt = build_prompt_resumen(registro)
        texto = self._ai.completar_texto(prompt)
        if id_empresa is not None:
            _enviar_texto(id_empresa, wa_id, texto, id_plataforma)
        return {"resumen": texto}
