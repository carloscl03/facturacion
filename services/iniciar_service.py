from fastapi import HTTPException

import requests

from repositories.base import CacheRepository


class IniciarService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_empresa: int, tipo: str) -> dict:
        tipo_lower = tipo.lower()
        if "compr" in tipo_lower:
            operacion = "compra"
        elif "vent" in tipo_lower:
            operacion = "venta"
        else:
            raise HTTPException(status_code=400, detail="El tipo debe ser relacionado a compras o ventas")

        try:
            res = self._repo.insertar(wa_id, id_empresa, {
                "operacion": operacion,
                "estado": 0,
            })

            if isinstance(res, dict) and res.get("status_code", 200) != 200:
                return {
                    "success": False,
                    "status_code": res.get("status_code"),
                    "error": res.get("error", "Error desconocido en el backend"),
                }

            return res

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Error de conexión: {str(e)}"}
        except HTTPException:
            raise
        except Exception as e:
            return {"success": False, "error": str(e)}
