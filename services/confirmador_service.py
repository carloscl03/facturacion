"""Shim DEPRECATED.

Mantiene compatibilidad importando desde `services.legacy.confirmador_service`.
Usar directamente `services.legacy.confirmador_service.ConfirmadorService` en código nuevo.
"""
from services.legacy.confirmador_service import ConfirmadorService  # noqa: F401
