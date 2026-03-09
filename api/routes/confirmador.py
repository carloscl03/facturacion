from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo, get_identificador_service
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.confirmador_service import ConfirmadorService
from services.identificador_service import IdentificadorService

router = APIRouter()


@router.post("/confirmador")
async def servicio_confirmador(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    identificador: IdentificadorService = Depends(get_identificador_service),
    ai: AIService = Depends(get_ai_service),
):
    return ConfirmadorService(repo, identificador, ai).ejecutar(wa_id, id_empresa)
