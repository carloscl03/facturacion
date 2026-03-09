from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.preguntador_service import PreguntadorService, PreguntadorV2Service

router = APIRouter()


@router.post("/generar-pregunta")
async def generar_pregunta(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return PreguntadorService(repo, ai).ejecutar(wa_id, id_empresa)


@router.post("/preguntador")
async def servicio_preguntador(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return PreguntadorV2Service(repo, ai).ejecutar(wa_id, id_empresa)
