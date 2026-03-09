from config import settings
from repositories.base import CacheRepository
from repositories.cache_repository import HttpCacheRepository
from repositories.entity_repository import EntityRepository
from services.ai_service import AIService, OpenAIService


def get_cache_repo() -> CacheRepository:
    return HttpCacheRepository(settings.URL_API)


def get_entity_repo() -> EntityRepository:
    return EntityRepository(settings.URL_CLIENTE, settings.URL_PROVEEDOR)


def get_ai_service() -> AIService:
    return OpenAIService(settings.OPENAI_API_KEY, settings.MODELO_IA)
