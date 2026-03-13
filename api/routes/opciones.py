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
    action: str | None = None,
    campo: str | None = None,
    valor: str | int | None = None,
    body: OpcionesBody | None = Body(None),
    cache: CacheRepository = Depends(get_cache_repo),
    informacion: InformacionRepository = Depends(get_informacion_repo),
    parametros: ParametrosRepository = Depends(get_parametros_repo),
    ai: AIService = Depends(get_ai_service),
):
    """
    Query:
      - wa_id, id_from (cache).
      - mensaje: texto libre del usuario (se usa como valor cuando no se envía en el body).
      - action, campo, valor: opcionales; si vienen en query tienen prioridad sobre el body.

    id_from se usa también como id de tablas para sucursales/métodos.

    Modo GET (action=get):
      - Devuelve texto_lista y persiste opciones_actuales en Redis.

    Modo SUBMIT (action=submit):
      - campo + valor/mensaje (valor = id o mensaje con el nombre de la opción).
      - Si no se envía valor ni en query ni en body, se usa el query param mensaje.
      - Matchea por nombre (exacto, substring, IA) y devuelve texto_lista_siguiente.
    """
    b = body or OpcionesBody()

    # Prioridad de origen:
    # 1) Query param (action/campo/valor) si vienen.
    # 2) Body OpcionesBody.
    # 3) Defaults (action="get").
    action_final = (action or b.action or "get").strip().lower()
    campo_final = campo or b.campo

    # Valor: prioridad query.valor, luego body.valor, luego mensaje (query).
    if valor is not None:
        valor_final = valor
    elif b.valor is not None:
        valor_final = b.valor
    else:
        valor_final = mensaje

    service = OpcionesService(cache, informacion, parametros, ai=ai)
    if action_final == "submit":
        if campo_final is None:
            return {"success": False, "mensaje": "Se requiere campo para action=submit."}
        if valor_final is None and campo_final:
            return {
                "success": False,
                "mensaje": "Se requiere valor (id o texto con el nombre de la opción) ya sea en el body, en el query param 'valor' o en el query param 'mensaje'.",
            }
        return service.submit(wa_id, id_from, campo_final, valor_final)
    return service.get_next(wa_id, id_from)
