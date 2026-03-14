"""
Ruta POST /casual: mensaje sin registro → saludo contextual que invita a elegir Compra o Venta.
Con wa_id, id_from (id_empresa) e id_plataforma devuelve payload_whatsapp_list para enviar a WhatsApp.
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
    wa_id: str | None = None,
    id_from: int | None = None,
    id_plataforma: int = 6,
    ai: AIService = Depends(get_ai_service),
):
    """
    Primer mensaje sin registro. Recibe el mensaje del usuario y devuelve un texto corto
    contextual que invita a elegir entre las dos opciones (Compra/Venta).

    Query/body: mensaje, wa_id (teléfono), id_from (id_empresa para envío WhatsApp), id_plataforma (default 6).
    Si se envían wa_id e id_from, la respuesta incluye payload_whatsapp_list listo para ws_send_whatsapp_list.php.
    """
    return CasualService(ai).ejecutar(
        mensaje,
        wa_id=wa_id,
        id_empresa=id_from,
        id_plataforma=id_plataforma,
    )
