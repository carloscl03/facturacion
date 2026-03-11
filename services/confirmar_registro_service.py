"""
Confirma el registro cuando está en estado 3 (obligatorios completos, sin preguntas).
Pasa a estado 4 y el orquestador debe llamar a opciones (sucursal, forma de pago, medio de pago).
"""
from __future__ import annotations

from repositories.base import CacheRepository


class ConfirmarRegistroService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_from: int) -> dict:
        registro = self._repo.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            return {
                "success": False,
                "mensaje": "No hay registro activo.",
                "estado": None,
            }
        estado = int(registro.get("estado") or 0)
        if estado != 3:
            return {
                "success": False,
                "mensaje": "Solo se puede confirmar el registro cuando los obligatorios están completos (estado 3).",
                "estado": estado,
            }
        try:
            self._repo.actualizar(wa_id, id_from, {"estado": 4})
        except Exception as e:
            return {
                "success": False,
                "mensaje": str(e),
                "estado": 3,
            }
        return {
            "success": True,
            "estado": 4,
            "siguiente_paso": "opciones",
            "mensaje": "Registro confirmado. Siguiente: elegir sucursal, forma de pago y medio de pago.",
        }
