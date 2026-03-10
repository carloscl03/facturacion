from __future__ import annotations

from fastapi import Depends
from redis import Redis

from config import settings
from repositories.base import CacheRepository
from repositories.cache_repository import HttpCacheRepository
from repositories.entity_repository import EntityRepository
from repositories.informacion_repository import InformacionRepository
from repositories.redis_cache_repository import RedisCacheRepository
from services.ai_service import AIService, OpenAIService
from services.identificador_service import IdentificadorService

_redis_client: Redis | None = None


def _get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_client


def get_cache_repo() -> CacheRepository:
    if settings.CACHE_BACKEND == "redis":
        return RedisCacheRepository(_get_redis(), ttl=settings.REDIS_TTL)
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
