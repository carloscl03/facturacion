from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.clasificador_service import ClasificadorService

router = APIRouter()


@router.post("/clasificar-mensaje")
async def clasificar_mensaje(
    mensaje: str,
    wa_id: str = None,
    id_from: int = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return ClasificadorService(repo, ai).ejecutar(mensaje, wa_id, id_from)
