from fastapi import APIRouter, Depends

from api.deps import get_cache_repo
from config import settings
from repositories.base import CacheRepository
from services.eliminar_service import EliminarService

router = APIRouter()


@router.post("/eliminar-operacion")
async def eliminar_operacion(
    wa_id: str,
    id_from: int,
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
):
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return EliminarService(repo).ejecutar(
        wa_id, id_from,
        id_empresa=id_empresa_final, id_plataforma=id_plataforma,
    )
