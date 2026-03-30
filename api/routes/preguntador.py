from fastapi import APIRouter, Body, Depends

from api.deps import get_ai_service, get_cache_repo
from config import settings
from repositories.base import CacheRepository
from services.ai_service import AIService
from services.preguntador_service import PreguntadorService, PreguntadorV2Service

router = APIRouter()


@router.post("/generar-pregunta")
async def generar_pregunta(
    wa_id: str,
    id_from: int,
    texto_desde_registrador: str | None = None,
    datos_registrados: dict | None = Body(None),
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return PreguntadorService(repo, ai).ejecutar(
        wa_id, id_from,
        texto_desde_registrador=texto_desde_registrador,
        datos_registrados=datos_registrados,
        id_empresa=id_empresa_final, id_plataforma=id_plataforma,
    )


@router.post("/preguntador")
async def servicio_preguntador(
    wa_id: str,
    id_from: int,
    texto_desde_registrador: str | None = None,
    datos_registrados: dict | None = Body(None),
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    repo: CacheRepository = Depends(get_cache_repo),
    ai: AIService = Depends(get_ai_service),
):
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return PreguntadorV2Service(repo, ai).ejecutar(
        wa_id, id_from,
        texto_desde_registrador=texto_desde_registrador,
        datos_registrados=datos_registrados,
        id_empresa=id_empresa_final, id_plataforma=id_plataforma,
    )
