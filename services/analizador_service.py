"""Shim DEPRECATED.

Mantiene compatibilidad importando desde `services.legacy.analizador_service`.
Usar directamente `services.legacy.analizador_service.AnalizadorService` en código nuevo.
"""
from services.legacy.analizador_service import AnalizadorService  # noqa: F401
