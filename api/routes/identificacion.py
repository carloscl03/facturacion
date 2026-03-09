from fastapi import APIRouter, Depends

from api.deps import get_cache_repo, get_entity_repo
from repositories.base import CacheRepository
from repositories.entity_repository import EntityRepository
from services.identificacion_service import IdentificacionService

router = APIRouter()


@router.post("/identificar-entidad")
async def identificar_entidad(
    wa_id: str,
    tipo_ope: str,
    termino: str,
    id_empresa: int,
    cache_repo: CacheRepository = Depends(get_cache_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
):
    return IdentificacionService(cache_repo, entity_repo).ejecutar(wa_id, tipo_ope, termino, id_empresa)
