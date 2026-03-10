from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo, get_identificador_service, get_informacion_repo
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from services.ai_service import AIService
from services.extraccion_service import ExtraccionService
from services.identificador_service import IdentificadorService

router = APIRouter()


@router.post("/procesar-extraccion")
async def procesar_extraccion(
    wa_id: str,
    mensaje: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
    identificador: IdentificadorService = Depends(get_identificador_service),
    informacion_repo: InformacionRepository = Depends(get_informacion_repo),
):
    return ExtraccionService(repo, ai, identificador, informacion_repo).ejecutar(wa_id, mensaje, id_empresa)
