"""
Estado 2: opciones (sucursal → centro de costo → método de pago).
Solo aplica con estado >= 4. Opciones se devuelven como texto_lista; el usuario responde con el nombre y se matchea por opciones_actuales en Redis.
Se trabaja solo con id_from tanto para Redis como para las APIs de información.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from api.deps import get_ai_service, get_cache_repo, get_informacion_repo, get_parametros_repo
from repositories.base import CacheRepository
from repositories.informacion_repository import InformacionRepository
from repositories.parametros_repository import ParametrosRepository
from services.ai_service import AIService
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
    mensaje: str | None = None,
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
    parametros: ParametrosRepository = Depends(get_parametros_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Query: wa_id, id_from (cache), mensaje (texto libre del usuario).
    id_from se usa también como id de tablas para sucursales/métodos.

    Body get: devuelve texto_lista y persiste opciones_actuales en Redis.
    Body submit: campo + valor/mensaje (valor = id o mensaje con el nombre de la opción);
    si no se envía valor en el body, se usa el query param mensaje. Matchea por nombre y
    devuelve texto_lista_siguiente.
    """
    b = body or OpcionesBody()
    action = (b.action or "get").strip().lower()
    campo = b.campo
    # Prioridad: si viene valor en el body, usarlo; si no, usar mensaje de query.
    valor = b.valor if b.valor is not None else mensaje

    service = OpcionesService(cache, informacion, parametros, ai=ai)
    if action == "submit":
        if campo is None:
            return {"success": False, "mensaje": "Se requiere campo para action=submit."}
        if valor is None and campo:
            return {
                "success": False,
                "mensaje": "Se requiere valor (id o texto con el nombre de la opción) ya sea en el body o en el query param 'mensaje'.",
            }
        return service.submit(wa_id, id_from, campo, valor)
    return service.get_next(wa_id, id_from)
