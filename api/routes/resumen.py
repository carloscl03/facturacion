from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.resumen_service import ResumenService

router = APIRouter()


@router.get("/generar-resumen")
async def generar_resumen(
    wa_id: str,
    id_from: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return ResumenService(repo, ai).ejecutar(wa_id, id_from)
