from repositories.base import CacheRepository


class EliminarService:
    def __init__(self, repo: CacheRepository) -> None:
        self._repo = repo

    def ejecutar(self, wa_id: str, id_from: int) -> dict:
        resultado = self._repo.eliminar(wa_id, id_from)
        if resultado.get("success"):
            return {
                "status": "borrado",
                "mensaje_usuario": "Entendido. He cancelado la operación y limpiado el borrador. ¿Deseas iniciar un registro nuevo?",
            }
        return {"status": "error", "mensaje": "No encontré ninguna operación activa para borrar."}
