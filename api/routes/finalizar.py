from fastapi import APIRouter, Depends

from api.deps import get_cache_repo, get_entity_repo
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository
from services.finalizar_service import FinalizarService

router = APIRouter()


@router.post("/finalizar-operacion")
async def finalizar_operacion(
    wa_id: str,
    id_from: int,
    cache_repo: CacheRepository = Depends(get_cache_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
):
    return FinalizarService(cache_repo, entity_repo).ejecutar(wa_id, id_from)
