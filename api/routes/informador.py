from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from config import settings
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.informador_service import InformadorService

router = APIRouter()


@router.post("/informador")
async def servicio_informador(
    mensaje: str,
    wa_id: str = None,
    id_from: int = None,
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return InformadorService(repo, ai).ejecutar(
        mensaje, wa_id, id_from,
        id_empresa=id_empresa_final, id_plataforma=id_plataforma,
    )
