from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.extraccion_service import ExtraccionService

router = APIRouter()


@router.post("/procesar-extraccion")
async def procesar_extraccion(
    wa_id: str,
    mensaje: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return ExtraccionService(repo, ai).ejecutar(wa_id, mensaje, id_empresa)
