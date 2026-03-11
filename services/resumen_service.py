from prompts.resumen import build_prompt_resumen
from repositories.base import CacheRepository
from services.ai_service import AIService


class ResumenService:
    def __init__(self, repo: CacheRepository, ai: AIService) -> None:
        self._repo = repo
        self._ai = ai

    def ejecutar(self, wa_id: str, id_from: int) -> dict:
        registro = self._repo.consultar(wa_id, id_from)

        if not registro:
            return {"resumen": "No tienes ninguna operación activa en este momento."}

        prompt = build_prompt_resumen(registro)
        texto = self._ai.completar_texto(prompt)
        return {"resumen": texto}
