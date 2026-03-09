from fastapi import APIRouter, Depends

from api.deps import get_cache_repo
from repositories.base import CacheRepository
from services.registrador_service import RegistradorService

router = APIRouter()


@router.post("/registrador")
async def servicio_registrador(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
):
    return RegistradorService(repo).ejecutar(wa_id, id_empresa)
