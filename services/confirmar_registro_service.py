"""
Confirma el registro cuando está en estado 3 o cuando los datos obligatorios están completos.
Pasa a estado 4 y el orquestador debe llamar a opciones (sucursal, forma de pago, medio de pago).
"""
from __future__ import annotations

from repositories.base import CacheRepository


def _datos_obligatorios_completos(registro: dict | None) -> bool:
    """True si monto/detalle, entidad, tipo_documento y moneda están definidos (equivalente a estado 3)."""
    if not registro:
        return False
    tiene_monto = float(registro.get("monto_total") or 0) > 0
    prod = registro.get("productos")
    tiene_productos = isinstance(prod, list) and len(prod) > 0
    if isinstance(prod, str) and (prod or "").strip() and (prod or "").strip() != "[]":
        tiene_productos = True
    tiene_entidad = bool(
        registro.get("entidad_nombre") or registro.get("entidad_numero") or registro.get("entidad_id")
    )
    tiene_doc = bool(registro.get("tipo_documento"))
    tiene_moneda = bool(registro.get("moneda"))
    return (tiene_monto or tiene_productos) and tiene_entidad and tiene_doc and tiene_moneda


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
        datos_completos = _datos_obligatorios_completos(registro)
        if estado != 3 and not datos_completos:
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
