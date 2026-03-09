from fastapi import APIRouter, Depends

from api.deps import get_cache_repo, get_identificador_service
from repositories.base import CacheRepository
from services.identificador_service import IdentificadorService
from services.registrador_service import RegistradorService

router = APIRouter()


@router.post("/registrador")
async def servicio_registrador(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
    identificador: IdentificadorService = Depends(get_identificador_service),
):
    return RegistradorService(repo, identificador).ejecutar(wa_id, id_empresa)
