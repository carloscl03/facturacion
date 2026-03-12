"""
POST /clasificar-mensaje: clasifica el mensaje y devuelve intención, destino y estado (leído de Redis).
Requiere wa_id e id_from para consultar Redis; el estado devuelto es siempre el leído del caché.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.clasificador_service import ClasificadorService

router = APIRouter()


class ClasificarBody(BaseModel):
    """Body: mensaje + wa_id + id_from (obligatorios para leer estado de Redis)."""
    mensaje: str
    wa_id: str
    id_from: int


@router.post("/clasificar-mensaje")
async def clasificar_mensaje(
    body: ClasificarBody = Body(...),
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Clasifica el mensaje. wa_id e id_from son obligatorios para consultar Redis;
    el campo estado de la respuesta es el leído directamente del caché (0 si no hay registro).
    """
    return ClasificadorService(repo, ai).ejecutar(body.mensaje, body.wa_id, body.id_from)
