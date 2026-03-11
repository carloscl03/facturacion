"""
Estado 2: agente de opciones múltiples (sucursal, forma de pago, método de pago).
Un solo endpoint POST /opciones: obtener siguiente lista o enviar selección.

Query: wa_id, id_from (contexto/cache), id_empresa (solo para la API PHP de lista WhatsApp), phone.
La API ws_send_whatsapp_list.php exige id_empresa; el resto del flujo usa id_from.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_cache_repo, get_informacion_repo
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from services.opciones_service import OpcionesService

router = APIRouter()


class OpcionesBody(BaseModel):
    action: str = "get"
    campo: str | None = None
    valor: str | int | None = None


@router.post("/opciones")
async def opciones(
    wa_id: str,
    id_from: int,
    id_empresa: int,
    phone: str = "",
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
):
    """
    Estado 2: opciones múltiples. Solo aplica cuando el registro tiene Estado 1 completo (estado >= 3).

    Query: wa_id, id_from (contexto/cache), id_empresa (para ws_send_whatsapp_list.php), phone (opcional).
    Body (opcional): { "action": "get" } o { "action": "submit", "campo": "sucursal", "valor": 29 }.
    - action=get: devuelve la siguiente lista. payload_whatsapp_list con id_empresa para el PHP.
    - action=submit: guarda la opción. campo: sucursal|forma_pago|medio_pago; valor: id o clave.
    """
    b = body or OpcionesBody()
    action = (b.action or "get").strip().lower()
    campo = b.campo
    valor = b.valor

    service = OpcionesService(cache, informacion)
    if action == "submit":
        if campo is None or valor is None:
            return {"success": False, "mensaje": "Se requieren campo y valor para action=submit."}
        return service.submit(wa_id, id_from, campo, valor)
    return service.get_next(wa_id, id_from, phone or wa_id, id_empresa)
