from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.unificado_service import UnificadoService

router = APIRouter()


@router.post("/unificado")
async def servicio_unificado(
    wa_id: str,
    mensaje: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return UnificadoService(repo, ai).ejecutar(wa_id, mensaje, id_empresa)
