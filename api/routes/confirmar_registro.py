"""
POST /confirmar-registro: en estado 3, confirma el registro y pasa a estado 4 (siguiente: opciones).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from api.deps import get_cache_repo
from repositories.base import CacheRepository
from services.confirmar_registro_service import ConfirmarRegistroService

router = APIRouter()


@router.post("/confirmar-registro")
async def confirmar_registro(
    wa_id: str,
    id_from: int | None = None,
    id_empresa: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
):
    """
    Solo aplica cuando el registro está en estado 3. Actualiza a estado 4 en Redis.
    Query params: wa_id, y id_from o id_empresa (mismo uso que en clasificar-mensaje).
    """
    id_from_final = id_from if id_from is not None else id_empresa
    if id_from_final is None:
        raise HTTPException(status_code=400, detail="Se requiere id_from o id_empresa.")
    return ConfirmarRegistroService(repo).ejecutar(wa_id, id_from_final)
