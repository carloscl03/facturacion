"""
POST /clasificar-mensaje: clasifica el mensaje y devuelve intención, destino y estado (leído de Redis).
Acepta query params: mensaje, wa_id, id_from (o id_empresa como alias de id_from para Redis).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.clasificador_service import ClasificadorService

router = APIRouter()


@router.post("/clasificar-mensaje")
async def clasificar_mensaje(
    mensaje: str,
    wa_id: str,
    id_from: int | None = None,
    id_empresa: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Clasifica el mensaje. Query params: mensaje, wa_id, y id_from (o id_empresa).
    id_empresa se usa como id_from para consultar Redis cuando id_from no viene.
    """
    id_from_final = id_from if id_from is not None else id_empresa
    if id_from_final is None:
        raise HTTPException(
            status_code=400,
            detail="Se requiere id_from o id_empresa (para consultar Redis).",
        )
    return ClasificadorService(repo, ai).ejecutar(mensaje, wa_id, id_from_final)
