from fastapi import APIRouter, Depends

from api.deps import get_bot_api_log_repo, get_cache_repo, get_entity_repo, get_sunat_client
from config import settings
from repositories.base import CacheRepository
from repositories.bot_api_log_repository import BotApiLogRepository
from repositories.entity_repository import EntityRepository
from services.finalizar_service import FinalizarService
from services.helpers.sunat_client import SunatClient

router = APIRouter()


@router.post("/finalizar-operacion")
async def finalizar_operacion(
    wa_id: str,
    id_from: int,
    id_empresa: int | None = None,
    id_plataforma: int | None = None,
    cache_repo: CacheRepository = Depends(get_cache_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
    sunat_client: SunatClient = Depends(get_sunat_client),
    bot_api_log: BotApiLogRepository = Depends(get_bot_api_log_repo),
):
    """
    id_from: manejo de datos (cache, registro, tablas).
    id_empresa: credenciales WhatsApp para enviar mensajes (fallback: ID_EMPRESA_WHATSAPP o id_from).
    """
    id_empresa_final = id_empresa if id_empresa is not None else (settings.ID_EMPRESA_WHATSAPP or id_from)
    return FinalizarService(
        cache_repo, entity_repo, sunat_client=sunat_client, bot_api_log=bot_api_log,
    ).ejecutar(wa_id, id_from, id_empresa_final, id_plataforma)
