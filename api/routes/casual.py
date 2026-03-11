"""
Ruta POST /casual: mensaje sin registro → saludo contextual que invita a elegir Compra o Venta.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_ai_service
from services.ai_service import AIService
from services.casual_service import CasualService

router = APIRouter()


@router.post("/casual")
async def casual(
    mensaje: str = "",
    ai: AIService = Depends(get_ai_service),
):
    """
    Primer mensaje sin registro. Recibe el mensaje del usuario y devuelve un texto corto
    contextual que invita a elegir entre las dos opciones (Compra/Venta) para el sistema de botones.
    """
    return CasualService(ai).ejecutar(mensaje)
