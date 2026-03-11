"""
Estado 2: agente de opciones (centro de costo, sucursal, forma de pago, medio de pago).
Alineado con test_opciones.py: id_empresa para tablas y/o id_whatsapp; id_empresa_tablas opcional.

Query: wa_id, id_from (cache), id_empresa (id_whatsapp para lista), phone, id_empresa_tablas (opcional, para jalar tablas).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_cache_repo, get_informacion_repo, get_parametros_repo
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository
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
    id_empresa_tablas: int | None = None,
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
    parametros: ParametrosRepository = Depends(get_parametros_repo),
):
    """
    Estado 2: opciones. Solo aplica con estado >= 4.

    Query: wa_id, id_from (cache), id_empresa (id_whatsapp, payload lista), phone, id_empresa_tablas (opcional; si no se pasa, se usa id_empresa para jalar sucursales/métodos).
    Body: { "action": "get" } o { "action": "submit", "campo": "centro_costo"|"sucursal"|"forma_pago"|"medio_pago", "valor": id o clave }.
    """
    b = body or OpcionesBody()
    action = (b.action or "get").strip().lower()
    campo = b.campo
    valor = b.valor

    service = OpcionesService(cache, informacion, parametros)
    if action == "submit":
        if campo is None or valor is None:
            return {"success": False, "mensaje": "Se requieren campo y valor para action=submit."}
        return service.submit(wa_id, id_from, campo, valor)
    return service.get_next(wa_id, id_from, phone or wa_id, id_empresa, id_empresa_tablas)
