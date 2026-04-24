"""
Confirma el registro cuando está en estado 3 o cuando los datos obligatorios están completos.
Pasa a estado 4 y el orquestador debe llamar a opciones (sucursal, forma de pago, medio de pago).
"""
from __future__ import annotations

from config.logging_config import get_logger
from repositories.base import CacheRepository
from services.whatsapp_sender import enviar_texto as _enviar_texto

_log = get_logger("maravia.confirmar_registro")


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

    def ejecutar(self, wa_id: str, id_from: int, *, id_empresa: int | None = None, id_plataforma: int | None = None) -> dict:
        registro = self._repo.consultar(wa_id, id_from) if wa_id and id_from else None
        if not registro:
            _debug_registro = {
                "confirmado": False,
                "motivo": "No hay ningún registro activo. Debe iniciar una operación (compra o venta) antes de confirmar.",
            }
            if getattr(self._repo, "guardar_debug", None):
                self._repo.guardar_debug(wa_id, id_from, "registro", _debug_registro)
            return {
                "success": False,
                "mensaje": "No hay registro activo.",
                "estado": None,
            }
        estado = int(registro.get("estado") or 0)
        datos_completos = _datos_obligatorios_completos(registro)
        if estado != 3 and not datos_completos:
            _debug_registro = {
                "confirmado": False,
                "motivo": "Aún no se puede confirmar: faltan datos obligatorios (cliente o proveedor, comprobante, moneda, monto o productos). Complete todo lo que se le indica y luego confirme.",
                "estado_actual": estado,
            }
            if getattr(self._repo, "guardar_debug", None):
                self._repo.guardar_debug(wa_id, id_from, "registro", _debug_registro)
            return {
                "success": False,
                "mensaje": "Solo se puede confirmar el registro cuando los obligatorios están completos (estado 3).",
                "estado": estado,
            }
        try:
            # Escribir registro completo con estado 4 para que Redis/API persistan correctamente.
            payload = {**registro, "estado": 4}
            self._repo.actualizar(wa_id, id_from, payload)
        except Exception as e:
            _debug_registro = {
                "confirmado": False,
                "motivo": "Error al guardar: no se pudo actualizar el registro.",
                "estado_actual": 3,
            }
            if getattr(self._repo, "guardar_debug", None):
                self._repo.guardar_debug(wa_id, id_from, "registro", _debug_registro)
            return {
                "success": False,
                "mensaje": str(e),
                "estado": 3,
            }
        _debug_registro = {
            "confirmado": True,
            "siguiente_paso": "opciones",
            "mensaje": "Registro confirmado. El siguiente paso es elegir sucursal, forma de pago y medio de pago.",
        }
        if getattr(self._repo, "guardar_debug", None):
            self._repo.guardar_debug(wa_id, id_from, "registro", _debug_registro)
        registro_confirmado = self._repo.consultar(wa_id, id_from) or {}
        _log.info("confirmar_registro_ok", extra={
            "wa_id": wa_id, "id_from": id_from,
            "entidad_nombre": registro_confirmado.get("entidad_nombre"),
            "monto_total": registro_confirmado.get("monto_total"),
            "tipo_documento": registro_confirmado.get("tipo_documento"),
            "operacion": registro_confirmado.get("operacion"),
        })
        mensaje = "Registro confirmado. Siguiente: elegir sucursal, forma de pago y medio de pago."
        if id_empresa is not None:
            _enviar_texto(id_empresa, wa_id, mensaje, id_plataforma)
        return {
            "success": True,
            "estado": 4,
            "siguiente_paso": "opciones",
            "mensaje": mensaje,
        }
