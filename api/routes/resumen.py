from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from config import settings
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.resumen_service import ResumenService

router = APIRouter()


@router.get("/generar-resumen")
async def generar_resumen(
    wa_id: str,
    id_from: int,
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return ResumenService(repo, ai).ejecutar(
        wa_id, id_from,
        id_empresa=id_empresa_final, id_plataforma=id_plataforma,
    )
