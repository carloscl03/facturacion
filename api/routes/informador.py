from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.informador_service import InformadorService

router = APIRouter()


@router.post("/informador")
async def servicio_informador(
    mensaje: str,
    wa_id: str = None,
    id_empresa: int = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    return InformadorService(repo, ai).ejecutar(mensaje, wa_id, id_empresa)
