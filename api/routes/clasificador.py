"""
POST /clasificar-mensaje: clasifica el mensaje y devuelve intención, destino y estado (leído de Redis).
Solo datos: mensaje, wa_id, id_from (no envía mensajes; id_empresa se usa en los agentes que sí envían).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_ai_service, get_cache_repo
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.clasificador_service import ClasificadorService

router = APIRouter()


@router.post("/clasificar-mensaje")
async def clasificar_mensaje(
    mensaje: str,
    wa_id: str,
    id_from: int,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Clasifica el mensaje. Query params: mensaje, wa_id, id_from (contexto Redis; no usa id_empresa).
    """
    return ClasificadorService(repo, ai).ejecutar(mensaje, wa_id, id_from)
