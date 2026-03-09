from fastapi import APIRouter, Depends

from api.deps import get_cache_repo
from repositories.base import CacheRepository
from services.iniciar_service import IniciarService

router = APIRouter()


@router.post("/iniciar-flujo")
async def iniciar_flujo(
    wa_id: str,
    id_empresa: int,
    tipo: str,
    repo: CacheRepository = Depends(get_cache_repo),
):
    return IniciarService(repo).ejecutar(wa_id, id_empresa, tipo)
