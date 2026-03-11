"""
POST /confirmar-registro: en estado 3, confirma el registro y pasa a estado 4 (siguiente: opciones).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_cache_repo
from repositories.base import CacheRepository
from services.confirmar_registro_service import ConfirmarRegistroService

router = APIRouter()


@router.post("/confirmar-registro")
async def confirmar_registro(
    wa_id: str,
    id_from: int,
    repo: CacheRepository = Depends(get_cache_repo),
):
    """
    Solo aplica cuando el registro está en estado 3 (obligatorios completos, sin preguntas pendientes).
    Actualiza a estado 4; el orquestador debe llamar a POST /opciones para mostrar sucursal / forma de pago / medio de pago.
    """
    return ConfirmarRegistroService(repo).ejecutar(wa_id, id_from)
