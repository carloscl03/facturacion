"""Shim DEPRECATED.

Mantiene compatibilidad importando desde `services.legacy.registrador_service`.
Usar directamente `services.legacy.registrador_service.RegistradorService` en código nuevo.
"""
from services.legacy.registrador_service import RegistradorService  # noqa: F401
