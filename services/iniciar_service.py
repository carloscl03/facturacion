from fastapi import HTTPException

import requests

from config.logging_config import get_logger
from repositories.base import CacheRepository

_log = get_logger("maravia.iniciar")


class IniciarService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_from: int, tipo: str) -> dict:
        tipo_lower = tipo.lower()
        if "compr" in tipo_lower:
            operacion = "compra"
        elif "vent" in tipo_lower:
            operacion = "venta"
        else:
            raise HTTPException(status_code=400, detail="El tipo debe ser relacionado a compras o ventas")

        _log.info("iniciar_flujo", extra={"wa_id": wa_id, "id_from": id_from, "operacion": operacion})

        try:
            res = self._repo.insertar(wa_id, id_from, {
                "operacion": operacion,
                "estado": 1,
            })

            if isinstance(res, dict) and res.get("status_code", 200) != 200:
                _log.error("iniciar_error_backend", extra={"wa_id": wa_id, "id_from": id_from, "operacion": operacion, "error": res.get("error")})
                return {
                    "success": False,
                    "status_code": res.get("status_code"),
                    "error": res.get("error", "Error desconocido en el backend"),
                }

            _log.info("iniciar_ok", extra={"wa_id": wa_id, "id_from": id_from, "operacion": operacion})
            return res

        except requests.exceptions.RequestException as e:
            _log.error("iniciar_conexion_error", extra={"wa_id": wa_id, "id_from": id_from, "error": str(e)}, exc_info=True)
            return {"success": False, "error": f"Error de conexión: {str(e)}"}
        except HTTPException:
            raise
        except Exception as e:
            _log.error("iniciar_excepcion", extra={"wa_id": wa_id, "id_from": id_from, "error": str(e)}, exc_info=True)
            return {"success": False, "error": str(e)}
