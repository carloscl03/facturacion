from fastapi import APIRouter, Depends

from api.deps import get_cache_repo
from repositories.base import CacheRepository
from services.eliminar_service import EliminarService

router = APIRouter()


@router.post("/eliminar-operacion")
async def eliminar_operacion(
    wa_id: str,
    id_empresa: int,
    repo: CacheRepository = Depends(get_cache_repo),
):
    return EliminarService(repo).ejecutar(wa_id, id_empresa)
