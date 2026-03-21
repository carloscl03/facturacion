"""
Ruta POST /casual: mensaje sin registro → saludo contextual que invita a elegir Compra o Venta.
Con wa_id e id_empresa resuelto (query id_empresa > ID_EMPRESA_WHATSAPP > id_from) se envía la lista por WhatsApp.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_ai_service
from config import settings
from services.ai_service import AIService
from services.casual_service import CasualService

router = APIRouter()


class CasualBody(BaseModel):
    """Campos opcionales en JSON body (misma idea que /opciones). Query tiene prioridad."""

    mensaje: str | None = None
    wa_id: str | None = None
    id_from: int | None = None
    id_empresa: int | None = None
    id_plataforma: int | None = None


@router.post("/casual")
async def casual(
    mensaje: str = "",
    wa_id: str | None = None,
    id_from: int | None = None,
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    body: CasualBody | None = Body(None),
    ai: AIService = Depends(get_ai_service),
):
    """
    Primer mensaje sin registro. Recibe el mensaje del usuario y devuelve un texto corto
    contextual que invita a elegir entre las dos opciones (Compra/Venta).

    Parámetros en query **o** en JSON body: mensaje, wa_id, id_from, id_empresa, id_plataforma.
    Prioridad: query sobre body (igual que /opciones). id_plataforma por defecto 6 solo si no viene en ninguno.

    id_empresa: credenciales WhatsApp (fallback: ID_EMPRESA_WHATSAPP o id_from).

    Si se envían wa_id y un id_empresa resuelto, se POSTea a ws_send_whatsapp_list
    (whatsapp_list_enviado, whatsapp_list_debug en la respuesta).
    """
    b = body or CasualBody()
    mensaje_final = mensaje if mensaje else (b.mensaje or "")
    wa_id_final = wa_id if wa_id is not None else b.wa_id
    id_from_final = id_from if id_from is not None else b.id_from
    id_empresa_q = id_empresa if id_empresa is not None else b.id_empresa
    id_plataforma_final: int = (
        id_plataforma
        if id_plataforma is not None
        else (b.id_plataforma if b.id_plataforma is not None else 6)
    )
    id_empresa_wa_final = (
        id_empresa_q if id_empresa_q is not None else (settings.ID_EMPRESA_WHATSAPP or id_from_final)
    )
    return CasualService(ai).ejecutar(
        mensaje_final,
        wa_id=wa_id_final,
        id_empresa=id_empresa_wa_final,
        id_plataforma=id_plataforma_final,
    )
