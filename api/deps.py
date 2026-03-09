from fastapi import Depends

from config import settings
from repositories.base import CacheRepository
from repositories.cache_repository import HttpCacheRepository
from repositories.entity_repository import EntityRepository
from repositories.informacion_repository import InformacionRepository
from services.ai_service import AIService, OpenAIService
from services.identificador_service import IdentificadorService


def get_cache_repo() -> CacheRepository:
    return HttpCacheRepository(settings.URL_API)


def get_entity_repo() -> EntityRepository:
    return EntityRepository(settings.URL_CLIENTE, settings.URL_PROVEEDOR)


def get_informacion_repo() -> InformacionRepository:
    return InformacionRepository(settings.URL_INFORMACION_IA)


def get_ai_service() -> AIService:
    return OpenAIService(settings.OPENAI_API_KEY, settings.MODELO_IA)


def get_identificador_service(
    cache_repo: CacheRepository = Depends(get_cache_repo),
    entity_repo: EntityRepository = Depends(get_entity_repo),
) -> IdentificadorService:
    return IdentificadorService(cache_repo, entity_repo)
